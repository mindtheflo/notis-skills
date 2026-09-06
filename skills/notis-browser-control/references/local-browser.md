## Local Shell Browser Control

Use this when the browser must run on the user's computer.

### Local Shell Setup

```bash
command -v agent-browser >/dev/null 2>&1 || npm i -g agent-browser
agent-browser install
agent-browser skills get core --full
```

### Authenticated Sites

Always use the canonical Notis profile and state file (see
[Canonical Notis Profile And State Persistence](profile-and-state.md)).
Do **not** copy the user's main Chrome profile and do **not** drive their
real signed-in browser session.

1. `agent-browser close --all`
2. `agent-browser --headed --profile ~/.notis-agent-browser/main open <login-url>`
3. Wait for the user to sign in inside that window.
4. Immediately save state to `~/.notis-agent-browser/<site>-state.json`.
5. Continue the task with `--profile ~/.notis-agent-browser/main`.
6. At the end of the run, save state again before closing.

If the user has previously signed in but the profile now lands on login
(rare; usually means the cookies expired), reuse the saved state file:

```bash
agent-browser --profile ~/.notis-agent-browser/main state load ~/.notis-agent-browser/<site>-state.json
```

If both the profile and state file are empty for a site, ask the user to
sign in once. Do not try to read the user's main Chrome profile as a
fallback.

### Why Not The User's Main Chrome Profile

- Chrome 136+ no longer honors `--remote-debugging-port` against the default
  data dir; CDP requires a separate `--user-data-dir`.
- Driving the user's real signed-in browser risks corrupting tabs, state,
  and extensions they actively use.
- Login bot detection on sites like LinkedIn is more aggressive when an
  automated client touches the user's primary session.

The canonical Notis profile is isolated, persistent, and reusable across
runs — that is the supported path.
