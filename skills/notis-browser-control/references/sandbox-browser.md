## Sandbox Shell Browser Control

Use this when the browser should run in the Vercel Sandbox.

Sandbox browser control is isolated. It cannot access the user's local Chrome
profiles, cookies, browser tabs, extensions, host keychain, or desktop UI. Do
not run `agent-browser profiles` in sandbox and do not search for the user's
main browser profile there.

### Basic Sandbox Session

The sandbox uses the same canonical profile name (`main`), even though the
sandbox is isolated and starts empty on every run:

```bash
npm exec --yes --package agent-browser@latest -- agent-browser install
npm exec --yes --package agent-browser@latest -- agent-browser skills get core --full
npm exec --yes --package agent-browser@latest -- agent-browser --profile ~/.notis-agent-browser/main open https://example.com
npm exec --yes --package agent-browser@latest -- agent-browser --profile ~/.notis-agent-browser/main snapshot -i
```

Use sandbox sessions for:

- public pages
- pages with provided test credentials
- repeatable QA
- screenshots
- scraping
- app testing

### Sandbox Auth

The sandbox cannot reuse the user's local browser profile. For Notis itself,
use the existing sign-in-link tool through native tools or the authenticated
Notis CLI; follow the reading guide under the Notis Apps skill (hosted guide:
`notis://docs/notis-apps/references/reading.md`). No local cookies, password vault,
or user-opened Portal session is needed for that flow.

For other sites, use one of these:

- The **1Password Service Account** flow described above. This is the
  preferred path because it works in both runtimes and keeps credentials
  out of disk and shell history.
- A saved Agent Browser state file the user explicitly provisioned for
  sandbox use (uploaded into the sandbox at run start).
- Dedicated test credentials provided per task.

Always save state at the end of the sandbox run too, so subsequent steps
in the same sandbox lifecycle can reuse it:

```bash
npm exec --yes --package agent-browser@latest -- agent-browser --profile ~/.notis-agent-browser/main state save ~/.notis-agent-browser/<site>-state.json
```

Never assume the sandbox can see the user's local auth state.

### Vercel Sandbox Implementation Work

If the task is specifically about implementing browser automation inside app
code, load:

```bash
agent-browser skills get vercel-sandbox --full
```

Then follow the Vercel Sandbox pattern with `@vercel/sandbox`, optional sandbox
snapshots, and in-sandbox `agent-browser` commands.
