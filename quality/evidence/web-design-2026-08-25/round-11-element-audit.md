# Round 11 — element and interaction audit

| Surface | Deletion test | Decision | Automated gate |
|---|---|---|---|
| Shared-fragment icon | Without it, `task-defaults` looks like arbitrary data although it participates in task composition. | Keep one stacked-files icon and accessible state text; no filename color. | `shared-fragment-semantic-icon` |
| Case search | Three one-level cases remain fully visible; search adds a mode and occupies space without improving retrieval. | Remove. | absence assertion in Edge |
| Unselected count | `×0` or `auto` explains an absence already conveyed by the neutral card. | Remove. | `case-click-increment` |
| Selected `×N` | Removing it hides run multiplicity and the exact-edit entry. | Keep as compact trailing control. | `case-count-progressive-editor` |
| Permanent number input | Most runs need one click, not exact typing. | Disclose only after clicking `×N`. | `case-count-progressive-editor` |
| Batch toolbar | It is useless for zero or one selected case. | Render only for multi-selection. | `case-batch-adjustment` |
| Seed helper text / `auto` | Blank already means generate a seed; the text consumes a second row. | Blank, single aligned row. | `blank-seed` |
| Run-page context | Losing the selected config or values on a tab switch repeats work. | Preserve per-tab file, mode, and values. | `run-context-memory` |
| Hidden terminal mount | Preserving it would duplicate WebSocket/xterm resources when not visible. | Unmount live terminal pages; persist only lightweight run state. | browser connection behavior |
| Error run action | Allowing a malformed config to run bypasses the diagnosis contract. | Hide/disable use flow and return HTTP 422. | invalid corpus tests |

## Closed-loop defects found

1. Keeping every primary page mounted duplicated hidden terminal resources. Only the Run page is retained; terminal views unmount.
2. YAML parser errors were diagnosed in the explorer but escaped the run API boundary. The endpoint now converts parser/type/plugin failures into HTTP 422.
3. The first marquee test used a one-pixel fractional boundary, so down/up landed on an adjacent container. The gate now starts four CSS pixels inside the first card and ends inside the last card, proving card-origin marquee rather than testing hit-test rounding.

## Acceptance

- Desktop Edge and 390 px screenshots must show no filename tint, no Case search, one-row blank seed, uniform action sizes, and no overflow.
- Mouse marquee, direct click, exact count editing, batch decrement, tab-switch restoration, invalid diagnosis, and non-runnable errors are separately asserted.
- Syntax error, missing required field, and wrong field type examples remain outside the normal starter list and are copied into isolated tests.
