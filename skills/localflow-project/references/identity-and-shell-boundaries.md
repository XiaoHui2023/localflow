# Persistent identity and adaptive Shell boundaries

Use this topic for repeated browser login, multi-server access, secret rotation, or commands that rely on `.bashrc`, `.cshrc`, `.zshrc`, `config.fish`, aliases, or Shell functions.

## Browser session model

- `secrets/web-admin-key` is create-once state. Starting LocalFlow, finishing a task, or changing ports never rotates it. An owner explicitly replacing the file revokes all signed browser sessions.
- Default to a host-only `HttpOnly; SameSite=Strict` persistent cookie. Cookies ignore ports, so the same hostname survives a random-port restart without broadening host authority.
- Cross-server reuse is opt-in through one dedicated parent DNS domain. Every trusted sibling uses the identical key and `server.session_cookie_domain`; requests must be HTTPS and inside that domain, and cookies are always Secure.
- A shared Domain cookie makes every included sibling part of one administrator trust boundary. Never use a public suffix, mixed-trust parent, raw IP fleet, localStorage, or a browser-stored administrator key. Prefer one stable reverse-proxy hostname when available.

## Shell selection model

- String commands are intentionally personalized. Select `$SHELL` when the service manager propagated it; otherwise read the effective user's passwd login Shell; use `/bin/sh` only as the final fallback. Reject `false` and `nologin` as launch choices.
- Invoke the selected program with `-ic`, which is the common interface for bash, zsh, csh/tcsh, fish, and common POSIX-derived Shells. Explicit `shell` remains an escape hatch for unusual service deployments.
- Exact argv lists never enter a Shell and never load startup configuration.
- The Shell startup file may change directories. Prefix the actual command with a safely quoted `cd` to the frozen absolute task directory after startup completes.
- Show the selected Shell in run inspection and freeze it in the task argv. A plugin never guesses, sources rc files itself, or owns this policy.

## Regression corpus

Linux tests create isolated HOME directories with real `.bashrc` and `.cshrc` aliases, both of which deliberately `cd` to the LocalFlow root. Omitting the plugin `shell` field must still select the test user's Shell, expand the shortcut, write only below the configured external directory, and leave no root-side marker. Model tests cover bash and tcsh command shapes plus exact-argv rejection.

## References

- RFC 6265 Domain, host-only, Secure, HttpOnly, persistence, and port caveats: https://www.rfc-editor.org/rfc/rfc6265.html
- Bash startup files: https://www.gnu.org/software/bash/manual/html_node/Bash-Startup-Files
- Bash alias behavior: https://www.gnu.org/software/bash/manual/html_node/Aliases.html
- zsh startup files: https://zsh.sourceforge.io/Doc/Release/Files.html
- fish configuration: https://fishshell.com/docs/current/index.html#configuration
- POSIX passwd `pw_shell`: https://man7.org/linux/man-pages/man0/pwd.h.0p.html
