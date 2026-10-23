# Validation — Claude Code ↔ Cursor agent

Date: 2026-10-23, Linux. Live checks ran in disposable fixtures; no production repository was built or modified.

## Automated checks

- `python scripts/validate.py`: active skill frontmatter, local references, Claude and Cursor plugin manifests, shared-runner presence.
- `python -m unittest discover -s tests -v`: **44 passing tests** with fake CLI executables and real temporary Git repositories, without model calls.
- `git diff --check`.

The suite covers both host directions, Cursor plan-mode/resume argument construction (no `--sandbox`), the reviewer's private config denying shell and writes (and its reuse on resume), stream-json parsing (init + result events, failed or missing result, mismatched session), fenced or wrapped JSON replies, the Cursor model policy (default, `$CLAUDOR_CURSOR_MODEL`, explicit override, refused Anthropic models before launch and when reported, `auto` only with `--allow-unverified-model` and recorded as unverified, `--effort` refused), fail-closed handling of configured Cursor MCP servers, and the upstream contract tests: timeouts, plan-hash invalidation, staged/untracked/deleted change coverage, inspection invalidation and build resumption.

## Live checks

| Check | CLI | Result |
|---|---|---|
| `agent -p --mode plan --sandbox enabled` asked to create a file and run `touch` | 2026.10.01, composer-2.5 | Both refused; no files created |
| Runner review with `--mode plan --sandbox enabled` (first adapter version) | 2026.10.22, grok-4.7-high | **Reviewer ran `python3 -c ...` shell commands** in a `WORKSPACE_READWRITE` sandbox. Plan mode alone also rejects only commands it judges as writes. Led to the private deny config below |
| Plan mode, no sandbox flag, `python3 -c "print(6*7)"` | 2026.10.22, composer-2.5 | `rejected` |
| Private `CURSOR_CONFIG_DIR` with `deny: Shell(*), Write(**)`, with and without `--sandbox enabled` | 2026.10.22, composer-2.5 | `permissionDenied: Command blocked by permissions configuration`; global config unchanged |
| `agent -p` (no `--force`) asked to create a file and run `touch` | 2026.10.01, composer-2.5 | Edit made; shell command refused. Builders therefore never get `--force` |
| `--resume SESSION` with a JSON-only instruction | 2026.10.01, composer-2.5 | Same session UUID; bare JSON object in `result` |
| `--output-format stream-json` | 2026.10.01 | `system/init` event names the model ("Composer 2.5"); `--model auto` reports only "Auto Balance" |
| Unknown `--model` | 2026.10.01 | Exit 1 with the available-model list |
| Hardened runner, round 1: plan that deletes the only backup before copying | 2026.10.22, `grok-4.7-high` | REVISE in 316 s; delete-before-copy data loss found as high, plus missing destination directory (high) and four lesser findings. 10 read/glob/grep calls; its one shell attempt got `permissionDenied`. Observed "Grok 4.7 256K High", `independence: verified` |
| Hardened runner, round 2: `--resume` with the revised plan and dispositions | 2026.10.22, `grok-4.7-high` | Same session UUID and private config dir. REVISE in 723 s: acknowledged the fixes and found new real defects (passing the `NamedTemporaryFile` object to `os.replace`, a test patch that Linux `sendfile` bypasses, `makedirs` before the missing-source check, no directory fsync). 15 read/glob/grep calls, no shell. Fixture repo unchanged apart from the host's plan edit |
| Earlier round 2 with `--timeout 500` | 2026.10.22, `grok-4.7-high` | Timed out while still working; recorded as failed. Cursor's default timeout is now 1200 s |

## Model comparison (same fixture, same two plans)

| Model | Round 1 (seeded delete-before-copy) | Round 2 (revised plan, `--resume`) |
|---|---|---|
| `composer-2.5` | 36 s, 2.8k output tokens; REVISE, seeded defect (high) + 6 others | 63 s; REVISE: `makedirs` before the missing-source check, live-DB copy, leftover temp on `os.replace` failure; missed the `NamedTemporaryFile`-object bug and directory fsync, mentioned the `copyfileobj` patch only as low |
| `grok-4.7-medium` | 137 s, 6.5k; REVISE, seeded defect (high) + 2 others | not run |
| `grok-4.7-high` | 316 s, 15k; REVISE, seeded defect (high) + 5 others | 723 s, 31.6k; REVISE, found the `NamedTemporaryFile`-object bug (high), the Linux `sendfile` test bypass, directory fsync and three more |

Time goes into hidden reasoning, not tool calls (reads/greps return in under a second). Hence the defaults: Composer for iterative rounds and builds, Grok 4.7 High for the final code inspection.

The Cursor CLI auto-updated from 2026.10.01 to 2026.10.22 during development; each result records the `cli_version` actually used.

These checks exercise transport, permission boundaries and obvious-defect detection, not comparative model quality. An APPROVED response does not prove exhaustive correctness.

## Limits

- Project-level Cursor hooks cannot be disabled per call and still fire in reviewer and builder runs.
- One fixture and one run per model: the comparison below shows speed and recall on these plans, not a general ranking.
- Plan mode does not govern MCP tools; the runner refuses Cursor reviews while servers are configured unless explicitly allowed.
- The observed Cursor model is a display name from the client's init event, not a server confirmation.
- Windows and macOS were not live-tested with Cursor; a Cursor batch shim on Windows is refused rather than launched through a shell.
- Claude adapter behaviour is inherited from upstream claudex-loop; it was not re-validated live here.
