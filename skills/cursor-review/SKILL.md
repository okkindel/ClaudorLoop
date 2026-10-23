---
name: cursor-review
description: "Have Cursor agent independently review an existing implementation plan while Claude coordinates a bounded revision loop. For automatic reviewer selection from either host, use claudor-loop with mode=review."
---

# Cursor Review

Compatibility entry point: explicitly use Cursor agent as the plan reviewer. The shared workflow and executable live in the sibling `claudor-loop` skill; install that skill alongside this one.

In Claude Code, load [claudor-loop](../claudor-loop/SKILL.md) and start at `mode=review`, `host=claude`, reviewer Cursor. Preserve `PLAN_FILE`, `LOG_FILE`, `MAX_ROUNDS` / `rounds`, and an explicit `reviewer_model`. Without one, the runner uses `$CLAUDOR_CURSOR_MODEL` or `composer-2.5` (fast); suggest `grok-4.7-high` for a consequential plan. The invocation authorizes reviewing, not implementation. Do not restart an interview when the supplied plan is already adequate.

In Cursor, explain that this explicit command would use the same provider for planning and review. Use the shared `claudor-loop mode=review` workflow with Claude as the independent reviewer unless the user specifically requested same-provider review. If they did, perform and label that as ordinary Cursor review; do not claim cross-provider approval or use the cross-provider approval runner to certify it.

Read the shared [runtime reference](../claudor-loop/references/runtime.md). Resolve the runner from the installed sibling skill, not the target repository. Use the actual resolved plan path on every round and build handoff. A valid completed result and APPROVED verdict are both required; failed, empty, blocked or malformed results are not approval. A result marked `independence: unverified` (Cursor `auto`) is not independent approval. The host logs findings and dispositions, and stops at the round cap.

If implementation follows, use the shared build/inspection phase. An independent plan review does not replace independent review of the final code.
