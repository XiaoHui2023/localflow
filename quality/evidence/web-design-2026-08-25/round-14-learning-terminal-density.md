# Round 14 — rejection recovery, terminal density and local feedback

## Failed baseline

The user rejected the nested `CircleStop` inside a bordered square, blue hover around copy rows, wrapped code values, blank space below task details, the terminal page composition and fixed-width Case cards. The prior Round 13 visual PASS is revoked for these dimensions; its functional xterm and clipboard evidence remains local evidence only.

## Mature comparison

- Keep xterm.js 5.5 with official Fit/Search/WebLinks: it already owns VT rendering, selection, scrollback and links. Replacing it would add risk without addressing the failed outer layout.
- Follow VS Code's compact terminal panel pattern: one active identity, terminal list only when useful, compact inline actions, find disclosed in the terminal and the viewport owning remaining space.
- Use one unboxed `CircleX` for interruption; a plain `X` reads as close and the former `CircleStop` repeated square/circle silhouettes.
- Use intrinsic CSS Grid for Case options instead of fixed 180–220px cards.

Primary evidence: xterm.js official addon guide and repository, VS Code Terminal Basics/Appearance, xterm Fit implementation and maintainer resize discussions, Lucide icon catalog. Find Skills queries were also run for `web terminal ui xterm`, `responsive dense interface`, `icon interaction motion` and `react case picker grid`; candidates were discovery-only and not installed because the existing user-root design and quality skills are already more specific to the offline operator-console contract.

## New gates

- Stop action has zero border width, one semantic SVG and adds no detail grid row.
- Every detail code value is `nowrap`, owns horizontal overflow, uses neutral hover, and displays an in-place check animation with a screen-reader status.
- Terminal page uses xterm.js, fills the remaining viewport, has no persistent notice row, and shrinks from a narrow task rail to a horizontal task strip.
- Case grid uses intrinsic equal-width columns and compact 36px rows; narrow width is one full-width row per Case.
- Browser build lineage and UI revision must prove the live test URL serves the current sources before visual claims are restored.

## Iteration evidence

- Round 1 rejected a scroll assertion because the fixture command was not long enough at 1440px; the fixture was changed to a valid deterministic long command instead of weakening the gate.
- Round 2 rejected an Oracle that equated “multi-column” with “all items in one row”; the grid minimum was reduced and the gate now checks multiple filled columns plus compact row height.
- Round 3 exposed a real marquee bug: a global click-suppression boolean consumed the next click on any Case. Suppression is now bound to the drag-origin Case and expires after 300ms, so later group edits remain responsive.
- The first post-pass visual review revoked terminal completion because the Windows development pipe backend returned false for every valid resize and the WebSocket printed `[terminal resize rejected]` into task output. Valid resize is now an explicit no-op for the non-PTY development backend; Ubuntu's systemd/PT​​Y backend still performs the real resize. The exact error text is a browser negative assertion.
