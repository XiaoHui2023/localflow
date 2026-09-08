# Configuration workbench

## Decision

Use the existing semantic disclosure button, resource tree, Monaco editor, and task workspace. Name the control `配置`. Default a fresh browser session to expanded; preserve an explicit user collapse for that session. On wide screens, place the disclosed configuration workbench on the left and the task status pane on the right; below the existing breakpoint, stack configuration before tasks. Put labeled `编辑` and `运行` actions immediately after the selected file name in one contextual action group. Disable Save when editor text exactly equals the loaded base version; syntax or plugin validity never controls Save.

Use Monaco model markers plus a bounded Problems region below the editor for syntax/import feedback. Debounce edits briefly, abort the previous request, ignore stale responses, and return structured one-based line/column ranges from the server. Markers, the Problems row, and the resource-tree state are three projections of the same current diagnosis. Selecting a problem focuses and reveals its range; saving never changes page or mode. Do not add a full YAML language server when the product-specific configlib include parser remains the authority.

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
- The disclosure has the exact visible name `配置`, starts expanded when no preference exists, retains one DOM location, and reports state through `aria-expanded`/`aria-controls`.
- The selected file name and contextual action group are adjacent; `编辑` and `运行` are both visible labels and require no menu/navigation step.
- Closing/reopening and leaving/returning to Tasks preserves file, mode, and unfinished inputs.
- Save is disabled before an edit and immediately after a successful save, but enabled for any byte-changing edit even when diagnosis fails.
- Every edit produces at most one current diagnosis after the debounce window; an older response cannot overwrite a newer edit. Invalid YAML has a Monaco error marker and a bottom Problems row with line/column; selecting it returns focus to that position without changing mode. Saving the invalid draft remains possible.
- Live and terminal-state xterm text contains the task bytes and contains no application-authored connection/replay sentences.

Fault mutants restore right-side grid order, the long label, icon-only run, remote `space-between` actions, or synthetic `term.writeln` status. Each must make the browser gate fail.

## Sources checked 2026-09-08

- W3C WAI-ARIA disclosure example: https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/examples/disclosure-navigation/
- VS Code sidebar UX and views: https://code.visualstudio.com/api/ux-guidelines/sidebars and https://code.visualstudio.com/api/ux-guidelines/views
- VS Code workbench/custom layout: https://code.visualstudio.com/docs/editing/userinterface and https://code.visualstudio.com/docs/configure/custom-layout
- Material navigation drawer: https://m3.material.io/components/navigation-drawer/overview
- xterm.js: https://xtermjs.org/
- Monaco marker API: https://microsoft.github.io/monaco-editor/typedoc/modules/editor_editor_api.editor.html
- VS Code errors, warnings and Problems panel: https://code.visualstudio.com/docs/editing/editingevolved#_errors-warnings

Community search covered Stack Overflow, Reddit, UX StackExchange, Medium, and operator-console discussions. It produced no stronger LocalFlow-specific primitive than the official patterns above, so no third-party Skill or runtime package was installed.
