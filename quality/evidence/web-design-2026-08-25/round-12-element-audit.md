# Round 12 — element and interaction audit

| Element/state | User concern | Decision | Gate |
|---|---|---|---|
| Default `case-a ×1` | It silently schedules work before the user chooses anything. | Remove from starter and live example. | `case-empty-default` |
| Marquee changing counts | Selection and mutation become inseparable and accidental. | Marquee changes ephemeral scope only. | `case-marquee-scope-only` |
| Strong scope outline | Users must know which items a subsequent edit will affect. | Keep one accent outline/background; retain count text separately. | scoped DOM and screenshot |
| `3 个 / − / +` toolbar | It repeats operations already available on the items and creates a second interaction location. | Remove. | absence assertion |
| Hover wheel | Repeated quantities need a fast desktop adjustment. | Keep as normalized accelerator on the hovered item/scope; consume page scroll locally. | `case-hover-wheel` |
| Editing one scoped item | Users expect one edit to apply to the selected set. | Body/wheel use relative delta; numeric entry sets a fixed shared value. | `case-group-relative-edit`, `case-group-fixed-edit` |
| Persistent scope | A forgotten selection can affect later edits. | Clear on outside pointer-down or explicit new scope. | `case-scope-dismissal` |
| Native number spinners | They add cramped arrows beside an already progressive exact editor. | Hide native spinner decoration; retain number semantics. | screenshot + spinbutton role |
| Wheel-only behavior | Trackpad, touch, and keyboard users may not have a wheel. | Reject as primary path; keep direct click and number input. | click/input gates |

## Defect transaction

- Failure: the first Edge gate used a label locator shared by three scoped count buttons and the active number input.
- Evidence: Playwright strict-mode error listed all four matching elements; the screenshot showed the correct group input.
- Root cause: test Oracle ambiguity, not product state.
- Fix: target the semantic `spinbutton` role for exact group entry; retain identical accessible labels on the passive badges because they describe the same group action.

- Failure: React's delegated `wheel` listener was passive in the tested runtime, so `preventDefault()` logged `Unable to preventDefault inside passive event listener invocation` three times.
- Evidence: the Edge gate reached every functional assertion but rejected the console errors.
- Root cause: framework event delegation did not satisfy the component's cancelable-wheel contract.
- Fix: register one native delegated listener on the Case grid with `{ passive: false }`; keep state mutation in React and remove the per-card synthetic wheel handlers.

- Failure: the quality Oracle required exactly seven screenshots, so adding empty and scoped-state visual evidence made the otherwise current receipt fail.
- Root cause: the Oracle encoded an evidence count instead of the required evidence identities.
- Fix: require the explicit nine-file screenshot set and continue hashing every bound image; unexpected stale images and missing required states both fail.

## Acceptance boundaries

- Proven in Microsoft Edge with a mouse wheel, direct clicks, numeric input, marquee, outside dismissal, desktop and 390 px geometry.
- Touch has the direct click/input path and keeps vertical panning; touch marquee and wheel hardware equivalence are not claimed.
