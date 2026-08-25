# Round 11 — plugin run controls

## Learning targets

- Distinguish shared configuration fragments from ordinary parameter files without coloring filenames.
- Define plugin-registered run controls without coupling plugins to React or a component library.
- Design compact repeated-case quantity selection, batch adjustment, and per-tab context retention.
- Fail closed for syntax, common-field, type, and plugin-field errors.

## Primary references

- WAI-ARIA APG Grid Pattern: composite-grid keyboard conventions and the need to manage focus inside interactive grids. <https://www.w3.org/WAI/ARIA/apg/patterns/grid/>
- React Aria Selection: selection state should be controlled independently from collection rendering. <https://react-aria.adobe.com/selection.html>
- MDN Pointer Events: one event model can cover mouse, pen, and touch; touch must retain scrolling behavior. <https://developer.mozilla.org/en-US/docs/Web/API/Pointer_events>
- MDN `sessionStorage`: data is scoped to the current origin and browser tab, matching unfinished run context better than cross-session storage. <https://developer.mozilla.org/en-US/docs/Web/API/Window/sessionStorage>
- Material chips: compact selectable objects use a restrained selected state and concise trailing action. <https://m2.material.io/components/chips/android>

## Synthesis

- `task-defaults` is a valid shared fragment: it contains task-common fields and can be imported, but has no plugin and is not directly runnable. It therefore uses a stacked-files icon and the accessible label “共享片段”. Ordinary parameter files keep a plain-file icon; runnable files use a checked/document action icon; invalid files alone use the red warning icon.
- A plugin declares `RunFieldSpec` data only. The host validates the finite component type set, renders the control, owns accessibility, and can change the visual library without changing plugin code.
- Case cards are a quantity selector, not a searchable file list. Direct click increments, `×N` progressively discloses exact editing, and a contextual batch toolbar appears only for multi-selection. Marquee is an accelerator; each card and toolbar button remain the keyboard/touch path.
- Run context belongs to one browser tab, while theme is a durable preference. Thus unfinished values use `sessionStorage`; theme continues to use `localStorage`.

## Skill discovery

`skills find` returned third-party design-system and form-accessibility packages. None was installed: the built-in skill references and primary browser/accessibility documentation covered the need, while installation would add an unreviewed external dependency.

## Access result

All listed references and local skills were accessible. There was no network, download, permission, login, dependency, or service failure to disclose.
