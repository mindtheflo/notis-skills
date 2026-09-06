## Canonical Notis Profile And State Persistence

Notis browser automation always uses **one shared persistent profile** and
**always saves session state at the end of the run**. Do not invent per-task
profiles; do not skip the final save.

Canonical paths:

- Profile directory: `~/.notis-agent-browser/main`
- Session state file: `~/.notis-agent-browser/<site>-state.json`
  (one per site, e.g. `linkedin-state.json`, `gmail-state.json`)

Mandatory rules:

1. Pass `--profile ~/.notis-agent-browser/main` on **every** `agent-browser`
   invocation. The daemon may restart between commands; without the flag a
   fresh daemon falls back to a different empty profile and the user appears
   signed out.
2. When the user must sign in, use `--headed` so they can see the window.
3. As soon as the user confirms login, **immediately** run
   `agent-browser state save ~/.notis-agent-browser/<site>-state.json`.
   Chrome writes cookies asynchronously; closing the window or letting the
   daemon exit can race the on-disk flush and lose the session. The state
   file is a synchronous snapshot that does not depend on Chrome's shutdown.
4. At the **end of every automation run**, before `agent-browser close`,
   run `agent-browser state save ~/.notis-agent-browser/<site>-state.json`
   again to capture any rotated cookies or new login state.
5. If a future run lands on a login page despite the profile existing,
   `agent-browser state load ~/.notis-agent-browser/<site>-state.json`
   before retrying the URL.

Canonical login flow:

```bash
agent-browser close --all
agent-browser --headed --profile ~/.notis-agent-browser/main open https://www.example.com/login
# user signs in inside the headed window, then confirms
agent-browser --profile ~/.notis-agent-browser/main state save ~/.notis-agent-browser/example-state.json
```

Canonical run flow (already signed in):

```bash
agent-browser --profile ~/.notis-agent-browser/main open https://www.example.com/dashboard
agent-browser --profile ~/.notis-agent-browser/main snapshot -i
# ...interact with the page...
agent-browser --profile ~/.notis-agent-browser/main state save ~/.notis-agent-browser/example-state.json
```

State recovery flow (profile exists but session looks logged out):

```bash
agent-browser --profile ~/.notis-agent-browser/main open https://www.example.com/
agent-browser --profile ~/.notis-agent-browser/main state load ~/.notis-agent-browser/example-state.json
agent-browser --profile ~/.notis-agent-browser/main open https://www.example.com/dashboard
```

Treat `~/.notis-agent-browser/` as credential material. Never commit it,
never copy it out of the user's machine, and never write secrets into the
shell history (use the auth vault for credential-based login).

### 1Password Service Account Fallback

When the same site needs to be reached from both `local_shell` and
`sandbox_shell`, the persistent Notis profile only covers the local side —
the sandbox starts cookie-empty on every run. The portable option is the
**1Password Service Account** (`op` CLI with `OP_SERVICE_ACCOUNT_TOKEN`).

Flow:

```bash
# Token is provided via env, never written to disk in plaintext.
export OP_SERVICE_ACCOUNT_TOKEN=...
EMAIL=$(op read "op://Notis/example.com/username")
PASSWORD=$(op read "op://Notis/example.com/password")

agent-browser --profile ~/.notis-agent-browser/main open https://www.example.com/login
agent-browser --profile ~/.notis-agent-browser/main fill 'input[name=email]' "$EMAIL"
agent-browser --profile ~/.notis-agent-browser/main fill 'input[name=password]' "$PASSWORD"
agent-browser --profile ~/.notis-agent-browser/main click 'button[type=submit]'
agent-browser --profile ~/.notis-agent-browser/main wait --load networkidle
agent-browser --profile ~/.notis-agent-browser/main state save ~/.notis-agent-browser/example-state.json
```

This works identically in `local_shell` and `sandbox_shell`. The service
account scope should be narrowed to the specific vault Notis needs.
