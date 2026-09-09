# Run inspection and draft decisions

## Operator question

The run surface answers: “What exactly will LocalFlow run, and is any required input unavailable?” The editor/explorer answers: “Which files contain work I have not saved?”

## Element concern audit

| Element | Job | Decision |
| --- | --- | --- |
| Resolved working directory | Proves the execution context | Keep; availability checked |
| User-authored command | Proves the operator's intent | Keep; hide executor shell/`-ic`/`cd` wrappers |
| Command entry | Repeats only the first token of the full command and is unreliable for shell built-ins, aliases, wrappers, and compound commands | Remove |
| Case directory | Required discovery input | Keep; plugin declares availability check |
| Compile/run log paths | Lets the operator review future outputs | Keep; never check pre-run existence |
| Labels | Lets the operator identify a run | Keep as separate non-copyable tokens |
| Operator text | Lets the operator review/copy configured notes | Keep as individual copy surfaces |
| Success checkmarks | Add no action when everything is normal and compete with the values | Remove |
| Missing-path cross | Makes the only actionable exception discoverable without relying on color | Keep only for explicit availability + error |
| Copy feedback | Confirms an invisible clipboard side effect | Make the value the button; no repeated Copy/Check glyph, pressed/success surface, no toast or layout movement |
| Dirty dot | Warns that switching context does not imply persistence | Keep on the file and propagate to a collapsed ancestor folder |
| Verification seed/run-log task rows | Duplicate template/operator text or the dedicated terminal history while adding no task action | Hide in verification task detail; retain in API snapshot and result evaluation |

## Candidate comparison

| Candidate | Benefit | Cost/risk | Decision |
| --- | --- | --- | --- |
| Success icon on every row | Uniform status column | Visual noise; implies every displayed value was validated | Reject |
| Severity icon for every item | Exposes warnings | Still overloads informational/future-output rows | Reject |
| Failure-only explicit check policy | Quiet normal state and truthful ownership | Requires one API field | Selected |
| One editor buffer only | Minimal state | Switching files loses work | Reject |
| Per-file in-memory drafts | VS Code-like switching, bounded to changed files | Lost on a full page reload by design | Selected |
| Persist every draft in browser storage | Survives reload | Quota/privacy/stale-version complexity | Defer until explicitly required |
| Toast after copy | Highly visible | Detaches feedback and can stack/shift attention | Reject |
| Whole-value in-place state transition | Strong local causality, no repeated glyph, stable geometry | Needs clear hover/focus and reduced-motion handling | Selected |

## Contracts

- Inspection items default to no check. A plugin opts into availability only for an input that must exist before submission.
- The UI renders a cross only when check is availability and severity is error. Existing inputs, informational items, warnings, and future outputs render no status icon.
- A shell command is a complete string contract. Never derive a second “entry” row from its first token.
- Shell choice and injected cwd wrapper are executor mechanics. Retain them in the durable API command array, but add a user-facing display command derived by removing only LocalFlow's known wrapper.
- Labels use the typed `tokens` inspection kind; the host renders pills and no copy action. Do not overload `text` with comma-separated multi-values.
- Verification custom text remains template-shaped in run review: case and seed placeholders do not react to selection. Per-task expansion still freezes real values.
- Draft identity is the logical resource path. Rename/move remaps all affected keys; delete removes them; save and explicit conflict resolution clear them.
- Dirty state is byte equality against the loaded base, independent of syntax diagnosis.
- A dirty configuration cannot submit a run based on stale persisted bytes.
- Presentation hiding is template-scoped. Verification task details omit `seed` and `运行日志`, but storage, API, deferred allocation and plugin result evaluation remain unchanged.

## Direct proof

- API tests assert check policy, absence of command_entry, and stable custom-text placeholders under selected Case/seed inputs.
- Edge changes one YAML, switches away and back, observes exact draft recovery, saves, and observes the file decoration disappear.
- Edge sees zero inspection status icons for the valid verification configuration and one keyboard-focusable cross with a tooltip for a missing Case directory.
- Copy tests prove the full value surface copies without a glyph and keeps dimensions fixed; CSS disables motion under reduced-motion preference.

## Sources and learning record

Checked 2026-09-08:

- Carbon disclosure, accordion, and form patterns: https://carbondesignsystem.com/patterns/disclosures-pattern/ , https://carbondesignsystem.com/components/accordion/usage/ , https://carbondesignsystem.com/patterns/forms-pattern/
- VS Code API dirty state and file decorations: https://code.visualstudio.com/api/references/vscode-api
- VS Code modified editor and Explorer indicators: https://code.visualstudio.com/updates/v1_29 and https://code.visualstudio.com/docs/sourcecontrol/staging-commits

The external Skills registry query for “concise operator inspection information hierarchy” and then “information hierarchy” produced no output and did not exit within a bounded 60 seconds; both processes were terminated. This prevented comparing third-party Skill packages, but did not block implementation because the installed operator-interface catalog and official Carbon/VS Code material covered the decision. Retry only when the Skills CLI/registry responds.
