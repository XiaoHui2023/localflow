# Round 12 — scoped multi-edit Case control

## Question

How can a plugin expose a compact repeated-item quantity editor where marquee defines an edit scope, changing one item updates the group, and the resting page remains quiet?

## Source coverage

- Figma multi-edit describes selection as an edit scope and applies one edit across matching selected objects; it preserves familiar selection mechanics instead of inventing a permanent bulk panel. <https://www.figma.com/blog/behind-the-feature-the-multiple-lives-of-multi-edit/>
- GNOME selection mode separates collection selection from the actions applied afterward and requires an explicit way to leave selection mode. <https://developer.gnome.org/hig/patterns/containers/selection-mode.html>
- SAP mass editing and industrial multi-edit documentation distinguish relative existing values from assigning one fixed shared value. <https://www.sap.com/design-system/fiori-design-web/v1-84/foundations/best-practices/global-patterns/object-handling/mass-editing>
- MDN documents cancelable `wheel` events and the need for a non-passive handler when the control intentionally consumes the wheel. <https://developer.mozilla.org/en-US/docs/Web/API/Element/wheel_event>
- WHATWG and React issue discussions show that unrequested wheel changes on number fields are surprising, so wheel adjustment must be explicitly owned by the hovered Case component and remain supplementary. <https://github.com/whatwg/html/issues/10911> <https://github.com/react/react/issues/32156>
- Community reports from Blender users consistently expect editing one numeric property to affect all selected objects, but also show that hidden modifier-only behavior is difficult to discover. The Case control therefore uses direct scope visuals and no mandatory modifier for the main group edit. <https://www.reddit.com/r/blenderhelp/comments/ercusa>

## Find Skills

Queries covered `multi selection batch edit interface design`, `quantity picker wheel interaction accessibility`, and `canvas marquee selection react`. Candidates included interface-design, platform-conventions, Spectrum components, and editor-gui. None was installed because primary design-system/browser sources plus the existing project component contract were sufficient; installing an unreviewed package would add supply-chain and visual-default costs.

## Resulting model

1. Persisted state: each Case has a nonnegative run count; count zero is omitted from the request.
2. Ephemeral state: marquee or Ctrl/Command click creates a scope set; it never changes persisted counts.
3. Relative edit: body click or wheel step changes each scoped item's own count by the same delta.
4. Fixed edit: opening any scoped `×N` and committing a number sets every scoped item to that number.
5. Dismissal: pointer-down outside the Case grid clears scope without changing counts.
6. Compatibility: wheel deltas are normalized and consumed only while hovering a Case; click and exact numeric input remain the keyboard/touch-compatible primary paths.

## Learning access

All local skill files, web references, Find Skills queries, and project files were accessible. No network, login, permission, dependency, download, or service failure occurred.
