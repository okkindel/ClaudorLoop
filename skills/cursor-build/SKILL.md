---
name: cursor-build
description: "Have Cursor agent implement a concrete work order and have Claude independently inspect the final changes. Preserves the explicit Cursor builder choice; use claudor-loop for host-based planning and automatic reviewer selection."
---

# Cursor Build

Compatibility entry point: the builder is explicitly Cursor agent. The shared workflow and executable live in the sibling `claudor-loop` skill; install that skill alongside this one.

Load the shared [build reference](../claudor-loop/references/build.md) and [runtime reference](../claudor-loop/references/runtime.md). Preserve `SPEC_FILE` (mapped to the runner's `--plan`), `LOG_FILE`, `PROOF_CMD`, `MAX_FIX_ROUNDS`, and an explicit `builder_model` (default `$CLAUDOR_CURSOR_MODEL` or `composer-2.5`; `grok-4.7-high` for harder work). The spec may have any filename; never substitute PLAN.md silently.

- In Claude Code, Claude coordinates and delegates implementation to Cursor through the runner's `build --host claude --builder cursor` path. Claude then inspects all changes and independently runs proof checks. Log evidence and limitations. A fresh Claude CLI inspector is also available through the shared runner if useful.
- In Cursor, implement in the current host session with its normal tools, then use a fresh Claude inspector through `inspect --host cursor --builder cursor`. Do not ask Cursor to certify its own changes as independent review.

Use the current valid plan approval when this follows claudor-loop. An explicitly requested standalone work order can use `--unreviewed-spec`, with that status recorded. If the spec still needs consequential decisions, settle those before delegating; do not build by inventing missing requirements.

Preserve unrelated changes, record the baseline, independently run the proof, inspect staged and new files as well as the unstaged diff, and keep fix rounds bounded. After a Claude takeover, require fresh Cursor inspection of Claude's edits; if both contributed, log authorship and have each inspect the other's changes. Never present an earlier review as covering later fixes. Present the completed diff for any remaining sign-off required by the user's authorization.
