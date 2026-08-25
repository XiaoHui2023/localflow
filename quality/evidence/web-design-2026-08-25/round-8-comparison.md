# Round 8 comparison

| Candidate | Strength | Failure mode | Decision |
|---|---|---|---|
| Whole-row background per state | Maximum visibility | Competes with hover/selection and turns the tree into a heat map | Rejected |
| Filename foreground only | Compact and familiar from source-control tools | Color-only semantics; valid files create too much green text | Rejected |
| Small state icon + semantic color + accessible state text | Compact, works with selection, distinct without color | Requires server-side classification metadata | Selected |
| Trailing text badge on every row | Explicit wording | Repeats status, shortens filenames and increases visual density | Rejected |

The selected treatment uses four shapes: file for generic data, braces for a reusable common fragment, check-circle for a runnable task, and warning-triangle for an invalid file. Only the invalid filename is tinted because it requires attention; other labels remain neutral.

Run/edit alternatives were also compared. Separate destinations repeat file selection and plugin context; always opening edit optimizes the rare action. A single file workbench with runnable files defaulting to “使用” preserves configuration-as-code while optimizing repeated launches.
