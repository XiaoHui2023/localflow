# Command inspection density closure

## Natural reproduction

The released source at `2baf8287a81ac6c3d8a4fc49acb01b16783674d8` was built before product CSS changed. A real Edge session opened `config/command/hello-world.yaml` at 1440×900. The command plugin exposed only `工作目录` and `命令`, yet the inspection grid occupied almost the complete workbench height and each row consumed roughly half of it. The captured failing screenshot is the test attachment for `command run information keeps content-driven compact rows`.

## Cause and correction

`.use-config` is a full-height flex row. Its child `.run-surface` is stretched in the cross axis. Both `.run-surface` and `.inspection-grid` were Grid containers with implicit auto rows and no content alignment. CSS Grid's default `align-content: normal` resolves to stretch, so the available block-axis space was first assigned to the inspection region and then divided between its two command rows.

The inspection renderer and clipboard renderer are now explicit React modules. Inspection geometry moved out of the accumulated general stylesheet into `run-inspection.css`; both Grid boundaries declare start alignment and max-content implicit tracks. Short command metadata stays compact, while tokens, long values and code lists retain content-driven growth.

The first full browser run also rejected an incomplete module boundary: moving the clipboard implementation without exporting it left the terminal's selection-copy path with a runtime-only undefined reference that the production build did not flag. Clipboard writing is now an exported shared service consumed by both copy-value and terminal components; the existing live/history terminal copy journeys remain part of the closure gate.

## Oracle

Edge opens the actual command configuration at 1440×900 and 760×900 and requires every scalar row to be at most 44px. The test then injects the former stretch rules and requires at least one row to exceed the limit, proving the oracle detects the reported failure rather than merely observing fields. Full browser, compatibility, Python, quality and release gates provide the final evidence.
