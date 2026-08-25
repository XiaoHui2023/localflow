# Round 8 sources — resource-tree state and feedback

Retrieved 2026-08-25. The implementation uses the sources as design evidence, not as copied component code.

- [VS Code theme color reference](https://code.visualstudio.com/api/references/theme-color): mature list/tree semantics separate invalid and error foregrounds from selection backgrounds; file and source-control decorations use foreground color rather than large row fills.
- [VS Code API — FileDecoration and FileDecorationProvider](https://code.visualstudio.com/api/references/vscode-api): a compact decoration can carry a badge, tooltip and theme color.
- [GitHub Primer TreeView guidelines](https://primer.style/product/components/tree-view/guidelines/): keep node labels short, align leading visuals, and do not turn a tree node into a collection of controls.
- [GitHub Primer TreeView accessibility](https://primer.style/product/components/tree-view/accessibility/): meaningful visuals require text alternatives; the accessible name must retain the visible node label. Icon contrast target is 3:1 and text target is 4.5:1.
- [Material Design 3 states](https://m3.material.io/foundations/interaction/states/overview): state needs redundant visual indicators rather than color alone.
- [Community complaint about red file decorations](https://www.reddit.com/r/vscode/comments/wps00v/): coloring normal edits red is easily confused with errors and makes the explorer noisy. This is a qualitative counterexample, not an authority.

Find Skills queries were `file explorer status decoration`, `configuration validation UI`, and `VS Code explorer diagnostics accessibility`. Results were generic design, validation and accessibility packages; none supplied a focused, reviewable resource-tree decoration contract, so no package was installed.
