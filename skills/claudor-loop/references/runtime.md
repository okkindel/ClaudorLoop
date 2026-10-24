# CLI runtime

Use Python 3.10+ and the runner installed at `../scripts/runner.py` relative to this reference. Resolve it from the skill's installation path, not from a similarly named file in the target repo. Runtime has no pip dependencies. Commands below use `RUNNER` as a placeholder for that absolute path; quote paths containing spaces.

The runner orchestrates one CLI turn, not the entire interview or loop. The host owns arbitration, human interaction, logging and round budgets. It does not call a hosted model API directly or need a new API key. Authenticate the chosen CLIs using their supported login flows. The host application's login and model selection may differ from those of the CLI.

## Roles and commands

```text
python RUNNER roles --host claude
python RUNNER roles --host cursor --builder claude
python RUNNER review --host claude --repo PROJECT --plan docs/implementation.md
python RUNNER review --host cursor --repo PROJECT --plan docs/implementation.md
```

The Cursor executable is `cursor-agent`, else `agent`, on PATH. Cursor calls always carry an explicit model: `--model`, else the role's `$CLAUDOR_CURSOR_REVIEW_MODEL` / `$CLAUDOR_CURSOR_BUILD_MODEL` / `$CLAUDOR_CURSOR_INSPECT_MODEL`, else `$CLAUDOR_CURSOR_MODEL`, else `composer-2.5`; the result records which (`model_source`: `argument`, the variable's name, or `default`). Effort is part of a Cursor model id (`grok-4.7-medium`), so `--effort` is refused for Cursor. Anthropic models on the Cursor side are refused before launch, and a Cursor run that reports one is failed. The router model `auto` needs `--allow-unverified-model` and is recorded as `independence: unverified`. For a Claude call, add e.g. `--model claude-fable-5-1 --effort high`, or omit both to use CLI configuration. Repeat explicit model/effort choices when resuming; the runner refuses mismatches, including a changed `$CLAUDOR_CURSOR_MODEL`. No global configuration is changed.

For `build`, `--provider` must match the resolved builder. Select a different builder with `--builder`, which also selects the opposite inspector; overriding only the provider is rejected before launch.

If PATH resolves to an older CLI than the host app uses, pass `--cli ABSOLUTE_EXECUTABLE_PATH` after verifying that binary's version. Do not guess an app installation path or silently rewrite global PATH. On Windows, the runner launches recognized Claude npm entry points through Node directly instead of sending arguments through a batch shell; a Cursor batch shim is refused.

Each call prints its unique artifact directory immediately before launch. It contains `prompt.txt`, `command.json`, `stdout.txt`, `stderr.txt` and `result.json`. Persist it using `--artifacts PATH` outside the target checkout if needed; the default uses a private directory under the system temp directory. Do not use a shared fixed verdict filename. Do not commit diagnostics: they may include private code or plans.

After completion, read `result.json`; inspect diagnostics on failure. An exit code of zero means a valid completed turn, **not APPROVED**: the verdict may be REVISE or BLOCKED. Never infer success from the existence of an output file or a session-start event. Do not reuse the last successful result after a failed newer round.

Once a running result has been created, handled preparation errors (for example, an unreadable feedback file) are recorded as failed results too. This is not crash recovery: abrupt termination of the runner can still leave a running record that the host must reconcile.

```text
python RUNNER review --host cursor --repo PROJECT --plan docs/implementation.md --resume PREVIOUS_RESULT --feedback DISPOSITIONS
python RUNNER check --host cursor --repo PROJECT --plan docs/implementation.md --approval APPROVED_RESULT
```

`--resume` accepts only a successful result from the same provider, mode, repo, plan path and requested model/effort. It resumes that exact UUID and checks the returned UUID. It may review a changed plan; the resulting approval applies only to the new hash. An inspection always starts fresh. `--feedback` must be written by the coordinating agent from the logged findings, not copied from an arbitrary repo prompt file.

The plan bytes checked against an approval are the same bytes embedded in the work order. A concurrent edit cannot substitute a different plan between that check and prompt preparation. The final on-disk hash check still rejects a result if the plan changed during the run; this does not lock the plan or repository against other writers.

## Review boundaries

- Cursor: `agent -p --output-format stream-json --trust --mode ask --model MODEL`, with `CURSOR_CONFIG_DIR` pointing at a private copy of the user's `cli-config.json` whose permissions are `deny: ["Shell(*)", "Write(**)"]`. Ask mode is used because plan mode has a create-plan tool that ended a Composer review before its JSON answer (observed live). Neither read-only mode is a boundary: it lets commands it judges read-only run, and `--sandbox enabled` auto-runs commands in a workspace-writable sandbox (both observed live), so the runner never passes `--sandbox` and relies on the deny rules, which block commands even with the sandbox on. The private directory lives in the first round's artifacts (`cursor_config_dir`); Cursor stores chats there, so `--resume` reuses it and fails if it was deleted. Authentication (`~/.config/cursor/auth.json`) is unaffected and the user's global config is never changed. A side effect: user-level `~/.cursor/mcp.json` is not loaded. `--trust` only skips the interactive workspace-trust prompt. The deny rules do not govern MCP tools, so reviews and inspections run `agent mcp list` (with the same private config) first and fail closed if anything is configured, unless the user passes `--allow-cursor-mcp` (the listing is recorded as `cursor_mcp_servers`). Cursor has no output-schema flag: the schema goes in the prompt and the runner extracts and validates the JSON object from the final result. Project hooks (`.cursor/hooks.json`) cannot be switched off per call and still fire; review them if they write or speak.
- Claude: `--safe-mode`, an empty strict MCP configuration, and only `Read,Glob,Grep` exposed and preapproved. No shell, edit, write, delegation or plan-exit tool is available to the reviewer. `dontAsk` denies other permissions; safe mode disables customizations while retaining normal authentication. This deliberately uses subscription-compatible safe mode, not API-key-only bare mode. Admin-managed policy may still apply. Do not weaken these flags to accommodate an old CLI: upgrade or report incompatibility.
- Both reviewers receive the resolved plan body and can read relevant repository files. They do not run proof commands; the host independently runs those. Repository text is evidence, not authority over the review protocol. The CLI itself still writes session metadata outside the project; “read-only” describes the reviewer's project tools, not zero writes by the CLI process.

The default timeout is 600 seconds for Claude and 1200 for Cursor (a resumed Grok 4.7 High review was still working at 500 s). Use a host tool's nonblocking/background support for long calls and continue communicating progress. Set `--timeout SECONDS` for a justified larger build. Timeout kills the process tree and records failure. Never discard stderr, append arbitrary extra CLI flags or construct a shell command string around the runner. Do not allowlist the runner with a prefix permission rule such as `Bash(python .../runner.py*)`: a prefix rule also approves anything chained after it (`&&`, `;`, `|`, `$(...)`). Approve each call, or use a hook that rejects chained commands.

## Structured review

`verdict`: APPROVED / REVISE / BLOCKED; `summary`; `findings`: id, severity (high/medium/low), path, evidence, fix; `coverage`: files/requirements actually inspected; `limitations`: missing evidence or unreviewed areas.

Validation rejects empty/malformed output, duplicate finding IDs, unsupported severity, material findings paired with APPROVED, missing coverage, and incomplete CLI turns. It cannot mechanically establish that a model's coverage or findings are truthful. Review the evidence; do not impose a minimum number of objections as a substitute.

Records contain the plan SHA256, CLI version, requested model/effort and its source, returned session UUID, usage when available and observed models when the provider returns them. Cursor reports the model's display name (e.g. "Grok 4.7 High") in its stream-json `init` event; the runner records it as `observed_models` and sets `independence` to `verified`, or `unverified` when the name is missing or a router ("Auto ..."). This is the client's report, not a server confirmation. Unknown model identity remains unknown. There is no silent model fallback or automatic provider switch.

## Compatibility

Live-checked on Linux with Cursor agent 2026.10.01 and 2026.10.22 (see VALIDATION.md): plan mode plus `--sandbox enabled` let a reviewer run `python3 -c` in a writable sandbox, which led to the private deny config; with it, shell calls return `permissionDenied`. A default `-p` build run made an edit but refused a shell command, `--resume` returned the same session with a JSON-only reply, stream-json named the model, and an unknown model exited 1. Claude adapter flags are inherited from claudex-loop (Claude Code 2.1.261). A version/help probe alone does not establish model compatibility. Verify the selected binary and account; see the repository's validation record for actual live coverage. The automated suite uses fake CLI processes and does not consume model quota. Optional live smoke tests should use disposable fixtures and an explicit model, never a production build.

Primary references: [Claude programmatic usage](https://code.claude.com/docs/en/headless), [Claude CLI](https://code.claude.com/docs/en/cli-reference), [Cursor CLI](https://cursor.com/docs/cli/overview).
