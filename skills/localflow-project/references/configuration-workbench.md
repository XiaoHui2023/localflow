# Configuration workbench

## Decision

Use the existing semantic disclosure button, resource tree, Monaco editor, and task workspace. Name the control `配置`. Default a fresh browser session to expanded; preserve an explicit user collapse for that session. On wide screens, place the disclosed configuration workbench on the left and the task status pane on the right. When the available width cannot support both panes, use a focused single-pane state: open shows only configuration; one collapse reveals a full-width task pane. Do not stack two incomplete work surfaces. Keep the configuration component mounted so the transition preserves its selected file, mode, drafts and run inputs. At compact widths, reflow the explorer above the editor inside that one configuration pane. Put labeled `编辑` and `运行` actions immediately after the selected file name in one contextual action group. Disable Save when editor text exactly equals the loaded base version; syntax or plugin validity never controls Save. Preserve an independent draft per file, decorate dirty files and collapsed parents with a dot, and never discard a draft merely because the operator changes files or opens the run surface.

Use Monaco model markers plus a bounded Problems region below the editor for syntax/import feedback. Debounce edits briefly, abort the previous request, ignore stale responses, and return structured one-based line/column ranges from the server. Markers, the Problems row, and the resource-tree state are three projections of the same current diagnosis. Selecting a problem focuses and reveals its range; saving never changes page or mode. Do not add a full YAML language server when the product-specific configlib include parser remains the authority.

The terminal buffer contains only task log/process bytes. Connection, live/read-only state, and replay state belong to the terminal page header and accessibility status, never `xterm.write` or `xterm.writeln`.

## Candidate comparison

| Candidate | Strength | Rejection or boundary |
| --- | --- | --- |
| Left persistent workbench + disclosure | Matches the left-side trigger, preserves task context, reuses current mature components | Chosen on wide screens |
| Adaptive dual pane → focused single pane | Preserves simultaneous context only when both panes are useful; gives the active workbench full width otherwise | Chosen for medium/narrow workspace ownership |
| Right supplementary panel | Preserves task width | Rejected: trigger and result occupy opposite edges |
| Modal/drawer overlay | Strong temporary focus | Rejected for frequent wide-screen editing because it covers task context; not needed on phones while stack works |
| Separate configuration page | Large editor area | Rejected: adds a navigation round trip and violates the unified Tasks workspace contract |

WAI-ARIA disclosure supplies the interaction contract (`button`, `aria-expanded`, `aria-controls`). VS Code's primary sidebar/view-title actions supply the spatial and contextual-action model. Material persistent drawer/side-sheet guidance supports persistent wide layouts but does not justify adding a dependency when the current native control meets the contract.

## Direct gates

- At 1440 px, `run-panel.right <= task-pane.left`, their top edges align, and document overflow is zero.
- At 1000 and 760 px, open configuration is the only visible pane and spans the app content; one disclosure activation hides it and reveals the full-width task pane. At 390 px, explorer ends before editor begins inside configuration. All widths have zero overflow.
- The disclosure has the exact visible name `配置`, starts expanded when no preference exists, retains one DOM location, and reports state through `aria-expanded`/`aria-controls`.
- The selected file name and contextual action group are adjacent; `编辑` and `运行` are both visible labels and require no menu/navigation step.
- Closing/reopening and leaving/returning to Tasks preserves file, mode, and unfinished inputs.
- Save is disabled before an edit and immediately after a successful save, but enabled for any byte-changing edit even when diagnosis fails.
- Switching among configuration files restores each unsaved byte buffer and its base version. File and ancestor-folder dirty dots disappear only after save, delete, or an explicit external-version choice; rename/move remaps them.
- Direct disk writes use the same path-scoped refresh for valid and invalid YAML. Invalid events carry the new content version and load the real bytes plus Problems into a clean editor; a dirty per-file draft remains untouched and receives a conflict notice. A notice without refreshing invalid disk content is not synchronization.
- Every edit produces at most one current diagnosis after the debounce window; an older response cannot overwrite a newer edit. Invalid YAML has a Monaco error marker and a bottom Problems row with line/column; selecting it returns focus to that position without changing mode. Saving the invalid draft remains possible.
- Live and terminal-state xterm text contains the task bytes and contains no application-authored connection/replay sentences.
- A Case row is the primary increment target: pointer-down adds exactly one immediately, then repeats only after 550 ms and accelerates in bounded stages. There is no separate plus button. The decrement appears only above zero, shares the repeat state machine, and cannot bubble into row increment. Keyboard activation increments once; Ctrl/Cmd click edits the explicit group; wheel and focus never change counts.

Fault mutants restore right-side grid order, the medium-width run-then-tasks stack, the long label, icon-only run, remote `space-between` actions, synthetic `term.writeln` status, or an invalid-file event that only shows a notice without loading the changed bytes. Each must make the browser gate fail.

For the element-level inspection, copy-feedback, and draft identity rationale, read [run inspection and draft decisions](run-inspection-and-drafts.md).

## Sources checked 2026-09-08

- W3C WAI-ARIA disclosure example: https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/examples/disclosure-navigation/
- VS Code sidebar UX and views: https://code.visualstudio.com/api/ux-guidelines/sidebars and https://code.visualstudio.com/api/ux-guidelines/views
- VS Code workbench/custom layout: https://code.visualstudio.com/docs/editing/userinterface and https://code.visualstudio.com/docs/configure/custom-layout
- Material navigation drawer: https://m3.material.io/components/navigation-drawer/overview
- xterm.js: https://xtermjs.org/
- Monaco marker API: https://microsoft.github.io/monaco-editor/typedoc/modules/editor_editor_api.editor.html
- VS Code errors, warnings and Problems panel: https://code.visualstudio.com/docs/editing/editingevolved#_errors-warnings

Community search covered Stack Overflow, Reddit, UX StackExchange, Medium, and operator-console discussions. It produced no stronger LocalFlow-specific primitive than the official patterns above, so no third-party Skill or runtime package was installed.

## Adaptive pane study, 2026-09-09

- WAI-ARIA disclosure: https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/
- VS Code custom workbench layout: https://code.visualstudio.com/docs/configure/custom-layout
- Material 3 adaptive list-detail: https://developer.android.com/develop/adaptive-apps/guides/list-detail
- Microsoft adaptive list/details: https://learn.microsoft.com/windows/apps/develop/ui/controls/list-details
- UX StackExchange narrow master/detail discussion: https://ux.stackexchange.com/questions/149105/switching-between-master-and-detail-on-smaller-screens
- Responsive overview/detail research: https://arxiv.org/abs/2503.07782

The candidate search also found responsive-design and responsive-QA Agent Skills. They were not installed: the existing user-root web-design Skill already owns stronger accessibility, legacy-browser and machine-gate constraints, while LocalFlow needs only a small semantic/CSS state change. CSS container queries were rejected as the primary mechanism because the released product explicitly gates Chrome 84 and Firefox 78.
