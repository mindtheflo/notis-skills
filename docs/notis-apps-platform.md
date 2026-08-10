# Notis Development Workflow And Apps Platform

This is the canonical reference for local Notis development and the Notis Apps platform: repo setup, environment files, dev-stack discovery, branch/release policy, what a Notis App is, how the platform works, every way a user can create and edit apps, and the architectural rules that matter when building, debugging, or documenting apps.

Use this together with [server/skills/notis-apps/SKILL.md](../server/skills/notis-apps/SKILL.md):
- this document explains the platform model, contracts, and all creation/editing paths
- the skill explains the execution workflow for using the CLI

### Tool boundaries

Two surfaces, two responsibilities. Each one keeps its lane — see [Publishing to the Public App Store](#publishing-to-the-public-app-store) and [CLI Command Reference](#cli-command-reference) for the full contract.

| Action | CLI | Portal |
|---|---|---|
| Scaffold a new app, pull source from another app, dev, build, verify, deploy | ✅ | ❌ |
| Edit listing metadata + media (screenshots, tagline, category) | ✅ (edit `notis.config.ts` + `metadata/`) | ❌ |
| Install or update a mounted local-dev snapshot into the user's workspace | ✅ | ✅ (Local development action) |
| Publish or Update a store listing (Team or Public) | ✅ after explicit confirmation (`apps publish --confirm-ready`) | ✅ (App Details → Publish/Update) |
| Unpublish a listing | ❌ | ✅ |

---

## Table of Contents

1. [What A Notis App Is](#what-a-notis-app-is)
2. [Core Platform Model](#core-platform-model)
3. [Architecture](#architecture)
4. [Repository Development Workflow](#repository-development-workflow)
5. [Creating Apps](#creating-apps)
   - [Path 1: Build with Notis (chat / Vercel sandbox)](#path-1-build-with-notis-chat--vercel-sandbox)
   - [Path 2: Build with your local code agent (Cursor, Claude Code, terminal)](#path-2-build-with-your-local-code-agent-cursor-claude-code-terminal)
   - [Forking an existing app](#forking-an-existing-app)
   - [Other entry points](#other-entry-points)
6. [Editing an Existing App](#editing-an-existing-app)
7. [Publishing to the Public App Store](#publishing-to-the-public-app-store)
8. [App Contract](#app-contract)
9. [Main Components](#main-components)
10. [Runtime Bridge](#runtime-bridge)
11. [Data Model](#data-model)
12. [Rendering Model](#rendering-model)
13. [App Structure Reference](#app-structure-reference)
14. [SDK Reference](#sdk-reference)
15. [CLI Command Reference](#cli-command-reference)
16. [Notis Apps Local Development](#notis-apps-local-development)
17. [Design Guidelines](#design-guidelines)
18. [Non-Negotiable Invariants](#non-negotiable-invariants)
19. [Where To Look In The Repo](#where-to-look-in-the-repo)
20. [Agent Guidance](#agent-guidance)

---

## What A Notis App Is

A Notis App is the top-level packaging unit for a product experience inside Notis.

A Notis App:
- is authored as a standard **Vite + React** project using `@notis/sdk`
- is built as an **ES module bundle** (app.js + app.css) via Vite library mode
- is installed into the **Notis Portal** and rendered as a **React component** directly in the portal's React tree
- communicates with the platform through generic SDK hooks (`useTool`, `useTools`, etc.) backed by a `NotisRuntime` provided via React context
- can reference **databases**, package **views/routes**, and work with **documents**
- can bundle **skills** and **automations** by reference

Every native database is **owned by exactly one app** (`databases.owner_app_id`,
enforced NOT NULL with an `ON DELETE CASCADE` foreign key to `apps`). Creating a
database through `LOCAL_NOTIS_DATABASE_UPSERT_DATABASE` requires the owning
app's slug or id in the `app` argument; app install/materialization stamps
ownership automatically. App detail includes both databases declared by the
source manifest and databases created interactively for that app. Deleting an
app deletes its databases and their documents. Team/Public publication
snapshots remain manifest-only: interactive runtime databases and their
documents are never copied into a store listing.

The right mental model is:

```
Vite + React project + notis.config.ts + ES module bundle + SDK hooks + installed app record
```

### What an app contains

| Component | Description |
|-----------|-------------|
| `notis.config.ts` | Declarative config: app metadata, database slug refs, routes, tool access |
| `app/` directory | React pages (the UI) |
| `components/` | shadcn UI components (scaffolded) |
| `vite.config.ts` | Vite config wrapped with `notisViteConfig()` |
| `.notis/output/` | Built artifact: manifest.json + bundle/app.js + bundle/app.css |

---

## Core Platform Model

Notis Apps are intentionally a frontend-product platform centered on a standard Vite + React project.

### Subscription entitlement

Portal app routes keep the consumer-to-builder entitlement ladder:
`prices.apps` controls installation/runtime (PRO and above), while
`prices.apps_builder` controls Portal source/build/publish workflows (PRO+ and
above). CLI-only app source/build commands outside the reviewed native-tool
matrix also use the central developer entitlement and canonical upgrade
response.

Reviewed native App/database tools are different: they declare PostHog `store`
for visibility and no App/database plan entitlement. Once their surface allows
them and `store` resolves true, they execute without a second App gate. Skills,
automations, and Cloud Computer work invoked during an app workflow still
enforce their own central entitlements.

After PostHog resolves `store=true`, the Portal may use an active team
relationship to scope Team Store listings. A team relationship never overrides
a false, missing, or unavailable PostHog decision for Store UI, tools, or
skills.

| App action / Notis tool | Minimum plan | Denied response |
| --- | --- | --- |
| Browse Store and inspect listings | Signed-in user | No billing gate |
| Install and run apps | PRO | `apps_upgrade_required`, `capability=apps_runtime`, `required_plan=PRO` |
| Reviewed native App/database tools | No App entitlement | Hidden unless surface + PostHog `store` allow them |
| Six native skill-management tools | PRO+ | Canonical `skills` entitlement response |
| Nine native automation-management tools | PRO+ | Canonical `automations` entitlement response |
| Cloud Computer shell/files | PRO+ | Canonical `cloud_computer` entitlement response |
| Portal source/build/publish workflows | PRO+ | Canonical app-builder/publishing response |
| CLI-only app source/build commands | PRO+ | Canonical developer-entitlement response |

PRO installs the app UI, routes, databases, and starter documents. Premium
bundled skills and automations remain pending and the response reports their
counts; onboarding opens with a persistent PRO+ ribbon instead of failing
before the chat appears. After an upgrade, the first PRO+ onboarding explicitly
activates those pending assets, maps them to installer-owned IDs, and refreshes
the Store-install baseline without treating activation as a customization.
PRO+ installs the same app with those resources active from the start.
Duplicating a source app remains a PRO runtime action when it contains only UI,
database structure, and starter rows. If duplication would materialize bundled
skills or automations, the backend requires PRO+ before creating any copy; it
never bypasses the normal resource entitlement by cloning them directly.

Trials mirror the selected plan. After a downgrade, installed apps and their
data stay available on PRO while builder actions are locked. Cleanup actions
such as unpublish, withdraw, reset, and delete remain available. Never delete
app-owned data as a subscription side effect.

When the PostHog `store` flag is false, missing, or unavailable, the Portal
hides Store and installed app surfaces, direct Store/App routes redirect to
Manager, and Manager neither loads nor accepts database/app/view mentions.
Active team members and owners follow the same visibility boundary. Their team
relationship scopes shared content only after PostHog resolves `store=true`.

The canonical flow is:

1. The app is created or updated using the Notis CLI.
2. The app declares metadata, database slug refs, routes, and tool access in `notis.config.ts`.
3. The app is built as an ES module bundle with a generated `manifest.json`.
4. The bundle is saved to platform storage and associated with the app record on the Python backend.
5. The Portal dynamically imports the bundle and renders the app's route components directly in its own React tree.
6. The portal provides a `NotisRuntime` via React context so the app's SDK hooks can query databases and call approved tools.

---

## Architecture

```text
Notis CLI (local workspace or Vercel Sandbox)
  -> notis.config.ts + app/ + @notis/sdk
  -> notis apps init / build / create / link / deploy
  -> .notis/output/ (bundle/app.js + bundle/app.css + manifest.json)

Bundle + platform
  -> /cli_tools (upload bundle)
  -> Supabase Storage app-code/{app_id}/v{version}/
  -> Supabase Storage app-source/{app_id}/v{version}/
  -> apps table manifest/current_version update
  -> /portal_views/get (returns signed bundle URLs)
  -> Portal dynamically imports bundle
  -> Renders as React component with NotisRuntime context
  -> /portal_views/runtime_query (database ops, tool calls)
```

All Notis apps are built using the Notis CLI. The CLI runs either locally in a repo workspace or inside a Vercel Sandbox. The platform contract is the same regardless of where the CLI runs:
- the agent edits files directly in the workspace
- the agent uses the Notis CLI
- build, develop, create, link, and deploy happen through CLI commands

---

## Repository Development Workflow

This section covers local repo setup, environment files, dev-stack discovery, and branch/release policy.

### Canonical setup

1. Run `./setup.sh`.
   This links the available `server/.env`, `portal/.env`, and `website/.env` files independently from the main checkout or another local worktree. Missing env files produce warnings without blocking setup, which is expected in Cloud Agent VMs. It then creates the Python virtual environment, installs server pip dependencies, and runs `npm install` in `portal`, `server/node-server`, `electron`, `website`, and `packages/cli`.
2. Create `.env` files.
3. Run `./dev.sh`.
   This starts the Python backend, Next.js portal, and collaboration node-server in parallel with labeled log output.

The full live terminal stream is written to `.context/terminal.txt`. The file is cleared on every `dev.sh` launch and deleted by `./archive.sh`.

`dev.sh` stops itself after 30 minutes without activity. App development that parks the stack without traffic should run `./dev.sh --no-idle-timeout` or keep a `touch .context/dev-activity` keepalive; see the Idle Shutdown section in `docs/development-workflow.md`.

### Environment files

`.env` files are not committed. In Cloud Agent VMs, generate them from injected environment variables.

Required secrets:

- `SUPABASE_SUBDOMAIN`
- `SUPABASE_SERVICE_KEY`
- `SUPABASE_ANON_KEY`
- `OPENAI_API_KEY`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `STRIPE_SECRET_KEY`
- `NOTIS_STRIPE_TEST_API_KEY`
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`

Stripe key convention:

- `ENV=dev` uses `NOTIS_STRIPE_TEST_API_KEY`, falling back to `STRIPE_SECRET_KEY` if unset.
- `ENV=beta`, `ENV=prod`, or unset uses `STRIPE_SECRET_KEY`.
- `server/lib/user_creation.py:_get_stripe_api_key()` is the canonical implementation.

`server/.env` must include:

- `ENV=dev`
- `PORT=3001`
- `DOMAIN_WEB_SERVER` pointing to the server origin on port 3001
- `DOMAIN_PORTAL` pointing to the portal origin on port 3000

Remove hardcoded `VERCEL_SANDBOX_BRIDGE_URL`; `dev.sh` clears it during local runs so the backend always uses the portal bridge. `VERCEL_TOKEN`, `VERCEL_TEAM_ID`, and `VERCEL_PROJECT_ID` can still live in `server/.env` so the portal bridge can resolve Vercel auth from repo env files during local development.

`portal/.env` must include:

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `NEXT_PUBLIC_SERVER_URL`
- `NEXT_PUBLIC_APP_URL`
- `STRIPE_SECRET_KEY`
- `SUPABASE_SERVICE_KEY`

If running `server/node-server` manually, its `.env` needs `ENV=dev`, `NODE_PORT=8080`, and standard Supabase envs inherited from `server/.env`.

### Dev stack

`./dev.sh` starts:

- Python backend
- Next.js portal
- collaboration node-server from `server/node-server`

The node-server inherits `server/.env`. `dev.sh` derives `NODE_SERVER_PORT` as `PORTAL_PORT + 4` by default, so it defaults to port 3004 when the portal is on 3000, kills any existing process already bound to that worktree port, and passes the resulting value as `NODE_PORT`.

For local sandbox work, the backend is pointed at `http://localhost:<portal_port>/api/sandbox`.

If you need to run the node-server manually:

```bash
cd server/node-server
node node-server.js
```

### Dynamic ports and auth links

Ports are dynamic inside Conductor. `dev.sh` prints active URLs at startup and writes them to `.context/terminal.txt`.

Expected startup lines include:

```text
Portal:  http://localhost:<portal_port>
Backend: http://localhost:<backend_port>
Node server: http://localhost:<node_server_port>
Electron webpack: http://localhost:<electron_webpack_port>
Electron logger:  http://localhost:<electron_logger_port>
Sandbox bridge: http://localhost:<portal_port>/api/sandbox
Portal entry link:
parisetflorian+dev@gmail.com:
http://localhost:<portal_port>/auth/confirm?redirect=%2Fmanage&token_hash=<DEV_MAGIC_LINK_TOKEN_HASH>&type=email
<optional secondary email when DEV_PERSONAL_USER_ID and DEV_PERSONAL_USER_EMAIL are set>:
http://localhost:<portal_port>/auth/confirm?redirect=%2Fmanage&token_hash=<SECONDARY_MAGIC_LINK_TOKEN_HASH>&type=email
```

Use `.context/terminal.txt` as the canonical source for:

- current portal URL
- current backend URL
- current node-server URL
- current sandbox bridge URL
- live server tail while debugging startup failures, backend exceptions, frontend build issues, or runtime errors

Auth-link files:

- `.context/portal-entry-link.txt` - latest scanner-safe Portal token-hash link for `parisetflorian+dev@gmail.com`.
- `.context/electron-dev-login-url.txt` - latest pre-consumed `/auth/confirm` session URL for Electron. By default this uses `parisetflorian+dev@gmail.com`; `./dev.sh --electron-user-id <id> --electron-user-email <email>` can select another Electron login user.
- `.context/dev-portal-auth.json` - structured dev-user payload with both URLs and metadata.

When `DEV_PERSONAL_USER_ID` and `DEV_PERSONAL_USER_EMAIL` are set, `dev.sh` also prints a second browser magic link in the terminal log.

The auth-link helper does not start the app. Start the local dev stack with `./dev.sh` first.

Useful commands:

```bash
grep -m1 '^Portal:' .context/terminal.txt
grep -m1 '^Backend:' .context/terminal.txt
grep -m1 '^Node server:' .context/terminal.txt
grep -m1 '^Electron webpack:' .context/terminal.txt
grep -m1 '^Electron logger:' .context/terminal.txt
grep -m1 '^Sandbox bridge:' .context/terminal.txt
cat .context/portal-entry-link.txt
cat .context/electron-dev-login-url.txt
cat .context/dev-portal-auth.json
./dev.sh --refresh-portal-entry-link
./dev.sh --electron-user-id <id> --electron-user-email <email>
./dev.sh --restart-running-dev-session
tail -n 200 .context/terminal.txt
```

`./dev.sh --refresh-portal-entry-link` only refreshes the one-time link. It does not boot the app.

`DEV_PERSONAL_USER_ID=<id> DEV_PERSONAL_USER_EMAIL=<email> ./dev.sh --refresh-portal-entry-link` prints an optional second browser magic link without hardcoding a personal account in the repo.

`./dev.sh --electron-user-id <id> --electron-user-email <email>` starts the Electron app logged in as that user.

`./dev.sh --restart-running-dev-session` stops the tracked workspace dev session and restarts the stack in place with the same startup flags. The command becomes the new long-lived dev session.

Port derivation fallback:

- If `CONDUCTOR_PORT` is set: portal = `CONDUCTOR_PORT`, backend = `CONDUCTOR_PORT + 1`.
- Otherwise: portal = 3000, backend = 3001.
- Node server defaults to `PORTAL_PORT + 4`.

Use `CONDUCTOR_PORT` only as a fallback when `.context/terminal.txt` is unavailable.

### Branch and release policy

Production hotfixes:

```text
production -> hotfix/... -> production
```

Backports:

```text
production hotfix commit(s) -> cherry-pick onto beta
```

Normal releases:

```text
beta -> production PR
```

Rules:

- Branch urgent production fixes from `production`, never from `beta`.
- Merge and deploy the hotfix to `production` first.
- Backport the merged production hotfix commit or commits into `beta`, usually with `git cherry-pick`.
- If `beta` has refactored the touched area, prefer a small manual re-apply on a `beta` branch instead of forcing a messy cherry-pick.
- Keep normal release promotion as a reviewed `beta -> production` pull request.
- Do not use `beta` as the source branch for production hotfixes.

---

## Creating Apps

There is **one entry point** and **two paths**.

The entry point is the **Create app wizard**, opened from the `+ Create app` button in the App Store (`/store`) or the `+` shortcut next to the Store row in the sidebar's Customize section. The wizard asks two questions:

1. **What do you want to build?** A name and (optional) starting point.
2. **Who builds it?** *Notis* or *your local code agent*.

The starting point can be:

- **Empty scaffold** — bare Vite + React project with `@notis/sdk`.
- **A scaffold from the bundled catalog** — every app in `scaffolds/` becomes a scaffold automatically when the CLI is built. The generated `packages/cli/dist/scaffolds/` output is a package artifact, not committed source. Local monorepo CLI runs fall back to reading `scaffolds/` directly when that artifact has not been generated. The wizard, the CLI's `notis apps init --from <slug>`, and the Notis-sandbox skill all read from the same catalog shape (today: `notis-database`, `notis-journal`, `notis-notes`, `notis-random`).

Both paths produce the same thing: a Vite + React app installed into the Portal and rendered as a React component. They differ only in *where the CLI runs*.

> Pulling source directly from a Store listing — picking any published app as a scaffold — is not supported. The wizard only exposes the bundled scaffolds. To start from an existing listing, install it first, then use the CLI to run `notis apps pull <app-id>` from your own installed copy. The Portal never downloads app source. See [Forking an existing app](#forking-an-existing-app).

### Path 1: Build with Notis (chat / Vercel sandbox)

The simplest way to create an app. The wizard sends your request to the Notis assistant, which builds the app for you in a Vercel sandbox using the authenticated CLI.

#### How it works

1. **The wizard sends your prompt** to the Notis assistant when you click *Open Notis chat*.
2. **The orchestrator** triages your request and routes it to the app-building agent.
3. **A sandbox session** is created for you (one persistent sandbox per user, reused across turns). The CLI is pre-authenticated through `NOTIS_JWT`.
4. **The agent builds the app** inside the sandbox, choosing the right starting point:
   - Lists bundled scaffolds with `notis apps scaffolds list`, then runs `notis apps init <name> --from <slug>` when one fits, OR
   - Runs plain `notis apps init <name>` for the empty scaffold, OR
   - Pulls source from one of the user's already installed apps with `notis apps pull <app-id>`.
5. **The agent fills in `notis.config.ts`** including manifest listing metadata (tagline and categories), writes the root `CHANGELOG.md`, and runs `notis apps screenshot` to generate `metadata/screenshot-N.png` so it's ready for publish later.
6. **The agent verifies and deploys** with `notis apps build`, `notis apps verify`, `notis apps deploy`. In this hosted path the sandbox has no desktop **Local development** session, so deploying to your Portal is the only way to preview — that is why deploy is part of the flow here. (Contrast with **Path 2**, where a local desktop dev session exists, deploy is user-gated, and the agent hands off for you to test in Local development first.)
7. **You see progress** in real time and can refine requirements conversationally.
8. **The app appears** in your Portal, ready to use.

#### What you can ask

- _"Build me a CRM app"_
- _"Create a project tracker with tasks and deadlines"_
- _"Add a new database called clients to my CRM app"_
- _"Change the dashboard layout to show a table instead of cards"_
- _"Add a route for analytics"_

#### What happens under the hood

```
User message
  -> Orchestrator triage
  -> App-building agent spawned
  -> Vercel Sandbox session (persistent per user)
  -> Agent runs Notis CLI commands in sandbox
  -> App created, built, and deployed
  -> Visible in Portal
```

The agent has access to:

- **App tools**: `create_app`, `update_app`, `list_apps`, `get_app`
- **Shell tool**: Runs CLI commands in the sandbox (init, build, deploy, etc.)
- **Skills**: The `notis-apps` skill provides the agent with platform knowledge

#### Iterating on your app

The sandbox persists across conversation turns. You can:

- Ask for changes and the agent will modify the code and redeploy
- Request new databases, routes, or features
- Ask the agent to fix bugs or change the design
- Switch to a different app in the same conversation

---

### Path 2: Build with your local code agent (Cursor, Claude Code, terminal)

For developers — or their local agent — who want full control over the code. You work in your local editor, use the CLI to scaffold or pull an existing app, develop, build, verify, and deploy. The Notis CLI ships with the desktop app, pre-authenticated for the logged-in user.

The wizard's *Get the prompt* button generates a copy-paste prompt tuned for your selected starting point, so the agent runs the right `notis apps init --from <slug>` or plain `notis apps init` command and then walks you through the code. You can also drive the CLI by hand.

Use [Notis Apps Local Development](#notis-apps-local-development) as the acceptance spec for the Portal-side development experience.

#### Setup

Install the Notis desktop app and sign in. Desktop writes the authenticated CLI profile; run the CLI through NPX, for example `npx --package @notis_ai/cli@latest -- notis apps list`.

Verify your setup:

```bash
notis doctor
notis whoami
```

#### Full workflow

##### Step 1: Scaffold a new app

```bash
notis apps scaffolds list
notis apps init "My Task Manager" --from notis-database
```

This creates a Vite + React project with:
- `notis.config.ts` (app declaration)
- `CHANGELOG.md` (editable Store release history)
- `vite.config.ts` (with `notisViteConfig()` wrapper)
- `app/` directory (pages)
- `components/` (scaffolded shadcn components)
- Tailwind CSS pre-configured
- `@notis/sdk` installed

##### Step 2: Define your app config

Edit `notis.config.ts`:

```typescript
import { defineNotisApp } from '@notis/sdk/config';

export default defineNotisApp({
  name: 'task-manager',
  title: 'Task Manager',
  description: 'Track and manage team tasks',
  icon: 'phosphor:check-square',
  categories: ['Productivity'],
  tagline: 'Plan, assign, and ship team tasks.',

  databases: ['tasks'],

  routes: [
    {
      path: '/',
      slug: 'dashboard',
      name: 'Dashboard',
      icon: 'phosphor:squares-four',
      default: true,
    },
    {
      path: '/tasks',
      slug: 'tasks',
      name: 'All Tasks',
      icon: 'phosphor:list',
      collection: {
        database: 'tasks',
        titleProperty: 'title',
      },
    },
  ],

  tools: [
    'LOCAL_NOTIS_DATABASE_QUERY',
  ],
});
```

##### Read-only database catalog apps

A database catalog is a normal installable Notis App. Declare the canonical read-only tools explicitly, keep database-specific TypeScript shapes inside the app, and call them through generic `useTool<TArgs, TResult>()`:

```typescript
tools: [
  'LOCAL_NOTIS_DATABASE_LIST_DATABASES',
  'LOCAL_NOTIS_DATABASE_GET_DATABASE',
],
```

Use `LOCAL_NOTIS_DATABASE_LIST_DATABASES` for the catalog/list pane and `LOCAL_NOTIS_DATABASE_GET_DATABASE` for the selected database detail pane.

##### Route-first sidebar trees

Routes are the only canonical navigation contract for Notis apps. Every configured route must declare an explicit `slug`, and nested static navigation uses `parentSlug`.

To model Notes-style sidebars where the portal shows a static route row and injects live collections/sub-collections beneath it, declare the collection on the route itself:

```typescript
routes: [
  {
    path: '/',
    slug: 'notes',
    name: 'Notes',
    icon: 'phosphor:note-pencil',
    default: true,
    collection: {
      database: 'notes',
      titleProperty: 'Title',
      parentProperty: 'Parent note',
      sidebar: {
        mode: 'tree',
        allowCreate: true,
      },
    },
  },
]
```

Rules:
- `collection.sidebar.mode === 'tree'` requires `parentProperty`.
- `parentProperty` must be a self-relation on the bound database.
- Root collection rows store an empty relation array.
- Child collection rows store `[parent_item_id]`.
- Tree collection routes cannot also have static child routes in v1.

##### Step 3: Build your pages

Create pages in `app/` using SDK hooks and scaffolded components:

```tsx
// app/page.tsx
'use client';
import { useEffect, useState } from 'react';
import { useTool } from '@notis/sdk';
import { Card } from '@/components/ui/card';

type QueryTasksArgs = { database_id?: string; database_slug?: string; query: { page_size?: number } };
type TaskDoc = { document_id?: string; id?: string; title?: string; properties?: Record<string, unknown> };
type QueryTasksResult = { documents?: TaskDoc[] };

export default function Dashboard() {
  const queryTasks = useTool<QueryTasksArgs, QueryTasksResult>('LOCAL_NOTIS_DATABASE_QUERY');
  const [documents, setDocuments] = useState<TaskDoc[]>([]);

  useEffect(() => {
    void queryTasks
      .call({ database_id: 'tasks-db-id', query: { page_size: 25 } })
      .then((result) => setDocuments(result.documents || []));
  }, [queryTasks.call]);

  if (queryTasks.loading) return <div>Loading...</div>;

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-2xl font-bold">Dashboard</h1>
      {documents.map((doc) => (
        <Card key={doc.id || doc.document_id} className="p-4">
          <h3 className="font-medium">{doc.title || 'Untitled'}</h3>
          <p className="text-muted-foreground">{String(doc.properties?.status || '')}</p>
        </Card>
      ))}
    </div>
  );
}
```

##### Step 4: Set up the root layout

```tsx
// app/layout.tsx
import { NotisProvider } from '@notis/sdk';
import '@notis/sdk/styles.css';
import './globals.css';

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>
        <NotisProvider>{children}</NotisProvider>
      </body>
    </html>
  );
}
```

##### Step 5: Develop locally — and let the user test here first

```bash
notis apps dev
```

This is the canonical local-development command. It should open the Electron Portal directly to the first local app when one is available, and every active local app appears in the **Local development** sidebar group (with a green `DEV` badge). When run from a monorepo root, it discovers every app in the workspace. Local app development requires the desktop app.

> **This is where a build request finishes.** When a code agent builds an app in this path, the expected endpoint is a working app running under `notis apps dev` in the **Local development** group — *not* a deployed app. The agent should keep `apps dev` running, tell the user the app is testable in Local development, and stop. The app only appears in Local development while an `apps dev` session is running; without one it is absent from that group even if it has been deployed.
>
> **Desktop targeting and mount acknowledgment.** `apps dev` records its session in the registry owned by its resolved runtime. A normal published-CLI run uses the global desktop registry and targets the desktop name stored by the active profile (`Notis` or `Notis Beta`, with an API-host fallback). A CLI run inside an active source worktree reads the exact session-registry path, desktop name, and deep-link scheme from that worktree's runtime lease; a nearby `.context` directory is never enough to redirect it. Electron filters sessions by user, API base, and target desktop name. Once the exact nonce-backed session enters the visible target Portal's final **Local development** sidebar model, the Portal asks Electron to validate it and Electron writes a `listed` acknowledgment beside the registry. Only then does the CLI print `Mounted in <target desktop>`. When the opened route has actually committed its shadow-root content, Portal writes a separate `rendered` acknowledgment and the CLI prints `Rendered in <target desktop>`. A registry row or healthy bundle proves **serving**, not **mounted** or **rendered**.
>
> Electron routes whose synthetic app id contains `__local_dev__` bypass the Store rollout gate. This exception is intentionally limited to a mounted local-development route inside Electron; Store pages, installed apps, and browser routes keep their existing rollout and entitlement gates.

##### Step 6: Build the artifact

```bash
notis apps build
```

Produces `.notis/output/` containing `manifest.json` and the ES module bundle under `bundle/app.js` plus `bundle/app.css`. Building and verifying are safe, local, non-destructive steps — they are **not** a trigger to deploy.

##### Step 7: Install/update the workspace app — only when the user asks

> **Deploy is user-gated.** Installing or updating the workspace app writes the local snapshot to the user's account (it then shows under **Workspace**, not Local development). A code agent should run these **only after the user has tested the local build and explicitly requested it** — never automatically after a clean build/verify. Treat it like publishing: an outward-facing action the user initiates.

```bash
# First install: create a workspace app and link this checkout to it
notis apps create "Task Manager" .

# Later installs from this checkout update the same linked app
notis apps deploy
```

Or if the remote app already exists:

```bash
notis apps link <app-id>
notis apps deploy
```

After the first install, the local checkout is durably linked to the installed app id in `.notis/state.json`. While `notis apps dev` is running, the dev-session registry mirrors that id so the Portal can show **Update** instead of **Install**. Re-running `notis apps dev` after the app was unmounted must preserve that link.

Development runtime app ids (`manifest.is_dev: true`) are internal mount identities, not install/update targets. `notis apps link` rejects them. If an older CLI or stale state file placed one in `app_id`, `notis apps dev` moves it to `dev_app_id` (unless a newer runtime id is already present), clears the invalid installed-app link, and mounts the project as local-only. A link to a deleted or inaccessible installed app is cleared in the same way, while transport and authentication failures still stop the mount without rewriting state. The Portal also treats any session whose target is absent or hidden as local-only, so malformed legacy state cannot make a running app disappear from **Local development**.

Before every mount, the CLI also revalidates `dev_app_id` against the resolved
runtime. If the checkout last ran against another worktree, Beta, or Production
and that development id is inaccessible in the current runtime, the CLI clears
only the stale development link and lets the backend reuse or create the
current user's development identity for the same slug. Authentication and
transport failures remain fail-closed and never rewrite the link. This
revalidation is metadata-only and does not load app document rows.
Only the app service's canonical missing-app response authorizes this repair;
unrelated lookup failures leave the local link untouched and fail closed.

##### Step 8: Check project health

```bash
notis apps doctor
```

Reports issues and warnings about your project configuration.

---

#### Forking an existing app

Both paths can start from an installed app. To fork a Store listing, **install it first** from `/store`, then pull source from your own installed copy:

```bash
notis apps pull <app-id> ./<dir>
```

After editing, run `notis apps create "My Fork"` (or `notis apps link <new-app-id>`) and `notis apps deploy`, then Publish from the Portal at `/apps/<new-app-id>`. The fork becomes a separate listing with its own lifecycle. Existing installs of the original app keep their upstream link and continue to receive updates from the original publisher — see [Forking from the store](#forking-an-existing-app-1) under the Editing section for the full rules.

The platform contract is identical between Path 1 and Path 2. The CLI commands, config format, SDK, and deployment target are the same regardless of where the CLI runs (Vercel sandbox vs your laptop).

---

### Other entry points

#### Install from the App Store

Browse and install pre-built apps from the Notis App Store.

#### How it works

1. Open the **App Store** in the Notis Portal.
2. Browse or search for apps by category.
3. Review any requested workspace capability shown on the listing, then click **Install**.
4. The app is installed to your workspace with cloned databases and its published routes.

#### What happens on install

- A new app record is created in your workspace
- Snapshot databases are cloned into your workspace
- The installed app reuses the published artifact snapshot via the stored manifest
- Sensitive manifest capabilities are never grants by themselves. For example,
  `capabilities.workspaceDatabases: "read"` is activated only when installation
  persists the user's `workspace_databases_read` approval. Store updates cannot
  silently add that access. A fresh local app may use its own declaration only
  for its author; sharing the app with a teammate does not grant that teammate
  access to their workspace databases. Store-derived duplicates persist both
  their source provenance and any carried grant instead of becoming implicitly
  trusted local apps.
- The app appears in your Portal sidebar

#### Via the assistant

You can also ask the Notis assistant:

- _"Show me available apps"_
- _"Install the project tracker app"_

The agent uses `list_public_app_store` and `install_app` tools behind the scenes.
The listing response includes `required_capabilities`. The agent must explain
each capability and obtain explicit approval before copying its token into
`approved_capabilities`; it must never infer approval from the install request.

---

#### Portal UI (App Management)

The Portal provides a web interface for managing your installed apps. While you don't build apps directly in the Portal UI, you can:

- **View** your installed apps and their routes from the workspace sidebar.
- **See an app's details** at `/apps/[appId]` — icon, listing metadata, theme-matched screenshots, and compact hover previews for resources (views, databases, automations, skills).
- **Pick the app's visibility** (Personal / Team / Public) on the App Details page.
- **Publish or Update** the listing in one click from the App Details page.
- **Unpublish** an active listing from the App Details ⋯ menu.
- **Reset** store-installed apps to the latest published store version.
- **Install** a local-only dev session into the workspace, or **Update** the linked installed app when the mounted dev session already targets one.
- **Mount for development** from an installed app by pulling its saved source snapshot, linking the checkout to that app id, and starting `notis apps dev`.
- **Uninstall** apps from the sidebar context menu.

The Portal does **not** directly build app code. Source checkouts and dev servers still go through the CLI (or the Notis assistant's sandbox running the CLI). Portal local-development actions may call the active local dev session to snapshot the already-mounted project and to persist the installed-app link that the CLI will use later.

#### Portal API endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/portal_apps/list` | GET | List your apps |
| `/portal_apps/get` | GET | Get app details |
| `/portal_apps/create` | POST | Create an app |
| `/portal_apps/update` | PATCH | Update app metadata (name, description, icon, **visibility**) |
| `/portal_apps/bundle` | POST | Bundle skills/automations |
| `/portal_apps/update/apply` | POST | Apply a clean store update |
| `/portal_apps/update/resolve` | POST | Start Notis-assisted store update conflict resolution |
| `/portal_apps/update/reset` | POST | Reset store-installed app customizations |
| `/portal_apps/publish` | POST | Publish/Update the deployed app to the Team or Public channel — reads listing metadata from the deployed manifest |
| `/portal_apps/unpublish` | POST | Unpublish an active listing (archives team listings, opens a removal PR for public listings) |
| `/portal_apps/submissions` | GET/PATCH | List active and historical store submissions for an app |
| `/portal_apps/submissions/withdraw` | POST | Withdraw a *pending review* submission |
| `/portal_app_store/get` | GET | Read a published listing with version history and aggregate ratings/reviews |
| `/portal_app_store/rate` | POST | Create or update the authenticated user's rating and optional review |
| `/portal_views/get` | GET | Route detail + runtime descriptor with signed bundle URLs |
| `/portal_views/runtime_query` | POST | Proxy tool calls and DB operations |
| `/portal_views/collection_items` | GET | List collection items |
| `/portal_views/collection_tree` | GET | List normalized tree nodes for sidebar tree routes |
| `/portal_views/collection_tree/create` | POST | Create root or child collection items from the sidebar |
| `/portal_views/collection_tree/delete` | POST | Delete a collection tree item from the sidebar |
| `/cli_tools` | POST | CLI tool execution (save_app_files, create_app, etc.) |

---

## Editing an Existing App

### Via the Notis Assistant

Just describe what you want changed:

- _"Add a priority field to the tasks database"_
- _"Change the dashboard to show a kanban board"_
- _"Add a new route for reports"_

The agent modifies the code in your sandbox session and redeploys.

### Via the CLI (local development)

1. Make changes to your local project files (`notis.config.ts`, pages, components).
2. Test locally:
   ```bash
   notis apps dev    # Live development in the desktop sidebar's Local development group
   notis apps build  # Build artifact
   ```
3. Deploy the update:
   ```bash
   notis apps deploy
   ```

Each deploy increments the app version. The Portal automatically loads the latest version.

If the checkout is not linked yet, link it before deploying:

```bash
notis apps link <installed-app-id> .
notis apps deploy
```

Do not rely on name or slug matching to choose an update target. The CLI may warn that an installed app looks related, but only `.notis/state.json` with an explicit `app_id` makes a dev checkout an update of that installed app.

### Resetting a store-installed app

Store-installed apps can be reset from the app detail page or through the `reset_app_customizations` app tool. Reset restores app metadata, routes, tools, and update state to the latest published store listing. Database rows and documents are not deleted.

By default, reset preserves the installed app's current database definitions so user-added fields remain available. Users can explicitly choose **Restore database schema** to replace database schemas with the latest store schemas. Even with schema restore enabled, existing documents remain in place.

### Forking an existing app

Any user can install an app they have access to (their own apps, public Store listings, or team Store listings their team can see), pull source from their installed copy, and edit it as the basis for a new app. This is the "fork" flow.

```bash
# 1. Install the app from /store first.
# 2. Pull source from your own installed copy.
notis apps pull <app-id> ./my-fork
cd my-fork
# ...edit notis.config.ts, app/, components/, metadata/...
notis apps create "My Fork"             # creates a new remote app, links the directory
notis apps deploy
# After the owner confirms App Details is ready for Store review:
notis apps publish --confirm-ready
```

Why install-first: the CLI only pulls source from apps you own or can access as installed copies. Pulling directly from a Store listing without installing is not supported.

Team-scoped access: anyone on the team can install and edit team-published apps. No one outside the team sees them. Public-published apps are installable by anyone with a Notis account.

What happens to relationships when you fork:

- The pulled directory has **no** `.notis/state.json` link until you run `notis apps create` or `notis apps link`. Pulling alone does not affect any apps.
- When you `create` + `deploy` + Publish the fork, it becomes a new listing with its own slug and lifecycle.
- If you previously edited the *installed copy*'s source and published it as a derivative, the backend clears `apps.source_listing_id` on the published copy after the new submission opens. Your installed copy stops auto-updating from the original publisher; it now lives under the new listing it just became.
- Other people's installs of the original listing are untouched. They keep their upstream link to the *original* publisher and continue to receive updates from the *original* listing.

### What you can change

| Change | Where to edit |
|--------|--------------|
| App name, description, icon | `notis.config.ts` metadata |
| Add/modify database refs | `notis.config.ts` databases array |
| Add/modify routes | `notis.config.ts` routes array |
| Change tool access | `notis.config.ts` tools array |
| Modify UI/pages | `app/` directory |
| Add components | `components/` directory |
| Update metadata only | Portal UI or `update_app` tool |
| Ship a source-owned skill or onboarding | `notis.config.ts` + `skills/<name>/SKILL.md` |
| Bundle unrelated skills/automations by reference | Portal UI or `update_app` tool |

### Database schema changes

`notis.config.ts` does not define database schema. Create or evolve databases through native Notis database tools, then reference the resulting slugs from the app config. The runtime resolves the real database rows when the app loads. An app-owned database slug is part of the deployed contract: bundles and collection routes may refer to it directly, so schema tools reject changing that slug. Rename the database's display title instead; changing a slug requires a new app package and an explicit migration strategy.

---

## Publishing to the Public App Store

`notis apps deploy` updates a single linked installed app — it's a private operation between the developer and their own account. Store submission is a separate action. The owner can click Publish/Update in App Details, or an agent can run `notis apps publish --confirm-ready` after the user explicitly confirms that the current App Details page is ready. Both surfaces call the same authenticated endpoint and submit the deployed manifest, not un-deployed local files.

### App Details publish flow

1. **Pick visibility.** On the App Details page (`/apps/[appId]`), the owner picks **Personal**, **Team**, or **Public** in the visibility selector. Personal hides the publish CTA — the app is private to the owner. Visibility persists on the `apps` row.
2. **Submit the confirmed listing.** With Team or Public selected, the owner clicks **Publish/Update**, or an agent with explicit approval runs `notis apps publish --confirm-ready`. The CLI checks local listing readiness, confirms `.notis/state.json` matches the current deployed version, blocks duplicate pending reviews, and then sends only `{ app_id }` to `/portal_apps/publish`. The server reads `apps.visibility` and listing metadata from the deployed `manifest.json` (`title`, `tagline`, `categories`, screenshots from `metadata/`, and parsed entries from the root `CHANGELOG.md`).
3. **Publish behavior depends on visibility:**
   - **Team** (`visibility='team'`): instant. Server upserts an `app_store_listings` row with `channel='team'`, `review_status='published'`, and the manifest metadata. Anyone on the team can install it from the Team section of `/store` immediately.
   - **Public** (`visibility='public_store_hidden'`): server opens a PR on `mindtheflo/notis-apps`, assembling the complete editable `apps/<slug>/` source tree plus `notis-listing.json` and Store screenshots. The listing metadata carries a reviewable install snapshot: the exact schema of every source-declared database, only rows from databases with `seedDocuments: true`, and bundled app resources. Registry CI validates source, schemas, seed privacy budgets, screenshot dimensions/size/alt text, type safety, bundle size, and forbidden patterns. On merge it builds the bundle, signs an HMAC payload containing that install snapshot, and POSTs to `/registry_publish`; the handler upserts a fully installable public `app_store_listings` row.
4. **Update presses do the same thing.** The button reads **Update** instead of **Publish** when an active submission already exists. Same channel rules: Team is instant, Public goes through PR review. The submission row in `app_submissions` tracks PR state.
   **What’s New** is the first entry in the latest published `CHANGELOG.md`; **Version History** renders every entry from that same file. Because the latest file is authoritative, editing an older entry and publishing again updates that past Store entry instead of leaving an immutable database copy behind.
5. **Visibility is locked while a listing is live.** Once an active submission exists (pending review or merged), the visibility selector is disabled. The owner must Unpublish before flipping between Team and Public.
6. **Conflict resolution lives at install time, not publish time.** When a Team or Public listing updates, propagation applies the new snapshot automatically to clean installs and compatible customization overlays. Installs with conflicting customizations move to `needs_resolution` and surface the App Details resolution flow through `/portal_apps/update/resolve`; `/portal_apps/update/apply` remains the explicit clean-apply endpoint. The publisher is not asked to resolve installers' conflicts.

If an installed Public store app is **modified and republished as a new app** (a fork), the backend clears `apps.source_listing_id` on the developer's installed copy after the new submission opens. That copy stops receiving upstream update notifications and owns its new lifecycle. The original listing keeps updating its other installs untouched. See [Forking an existing app](#forking-an-existing-app-1).

### Unpublish

The App Details ⋯ menu offers **Unpublish** when there's an active submission:

- **Pending review**: Unpublish withdraws the submission immediately (`/portal_apps/submissions/withdraw`). Already-installed copies are unaffected (there were none yet).
- **Team listing** (`channel='team'`, `review_status='published'`): Unpublish flips the row to `archived` (or deletes it). Anyone who already installed the team app keeps using it; new installers from the team Store no longer see it.
- **Merged Public listing**: Unpublish opens a *removal PR* on `mindtheflo/notis-apps` deleting `apps/<slug>/`. The listing **stays live in `/store` until the PR merges** — App Details shows a "Removal pending review" badge while the PR is open. On PR merge, registry CI removes the listing (the same handler that adds it on publish — extended to handle deletes). On PR close-without-merge, the badge clears, no DB change, the listing remains live. This mirrors how Raycast handles extension removals.

Already-installed copies of an unpublished app keep working until users uninstall them — un-listing affects discovery and new installs only.

### Why publishing requires explicit confirmation

Listing media (screenshots, tagline, category) lives in `notis.config.ts` and `metadata/` because it travels with the source. Store submission is outward-facing and remains separately user-gated: deploy approval is not Store approval. `apps publish --confirm-ready` exists so an agent can complete the confirmed workflow without bypassing App Details safeguards; it rejects missing confirmation, incomplete listing media, a local/deployed version mismatch, private visibility, and existing pending review.

Every app package must declare a semver `notisAppVersion`. The first publication can start at `0.1.0`; every later Store update must increment it beyond the version already on the registry's `main` branch. This release version is separate from the installed app's auto-incrementing deployed source version.

### Difference from `notis apps deploy`

| | `notis apps deploy` | App Details or `notis apps publish --confirm-ready` |
|---|---|---|
| Audience | Just you / your team | Everyone in the App Store, by channel |
| Surface | CLI | Portal `/apps/[appId]` or CLI after explicit confirmation |
| Mechanism | Uploads bundle and source snapshot to `app-code` / `app-source` and updates the linked `apps` row | Reads the deployed source, manifest, exact database schemas, and opt-in starter rows; Team writes directly to `app_store_listings`, while Public opens a full-source registry PR |
| Manifest media required | No | Yes — backend requires a tagline, category, and at least three valid 2000×1250 PNG screenshots with descriptive alt text |
| Versioning | Auto-incrementing integer on the installed app | `app_submissions` row tied to the deployed source version |

### Source portability

Every deploy writes the editable source snapshot and listing media to `app-source/{app_id}/v{version}/`. Anyone with access to an installed app can pull source from a terminal:

```bash
notis apps pull <app-id> [dir]
```

Pulled source includes the same files that were deployed for that installed app version: app code, `notis.config.ts`, and `metadata/` listing assets. See [Forking an existing app](#forking-an-existing-app-1).
Current CLI deploys also persist lockfiles so pulled checkouts can reproduce the original install. Older apps that predate source snapshots must be redeployed once before `notis apps pull` can recreate an editable checkout.

---

## App Contract

Every Notis App is defined by three things working together:

### 1. Source project

A standard Vite + React project with UI, routes, and components.

### 2. `notis.config.ts`

This is the declarative app contract. It defines:
- app metadata (name, description, icon)
- **listing metadata + media** as top-level manifest fields (`title`, `tagline`, `categories`) plus the `metadata/` folder and root `CHANGELOG.md`
- routes shown in the portal
- referenced databases by slug
- tool access allowed at runtime
- source-owned skills and an optional onboarding entrypoint

#### Source-owned onboarding

An app can expose a permanent onboarding action on its root sidebar row by declaring a source-owned skill and an onboarding prompt:

```typescript
defineNotisApp({
  // ...
  skills: [
    {
      key: 'journal-onboarding',
      path: './skills/journal-onboarding/SKILL.md',
      name: 'journal-onboarding',
      description: 'Set up the Journal daily routine.',
    },
  ],
  onboarding: {
    skill: 'journal-onboarding',
    prompt: 'Help me set up my Journal reminders.',
  },
})
```

`skills[].key` is the stable source identity; `onboarding.skill` must equal one of those keys. The Portal resolves the runtime skill by that explicit mapping, opens a new floating Notis conversation, and restores an editable structured `/skill` mention plus the configured prompt. It never auto-sends the prompt, and the action remains available after onboarding is completed.

During Local development, starting the app upserts these source-owned skills onto the stable development app identity. Clicking onboarding refreshes the current `SKILL.md` from the loopback snapshot before opening chat, so skill edits can be tested without deploying or manually replacing a bundled skill. A normal deploy performs the same source-skill sync for the installed app.

#### Listing metadata + media

Everything the App Store needs to render a listing lives in `notis.config.ts`, `metadata/` for image assets, and a root `CHANGELOG.md` for editable release history, so it travels with the source. The schema mirrors how Raycast extensions describe themselves — short, flat metadata plus conventional source files:

```typescript
defineNotisApp({
  // Identity
  name: 'random-number-generator',           // URL slug — short, lowercase, hyphenated
  title: 'Random Number Generator',          // display title shown across the Store and Portal
  description: 'Generate random numbers with configurable bounds, and keep a history of everything you rolled.',
  icon: 'phosphor:dice-five',                      // a `phosphor:*` value or `metadata/icon.png`; falls back to two-letter initials
  accent: 'amber',                                 // optional avatar color (blue|violet|emerald|amber|rose|sky|fuchsia|teal); default derived from id
  author: { name: 'Florian Pariset', handle: 'florian' },

  // Listing
  tagline: 'Roll dice, keep history.',       // single-line pitch shown on Store cards
  categories: ['Personal'],                  // 1+ values from the AppCategory enum
  screenshots: [
    {
      path: 'metadata/screenshot-1.png',
      alt: 'Preset editor with minimum and maximum number fields',
      route: 'generator',                    // optional route slug used by screenshot capture
      scenario: 'preset-editor',             // optional fixture scenario for a truthful demo state
      focus: '[data-preset-editor]',          // optional selector for a truthful detail crop
      theme: 'dark',                          // optional light | dark; defaults to light
    },
  ],

  // Structure
  databases: [...],
  routes: [...],
  tools: [...],
})
```

Image assets live in a `metadata/` folder at the project root, with these conventional filenames:

- `metadata/screenshot-1.png` … `metadata/screenshot-6.png` — product screenshots (exactly 2000×1250 PNG, ≤2 MB each, 3–6 required for publishing). Generate these with `notis apps screenshot` rather than authoring them by hand.
- `metadata/icon.png` — optional raster icon when `icon: 'metadata/icon.png'` is used instead of a `phosphor:*` value.

There is no cover image. Apps are icon-led like Raycast: the `icon` in `notis.config.ts` represents the app across the Store grid, the listing detail header, and App Details. The listing detail page leads with the icon + name + tagline and a screenshot gallery.

Declare `screenshots` in `notis.config.ts` to give every image descriptive alt text and a stable editorial order. Optional `route` and `scenario` fields let one route produce multiple truthful states during `notis apps screenshot`; scenario data comes from the local screenshot fixture and never replaces live app data. An optional `focus` CSS selector captures a real element when a screenshot should spotlight one part of the UI and avoids empty browser canvas around narrow layouts. Set `theme` to `light` or `dark` to capture against the matching Portal color scheme; paired light/dark entries can reuse the same route and scenario.

The screenshot command opens the real app route in the headless browser harness, applies the configured fixture `scenario` and Portal `theme`, waits for the route to settle, and captures either the configured `focus` element or the app surface. The compositor resizes that truthful capture into a large 16:10 rounded window over the shared Store background, adds only a thin theme-aware edge, and writes a true-color 2000×1250 PNG. It does not redraw the app or add a synthetic shadow. Use `--raw` for a diagnostic capture without the Store frame. Bundled assets ride along with the source upload (no separate bucket): `notis apps deploy` writes them into `app-source/{app_id}/v{version}/metadata/` together with the rest of the source, and the deployed `manifest.json` records the upload paths so the portal can sign URLs through the existing source-bucket flow.

#### Release history

Release history lives in one root file, newest entry first:

```markdown
# Random Number Generator Changelog

## [Saved Presets] - {PR_MERGE_DATE}

- Added reusable minimum and maximum presets.

## [Initial Release] - 2026-07-01

- Generate random numbers and keep a roll history.
```

Use `## [Release title] - YYYY-MM-DD`; `{PR_MERGE_DATE}` is also accepted for the newest unpublished entry. The build parses the complete file into the deployed manifest. The first entry powers **What’s New**, and the complete ordered list powers **Version History**.

The `categories` array accepts one or more values from the `AppCategory` enum exported by `@notis/sdk/config`:

- `Productivity`
- `Sales & Marketing`
- `Operations`
- `Product & Engineering`
- `Personal`

The Store filters listings by these categories and the App Details listing block displays them as chips.

`notis apps verify` enforces:
- Required listing fields (`title`, `description`, `tagline`, `categories[≥1]`) when the manifest is otherwise complete.
- A valid root `CHANGELOG.md` with at least one Raycast-style release entry.
- Three to six screenshots, exact 2000×1250 PNG dimensions, max size (≤2 MB per screenshot), and descriptive alt text for every image.
- Asset paths stay inside the project root.
- Runtime database queries stay inside the app's declared database references, and collection routes actually query their configured collection database. A database may still be packaged for automations or agent workflows without every UI route reading it.

The CLI reports these checks during development, App Details shows the same readiness checklist, and the backend enforces them again on Publish. Apps without listing metadata still **deploy and run normally**, but the Publish action remains disabled until the deployed manifest is complete.

### 3. Generated manifest

`notis apps build` generates `.notis/output/manifest.json`, which is the packaged runtime description used by the platform.

The manifest includes:
- app identity (name, title, description, icon, author)
- listing metadata (tagline, categories, parsed `CHANGELOG.md` entries)
- discovered media paths (screenshots from `metadata/`) — populated at build time and rewritten with deployed asset URLs at upload time
- routes
- database slug references
- tool allowlist
- bundle paths and per-route export names

The manifest `author` describes the app package, but it does not control the
Store's visible publisher. Public and team listings are attributed to the Notis
account that publishes them: the listing owner's `users.full_name` is displayed,
and the corresponding `user_id` is returned as `metrics.publisher.id`. This keeps
publisher identity tied to the authenticated account rather than mutable app
source metadata.

---

## Main Components

### `@notis/sdk`

`packages/sdk/` is the single SDK package for app developers.

The package is mirrored automatically to the public
[`mindtheflo/notis-sdk`](https://github.com/mindtheflo/notis-sdk) repository by
`.github/workflows/sync-public-repositories.yml` after relevant changes reach
`beta`. The monorepo remains the source of truth; public mirror files are
generated and must not be maintained separately. The same workflow mirrors the
CLI to `mindtheflo/notis-cli`. The independent `mindtheflo/notis-apps` registry
keeps its own PR-validation and merge-publish workflows because its app entries
are the public contribution surface rather than a monorepo mirror.

It provides:
- `@notis/sdk` for `NotisProvider` and runtime hooks
- `@notis/sdk/config` for `defineNotisApp()`
- `@notis/sdk/vite` for `notisViteConfig()`
- `@notis/sdk/styles.css` for shadow-safe app shell styles and base app-surface classes

Important hooks include:
- `useTool`
- `useTools`
- `useNotis`
- `useNotisNavigation`
- `useTopBarSearch`
- `useBackend`

### CLI

The repo-local Notis CLI is the supported interface for app work in a normal repo workspace, primarily in:
- `packages/cli/src/command-specs/apps.js`
- `packages/cli/src/runtime/app-platform.js`

Canonical commands:
- `notis apps init`
- `notis apps dev`
- `notis apps build`
- `notis apps verify`
- `notis apps create`
- `notis apps deploy`
- `notis apps link`
- `notis apps pull`
- `notis apps doctor`
- `notis apps list`

### Python backend

The Python backend is the source of truth for installed apps, artifact serving, runtime enforcement, and database/tool proxying.

Important surfaces:
- `/cli_tools` for CLI-triggered app operations
- `/portal_apps` for app CRUD, visibility, App Store publishing, unpublishing, and submission metadata
- `/portal_views/get` for view details and signed bundle URLs
- `/portal_views/runtime_query` for database and tool proxying
- `/registry_publish` for the signed registry CI webhook that publishes merged App Store submissions

### Portal

The Portal renders installed apps as React components directly in its React tree. The main renderer lives under `portal/src/components/apps/`.

The portal is responsible for:
- loading app navigation and route metadata
- dynamically importing the app bundle and rendering the correct route component
- supplying the host theme
- keeping app execution isolated from the main portal runtime

---

## Runtime Bridge

Apps do not talk directly to privileged backend internals. The portal owns the runtime and injects it into the rendered app subtree with `NotisProvider runtime={runtime}`.

The supported contract is the runtime object exposed through the SDK hooks. Apps must not read globals such as `window.__NOTIS_RUNTIME__`.

The runtime provides capabilities like:
- `listTools()`
- `callTool()`
- `request()`

Two runtime modes matter:
- **Portal development runtime**: a local bundle loaded inside the Electron Portal while the CLI keeps an active dev session alive
- **Portal runtime**: the installed or deployed bundle backed by `/portal_views/runtime_query`

The bridge is HTTP-based for data operations. Cross-surface coordination hooks are only for narrow UI concerns such as resize or navigation, not for primary data access.

You should use the SDK hooks rather than calling the runtime bridge directly. The hooks handle loading states, error handling, and work in both local development sessions and normal Portal runtime.

---

## Data Model

The main persistence model is:

- `apps`
  - the installed app record
  - stores app metadata, manifest, version, ownership, visibility, bundled asset references, and store-update state
- `databases`
  - every row belongs to one app through `owner_app_id`; manifests reference
    that app's rows by slug
- `documents`
  - records stored inside databases
- `app_store_listings`
  - versioned snapshots for store publishing and installation flows
- `app_submissions`
  - Portal App Store submissions, GitHub PR metadata, listing screenshots, and review status
- `app_store_listing_versions`
  - legacy release-history fallback for listings published before source-controlled `CHANGELOG.md`; new history is read from the latest published file
- `app_store_ratings`
  - one 1–5 rating and optional written review per user and Store listing; browser access stays behind authenticated server endpoints
- Supabase Storage `app-code`
  - stores deploy artifacts at `{app_id}/v{version}/`
- Supabase Storage `app-source`
  - stores editable source snapshots at `{app_id}/v{version}/`
- Supabase Storage `app-listing-assets`
  - legacy upload bucket for pre-manifest listing screenshots; current manifest listing media rides in `app-source/metadata/`

### apps table

| Column | Type | Description |
|---|---|---|
| id | uuid PK | App ID |
| user_id | uuid FK | Owner |
| team_id | uuid FK | Team (nullable) |
| name | text | Display name |
| slug | text UNIQUE | URL slug |
| description | text | App description |
| icon | text | Phosphor icon (e.g. "phosphor:list") |
| status | text | draft, active, archived |
| visibility | text | private, team, public_store_hidden |
| manifest | jsonb | Latest deployed manifest |
| current_version | integer | Version counter |
| source_listing_id | uuid FK | Source App Store listing for installed store apps; cleared when submitted as a derivative |
| installed_listing_version | text | Human listing version installed from the store |
| installed_listing_store_version | integer | Numeric store listing version installed from the store |
| installed_snapshot | jsonb | Store-installed baseline used for update/reset comparison |
| customization_overlay | jsonb | User changes over the installed store baseline |
| update_status | text | up_to_date, update_available, needs_resolution, update_failed |
| pending_listing_version | text | Pending human listing version when an update is available |
| pending_listing_store_version | integer | Pending numeric store listing version |
| pending_update_conflict | jsonb | Conflict details for Notis-assisted update resolution |
| bundled_automation_ids | uuid[] | Linked automations |
| bundled_skill_ids | uuid[] | Linked skills |

### Related tables

- **databases** -- Schema lives on the database row. `owner_app_id` is the
  lifecycle and authorization owner; `user_id` remains creator/actor
  provenance. Slugs are unique within an app, user, and team namespace.
- **documents** -- `database_id` links to databases with `ON DELETE CASCADE`.
  `user_id` records the actor that created or last owns the document; access is
  inherited from the database's owner app rather than granted by provenance.
- **app_store_listings** -- Snapshots for publishing to the app store.
- **app_submissions** -- Portal review submissions keyed to an app source version and registry slug.

Generated database upsert tools are qualified by the immutable database ID,
not only by slug. This prevents two accessible databases with the same display
slug from resolving to the wrong executor. Runtime reads and mutations resolve
the database ID first and reject a document operation bound to a different
database tool.

Important implication: the app owns the database lifecycle, but its manifest
does not define database schema. Agents should create or update databases
through native database tools, then wire those slugs into app configuration.

### Ownership migration rollout

Roll out database ownership in this order:

1. Apply `migration/20260721_databases_app_ownership.sql`. This additive
   migration takes write-blocking locks while it atomically removes orphan
   documents, installs the cascading foreign keys, and leaves
   `owner_app_id` nullable for the old runtime. It also installs the atomic
   account-deletion transfer helpers and fences app/database/document writes
   for identities with an active account-deletion job; deploy this migration
   before the server runtime that calls those helpers.
2. Deploy the server version that stamps and enforces `owner_app_id` on every
   create, install, update, runtime, and deletion path.
3. Quiesce database/app writes, then run
   `server/utilities/enforce_database_app_ownership.py --backfill --quiescent`,
   audit the remaining rows, and run
   `server/utilities/enforce_database_app_ownership.py --purge --quiescent`
   only when the operator has explicitly authorized deletion. Each purge is
   revalidated atomically against the current row and app manifests before it
   can remove the database. Until each user's rows have valid owners, account
   deletion fails closed for that user rather than deleting unresolved data.
4. Apply `migration/20260722_databases_owner_app_id_not_null.sql` only when the
   audit reports no null/dangling owners, team mismatches, or namespace
   duplicates. The migration rechecks those invariants under table locks
   before adding the unique indexes and `NOT NULL` constraint.

---

## Rendering Model

Notis Apps render as React components directly inside the portal's React tree.

The portal dynamically imports the app's ES module bundle, resolves the route component by its `export_name`, creates a dedicated `ShadowRoot` for the app surface, and renders the route into that shadow tree inside a `NotisProvider` with a real `NotisRuntime`. This gives apps:
- instant route switching (no iframe reload)
- shared auth and routing with the portal
- direct React context access for data operations
- error isolation via React Error Boundaries
- style isolation from portal chrome

The portal owns:
- sidebar and collection tree chrome
- top bar and breadcrumbs
- route shell and navigation structure
- theme tokens copied onto the app host

Apps own only the content surface inside the shadow tree. App CSS is injected into that shadow tree, not into `document.head`.

---

## App Structure Reference

A complete Notis app project looks like this:

```
my-app/
  app/
    layout.tsx          # Root layout that imports SDK/app styles
    page.tsx            # Default route
    globals.css         # Global styles
    tasks/
      page.tsx          # /tasks route
  components/
    ui/
      button.tsx        # shadcn components (scaffolded)
      card.tsx
      ...
  notis.config.ts       # App declaration (database refs, routes, tools)
  vite.config.ts        # Vite config with notisViteConfig()
  package.json
  tailwind.config.ts
  .notis/
    state.json          # Linked app ID (after notis apps link/create)
    output/
      manifest.json     # Generated manifest (after notis apps build)
      bundle/           # ES module bundle (after notis apps build)
        app.js
        app.css
```

### Generated manifest

`notis apps build` generates `.notis/output/manifest.json`:

```json
{
  "version": 1,
  "spec_version": 3,
  "app": {
    "name": "Task Manager",
    "description": "Track and manage team tasks",
    "icon": "phosphor:check-square"
  },
  "routes": [
    {
      "path": "/",
      "slug": "index",
      "name": "Dashboard",
      "icon": "phosphor:squares-four",
      "default": true,
      "export_name": "index",
      "collection": null
    },
    {
      "path": "/tasks",
      "slug": "tasks",
      "name": "All Tasks",
      "icon": "phosphor:list",
      "export_name": "tasks",
      "collection": {
        "database": "tasks",
        "titleProperty": "title",
        "parentProperty": "Parent task",
        "sidebar": {
          "mode": "tree",
          "allowCreate": true
        }
      }
    }
  ],
  "bundle": {
    "js": "bundle/app.js",
    "css": "bundle/app.css"
  },
  "databases": ["tasks"],
  "tools": ["LOCAL_NOTIS_DATABASE_QUERY"]
}
```

### Bundle storage

Deployed bundles are stored in Supabase Storage at:

```
app-code/{app_id}/v{version}/
  manifest.json
  bundle/app.js
  bundle/app.css
```

The matching editable source snapshot is stored privately at:

```
app-source/{app_id}/v{version}/
```

---

## SDK Reference

### Imports

| Import | Purpose |
|--------|---------|
| `@notis/sdk` | `NotisProvider`, runtime hooks |
| `@notis/sdk/config` | `defineNotisApp()` for `notis.config.ts` |
| `@notis/sdk/vite` | `notisViteConfig()` for `vite.config.ts` |
| `@notis/sdk/styles.css` | Shadow-safe app shell classes and base app-surface styles |

### Hooks

Explicit tool declarations and `useTool` calls should use canonical tool names such as `LOCAL_NOTIS_DATABASE_LIST_DATABASES` and `LOCAL_NOTIS_DATABASE_GET_DATABASE`. Database-specific argument/result types belong in the app implementation; the SDK keeps `useTool<TArgs, TResult>()` generic.

| Hook | Purpose | Example |
|------|---------|---------|
| `useTool<TArgs, TResult>(name)` | Call a platform tool | `const { call } = useTool<{ database_slug: string }, unknown>('LOCAL_NOTIS_DATABASE_GET_DATABASE')` |
| `useTools()` | List available tools | `const { tools } = useTools()` |
| `useNotis()` | Access app, route, generic context, and readiness | `const { app, route, context, ready } = useNotis()` |
| `useNotisNavigation()` | Navigate between routes/documents | `const { toRoute, toDocument, toApp } = useNotisNavigation()` |
| `useTopBarSearch(opts)` | Bind the current view to the Portal-owned top-bar search input | `const { setLoading } = useTopBarSearch({ value, onChange })` |
| `useBackend()` | Make direct backend requests | `const { request } = useBackend()` |
| `useMultiSelect(opts)` | Manage multi-item selection: hover checkboxes, cmd/shift-click, drag-select, Esc/Cmd+A/X/Shift+Arrow shortcuts | `const sel = useMultiSelect({ items: notes, getId: (n) => n.id })` |

### Multi-item actions

`useMultiSelect` is the reusable, view-agnostic multi-select primitive — the same one the Notis Inbox uses. It gives any list hover checkboxes, cmd/ctrl-click toggle, shift-click range, rubber-band drag, Esc to clear, Cmd+A to select all, Shift+Arrow to extend, plus per-action keyboard shortcuts in a floating bottom bar. The hook owns all selection state and interaction; apps supply the markup and the bulk actions. It works equally on a `<table>`, a card grid, or any custom layout — only the wiring below changes.

Wire it with the prop getters so nothing is hand-rolled:

- Spread `getContainerProps()` on the list's scroll container (owns drag-select + click-empty-to-clear).
- Spread `getItemProps(id)` on each row/card (adds the `data-notis-row-id` attribute the drag rectangle searches for, plus the cmd/ctrl-click handler).
- Spread `getCheckboxProps(id)` into `<MultiSelectCheckbox>`.
- Render `<MultiSelectDragOverlay rect={sel.dragRect} />` and `<MultiSelectActionBar>` once on the page (both are `position: fixed`).

```tsx
import {
  MultiSelectActionBar,
  MultiSelectCheckbox,
  MultiSelectDragOverlay,
  useMultiSelect,
} from '@notis/sdk';
import { TrashIcon as Trash2 } from '@phosphor-icons/react';

const sel = useMultiSelect({
  items: notes,
  getId: (n) => n.id,
  onHeadChange: (id) => {
    if (!id) return;
    document.querySelector(`[data-notis-row-id="${id}"]`)?.scrollIntoView({ block: 'nearest' });
  },
});

return (
  <>
    {/* Card grid — note the row is a plain <div>, not a <button> (see gotcha). */}
    <div {...sel.getContainerProps()} className="grid grid-cols-3 gap-4">
      {notes.map((note) => (
        <div key={note.id} {...sel.getItemProps(note.id)} tabIndex={0} onClick={() => open(note)}>
          <MultiSelectCheckbox {...sel.getCheckboxProps(note.id)} alwaysVisible={sel.isSelected(note.id)} />
          {/* ...card body... */}
        </div>
      ))}
    </div>

    <MultiSelectDragOverlay rect={sel.dragRect} />

    <MultiSelectActionBar
      selectedCount={sel.selectedCount}
      itemLabel={{ singular: 'note', plural: 'notes' }}
      actions={[
        {
          id: 'delete',
          label: 'Delete',
          shortcut: '#',
          destructive: true,
          icon: <Trash2 className="h-3.5 w-3.5" />,
          onRun: () => deleteAll(sel.getSelectedItems()),
        },
      ]}
    />
  </>
);
```

**Gotcha — rows must be plain elements, never `<button>` / `role="button"`.** Drag-select arms from a `mousedown` on the container but bails when the press lands on an interactive element (`button, a, input, textarea, select, [role="button"]`). If a whole row/card is a `<button>`, a drag can never start on it. Use a plain `<div>` (or `<tr>`) with `onClick` + `tabIndex={0}` + an Enter `onKeyDown` for accessibility, exactly like the Inbox's `ThreadRow`. Keep the checkbox itself a real `<button>` — it *should* be interactive so a click toggles instead of starting a drag.

**Customize per app via `actions[]`.** The action bar is intentionally dumb: each `MultiSelectAction` is just `{ id, label, icon, shortcut?, destructive?, onRun }`. `onRun` can fire a mutation directly, or open app-specific UI first — e.g. notis-notes' "Move to folder" action sets a `pendingFolderAction` state that renders a folder-picker popover, and only mutates once the user picks a target. Shortcuts only fire while the bar is mounted with `selectedCount > 0`.

**Shared selection across views.** Because the hook holds state, lifting the `useMultiSelect` call to the page component lets selection persist across view switches (e.g. Gallery ↔ Table) for free — render the chrome in each view and gate `bindKeyboardShortcuts` / `enableDragSelect` per active view. Use `bindKeyboardShortcuts: false` to drop the global Esc/Cmd+A/X/Shift+Arrow listeners and `enableDragSelect: false` to drop the rubber-band rectangle.

> Apps mount inside a **Shadow DOM** in the Portal, so the SDK's keyboard handlers resolve the real focused element via `event.composedPath()[0]` (not `event.target`, which the shadow boundary retargets to the host). This is handled inside the SDK — you don't need to do anything — but it's why typing in an app `<input>` doesn't trigger selection shortcuts.

### Database property types

| Type | Description |
|------|-------------|
| `title` | Primary title field (required, one per database) |
| `text` | Plain text |
| `number` | Numeric value |
| `select` | Single select from options |
| `date` | Date value |
| `checkbox` | Boolean |
| `people` | User reference |

---

## CLI Command Reference

| Command | Purpose |
|---------|---------|
| `notis doctor` | Check CLI config, auth presence, and API reachability |
| `notis whoami` | Show the active profile, user, and available toolkits |
| `notis apps list` | List your apps |
| `notis apps scaffolds list` | Print the scaffold catalog generated from `scaffolds/*` at CLI build time, or read `scaffolds/*` directly during local monorepo development before `dist/` exists |
| `notis apps init <name> [dir] [--from <scaffold-slug>]` | Scaffold a new app project. With `--from`, copies the named scaffold from the built CLI artifact, falling back to the monorepo `scaffolds/<slug>` source in local development. |
| `notis apps create <name> [dir]` | Create a remote app (and optionally link) |
| `notis apps dev [dir]` | Start desktop Portal local development for one app or every app in a monorepo workspace |
| `notis apps build [dir]` | Build and package to `.notis/output/` (bundles `metadata/*` along with the source) |
| `notis apps screenshot [dir] [--routes <slugs>] [--width <px>] [--height <px>] [--output-dir <dir>] [--raw] [--skip-build]` | Render the configured route/scenario/focus set in a headless harness, apply the deterministic Store presentation, and write the declared `metadata/screenshot-N.png` files (2000×1250). Apps are icon-led like Raycast — there is no cover image, only screenshots. |
| `notis apps verify [dir]` | Headless render-smoke every route, plus production listing-readiness checks (3–6 screenshots, PNG format, exact dimensions, size bounds, alt text) |
| `notis apps link <app-id> [dir]` | Link local project to remote app |
| `notis apps pull <app-id> [dir] [--force] [--version <n>]` | Download the source snapshot for one of your own installed apps. The pulled directory is linked to that `app_id` and version via `.notis/state.json`. |
| `notis apps deploy [dir] [--app-id <id>] [--skip-build] [--direct]` | Build and upload to the linked installed app (`--direct` uploads to Supabase storage directly, bypassing the backend server; auto-fallback on network errors). This does not submit to the Store. |
| `notis apps publish [dir] [--app-id <id>] --confirm-ready` | Submit the matching deployed version to Team or Public Store review after the user explicitly confirms App Details is ready. |
| `notis apps doctor [dir]` | Check project health (linked state, build artifacts) and **listing readiness** (which listing fields or `metadata/` images are missing for Publish) |

There is no separate `notis apps update` command: `apps publish --confirm-ready` submits both first publications and later updates. App Details remains the UI equivalent. See [Publishing to the Public App Store](#publishing-to-the-public-app-store).

### Common workflows

**New app from scratch:**
```bash
notis apps scaffolds list
notis apps init "My App" --from <scaffold-slug>
cd my-app
notis apps dev
# ... edit files in the desktop sidebar's Local development group ...
notis apps build
notis apps verify
notis apps create "My App" .
notis apps deploy
```

**Update an existing app:**
```bash
# ... edit files ...
notis apps dev
notis apps build
notis apps verify
notis apps deploy
```

**Link to an existing remote app:**
```bash
notis apps link <app-id>
notis apps deploy
```

---

## Notis Apps Local Development

`notis apps dev` is the single local-development workflow for Notis Apps. It gives developers a Raycast-style loop:

- one canonical command: `notis apps dev`
- one real host UI: the Notis Portal
- one local development surface: a **Local development** group at the top of the desktop sidebar (above Workspace), visible only when the user is in Electron *and* one or more `notis apps dev` sessions are active
- all apps in the target workspace run at the same time
- no mock portal, no mock-runtime dev mode, no `run dev`, no preview-only side path

Local app development requires the Electron desktop app. Hosted/browser Portal local-dev support is intentionally not part of this workflow — when the dev session ends, the sidebar group disappears and the user falls back to the installed app under Workspace.

### Target developer experience

Run `notis apps dev` from either:

- a single app directory containing `notis.config.ts`
- a monorepo root containing `apps/*/notis.config.ts`

The CLI should then:

1. Discover every local app in scope.
2. Start a local watch/build loop for every discovered app.
3. Serve all local bundles from one loopback dev server.
4. Register active dev sessions in the local desktop registry and heartbeat them while running.
5. Report each bundle as serving, then wait for an exact session/app/slug/nonce `listed` acknowledgment from the visible target Electron window before reporting it as mounted.
6. Open the explicitly targeted Electron Portal to the first active local app, falling back to the Store only when no local app route is available.
7. Report the first route as rendered only after the target Portal commits the app root inside the shadow mount and returns a separate `rendered` acknowledgment.

The Portal should then:

1. Show every active local app in the **Local development** sidebar group above Workspace.
2. Keep installed/live apps visible as normal installed apps.
3. Show a separate local-development variant when an active dev session targets an installed app by id.
4. Use the local bundle only for that local-development variant.
5. Fall back to only the installed bundle when the local session ends.
6. Acknowledge only nonce-backed sessions that reached the final Local development sidebar model; Electron must reject stale or invented acknowledgments that do not match a current authorized session.

Backend app rows use `id` as the stable identity. `apps.slug` is a user-scoped readable label and may be reused by different users; if the same user creates another app with that slug, the backend appends a numeric suffix. Portal routes must therefore use id-bearing slugs such as `/apps/<name>-<app-id>`, not `apps.slug` alone.

Local development has three different identities that must stay distinct:

- **Source checkout**: a directory with `notis.config.ts`, app files, and optional `.notis/state.json`.
- **Dev-session mount**: the ephemeral `notis apps dev` registry entry that tells Electron where the local bundle and snapshot endpoint live.
- **Installed app**: the durable backend `apps.id` that appears under Workspace and receives deployed or installed snapshots.

Only the installed app id is a valid update target. When the local checkout is linked to an installed app through `.notis/state.json`, `notis apps dev` registers the dev session with that `target_app_id`. For store-installed apps, the backend may recreate missing referenced databases by slug from the trusted store snapshot before the Portal runtime resolves the app. This repair only uses snapshot database schema; slug-only manifest references do not create empty databases.

If a local checkout is not linked by id but its snapshot name or development slug resembles an installed backend app, the Portal must not silently treat the local app as that installed app. Until the user or CLI writes an explicit `app_id` link, the primary action remains **Install** and a snapshot install creates a new workspace app. A suggestion-only **Link to existing app** affordance can be added later, but matching alone must never choose the update target.

### Development links and mount/update semantics

The durable development link lives in `.notis/state.json` and is mirrored into the active dev-session registry while `notis apps dev` runs. The link is created or refreshed by:

- `notis apps create "<name>" .` after first install
- `notis apps link <app-id> .`
- `notis apps pull <app-id> <dir>`
- the Portal **Install** action for a mounted local-only app, after the backend returns the created installed app id

Button and CLI behavior follow that link:

- **Unlinked mounted dev session**: Portal action is **Install**; CLI first-install flow is `notis apps create "<name>" .` then `notis apps deploy`. After success, the checkout and active dev session become linked to the created app id.
- **Linked mounted dev session**: Portal action is **Update**; CLI flow is `notis apps deploy` or `notis apps deploy --app-id <app-id>`. It must update the linked installed app rather than creating another app.
- **Unlinked session with possible match**: the CLI may print a warning or suggestion, and the Portal may add a secondary link action in a later pass. Neither surface should update a match until the link is explicit.
- **Mounted app gets unmounted**: stopping `notis apps dev` removes only the dev-session registry entry. It must not remove `.notis/state.json`. Running `notis apps dev` later remounts the project with the same `target_app_id`, so the Portal still shows **Update**.
- **Installed app is not mounted locally**: App Details can offer **Mount for development**. That flow should run the same source-checkout path as the CLI, `notis apps pull <app-id> <dir>`, which writes `.notis/state.json`, installs dependencies if needed, and starts `notis apps dev <dir>`. The newly mounted session is immediately linked and therefore shows **Update**.

The active dev-session registry should include the local session id, a unique per-app mount nonce, source directory, dev slug, manifest snapshot, bundle URLs, `app_id` for the hidden dev-runtime app row, and optional `target_app_id` for the installed workspace app. The registry is ephemeral and can be rebuilt from `.notis/state.json`; it is not the source of truth for the link. Electron persists validated `listed` acknowledgments in the sibling mount-ack file. The CLI accepts an acknowledgment only when its session id, app id, dev slug, and nonce all match the current run, so an acknowledgment from an earlier run cannot produce a false mounted result.

Manual cleanup for old dev rows is intentionally a runbook, not a migration. To find stale hidden runtime rows:

```sql
select id, user_id, team_id, name, slug, updated_at
from apps
where manifest->>'is_dev' = 'true'
order by updated_at desc;
```

Before archiving or deleting one of these rows, confirm no active local registry references it as `appId` in `.context/app-dev-sessions.json` or `~/.notis/app-dev-sessions.json`, and confirm any duplicate normal app row was created by the old install flow rather than by an intentional fork.

### Host model

The Electron Portal fetches local bundles directly from loopback, for example `http://127.0.0.1:<port>/a/<slug>/bundle/app.js`.

The stable loopback URL always serves the current SDK output under `.notis/output/bundle`. Legacy `dist/app.js` outputs are invalid and must be rebuilt with the current Notis CLI instead of normalized at runtime.

The same loopback server exposes `GET /a/<slug>/snapshot` for the Local development install/update and onboarding flows. When a user clicks **Install** or **Update** on an app that is currently running from a local dev session, the Portal snapshots the current manifest, bundle files, and editable source files, then saves them through `/cli_tools` to create or update the installed app version on the user's account. When the app declares onboarding, its root row also exposes a setup action; Local development uses the snapshot to refresh the source-owned onboarding skill before composing the Notis chat draft. App Store submission starts from an installed app version, not directly from a local-only dev session.

Update behavior depends on whether the local app has a backend target:

- If the local dev session targets an existing backend app by linked id, **Update** writes the latest local snapshot to that existing backend app and increments its installed version.
- If the local app has no backend target, **Install** first registers a backend app for the user's account, saves the local snapshot into that new app record, then persists the returned app id into both `.notis/state.json` and the active dev-session registry.
- The live/backend app entry is not replaced by the local bundle. Users can open the live version and the local-development version side by side while the dev session is active.

Electron is responsible for:

- reading active dev sessions from the local app-dev session registry
- authorizing visibility of those sessions to the owning user
- exposing dev-session metadata to the Portal renderer
- validating Portal mount acknowledgments against the current authorized session set and persisting exact nonce matches

By default, the registry is `~/.notis/app-dev-sessions.json`, and each session records its target desktop name so installed Notis and Notis Beta processes cannot claim one another's mounts. The repo `dev.sh` script writes the exact worktree registry path, desktop name, and deep-link scheme into `.context/notis-runtime.json`; any CLI launched below that active worktree consumes the lease directly. This keeps parallel worktrees isolated without relying on directory-name heuristics or requiring the caller to export routing variables manually. `dev.sh` also passes the freshly generated approved-test-user JWT to the auto-started `notis apps dev` process so it does not inherit a stale token from the shared CLI profile.

The backend does not track active local dev sessions and is not the bundle proxy.

### What `notis apps dev` does

1. Detects the layout:
   - **Single app** - a `notis.config.ts` next to the command.
   - **Monorepo** - `apps/<name>/notis.config.ts` for one or more apps. Running `notis apps dev` at the root builds every app under `apps/` in parallel.
2. For each app: reads `.notis/state.json` when present, verifies the linked installed app is accessible, and registers that app id as the dev-session target. If no link exists, the session remains local-only until the user installs or links it.
3. Spawns `vite build --watch` per app so bundles rebuild on every file change.
4. Runs a single HTTP server bound to `127.0.0.1:<port>`, with each app at a path prefix:
   - `GET /a/<slug>/bundle/app.js`
   - `GET /a/<slug>/bundle/app.css`
   - `GET /a/<slug>/events` - SSE push on rebuild
   - `GET /a/<slug>/snapshot` - current manifest, artifact files, and source files for Local development installs
   CORS allows Electron and loopback development origins.
5. Registers and heartbeats active dev sessions in the runtime-selected registry. Published CLI runs use `~/.notis/app-dev-sessions.json`; active source worktrees provide their exact isolated path through the runtime lease. Every session names its target desktop.
6. Reports the apps as serving, then watches the sibling acknowledgment registry. The CLI prints `Mounted in <target desktop>` only after the visible target Electron window has persisted exact `listed` acknowledgments for every app in the current run. It reports `Rendered in <target desktop>` separately after the first opened route commits app content. After the initial timeout it keeps serving and continues watching.
7. Brings the targeted desktop to its Manage surface while the session mounts, then opens the canonical local app route after the exact mount acknowledgment. The mounted route includes the current session id as a harmless query parameter so macOS cannot suppress it as a duplicate URL from a previous launch. On macOS, installed Prod/Beta launches use a normal, attached `open -b <channel bundle id> <deep link>` process rather than relying on either the shared URL-scheme owner, display-name activation, or an orphaned launcher; each of those can fail to deliver the URL to an already-running app. Source worktrees use their unique deep-link scheme. Every active local app appears in that desktop's Local development sidebar group.
8. The Local development context menu lets users install the current local snapshot to their account before any App Store submission, or update the existing backend app when the local app targets one.
9. App detail and view pages for installed apps keep using the installed bundle. Local-development entries open the local harness and load the local bundle.
   The local bundle still assumes portal-owned runtime injection and shadow-root mounting; there is no window-global runtime contract.
10. Each rebuild triggers an in-place reload of just the affected app, with no full page refresh.

### Portable source checkouts

Every `notis apps deploy` writes the runnable bundle to `app-code` and the editable source snapshot to `app-source` for the same app version. That makes installed apps portable across assistant sandboxes, Electron, and local CLI workspaces.

To edit an app locally from a terminal:

```bash
notis apps pull <app-id> [dir]
cd <dir>
npm install
notis apps dev
notis apps build
notis apps deploy
```

Pulled source includes app code, `notis.config.ts`, lockfiles, and `metadata/` listing assets from the deployed app version. Source checkout is a CLI/local-agent workflow only. The Portal never exposes a source-download button or downloads app source on the user's behalf. Legacy apps without a saved `app-source` snapshot must be redeployed once with the current CLI before they can be pulled.

### Security model

- The CLI dev server binds to `127.0.0.1` only, not the LAN.
- Electron rejects non-loopback local bundle origins when reading active dev sessions.
- Hosted/browser Portal does not show local dev sessions.
- After deploy, the app is loaded from Supabase storage like any installed app. There is no separate local-preview or alternate deployed mode.

### Examples

```bash
# Single app
cd my-app
notis apps dev

# Monorepo: builds every apps/<name>/notis.config.ts
cd notis-apps
notis apps dev
```

Press `Ctrl-C` to stop the dev server and all Vite watch processes.

### Non-goals

These paths are not part of the target workflow and should be removed as implementation completes:

- `notis run dev`
- the legacy local preview command
- `__notisDev` URL overrides
- mock-runtime app development in the CLI
- a separate preview portal or preview-only UI path

### Acceptance checklist

Use this list when the implementation is ready for verification.

1. `notis apps dev <single-app-dir>` opens the Electron Portal and lists exactly one active local app in the Local development sidebar group.
2. `notis apps dev <monorepo-root>` discovers all `apps/*/notis.config.ts` apps and lists all of them in the Electron Portal sidebar at once.
3. Hosted/browser Portal does not show local dev sessions.
4. Navigating from the Local development sidebar group into an app or view loads the local bundle instead of the installed bundle.
5. The Local development context menu offers **Install** for unlinked sessions and **Update** for linked sessions, not direct App Store submission.
6. When a linked backend app exists, the sidebar shows both entries: the live installed app and the local-development app.
7. Clicking **Update** for a linked local-development variant saves the current local snapshot to the linked backend app through `/cli_tools` and increments that installed app version.
8. Clicking **Install** for a local-only app creates a backend app first, saves the current local snapshot through `/cli_tools`, writes the returned app id to `.notis/state.json`, and changes the running dev-session action to **Update**.
9. Editing a file rebuilds the affected app and triggers an in-place reload without requiring a full page refresh.
10. Stopping the CLI removes the active dev session after TTL and the installed app remains available through the live bundle.
11. Restarting `notis apps dev` for a previously installed checkout remounts it with the same linked app id and shows **Update**.
12. App Details **Mount for development** pulls source for the installed app, writes the link, starts `notis apps dev`, and shows the mounted session as linked.
13. Non-loopback bundle origins are rejected.
14. One user cannot see or activate another user's local dev sessions.
15. A stale nonce or acknowledgment from a previous `apps dev` run never produces `Mounted in <target desktop>`.
16. A normal CLI run targets the active profile's Notis or Notis Beta desktop, while an active source-worktree run targets only the desktop instance named by its runtime lease.
17. The CLI distinguishes serving, mounted, and rendered; it warns without stopping the dev server when the desktop has not acknowledged the session and reports each later transition independently.
18. The Local development root row uses the app name rather than replacing it with the default route name.

---

## Design Guidelines

Notis Apps should feel native to the Portal.

Preferred UI approach:
- **Use scaffolded shadcn components** (`@/components/ui/*`) -- do not hand-roll buttons, cards, or badges.
- **Use Notis theme tokens** -- `bg-background`, `bg-card`, `border-border`, `text-foreground`, `text-muted-foreground`.
- **Use portal shell classes** -- `notis-app-shell`, `notis-app-surface` for layout.
- **Assume the portal provides theme tokens on the app host** -- apps should feel native by consuming those tokens inside the shadow tree, not by restyling the portal shell.
- **Keep layouts compact and dashboard-like** -- cards, tables, sections, badges. Not marketing-site heroes.
- **Use Phosphor icons only** with the `phosphor:` prefix. Never emojis.
- **Respect the host theme** -- do not hardcode dark/light mode or create app-specific palettes.

Avoid:
- custom marketing-site visual languages
- hardcoded app-specific dark/light themes
- raw hand-rolled primitives when scaffolded UI components already exist
- full-screen gradients, glassmorphism, bright neon palettes, or raw HTML controls

If a screen looks like a standalone microsite instead of a portal tool, it is too custom.

---

## Non-Negotiable Invariants

These rules are the canonical platform assumptions:

1. **Vite + React only** -- No Next.js, no custom server.
2. **ES module bundle** -- `notisViteConfig()` produces a library-mode bundle with React externalized.
3. **Component rendering** -- Apps render as React components directly in the portal. No iframes.
   The portal mounts each app into a shadow-scoped surface and injects the runtime provider itself.
4. **HTTP bridge for data** -- Use fetch for data operations. postMessage only for resize/navigation.
5. **Declarative tools** -- Declare in `notis.config.ts`, enforced server-side.
6. **Database refs only** -- Declare database slugs in `notis.config.ts`. A string packages schema only; `{ slug: 'templates', seedDocuments: true }` explicitly includes that database's small, non-personal starter dataset in Store snapshots. Database schema is managed through native database tools, not through app deploys.
7. **Phosphor icons, not emojis.**
8. **`notis apps deploy` is not store publishing** -- it updates the linked installed app and source snapshot only; review starts separately from App Details or `apps publish --confirm-ready` after explicit user approval.
9. **Portal-owned sidebar trees are structural** -- when a route declares `collection.sidebar`, the portal owns that sidebar. Agents must not replace it with custom in-app navigation as a workaround.
10. **Portal globals are unsupported** -- apps must not rely on `window.__NOTIS_RUNTIME__`, portal DOM hooks, or global DOM portals such as `createPortal(..., document.body)`.

### Unsupported shortcuts

When agents encounter older app instructions, prefer the current platform model in this document.

- `notis apps push` -- there is no push command; use `init -> build -> create/link -> deploy`. `notis apps pull <app-id>` is supported and downloads the persisted source snapshot for an installed app.
- Manual database creation is expected -- create databases through native tools, then declare slug refs in `notis.config.ts`. Use the object form with `seedDocuments: true` only for deliberate starter content that every installer should receive.
- Direct low-level tool calls instead of CLI -- use the CLI
- Raw `views/<slug>/index.js` files -- use standard React pages in `app/`
- Older dual-renderer or iframe-based assumptions

### Anti-patterns -- NEVER do these

- **NEVER assume app deploy creates databases** -- Create or update databases through native Notis tools first, then reference them by slug in `notis.config.ts`.
- **NEVER bypass the supported workflow by manually stitching together low-level save or lint calls** -- Use `notis apps pull`, `notis apps dev`, `notis apps build`, `notis apps verify`, `notis apps create`, `notis apps link`, and `notis apps deploy`.
- **NEVER write raw `views/<slug>/index.js` files** -- Write standard React pages in `app/`.
- **NEVER treat `apps deploy` as Store approval** -- It updates the linked installed app for the current account or team scope only. Submit only after the user explicitly confirms App Details is ready.
- **NEVER explore server code or tool schemas to invent an alternative app workflow** -- Use the Notis CLI.
- **NEVER replace a route-backed portal sidebar with a custom in-app sidebar because a preview looks wrong** -- preserve the manifest contract and escalate the missing sidebar as a platform/runtime issue.
- **NEVER invent a custom visual language** -- Apps should look like a natural extension of the portal.
- **NEVER hand-roll buttons/cards/badges when the scaffold already provides shadcn primitives.**

---

## Testing

1. **Build validation**: `notis apps build` must succeed without errors.
2. **Route smoke validation**: `notis apps verify` must render every route in the stub harness without runtime crashes.
3. **Project health check**: `notis apps doctor` shows problems/warnings.
4. **Local development acceptance**: `notis apps dev` must name the target desktop and report `Mounted in <target desktop>` after the visible matching Electron window validates the exact session/app/slug/nonce `listed` acknowledgment from the final Local development sidebar model. UI/runtime acceptance additionally requires `Rendered in <target desktop>`, which is emitted only after the local route commits app content inside the shadow root.
5. **Post-deploy verification**: Verify the deployed bundle via `/portal_views/get` -> `runtime_descriptor.bundle.js_url`. The signed bundle URL is the most reliable browser check in dev because it bypasses flaky local auth injection while still exercising the real runtime bridge, tool calls, and referenced databases.

---

## Where To Look In The Repo

Use these files when you need implementation detail after reading this doc:

- [AGENTS.md](../AGENTS.md)
- [server/skills/notis-apps/SKILL.md](../server/skills/notis-apps/SKILL.md)
- [packages/sdk](../packages/sdk)
- [packages/cli/src/command-specs/apps.js](../packages/cli/src/command-specs/apps.js)
- [packages/cli/src/runtime/app-platform.js](../packages/cli/src/runtime/app-platform.js)
- [packages/cli/src/runtime/app-dev-server.js](../packages/cli/src/runtime/app-dev-server.js)
- [server/lib/vercel_sandbox.py](../server/lib/vercel_sandbox.py)
- [server/lib/apps_service.py](../server/lib/apps_service.py)
- [server/lib/app_submission_service.py](../server/lib/app_submission_service.py)
- [server/lib/github_publish_helper.py](../server/lib/github_publish_helper.py)
- [server/lib/app_registry_service.py](../server/lib/app_registry_service.py)
- [server/routers/portal_views/_1_code/entry.py](../server/routers/portal_views/_1_code/entry.py)
- [server/routers/portal_apps/_1_code/entry.py](../server/routers/portal_apps/_1_code/entry.py)
- [server/routers/registry_publish/_1_code/entry.py](../server/routers/registry_publish/_1_code/entry.py)
- [portal/src/app/(protected)/apps/[appId]/AppPageClient.tsx](../portal/src/app/(protected)/apps/%5BappId%5D/AppPageClient.tsx)
- [portal/src/components/apps/AppViewRenderer.tsx](../portal/src/components/apps/AppViewRenderer.tsx)
- [portal/src/lib/appBundleLoader.ts](../portal/src/lib/appBundleLoader.ts)
- [portal/src/lib/appRuntimeBridge.ts](../portal/src/lib/appRuntimeBridge.ts)

---

## Agent Guidance

If the task is conceptual, start with this document.

If the task is execution-oriented, then read this document first and use the `notis-apps` skill second.

If the code seems to disagree with this document, treat this file as the intended platform contract and verify the specific implementation detail before changing behavior.

If a collection-tree sidebar appears missing, do not redesign the app around that absence. Keep `collection.sidebar` as the source of truth and treat the mismatch as a portal bug to investigate.
