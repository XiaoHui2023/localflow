# Inspection hierarchy and editor drafts

## Outcome

- Verification run inspection no longer repeats a string command's first token as “命令入口”.
- Inspection items expose an explicit none/availability check contract. Normal, existing, warning, and informational values have no status glyph; only availability + error renders a labelled, focusable cross.
- Verification custom text keeps case/seed placeholders unchanged during run selection. Task expansion still freezes the selected values.
- Every changed configuration has an independent in-memory draft. Switching files restores exact bytes and base version; file and ancestor-folder dots represent unsaved work. Save, delete, explicit conflict replacement, rename, and move have defined draft transitions.
- Copyable values keep a visible Copy affordance and give pressed-surface plus in-place Check feedback without layout movement or a toast.

## Natural reproduction and failure iterations

1. The new API contract test failed against the old implementation at working_directory.check because the field did not exist.
2. The first Edge rerun failed because the old test still looked for the removed floating copy-confirm element. The assertion was upgraded to require the in-button affordance and unchanged bounding box.
3. The second Edge rerun timed out trying to Save after the test had restored bytes exactly to the base version. The disabled button was correct behavior. The test now uses a different valid final value so successful-save clearing remains independently exercised.
4. Removing shlex together with the redundant inspection parser caused six plugin tests to fail because real string-command expansion still quotes case values with shlex. The import was restored; only the redundant inspection block remains removed.

These failures are retained as regression coverage rather than treated as informal observations.

## Direct receipts

- Focused API/plugin/static contract suite: 25 passed.
- Production frontend build: passed.
- Edge public-entry suite: 2 passed, including exact dirty draft restoration, save clearing, zero normal inspection icons, missing-path cross/tooltip, copy geometry and accessibility.
- Current Chromium and Firefox compatibility suite: 2 passed.
- Docker-backed fixed Chrome 84 and Firefox 78 probes: passed.
- Browser receipt: quality/evidence/browser/browser-receipt.json, completed 2026-09-08T07:16:47.994Z.
- Measured idle resources remained within the repository contract: server RSS 62.598 MiB, server CPU 1.78%, renderer heap 12.093 MiB, renderer CPU 0.819%, 1,759 DOM nodes, 299 listeners, 7 background requests, zero idle WebSockets.

## Research and failure disclosure

Learning goal: compare mature information-hierarchy, dirty-file, and local copy-feedback patterns and look for reusable third-party Skill guidance.

Official Carbon disclosure/form guidance and official VS Code dirty-editor/FileDecoration behavior were reviewed and distilled into the project topic and the user-root operator interaction catalog. The external Skills CLI searches for “concise operator inspection information hierarchy” and “information hierarchy” produced no output and did not exit within a bounded 60 seconds; both were terminated.

Impact: no external Skill package candidates could be compared or installed. This did not reduce the implemented runtime or test scope because installed user-root skills plus official Carbon/VS Code sources covered the interaction contracts.

Alternative used: existing modern-web-interface-design/operator-interaction solution catalog, element concern audit, official primary documentation, direct API tests, real Edge behavior, current Chromium/Firefox, and fixed legacy browser probes.

Recovery condition: retry the Skills search only when its registry/CLI responds within the bounded window.
