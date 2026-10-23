> Inherited from upstream [chaseai-yt/claudex-loop](https://github.com/chaseai-yt/claudex-loop). PR numbers below refer to that repository.

# Community contributions and PR reconciliation

The bidirectional workflow in [PR #16](https://github.com/chaseai-yt/claudex-loop/pull/16) was informed by concrete reports and proposed fixes from the contributors below. These contributions identified installation failures, review gaps and operational problems that the new workflow addresses.

The shared runner and rewritten skills implement these changes in a different structure. The original PR commits were not merged or cherry-picked into #16. Credit here recognizes the reports, analysis and proposed approaches; it does not imply that every feature or recommendation in each PR was adopted.

## Incorporated and overlapping work

| Contribution | Contributor | Included in #16 | Disposition after #16 merges |
|---|---|---|---|
| [#11: YAML frontmatter fix](https://github.com/chaseai-yt/claudex-loop/pull/11) | [@darian033](https://github.com/darian033) | Valid quoted descriptions for all active skills, plus automated frontmatter validation. | The reported installation defect is superseded by #16. Close the older PR with this credit after verifying the merged result. |
| [#13: review-prompt provenance and output paths](https://github.com/chaseai-yt/claudex-loop/pull/13) | [Uwe Jörk / @ujconsulting](https://github.com/ujconsulting) | The installed runner authors the review prompt, supplies it through stdin, and creates a unique private artifact directory per run. It no longer reads an arbitrary repo file named REVIEW_PROMPT or reuses fixed verdict/build output paths. | The active-skill defects are superseded by #16. Both changes leave the explicitly superseded legacy skills alone. Close the older PR with credit after the replacement lands. |
| [#15: non-Git plan reviews](https://github.com/chaseai-yt/claudex-loop/pull/15) | [@mraol08831](https://github.com/mraol08831) | `--skip-git-repo-check` on initial and resumed read-only Codex reviews; live non-Git review checks and retained failure diagnostics. | The review-path fix is superseded by #16. Delegated builds still require a clean Git baseline for diff verification. Close the older PR with credit after the replacement lands. |
| [#12: build gates and wider review scope](https://github.com/chaseai-yt/claudex-loop/pull/12) | [Bray / @Dwodgaming](https://github.com/Dwodgaming) | Worktree guidance that preserves unrelated/live work; source paths resolved against the build checkout; independent proof and review rather than relying on builder self-QA; checks that tests reflect acceptance criteria or valid regressions; review of related callers/writers beyond the plan's file list; explicit coverage and limitations. | Partially incorporated. Keep open while reconciling the remaining stronger review instructions against the rewritten skill. Do not close as fully superseded. |
| [#9: reviewer outages and trustworthy review results](https://github.com/chaseai-yt/claudex-loop/pull/9) | [Uwe Jörk / @ujconsulting](https://github.com/ujconsulting) | Retained stderr, validation of nonempty completed results, plan-hash-bound approval, and explicit failures instead of silent fallback. These address reliability concerns also raised in this PR; its adapter and quota scripts were not imported. | Partially overlapping. Keep open for a separate fallback/quota follow-up built against the shared runner. The primary feature request remains unimplemented. |

The discussion on #15 also corrected competing explanations of the Git startup guard. #16 uses the flag for non-Git read-only review without claiming that it defines the shell sandbox's writable roots or provides a security sandbox. CLI version, sandbox mode and external tool configuration remain separate concerns.

## Deliberate adaptations and remaining work

### #12 — review scope and tests

The test-review rule was adapted to allow legitimate regression coverage, including tests that do not map to a newly written spec sentence. The purpose remains to catch tests that simply endorse an incorrect or unrequested implementation.

The new reviewer is told to trace related callers and writers and report actual coverage. It does not mechanically enumerate every writer of every shared resource or compute a complete reviewed/unreviewed inventory. The PR's explicit instruction to verify guarantees asserted in code comments has not been carried over as a separate check. These remaining suggestions deserve a focused follow-up; reported coverage must not be described as an exhaustive audit.

### #9 — provider fallback and quota visibility

Third-provider adapters, local-model/OpenRouter integration, quota/reset-time discovery and configured fallback chains are not part of #16. They should be considered separately, with explicit disclosure when a fallback sees less repository context than the primary reviewer. Adding bidirectional Claude/Codex roles does not solve quota exhaustion.

The proposed rule that a first-round approval must include at least three findings was not adopted. A sound plan can have zero defects; requiring a finding count risks rewarding invented objections. The runner instead validates result structure, completion and verdict consistency, while the host evaluates the evidence. This validation still cannot prove the model's review is correct.

### #6 — translations

[@tura-ai-agent](https://github.com/tura-ai-agent) contributed [Simplified Chinese and Japanese README translations in #6](https://github.com/chaseai-yt/claudex-loop/pull/6). They have not been imported into #16. Keep the translation PR open and update it against the revised English README after that text settles, including both host routes, model/executable overrides, installation requirements and verification limits. The translations remain a separate contribution, not a superseded feature.

## Merge handling

While #16 is a draft, all six contributor PRs remain open. After #16 merges, verify the replacement behavior before closing #11, #13 and #15 as superseded, linking this acknowledgment and the merged change. Reconcile #12's remaining points separately; keep #9 and #6 available for their outstanding features. Do not mark unimplemented work complete merely because part of its rationale informed the new workflow.
