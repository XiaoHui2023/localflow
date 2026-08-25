# Round 13 — task density, terminal fit, and step economy

Primary questions: “这个任务是什么、何时结束、如何运行、输出在哪里？” and “如何以最少步骤操作所选配置？”

| Element | User concern | Decision | Measured effect |
| --- | --- | --- | --- |
| Task name + labels | identify work | merge into one row | row height reduced to 48px |
| End time | scan history | keep in row | visible before disclosure |
| Task ID / exit code | developer diagnosis only | remove from web detail | API retains both |
| Detail/terminal tabs | terminal has a primary destination | remove | one disclosure level removed; no hidden socket |
| Command, working directory, output path | reproduce and locate output | keep as clickable code values | one-click copy |
| `source` and “computed information” heading | no user action | remove | plugin values remain directly labelled when present |
| Stop text + square | action already represented by icon | replace with accessible CircleStop | one compact action, no redundant copy |
| File overflow menu | interface tax | remove | rename 2→1 clicks; delete 3→2 including confirmation |
| Terminal fixed widths | caused page overflow | add shrink boundaries and responsive control grid | 1440/760/390 page overflow = 0 |

The terminal remains xterm.js with official Fit, Search and WebLinks addons and bounded 5000-line scrollback. The official WebGL addon was evaluated but not enabled because repeated disposal currently has an upstream context-release defect; stable rendering and zero hidden connections take precedence. Edge screenshots and direct resource measurements are bound in `quality/evidence/browser/browser-receipt.json`.
