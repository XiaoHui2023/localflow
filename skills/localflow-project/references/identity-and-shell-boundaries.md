# Persistent identity and adaptive Shell boundaries

Use this topic for repeated browser login, multi-server access, secret rotation, or commands that rely on `.bashrc`, `.cshrc`, `.zshrc`, `config.fish`, aliases, or Shell functions.

## Browser session model

- `secrets/web-admin-key` is create-once state. Starting LocalFlow, finishing a task, or changing ports never rotates it. An owner explicitly replacing the file revokes all signed browser sessions.
- Secret modes are initialization defaults, not a runtime policy engine. Set a newly created directory to `0700` and a newly created key to `0600`; on later starts, do not audit, repair, reject, or regenerate because an operator changed owner/mode. Preserve the existing API-key mode across its required atomic content rotations.
- Default to a host-only `HttpOnly; SameSite=Strict` persistent cookie. Cookies ignore ports, so the same hostname survives a random-port restart without broadening host authority.
- Cross-server reuse is opt-in through one dedicated parent DNS domain. Every trusted sibling uses the identical key and `server.session_cookie_domain`; requests must be HTTPS and inside that domain, and cookies are always Secure.
- A shared Domain cookie makes every included sibling part of one administrator trust boundary. Never use a public suffix, mixed-trust parent, raw IP fleet, localStorage, or a browser-stored administrator key. Prefer one stable reverse-proxy hostname when available.

## Shell selection model

- String commands are intentionally personalized. Select `$SHELL` when the service manager propagated it; otherwise read the effective user's passwd login Shell; use `/bin/sh` only as the final fallback. Reject `false` and `nologin` as launch choices.
- Invoke the selected program with `-ic`, which is the common interface for bash, zsh, csh/tcsh, fish, and common POSIX-derived Shells. Explicit `shell` remains an escape hatch for unusual service deployments.
- Treat explicit task environment setup as a common execution concern, not plugin logic. `source` is strictly an ordered, non-empty list of script path strings; reject scalar strings, pasted statements, mappings, empty lists and mixed entries during configuration/API validation. Resolve relative paths against the frozen task working directory, safely quote spaces, load every item in the selected task Shell, restore the frozen cwd after the list, and run the exact user command only after every item succeeds. Preserve duplicates because sourcing the same script twice can be intentional. Never guess tool-specific arguments or mutate the controller `os.environ`: put vendor arguments in a user-owned wrapper script and process inheritance then guarantees one task cannot leak sourced variables into another.
- Do not infer a different interpreter from a source file extension or shebang. Sourcing must happen in one parent task Shell so environment variables, functions and aliases persist into later list items and the command. Mixed Shell languages therefore require separate tasks or a wrapper written for the selected Shell; launching child Shells would falsely appear to work while losing their environment on return.
- Exact argv lists never enter a Shell and never load startup configuration.
- The Shell startup file may change directories. Prefix the actual command with a safely quoted `cd` to the frozen absolute task directory after startup completes.
- Freeze the selected Shell in the task argv but keep this executor mechanism out of the concise run inspection. A plugin never guesses, sources rc files itself, or owns this policy.

## Regression corpus

Linux tests create isolated HOME directories with real `.bashrc` and `.cshrc` aliases, both of which deliberately `cd` to the LocalFlow root. Omitting the plugin `shell` field must still select the test user's Shell, expand the shortcut, write only below the configured external directory, and leave no root-side marker. Model tests cover bash and tcsh command shapes plus exact-argv rejection.

Source coverage adds ordered multi-file bash, POSIX sh and tcsh scripts, proves values from earlier files remain visible to later files and the command, covers relative/absolute/space/symlink paths, restores cwd after a script changes it, fails closed on a missing or failed file, and runs an unsourced task beside a sourced one to prove environment isolation. A wrapper-script case exercises a vendor-style argument without expanding the public contract. Contract tests reject scalar strings, complete statements, mappings, empty lists and mixed entries before submission. Common plugin expansion tests cover both command and verification so a plugin cannot accidentally omit the host field. Inspection and task-detail tests require every frozen path as its own code-list item and preflight each path. Terminal history records each path before `process.command`. Task command presentation strips host cwd/source wrappers and retains exactly the configured command.

## References

- RFC 6265 Domain, host-only, Secure, HttpOnly, persistence, and port caveats: https://www.rfc-editor.org/rfc/rfc6265.html
- Bash startup files: https://www.gnu.org/software/bash/manual/html_node/Bash-Startup-Files
- Bash alias behavior: https://www.gnu.org/software/bash/manual/html_node/Aliases.html
- zsh startup files: https://zsh.sourceforge.io/Doc/Release/Files.html
- fish configuration: https://fishshell.com/docs/current/index.html#configuration
- POSIX passwd `pw_shell`: https://man7.org/linux/man-pages/man0/pwd.h.0p.html
