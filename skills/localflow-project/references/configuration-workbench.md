# Configuration workbench

## Decision

Use the existing semantic disclosure button, resource tree, Monaco editor, and task workspace. Name the control `配置`. On wide screens, place the disclosed configuration workbench on the left and the task status pane on the right; below the existing breakpoint, stack configuration before tasks. Put labeled `编辑` and `运行` actions immediately after the selected file name in one contextual action group.

The terminal buffer contains only task log/process bytes. Connection, live/read-only state, and replay state belong to the terminal page header and accessibility status, never `xterm.write` or `xterm.writeln`.

## Candidate comparison

| Candidate | Strength | Rejection or boundary |
| --- | --- | --- |
| Left persistent workbench + disclosure | Matches the left-side trigger, preserves task context, reuses current mature components | Chosen; stack at medium/narrow widths |
| Right supplementary panel | Preserves task width | Rejected: trigger and result occupy opposite edges |
| Modal/drawer overlay | Strong temporary focus | Rejected for frequent wide-screen editing because it covers task context; not needed on phones while stack works |
| Separate configuration page | Large editor area | Rejected: adds a navigation round trip and violates the unified Tasks workspace contract |

WAI-ARIA disclosure supplies the interaction contract (`button`, `aria-expanded`, `aria-controls`). VS Code's primary sidebar/view-title actions supply the spatial and contextual-action model. Material persistent drawer/side-sheet guidance supports persistent wide layouts but does not justify adding a dependency when the current native control meets the contract.

## Direct gates

- At 1440 px, `run-panel.right <= task-pane.left`, their top edges align, and document overflow is zero.
- At 760 px, configuration ends before tasks begin; at 390 px, explorer ends before editor begins and overflow is zero.
- The disclosure has the exact visible name `配置`, retains one DOM location, and reports state through `aria-expanded`/`aria-controls`.
- The selected file name and contextual action group are adjacent; `编辑` and `运行` are both visible labels and require no menu/navigation step.
- Closing/reopening and leaving/returning to Tasks preserves file, mode, and unfinished inputs.
- Live and terminal-state xterm text contains the task bytes and contains no application-authored connection/replay sentences.

Fault mutants restore right-side grid order, the long label, icon-only run, remote `space-between` actions, or synthetic `term.writeln` status. Each must make the browser gate fail.

## Sources checked 2026-09-04

- W3C WAI-ARIA disclosure example: https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/examples/disclosure-navigation/
- VS Code sidebar UX and views: https://code.visualstudio.com/api/ux-guidelines/sidebars and https://code.visualstudio.com/api/ux-guidelines/views
- VS Code workbench/custom layout: https://code.visualstudio.com/docs/editing/userinterface and https://code.visualstudio.com/docs/configure/custom-layout
- Material navigation drawer: https://m3.material.io/components/navigation-drawer/overview
- xterm.js: https://xtermjs.org/

Community search covered Stack Overflow, Reddit, UX StackExchange, Medium, and operator-console discussions. It produced no stronger LocalFlow-specific primitive than the official patterns above, so no third-party Skill or runtime package was installed.
