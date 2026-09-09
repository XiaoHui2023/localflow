# Adaptive configuration and task workspace

## User question and failure baseline

The operator is either configuring a run or observing tasks. At 1100px and below the previous layout stacked an open 72vh configuration workbench above the task pane, so both incomplete work surfaces remained in the same viewport. The new contract rejects that medium-width run-then-tasks stack.

## Research and selection

The study covered WAI-ARIA disclosure semantics, VS Code primary-sidebar visibility, Material 3 and Microsoft adaptive list/detail guidance, UX StackExchange discussion, Reddit responsive-design experience, and overview/detail research. Find Skills searches used “responsive master detail layout”, “react adaptive workspace”, “ui ux responsive dashboard”, and “playwright responsive layout testing”. Candidate Agent Skills were not installed because the existing user-root design Skill already has stricter accessibility, offline, legacy-browser, and machine-gate requirements.

Candidates:

- Keep vertical stacking: rejected because it exposes two short, competing work surfaces.
- Overlay drawer: rejected because configuration is a sustained editor workflow, not a transient peek.
- Always single pane: rejected because wide screens can preserve useful task context.
- Adaptive dual pane to focused single pane: selected. At wide widths configuration stays left of tasks; at intermediate and compact widths an open configuration pane alone owns the content area, and one existing disclosure activation reveals full-width tasks.

CSS container queries were not selected as the primary mechanism because the product release gate includes Chrome 84 and Firefox 78. A normal media query plus semantic button state has no new dependency and preserves those targets.

## Machine oracles

- The capability contract validates with the user-root capability-loop validator.
- The operator interaction contract requires the focused-pane rule and forbids the old stack. A copied CSS mutant that restores task display was rejected with exit code 1.
- Playwright checks 1440px dual-pane order; 1000px and 760px single-pane focus; one-click and Enter-key task/config transitions; preserved selected configuration; 390px explorer/editor reflow; and zero horizontal overflow.
- The fixed-browser Selenium journey sets a 1000×900 viewport in Chrome 84 and Firefox 78, writes an unsaved Monaco draft, switches to the task pane and back, and proves both focused-pane ownership and draft preservation.
- The first Edge run failed at an old 760px task-detail geometry assertion because that test left configuration open. The test now explicitly collapses configuration before measuring tasks and reopens it before configuration checks. This is retained as an oracle-ownership correction, not hidden as a product failure.
- The strengthened matrix was invoked twice with unsuitable interpreter environments before the successful formal run: the system interpreter first could not import `localflow`, then an absolute source path exposed its missing `watchfiles` dependency. No browser test ran in either attempt. The project `.venv` interpreter was the verified replacement.
- The final formal run passed Edge (`2 passed`), current Chromium/Firefox compatibility (`2 passed`), Chrome 84, and Firefox 78. The browser receipt and fixed-browser JSON/screenshots were regenerated from this run.

## Sources

- https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/
- https://code.visualstudio.com/docs/configure/custom-layout
- https://developer.android.com/develop/adaptive-apps/guides/list-detail
- https://learn.microsoft.com/windows/apps/develop/ui/controls/list-details
- https://ux.stackexchange.com/questions/149105/switching-between-master-and-detail-on-smaller-screens
- https://arxiv.org/abs/2503.07782
