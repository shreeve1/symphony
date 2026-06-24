# 2026-06-24 ADR-0024 babysitting roadblocks

Curated session evidence from observing Podium issues #128-#132 after slicing ADR-0024 into auto-land issues.

## Evidence summary

- Issues #128 and #129 blocked with Codex `server_is_overloaded` / `service_unavailable_error` during implementation or review. #128 was recovered by requeueing to `todo`; #129 had succeeded implementation but failed review, so the failed `### Symphony Review (1)` marker block was stripped and the issue returned to `in_review` for a fresh review dispatch.
- Issue #130 implemented and reviewed successfully, then blocked during auto-land. The branch had been rebased and became FF-able, but the issue stayed blocked until `land_worktree` was manually invoked and the Podium row was flipped to `done`.
- Issue #131 repeated both classes: review first failed with the same Codex overload and was recovered by review-marker reset; after review passed, auto-land blocked when `main` advanced. Rebase hit a wiki claim-ID collision: `main` already had C-0327 for a frontend flyout overflow fix, while #131 used C-0327 for the empty-diff guard. The #131 claim was renumbered to C-0328 during rebase, then landed manually.
- Issue #132 implemented and reviewed successfully after #131 was landed. It added C-0329/C-0330 and superseded C-0328's dirty-empty-diff subcase.
- Restarting `symphony-host` onto `0ca14fe` exposed startup probe fragility: `verify_pi_support` timed out twice on `pi --print ... ping`, systemd restarted the service, then a later pi probe passed and the scheduler reached steady no-candidate polls.

## Outcome

All ADR-0024 issues #128-#132 landed, but recoveries were manual. ADR-0026 was authored to capture the retry/re-drive follow-up: transient agent failures should retry instead of blocking, and landable auto-land failures should be re-driven rather than requiring hand mutation of Podium state.
