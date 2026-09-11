# Configuration workbench

## Decision

Selecting a clean, non-empty configuration from the resource tree always opens its run/debug surface, even if the operator previously inspected its YAML. An empty file or a file with an unsaved draft opens the editor so creation and unfinished work remain continuous. Mode persistence across pane collapse is handled by keeping the component mounted; it must not turn a historical clean edit mode into an extra click on every later run.

Use the existing semantic disclosure button, resource tree, Monaco editor, and task workspace. Name the control `配置`. Default a fresh browser session to expanded; preserve an explicit user collapse for that session. On wide screens, place the disclosed configuration workbench on the left and the task status pane on the right. When the available width cannot support both panes, use a focused single-pane state: open shows only configuration; one collapse reveals a full-width task pane. Do not stack two incomplete work surfaces. Keep the configuration component mounted so the transition preserves its selected file, mode, drafts and run inputs. At compact widths, reflow the explorer above the editor inside that one configuration pane. Put labeled `编辑` and `运行` actions immediately after the selected file name in one contextual action group. Disable Save when editor text exactly equals the loaded base version; syntax or plugin validity never controls Save. Preserve an independent draft per file, decorate dirty files and collapsed parents with a dot, and never discard a draft merely because the operator changes files or opens the run surface.

Use Monaco model markers plus a bounded Problems region below the editor for syntax/import feedback. Debounce edits briefly, abort the previous request, ignore stale responses, and return structured one-based line/column ranges from the server. Markers, the Problems row, and the resource-tree state are three projections of the same current diagnosis. Selecting a problem focuses and reveals its range; saving never changes page or mode. Do not add a full YAML language server when the product-specific configlib include parser remains the authority.

Measure the actual task-workspace content box with ResizeObserver; browser width is not a valid proxy when navigation, sidebars, zoom, or embedding consume space. Split only when the measured box can preserve at least 830 px for the explorer plus workbench and 410 px for tasks. A direct or transitive include change owns a separate projection revision: it must re-run diagnosis and inspection even though the selected file's byte hash is unchanged.

Plugin inspection values use typed presentation contracts. tokens renders non-copyable chips. code-list keeps the producer's array and renders every element as a separate line, code block, and copy target; joining with spaces, commas, JSON, or a single code surface destroys item boundaries. Static inspection is derived only from YAML, so Case counts and seed input never rewrite the case or seed placeholders.

Treat YAML configuration extensibility and run-input strictness as separate contracts. Every plugin accepts site-owned top-level keys so includes and configlib can use them as variables; plugin Pydantic models validate only fields they declare. Keep `additionalProperties: true` on configuration schemas, pass the complete resolved tree to plugin expansion, and retain `additionalProperties: false` on strict per-run input schemas. Never fix an Extra inputs report by adding one special key to one built-in plugin.

Treat plugin extensibility and variable provenance as separate contracts too. The host contributes no hidden `root`, directory, or run-input variables; only `case` and `seed` may be plugin-deferred. This prevents a permissive editor from becoming environment-dependent and makes an unknown placeholder a deterministic inline debug result.

Call the reusable-configuration surface and its local tab `常用`: it describes the outcome shared by personal favorites and actual recent use without promising that every entry is pinned. Keep the global rail limited to the `配置` disclosure. Put `资源 / 常用` as a quiet horizontal tablist on the owning explorer header so both are peers, not indented pseudo-navigation. Use automatic activation because both panels are already local and immediate; support roving tabindex plus Left/Right/Home/End. Render a flat action list rather than a file tree, split it into explicit `已收藏` then `最近使用` groups, and sort each group by the last accepted run submission descending. A never-run favorite falls back to newest favorite first. Use the complete config-relative path as the only visible and accessible row identity: configuration names and labels can collide, while the path is the resource key already used by open, move, rename and deletion. Let long paths wrap inside the row without clipping or horizontal overflow.

Keep the Tasks workbench mounted when moving to another top-level destination. Hiding it preserves Monaco, the virtual tree, selected file, drafts and run controls, so returning from Terminal is a visibility change rather than a complete reconstruction. Continue to unmount the terminal destination itself so xterm, ResizeObserver and WebSocket cleanup remains immediate. Ignore zero-width ResizeObserver samples while the workbench is hidden, then recompute its adaptive layout when visible. Gate the return interaction from click through two animation frames and record the elapsed value against a versioned budget.

Record run history on the server in the same accepted batch transaction so refreshes and different browsers see truthful usage rather than click telemetry. Keep favorites browser-local until the product has user identity and preference synchronization; cap them at 100. The current configuration owns one star action beside Edit/Run/Save with stable pressed semantics and accessible `收藏配置`/`取消收藏` names. In-app move/rename remaps both server history and browser favorites; delete and external disappearance suppress stale entries. The local tablist exists inside the configuration panel, swaps only the explorer rail, and keeps the workbench mounted. Collapsing configuration hides the entire local control without moving it into global navigation.

The terminal buffer contains only task log/process bytes. Connection, live/read-only state, and replay state belong to the terminal page header and accessibility status, never `xterm.write` or `xterm.writeln`.

## Candidate comparison

| Candidate | Strength | Rejection or boundary |
| --- | --- | --- |
| Left persistent workbench + disclosure | Matches the left-side trigger, preserves task context, reuses current mature components | Chosen on wide screens |
| Adaptive dual pane → focused single pane | Preserves simultaneous context only when both panes are useful; gives the active workbench full width otherwise | Chosen for medium/narrow workspace ownership |
| Right supplementary panel | Preserves task width | Rejected: trigger and result occupy opposite edges |
| Modal/drawer overlay | Strong temporary focus | Rejected for frequent wide-screen editing because it covers task context; not needed on phones while stack works |
| Separate configuration page | Large editor area | Rejected: adds a navigation round trip and violates the unified Tasks workspace contract |
| Grouped `常用` rail | Combines truthful run history with personal pinning; direct reopen without file-tree traversal | Chosen; server history plus browser-local favorites |
| Explorer-header `资源 / 常用` tablist | Makes two local content views peers, keeps the global rail flat, and follows familiar composite keyboard behavior | Chosen |
| Indented `快捷` button below global `配置` | Keeps the control near the disclosure | Rejected: visually invents a third navigation depth and creates unexplained indentation |
| Segmented control in the global rail | Compact | Rejected: still assigns a local view switch to the global navigation owner and is too narrow at compact widths |
| Dropdown/menu in the explorer header | Saves a few pixels | Rejected for two frequent views because it hides state and adds an operation |
| Favorites-only rail | Simple personal collection | Rejected as the complete surface: previously used but unstarred YAML disappears |
| Recent-only rail | Requires no explicit management | Rejected as the complete surface: important configurations drift downward |
| Server-side shared favorites | Cross-browser/team sharing | Rejected until identity, ownership and synchronization semantics exist |
| Favorite modal/dropdown | Compact chrome | Rejected: hides a frequent navigation collection and overlays the active workbench |

WAI-ARIA disclosure supplies the interaction contract (`button`, `aria-expanded`, `aria-controls`). VS Code's primary sidebar/view-title actions supply the spatial and contextual-action model. Material persistent drawer/side-sheet guidance supports persistent wide layouts but does not justify adding a dependency when the current native control meets the contract.

## Direct gates

- At 1440 px, `run-panel.right <= task-pane.left`, their top edges align, and document overflow is zero.
- At 1000 and 760 px, open configuration is the only visible pane and spans the app content; one disclosure activation hides it and reveals the full-width task pane. At 390 px, explorer ends before editor begins inside configuration. All widths have zero overflow.
- The disclosure has the exact visible name `配置`, starts expanded when no preference exists, retains one DOM location, and reports state through `aria-expanded`/`aria-controls`.
- The selected file name and contextual action group are adjacent; `编辑` and `运行` are both visible labels and require no menu/navigation step.
- The global rail contains no indented local-view control. Inside the expanded panel, `资源 / 常用` are horizontal tabs with one selected tab, matching tabpanels, and Left/Right/Home/End keyboard switching. Collapsing configuration makes the local tablist unavailable. `已收藏` precedes `最近使用`; a successfully submitted YAML appears without being starred, stars move it to the first group, and each row exposes exactly one complete config-relative path with no name/label duplicate identity. Refresh preserves history and favorites, rename/move remaps them, and delete/external disappearance removes stale entries.
- Closing/reopening and leaving/returning to Tasks preserves file, mode, and unfinished inputs.
- Save is disabled before an edit and immediately after a successful save, but enabled for any byte-changing edit even when diagnosis fails.
- Switching among configuration files restores each unsaved byte buffer and its base version. File and ancestor-folder dirty dots disappear only after save, delete, or an explicit external-version choice; rename/move remaps them.
- Direct disk writes use the same path-scoped refresh for valid and invalid YAML. Invalid events carry the new content version and load the real bytes plus Problems into a clean editor; a dirty per-file draft remains untouched and receives a conflict notice. A notice without refreshing invalid disk content is not synchronization.
- Every edit produces at most one current diagnosis after the debounce window; an older response cannot overwrite a newer edit. Invalid YAML has a Monaco error marker and a bottom Problems row with line/column; selecting it returns focus to that position without changing mode. Saving the invalid draft remains possible.
- Saving valid or invalid text preserves the current editor mode. Missing plugin keys, illegal values, and unknown variables produce a stable disabled 配置无效 action plus the same-page debug projection.
- Two compile-log values produce exactly two full-owner-width copy-value code elements under one code-list; nested generic grid defaults may not collapse an unlabeled list row into the label column. Case/seed interaction leaves their exact text unchanged.
- Completed-task details preserve the same structural contract: any ordinary array becomes one labelled list with one full-width independently copyable row per element; it is never JSON-stringified into one line. The time row uses the plain textual label `开始时间`, with its full value retained by semantic `time` attributes rather than a one-off decorative icon.
- Leaving Terminal for Tasks preserves the same configuration-workbench DOM identity, removes the terminal destination and its socket, and reaches two post-click animation frames within the versioned interaction budget.
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

## Navigation hierarchy correction, 2026-09-11

- VS Code Activity Bar guidance treats each item as a top-level View Container; view content and actions belong inside the sidebar container.
- Fluent 2 recommends tablists for a small set of closely related, frequently accessed content categories, using short parallel labels.
- WAI-ARIA APG defines `tablist`/`tab`/`tabpanel`, one selected tab, roving tabindex and Left/Right/Home/End navigation.
- Find Skills surfaced navigation-pattern and tab-navigation candidates, but no third-party Skill or runtime was installed: the official patterns plus the existing project/browser gates cover this narrow decision without adding an unreviewed dependency.

The rejected baseline is the indented `快捷` button under the global `配置` disclosure. Its defect is ownership, not spacing: it makes a local content choice look like a third application destination. The selected correction keeps one global disclosure and moves the two local choices to the explorer header as a quiet underline tablist.

## Adaptive pane study, 2026-09-09

- WAI-ARIA disclosure: https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/
- VS Code custom workbench layout: https://code.visualstudio.com/docs/configure/custom-layout
- Material 3 adaptive list-detail: https://developer.android.com/develop/adaptive-apps/guides/list-detail
- Microsoft adaptive list/details: https://learn.microsoft.com/windows/apps/develop/ui/controls/list-details
- UX StackExchange narrow master/detail discussion: https://ux.stackexchange.com/questions/149105/switching-between-master-and-detail-on-smaller-screens
- Responsive overview/detail research: https://arxiv.org/abs/2503.07782

The candidate search also found responsive-design and responsive-QA Agent Skills. They were not installed: the existing user-root web-design Skill already owns stronger accessibility, legacy-browser and machine-gate constraints, while LocalFlow needs only a small semantic/CSS state change. CSS container queries were rejected as the primary mechanism because the released product explicitly gates Chrome 84 and Firefox 78.
