# Round 8 iterations

## Baseline

- Tree leaves had one file icon and no diagnostic state.
- Validity/type repeated as editor-header badges.
- A success status was fixed at the top right and could cover controls.
- Runnable files always opened in edit mode.

## Iteration 1 — diagnostic projection

The file-list endpoint now diagnoses each item independently. Generic, fragment, valid task and invalid task fixtures passed. Fault injection with syntax-invalid YAML initially escaped because PyYAML's `ParserError` is not a `ValueError`; the owner boundary was corrected to include `yaml.YAMLError`. The damaged file then remained in the list with an invalid diagnosis.

## Iteration 2 — tree decoration and daily path

The tree consumes the diagnostic projection, uses four icon shapes and semantic colors, and exposes the filename plus state through the accessible name. Header validity badges were removed. Invalid details remain in the opened workbench. Runnable files now open in “使用”; other files open in “编辑”.

## Iteration 3 — feedback ownership and browser oracle

Success feedback moved from a fixed green overlay to a neutral inline workbench status and expires after 2.8 seconds. The first Edge run rejected an ambiguous `role=alert` test selector because Monaco owns additional alerts; the oracle was tightened to `.config-diagnosis`. The second run passed with all four explorer states, opened invalid errors, default use mode, static expiring status, axe A/AA and narrow geometry.

Evidence: `quality/evidence/browser/admin-config-explorer-dark.png` and `quality/evidence/browser/browser-receipt.json`.
