"""Contract tests use real subprocesses and disposable Git repositories, no model calls."""
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("runner", ROOT / "skills/claudor-loop/scripts/runner.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
SESSION = "12345678-1234-4567-8123-123456789abc"
GOOD = {"verdict": "APPROVED", "summary": "The supplied acceptance criteria are consistent.",
        "findings": [], "coverage": ["docs/custom plan.md"], "limitations": []}

FAKE_CLI = r'''
import json, os, pathlib, sys, time
if '--version' in sys.argv:
    print('fake-cli 1.0')
    sys.exit(0)
if sys.argv[1:3] == ['mcp', 'list']:
    print(os.environ.get('FAKE_MCP', 'No MCP servers configured (expected in .cursor/mcp.json)'))
    sys.exit(0)
prompt = sys.stdin.read()
case = os.environ.get('FAKE_CASE', 'ok')
if case == 'timeout':
    time.sleep(30)
if case == 'exit':
    print('Authentication failed', file=sys.stderr)
    sys.exit(7)
if case == 'empty':
    sys.exit(0)
if case == 'mutate_plan':
    pathlib.Path(os.environ['FAKE_PLAN']).write_text('Changed after launch')
if case == 'mutate_code':
    pathlib.Path('new.py').write_text('changed during inspection')
if case == 'build':
    pathlib.Path('built.py').write_text('print(42)\n')
session = '12345678-1234-4567-8123-123456789abc'
if case == 'wrong_session':
    session = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
review = {'verdict':'APPROVED', 'summary':'Inspected supplied plan.',
          'findings':[], 'coverage':['custom plan.md'], 'limitations':[]}
if case == 'revise':
    review.update(verdict='REVISE', findings=[{'id':'R1','severity':'high','path':'plan',
                  'evidence':'Deletion before successful copy loses the only copy.',
                  'fix':'Verify the new copy before removing the old one.'}])
if case == 'blocked':
    review.update(verdict='BLOCKED', coverage=[], limitations=['Required schema unavailable.'])
if case == 'malformed':
    review = {'verdict':'APPROVED'}
if case == 'arrow':
    review['summary'] = 'Sound ' + chr(0x2192) + ' ok'
if 'stream-json' in sys.argv:
    if os.environ.get('CURSOR_CONFIG_DIR'):  # Cursor keeps chats under its config dir
        pathlib.Path(os.environ['CURSOR_CONFIG_DIR'], 'chats').mkdir(exist_ok=True)
    reply = 'Built; proof passed.' if case == 'build' else json.dumps(review)
    if case == 'fenced':
        reply = 'Here is the review:\n```json\n' + json.dumps(review) + '\n```'
    print(json.dumps({'type':'system', 'subtype':'init', 'session_id':session,
                      'model':os.environ.get('FAKE_MODEL', 'Grok 4.7 High')}))
    result = {'type':'result', 'subtype':'success', 'is_error':False, 'result':reply,
              'session_id':session, 'request_id':'r1', 'usage':{'inputTokens':10}}
    if case == 'turn_failed':
        result.update(subtype='error', is_error=True)
    if case != 'incomplete':
        print(json.dumps(result))
else:
    value = {'type':'result','subtype':'success','is_error':False,'session_id':session,
             'structured_output':review, 'result':'Built; proof passed.',
             'modelUsage':{'claude-test':{'inputTokens':10}},'usage':{'input_tokens':10}}
    if case == 'turn_failed':
        value.update(subtype='error_during_execution',is_error=True)
    print(json.dumps([{'type':'system','subtype':'init'}, value] if case == 'array' else value))
'''


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="claudor-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "repo with spaces"
        self.repo.mkdir()
        self.plan = self.root / "custom plan.md"
        self.plan.write_text("# Work order\nKeep the original until the copy is verified.\n", encoding="utf-8")
        self.artifacts = self.root / "runs"
        self.cli = self.root / "fake_cli.py"
        self.cli.write_text(FAKE_CLI)
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Test")
        (self.repo / "existing.py").write_text("original\n")
        (self.repo / "delete.py").write_text("delete me\n")
        self.git("add", ".")
        self.git("commit", "-qm", "baseline")
        self.base = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, stderr=subprocess.PIPE).decode()

    def invoke(self, host="claude", mode="review", case="ok", extra=(), env=None):
        args = [mode, "--host", host, "--repo", str(self.repo), "--plan", str(self.plan),
                "--artifacts", str(self.artifacts), *extra]
        old = set(self.artifacts.glob("*/result.json")) if self.artifacts.exists() else set()
        output, error = io.StringIO(), io.StringIO()
        with patch.object(runner, "cli_prefix", return_value=[sys.executable, str(self.cli)]), \
             patch.dict(os.environ, {"FAKE_CASE": case, "FAKE_PLAN": str(self.plan), **(env or {})}), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            code = runner.main(args)
        new = set(self.artifacts.glob("*/result.json")) - old if self.artifacts.exists() else set()
        path = next(iter(new)) if new else None
        return code, json.loads(path.read_text()) if path else None, path, error.getvalue()

    def test_host_role_defaults_and_builder_override(self):
        self.assertEqual(runner.resolve_roles("claude")["reviewer"], "cursor")
        self.assertEqual(runner.resolve_roles("cursor")["reviewer"], "claude")
        roles = runner.resolve_roles("cursor", builder="claude")
        self.assertEqual((roles["planner"], roles["builder"], roles["inspector"]), ("cursor", "claude", "cursor"))
        with self.assertRaises(runner.RunError):
            runner.resolve_roles("cursor", "cursor")

    def test_both_review_adapters_complete_and_bind_custom_plan(self):
        for host in ("claude", "cursor"):
            with self.subTest(host=host):
                code, record, path, _ = self.invoke(host)
                self.assertEqual(code, 0, record)
                self.assertEqual(record["session_id"], SESSION)
                self.assertEqual(record["plan"], str(self.plan))
                self.assertEqual(record["plan_sha256"], runner.digest(self.plan.read_bytes()))
                self.assertIn(str(self.plan), (path.parent / "prompt.txt").read_text())
                self.assertEqual(record["response"]["verdict"], "APPROVED")

    def test_unpinned_and_explicit_model_selection(self):
        for provider in runner.PROVIDERS:
            args = runner.command(provider, "review", self.root)
            self.assertNotIn("--model", args)
            self.assertNotIn("-m", args)
            pinned = runner.command(provider, "review", self.root, "chosen-model")
            self.assertIn("chosen-model", pinned)

    def test_claude_exposes_only_read_tools_and_no_mcp(self):
        args = runner.command("claude", "review", self.root)
        self.assertEqual(args[args.index("--tools")+1], "Read,Glob,Grep")
        self.assertIn("--safe-mode", args)
        self.assertIn("--strict-mcp-config", args)
        self.assertEqual(args[args.index("--permission-mode")+1], "dontAsk")

    def test_cursor_resume_keeps_plan_mode_and_explicit_session(self):
        args = runner.command("cursor", "review", self.root, "grok-4.7-high", session=SESSION)
        self.assertEqual(args[args.index("--mode") + 1], "ask")
        self.assertNotIn("--sandbox", args)  # it auto-runs commands in a writable sandbox
        self.assertEqual(args[args.index("--resume") + 1], SESSION)
        self.assertNotIn("--continue", args)
        self.assertNotIn("--force", args)

    def test_failures_never_approve_and_keep_diagnostics(self):
        for host in ("claude", "cursor"):
            for case in ("exit", "empty", "malformed", "turn_failed"):
                with self.subTest(host=host, case=case):
                    code, record, path, _ = self.invoke(host, case=case)
                    self.assertEqual(code, 1)
                    self.assertEqual(record["status"], "failed")
                    self.assertTrue((path.parent / "stderr.txt").exists())
                    if case == "exit":
                        self.assertIn("Authentication failed", (path.parent / "stderr.txt").read_text())

    def test_missing_cursor_result_is_failure(self):
        code, record, _, _ = self.invoke(case="incomplete")
        self.assertEqual(code, 1)
        self.assertEqual(record["status"], "failed")

    def test_claude_array_envelope(self):
        code, record, _, _ = self.invoke("cursor", case="array")
        self.assertEqual(code, 0)
        self.assertEqual(record["observed_models"], ["claude-test"])

    def test_revise_and_blocked_are_completed_but_not_approval(self):
        for case in ("revise", "blocked"):
            code, record, _, _ = self.invoke(case=case)
            self.assertEqual(code, 0)
            with self.assertRaises(runner.RunError):
                runner.check_approval(record, self.plan, self.repo)

    def test_empty_findings_allowed_but_contradictory_approval_rejected(self):
        runner.validate_review(copy.deepcopy(GOOD))
        value = copy.deepcopy(GOOD)
        value["findings"] = [{"id":"1", "severity":"high", "path":"plan", "evidence":"data loss", "fix":"retain copy"}]
        with self.assertRaises(runner.RunError):
            runner.validate_review(value)

    def test_changed_plan_invalidates_approval(self):
        _, record, _, _ = self.invoke()
        runner.check_approval(record, self.plan, self.repo)
        self.plan.write_text("Different requirements")
        with self.assertRaises(runner.RunError):
            runner.check_approval(record, self.plan, self.repo)

    def test_changed_plan_during_review_fails(self):
        code, record, _, _ = self.invoke(case="mutate_plan")
        self.assertEqual(code, 1)
        self.assertIn("changed during", record["error"])

    def test_resume_revised_plan_same_session(self):
        _, _, previous, _ = self.invoke(case="revise")
        self.plan.write_text("New revision")
        code, record, _, _ = self.invoke(extra=("--resume", str(previous)))
        self.assertEqual(code, 0, record)
        self.assertEqual(record["session_id"], SESSION)

    def test_wrong_session_is_refused(self):
        _, _, previous, _ = self.invoke()
        code, record, _, _ = self.invoke(case="wrong_session", extra=("--resume", str(previous)))
        self.assertEqual(code, 1)
        self.assertIn("different session", record["error"])

    def test_resume_wrong_provider_or_model_rejected_before_launch(self):
        _, _, previous, _ = self.invoke()
        code, record, _, error = self.invoke("cursor", extra=("--resume", str(previous)))
        self.assertEqual(code, 1)
        self.assertIsNone(record)
        self.assertIn("provider", error)
        code, record, _, error = self.invoke(extra=("--resume", str(previous), "--model", "new-model"))
        self.assertEqual(code, 1)
        self.assertIsNone(record)
        self.assertIn("requested_model", error)

    def test_timeout_records_failure(self):
        code, record, _, _ = self.invoke(case="timeout", extra=("--timeout", "1"))
        self.assertEqual(code, 1)
        self.assertIn("timed out", record["error"])

    def test_unique_artifacts_and_failed_round_does_not_reuse_reply(self):
        _, _, first, _ = self.invoke()
        code, record, second, _ = self.invoke(case="empty")
        self.assertNotEqual(first, second)
        self.assertEqual(code, 1)
        self.assertNotIn("response", record)

    def test_snapshot_covers_staged_unstaged_deleted_and_new_files(self):
        (self.repo / "existing.py").write_text("staged version\n")
        self.git("add", "existing.py")
        (self.repo / "existing.py").write_text("unstaged final version\n")
        (self.repo / "delete.py").unlink()
        (self.repo / "new.py").write_text("brand new\n")
        snap = runner.snapshot(self.repo, self.base)
        self.assertEqual({f["path"] for f in snap["files"]}, {"existing.py", "delete.py", "new.py"})
        self.assertEqual(next(f for f in snap["files"] if f["path"] == "delete.py")["kind"], "deleted")
        self.assertEqual(next(f for f in snap["files"] if f["path"] == "existing.py")["sha256"],
                         runner.digest((self.repo / "existing.py").read_bytes()))

    def test_inspection_requires_other_provider_and_fresh_session(self):
        code, _, _, error = self.invoke(mode="inspect", extra=("--base", self.base, "--provider", "claude"))
        self.assertEqual(code, 1)
        self.assertIn("opposite the builder", error)
        _, _, previous, _ = self.invoke()
        code, _, _, error = self.invoke(mode="inspect", extra=("--base", self.base, "--resume", str(previous)))
        self.assertEqual(code, 1)
        self.assertIn("fresh session", error)

    def test_changed_code_during_inspection_fails(self):
        (self.repo / "new.py").write_text("original new file")
        code, record, _, _ = self.invoke(mode="inspect", case="mutate_code", extra=("--base", self.base))
        self.assertEqual(code, 1)
        self.assertIn("Code changed", record["error"])

    def test_build_requires_explicit_review_override_and_clean_tree(self):
        code, _, _, error = self.invoke(mode="build", extra=("--proof", "python -m unittest"))
        self.assertEqual(code, 1)
        self.assertIn("--approval", error)
        (self.repo / "user_work.py").write_text("preserve me")
        code, _, _, error = self.invoke(mode="build", extra=("--unreviewed-spec", "--proof", "test"))
        self.assertEqual(code, 1)
        self.assertIn("clean checkout", error)
        self.assertEqual((self.repo / "user_work.py").read_text(), "preserve me")

    def test_build_rejects_provider_that_contradicts_builder_before_launch(self):
        with patch.object(runner, "execute", wraps=runner.execute) as launch:
            code, record, _, error = self.invoke(
                host="cursor", mode="build", case="build",
                extra=("--builder", "cursor", "--provider", "claude",
                       "--unreviewed-spec", "--proof", "python -m unittest"))
        self.assertEqual(code, 1, record)
        launch.assert_not_called()
        self.assertIsNone(record)
        self.assertIn("builder", error.lower())
        self.assertFalse((self.repo / "built.py").exists())
        self.assertFalse(self.artifacts.exists() and any(self.artifacts.iterdir()))

    def test_build_accepts_explicit_provider_matching_builder(self):
        code, record, _, _ = self.invoke(
            host="cursor", mode="build", case="build",
            extra=("--builder", "cursor", "--provider", "cursor",
                   "--unreviewed-spec", "--proof", "python -m unittest"))
        self.assertEqual(code, 0, record)
        self.assertEqual(record["provider"], record["roles"]["builder"])
        self.assertEqual(record["roles"]["inspector"], "claude")
        self.assertTrue((self.repo / "built.py").exists())

    def test_build_dispatches_approved_snapshot_and_rejects_changed_live_plan(self):
        self.plan.write_bytes(b"# Work order\r\nKeep the original until the copy is verified.\r\n")
        approved_bytes = self.plan.read_bytes()
        approved_body = self.plan.read_text(encoding="utf-8")
        _, _, approval, _ = self.invoke(host="cursor")
        real_check = runner.check_approval
        unapproved_body = "UNAPPROVED REPLACEMENT: delete the original before verification."

        def change_after_check(*args, **kwargs):
            result = real_check(*args, **kwargs)
            self.plan.write_text(unapproved_body, encoding="utf-8")
            return result

        with patch.object(runner, "check_approval", side_effect=change_after_check):
            code, record, path, _ = self.invoke(
                host="cursor", mode="build", case="build",
                extra=("--approval", str(approval), "--proof", "python -m unittest"))
        self.assertIsNotNone(path, record)
        prompt = (path.parent / "prompt.txt").read_text(encoding="utf-8")
        prompt_bytes = (path.parent / "prompt.txt").read_bytes()
        self.assertIn(approved_bytes, prompt_bytes)
        self.assertNotIn(b"\r\r\n", prompt_bytes)
        self.assertNotIn(unapproved_body, prompt)
        self.assertIn(approved_body, prompt)
        self.assertEqual(record["plan_sha256"], runner.digest(approved_bytes))
        self.assertEqual(code, 1, record)
        self.assertEqual(record["status"], "failed")
        self.assertTrue((self.repo / "built.py").exists())

    def test_missing_feedback_finalizes_created_run_as_failed(self):
        with patch.object(runner, "execute", wraps=runner.execute) as launch:
            code, record, _, _ = self.invoke(extra=("--feedback", str(self.root / "missing.txt")))
        self.assertEqual(code, 1)
        self.assertIsNotNone(record)
        self.assertEqual(record["status"], "failed")
        self.assertTrue(record["error"])
        self.assertGreaterEqual(record["elapsed_seconds"], 0)
        launch.assert_not_called()

    def test_invalid_utf8_feedback_finalizes_created_run_as_failed(self):
        feedback = self.root / "feedback.txt"
        feedback.write_bytes(b"Invalid UTF-8: \xff")
        with patch.object(runner, "execute", wraps=runner.execute) as launch:
            code, record, _, _ = self.invoke(extra=("--feedback", str(feedback)))
        self.assertEqual(code, 1)
        self.assertIsNotNone(record)
        self.assertEqual(record["status"], "failed")
        self.assertTrue(record["error"])
        self.assertGreaterEqual(record["elapsed_seconds"], 0)
        launch.assert_not_called()

    def test_invalid_utf8_plan_finalizes_created_run_as_failed(self):
        self.plan.write_bytes(b"Invalid UTF-8: \xff")
        with patch.object(runner, "execute", wraps=runner.execute) as launch:
            code, record, _, _ = self.invoke()
        self.assertEqual(code, 1)
        self.assertIsNotNone(record)
        self.assertEqual(record["status"], "failed")
        self.assertTrue(record["error"])
        self.assertGreaterEqual(record["elapsed_seconds"], 0)
        launch.assert_not_called()

    def test_build_resume_keeps_initial_baseline_and_existing_build_changes(self):
        extra = ("--builder", "cursor", "--unreviewed-spec", "--proof", "python -m unittest")
        code, record, path, _ = self.invoke(mode="build", case="build", extra=extra)
        self.assertEqual(code, 0, record)
        self.assertEqual(record["base"], self.base)
        code, record, _, _ = self.invoke(mode="build", case="build", extra=extra+("--resume", str(path)))
        self.assertEqual(code, 0, record)
        self.assertEqual(record["base"], self.base)
        (self.repo / "user_work.py").write_text("intervening edit")
        code, _, _, error = self.invoke(mode="build", case="build", extra=extra+("--resume", str(path)))
        self.assertEqual(code, 1)
        self.assertIn("Checkout changed", error)

    def test_completed_round_exits_0_when_stdout_cannot_encode_the_record(self):
        # Issue #31: a reply character outside the console code page turned a saved,
        # completed round into exit 1. U+2192 is outside cp1252 (an em dash is not).
        out = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        with patch.object(runner, "cli_prefix", return_value=[sys.executable, str(self.cli)]), \
             patch.dict(os.environ, {"FAKE_CASE": "arrow"}), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = runner.main(["review", "--host", "cursor", "--repo", str(self.repo), "--plan",
                                str(self.plan), "--artifacts", str(self.artifacts)])
        record = json.loads(next(self.artifacts.glob("*/result.json")).read_text(encoding="utf-8"))
        self.assertEqual((code, record["status"]), (0, "completed"))

    def test_builders_load_no_user_hooks_or_mcp_tools(self):
        claude = runner.command("claude", "build", self.root)
        self.assertEqual(json.loads(claude[claude.index("--settings") + 1]), {"disableAllHooks": True})
        self.assertEqual(claude[claude.index("--mcp-config") + 1], '{"mcpServers":{}}')
        self.assertIn("--strict-mcp-config", claude)
        cursor = runner.command("cursor", "build", self.root, "grok-4.7-high")
        self.assertNotIn("--force", cursor)
        self.assertNotIn("--approve-mcps", cursor)
        self.assertNotIn("--mode", cursor)

    def test_staged_rename_lists_old_path_as_deleted(self):
        self.git("mv", "delete.py", "moved.py")
        files = {f["path"]: f["kind"] for f in runner.snapshot(self.repo, self.base)["files"]}
        self.assertEqual((files.get("delete.py"), files.get("moved.py")), ("deleted", "file"))

    def test_git_subdirectory_is_refused_as_repo(self):
        # Manifest paths are repository-root relative; a subfolder would misread them.
        (self.repo / "sub").mkdir()
        code, _, _, error = self.invoke(mode="inspect", extra=("--base", self.base, "--repo", str(self.repo / "sub")))
        self.assertEqual(code, 1)
        self.assertIn("repository root", error)

    def test_cursor_review_refuses_configured_mcp_unless_allowed(self):
        # The deny config blocks shell and writes, not MCP tools.
        env = {"FAKE_MCP": "github: npx github-mcp (enabled)"}
        code, record, _, _ = self.invoke(env=env)
        self.assertEqual((code, record["status"]), (1, "failed"))
        self.assertIn("MCP", record["error"])
        self.assertFalse((Path(record["artifacts"]) / "command.json").exists())
        code, record, _, _ = self.invoke(env=env, extra=("--allow-cursor-mcp",))
        self.assertEqual(code, 0, record)
        self.assertIn("github", record["cursor_mcp_servers"])

    def test_cursor_reviewer_gets_private_config_denying_shell_and_writes(self):
        user = self.root / "cursor-home"
        user.mkdir()
        (user / "cli-config.json").write_text(json.dumps(
            {"version": 1, "permissions": {"allow": ["Shell(rm)"], "deny": []}, "editor": {"vimMode": True}}))
        code, record, _, _ = self.invoke(env={"CURSOR_CONFIG_DIR": str(user)})
        self.assertEqual(code, 0, record)
        private = Path(record["cursor_config_dir"])
        self.assertTrue(private.is_relative_to(Path(record["artifacts"])))
        config = json.loads((private / "cli-config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["permissions"], {"allow": [], "deny": ["Shell(*)", "Write(**)"]})
        self.assertEqual(config["editor"], {"vimMode": True})
        self.assertEqual(json.loads((user / "cli-config.json").read_text())["permissions"]["allow"], ["Shell(rm)"])
        argv = json.loads((Path(record["artifacts"]) / "command.json").read_text(encoding="utf-8"))
        self.assertNotIn("--sandbox", argv)

    def test_cursor_resume_reuses_review_config_and_fails_without_it(self):
        _, first, previous, _ = self.invoke(case="revise")
        code, record, _, _ = self.invoke(extra=("--resume", str(previous)))
        self.assertEqual(code, 0, record)
        self.assertEqual(record["cursor_config_dir"], first["cursor_config_dir"])
        shutil.rmtree(first["cursor_config_dir"])
        code, record, _, _ = self.invoke(extra=("--resume", str(previous)))
        self.assertEqual(code, 1)
        self.assertIn("start fresh", record["error"])

    def test_cursor_builder_keeps_user_config(self):
        code, record, _, _ = self.invoke(host="cursor", mode="build", case="build",
                                         extra=("--unreviewed-spec", "--proof", "python -m unittest"))
        self.assertEqual(code, 0, record)
        self.assertNotIn("cursor_config_dir", record)

    def test_cursor_default_model_and_env_override(self):
        code, record, _, _ = self.invoke()
        self.assertEqual(code, 0, record)
        self.assertEqual((record["requested_model"], record["model_source"]), ("composer-2.5", "default"))
        argv = json.loads((Path(record["artifacts"]) / "command.json").read_text(encoding="utf-8"))
        self.assertEqual(argv[argv.index("--model") + 1], "composer-2.5")
        self.assertEqual((record["observed_models"], record["independence"]), (["Grok 4.7 High"], "verified"))
        code, record, _, _ = self.invoke(env={"CLAUDOR_CURSOR_MODEL": "grok-4.7-medium"})
        self.assertEqual((record["requested_model"], record["model_source"]), ("grok-4.7-medium", "env"))
        code, record, _, _ = self.invoke(extra=("--model", "cursor-grok-4.6-high"),
                                         env={"CLAUDOR_CURSOR_MODEL": "composer-2.5"})
        self.assertEqual((record["requested_model"], record["model_source"]), ("cursor-grok-4.6-high", "argument"))

    def test_cursor_inspection_defaults_to_grok_high(self):
        (self.repo / "new.py").write_text("new\n")
        code, record, _, _ = self.invoke(mode="inspect", extra=("--base", self.base))
        self.assertEqual(code, 0, record)
        self.assertEqual((record["requested_model"], record["model_source"]), ("grok-4.7-high", "default"))

    def test_cursor_rejects_anthropic_models_before_launch(self):
        for model in ("claude-opus-5-5-high", "claude-fable-5-1-high", "claude-4.5-sonnet"):
            with self.subTest(model=model), patch.object(runner, "execute") as launch:
                code, record, _, error = self.invoke(extra=("--model", model))
                self.assertEqual(code, 1)
                self.assertIsNone(record)
                self.assertIn("Anthropic", error)
                launch.assert_not_called()

    def test_cursor_router_model_needs_explicit_opt_in_and_is_unverified(self):
        code, record, _, error = self.invoke(extra=("--model", "auto"))
        self.assertEqual(code, 1)
        self.assertIn("--allow-unverified-model", error)
        code, record, _, _ = self.invoke(extra=("--model", "auto", "--allow-unverified-model"),
                                         env={"FAKE_MODEL": "Auto Balance"})
        self.assertEqual(code, 0, record)
        self.assertEqual(record["independence"], "unverified")

    def test_cursor_reporting_an_anthropic_model_fails(self):
        code, record, _, _ = self.invoke(env={"FAKE_MODEL": "Claude Opus 5.5"})
        self.assertEqual((code, record["status"]), (1, "failed"))
        self.assertIn("not independent", record["error"])

    def test_cursor_rejects_effort_flag(self):
        code, _, _, error = self.invoke(extra=("--effort", "high"))
        self.assertEqual(code, 1)
        self.assertIn("--model", error)

    def test_cursor_fenced_json_review_is_accepted(self):
        code, record, path, _ = self.invoke(case="fenced")
        self.assertEqual(code, 0, record)
        self.assertEqual(record["response"]["verdict"], "APPROVED")
        self.assertIn("JSON Schema", (path.parent / "prompt.txt").read_text(encoding="utf-8"))

    def test_artifacts_cannot_contaminate_target_checkout(self):
        code, _, _, error = self.invoke(extra=("--artifacts", str(self.repo / "runs")))
        self.assertEqual(code, 1)
        self.assertIn("outside", error)


if __name__ == "__main__":
    unittest.main()
