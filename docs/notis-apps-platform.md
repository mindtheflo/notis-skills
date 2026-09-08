# Notis Development Workflow And Apps Platform

This is the canonical reference for local Notis development and the Notis Apps platform: repo setup, environment files, dev-stack discovery, branch/release policy, what a Notis App is, how the platform works, every way a user can create and edit apps, and the architectural rules that matter when building, debugging, or documenting apps.

Use this together with [server/skills/notis-apps/SKILL.md](../server/skills/notis-apps/SKILL.md):
- this document explains the platform model, contracts, and all creation/editing paths
- the skill explains the execution workflow for using the CLI

### Tool boundaries

Two surfaces, two responsibilities. Each one keeps its lane — see [Publishing to the Public App Store](#publishing-to-the-public-app-store) and [CLI Command Reference](#cli-command-reference) for the full contract.

| Action | CLI | Portal |
|---|---|---|
| Scaffold a new app, pull source from another app, build, verify, deploy | ✅ | ❌ |
| Edit listing metadata + media (screenshots, tagline, category) | ✅ (edit `notis.config.ts` + `metadata/`) | ❌ |
| Update app source in Workspace after checks | ✅ | ✅ (agent-assisted Update app) |
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
16. [Release-only delivery](#release-only-delivery)
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

Skills and automations use one canonical association contract: a resource's
`owner_app_id` and its owning app's `bundled_skill_ids` or
`bundled_automation_ids` membership change in the same database transaction.
Interactive moves use `/portal_apps/resource-association`; callers must not
edit only a bundle array because that leaves collection filters and App Details
with conflicting ownership. Resource deletes and skill tombstones unlink bundle
membership through database triggers in that same transaction. Store
customization overlays are derived afterward with compare-and-swap retries; a
derived-state warning must never make a committed association or deletion look
like it failed. Persist associations against the installed app ID.

App display names are presentation metadata, not identifiers. Skills and
Automations filters use the installed app's name, with readable spaced
capitalization for legacy lowercase machine names. Preserve deliberate mixed
casing and acronyms. Keep slugs, app IDs, and resource ownership unchanged when
correcting a display name. Resources group by their exact installed owner ID;
there is no local-session identity or development-label substitution. Separate
apps stay separate: labels use Archived or Unavailable where applicable and
numbered same-label copies, never raw slugs or UUIDs. Unavailable means the owner
is absent from the loaded app list; it does not prove deletion. Only eligible
installed apps remain move targets. Filter pills omit unselected apps with no resources in
the collection, before assigning same-name numeric labels; the Move to app
dialog still includes eligible empty apps.

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

Since the 2026-08 pricing re-cut the builder ladder is **all-tier**: the
`apps_builder` entitlement is granted on every tier including FREE, so
installing, running, developing, and deploying apps are available to any
signed-in user. Entitlements resolve from the tier map in
`server/lib/plan_entitlements.py`, not from `prices.*` booleans (see
`docs/subscription-management.md`); `apps_external_development` is collapsed
into `apps_builder` and is no longer read.

What is still tiered is not the builder — it is the compute and the resources an
app carries. Letting **Notis** write and deploy the code for you needs the Cloud
Computer (PRO and above). Bundled skills execute per the skills tier rules, and
bundled automations still need PRO+.

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
| Install and run apps | FREE | No billing gate |
| Reviewed native App/database tools | No App entitlement | Hidden unless surface + PostHog `store` allow them |
| CLI app source/build/deploy commands | FREE | No billing gate |
| Portal source/build/publish workflows | FREE | No billing gate |
| Six native skill-management tools | FREE | Skills are an all-tier entitlement |
| Nine native automation-management tools | PRO+ | Canonical `automations` entitlement response |
| Cloud Computer shell/files | PRO | Canonical `cloud_computer` entitlement response |
| Notis-builds-it-for-you (sandbox authoring chat) | PRO | Canonical `cloud_computer` entitlement response |

Installing an app materializes the app UI, routes, databases, starter documents,
and bundled skills on every tier. Bundled **automations** remain pending below
PRO+ and the response reports their counts; onboarding opens with a persistent
PRO+ ribbon instead of failing before the chat appears. After an upgrade, the
first PRO+ onboarding explicitly activates those pending assets, maps them to
installer-owned IDs, and refreshes the Store-install baseline without treating
activation as a customization. Duplicating a source app is an all-tier runtime
action unless duplication would materialize bundled automations, in which case
the backend requires PRO+ before creating any copy; it never bypasses the normal
resource entitlement by cloning them directly.

Trials mirror the selected plan. After a downgrade, installed apps and their
data stay available and the CLI builder keeps working; only the resources that
carry their own entitlement (automations, cloud sandbox) lock. Cleanup actions
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

The two halves of the bundle travel by different transports, which matters in the desktop
app: `app.js` is fetched and executed from a blob URL, while `app.css` is a
`<link rel="stylesheet">` injected into the app's shadow root. Nothing from the Portal's
own stylesheet crosses that shadow boundary, so if the link fails the app renders as raw
unstyled HTML and keeps working — see the CSP section in `docs/electron.md`. When the
descriptor carries no `css_url` at all, the server logs `No css_url resolved for app`.

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
   This starts the Python backend and Python cron workers. Add `--with-portal` for browser app testing or `--with-electron` for desktop integration; see [stack tiers](development-workflow.md#stack-tiers).

The full live terminal stream is written to `.context/terminal.txt`. The file is cleared on every `dev.sh` launch and deleted by `./archive.sh`.

`dev.sh` stops itself after 30 minutes without activity. App development that parks the stack without traffic should run `./dev.sh --no-idle-timeout` or keep a `touch .context/dev-activity` keepalive; see the Idle Shutdown section in `docs/development-workflow.md`.

### Environment files

`.env` files are not committed. In Cloud Agent VMs, generate them from injected environment variables.

Conductor stages uploaded environment files outside every checkout and applies
them under a kernel-released advisory lock. Its repository/workspace scripts
resolve the installed Conductor app first and address its databases by exact id;
a same-slug database owned by another app is never a fallback write target.

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

For off-machine mobile testing, see [Mobile testing with ngrok](development-workflow.md#mobile-testing-with-ngrok).

See [Development Workflow: Stack Tiers](development-workflow.md#stack-tiers) for service selection, dependencies and resource usage. App browser and local sandbox-bridge tests require `--with-portal`; desktop app tests require `--with-electron`.

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
- `.context/electron-dev-login-url.txt` - latest pre-consumed `/auth/confirm` session URL for Electron. Its auth redirect always targets the worktree's local Portal origin, even when the browser entry link uses ngrok or a public Conductor route. By default this uses `parisetflorian+dev@gmail.com`; `./dev.sh --with-electron --electron-user-id <id> --electron-user-email <email>` can select another Electron login user.
- `.context/dev-portal-auth.json` - structured dev-user payload with both URLs and metadata.

When `DEV_PERSONAL_USER_ID` and `DEV_PERSONAL_USER_EMAIL` are set, `dev.sh` also prints a second browser magic link in the terminal log.

The auth-link helper does not start the app. Start the local UI stack with `./dev.sh --with-portal` first.

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
./dev.sh --with-electron --electron-user-id <id> --electron-user-email <email>
./dev.sh --restart-running-dev-session
tail -n 200 .context/terminal.txt
```

`./dev.sh --refresh-portal-entry-link` only refreshes the one-time link. It does not boot the app.

`DEV_PERSONAL_USER_ID=<id> DEV_PERSONAL_USER_EMAIL=<email> ./dev.sh --refresh-portal-entry-link` prints an optional second browser magic link without hardcoding a personal account in the repo.

`./dev.sh --with-electron --electron-user-id <id> --electron-user-email <email>` starts the Electron app logged in as that user.

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

Workspace runs released versions only. Both Notis Manager and external coding agents use the
[release-only delivery workflow](#release-only-delivery). Portal-generated create/edit prompts are
owned by `portal/src/lib/appTemplateGallery.ts`; the Store entrypoint uses the same generator.
Scaffolding and source changes stay local until verification passes. The engineering `dev.sh`
stack, CLI worktree profiles and coding-agent bridges remain independent of app delivery.

### Source-owned skills and onboarding

Declare skills in `notis.config.ts` with stable `key`, `name`, and source `path`. A path may be a
Markdown file or a directory containing `SKILL.md` plus supporting files. The CLI packages that
exact source tree; the backend validates and prepares private bundles before activation. Stable
keys retain skill IDs, including restoration of tombstoned source-owned skills.

Onboarding and `runtime.handover()` resolve only the installed manifest and its `resolved_skill_ids`.
They do not synchronize local snapshots. Pending premium assets still use the existing activation
and capability checks. Independently attached skills/automations and ordinary editors remain immediate.

## Editing an Existing App

### With Notis or a coding agent

Use **Update app** from App Details. Pull the current release into the intended directory, preserve
local edits and its exact profile/app link, then follow [release-only delivery](#release-only-delivery).
No runtime preview is mounted in Workspace. Source edits do not affect the installed app until release.
For historical-source restoration, use the current deployment base and release the old source as a
new version; do not roll back database contents or external actions.

### Resetting a store-installed app

Store-installed apps can be reset from the app detail page or through the `reset_app_customizations` app tool. Reset restores app metadata, routes, tools, and update state to the latest published store listing. Database rows and documents are not deleted.

By default, reset preserves the installed app's current database definitions so user-added fields remain available. Users can explicitly choose **Restore database schema** to replace database schemas with the latest store schemas. Even with schema restore enabled, existing documents remain in place.

Creation retries keep a profile/name/slug/scope-bound idempotency intent until the exact editable app is reconciled. Only a typed `AppCreateRejected` validation, raised before insertion and returned as `outcome: rejected`, clears a rejected intent so a corrected request can use a new key. Transport failures, insertion errors, post-create resource failures and incomplete readback retain the key; they do not prove that creation was rolled back.

### Forking an existing app

Any user can fork a **published Store app** by downloading its source from the public registry with `notis apps init --from <slug>` — installing it first is not required. This scaffold is unlinked and becomes the basis for a new app identity.

```bash
# Fork a published Store app straight from the registry (no install needed):
notis apps init "My Fork" ./my-fork --from <slug>
cd my-fork
# ...edit notis.config.ts, app/, components/, metadata/...
npm install
notis apps build
notis apps verify
notis apps create "My Fork" .           # creates a new remote app, links this directory
notis apps deploy
# After the owner confirms App Details is ready for Store review:
notis apps publish --confirm-ready
```

`apps pull <app-id> ./existing-app` is the **update** workflow, not the new-identity fork workflow. It downloads the exact deployed source and writes the profile-scoped `.notis/state.json` link to that same app and deployment base. Subsequent deployment updates that copy. The CLI only pulls source from apps you own or can access as installed copies. To obtain source for a published Store app you have not installed, use the registry path (`notis apps init --from <slug>`) instead.

Team-scoped access: anyone on the team can install and edit team-published apps. No one outside the team sees them. Public-published apps are installable by anyone with a Notis account.

What happens to relationships when you fork:

- The `apps init --from` scaffold has no remote app link until you run `notis apps create` or `notis apps link`. Scaffolding alone does not affect any apps.
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

#### App-owned skill source and materializations

An app-owned skill has one editable definition: the skill directory declared by
the app's `notis.config.ts`. For a public Store app, the reviewed canonical copy
lives under `apps/<slug>/skills/<skill>/` in `mindtheflo/notis-apps`. A linked
checkout produced by `notis apps pull` is an editable snapshot of one deployed
version; after changing it, build and deploy that checkout, then publish the
Store update so the registry becomes canonical for the new version.

The other copies are generated materializations, not additional sources:

- `app-source/{app_id}/v{version}/` is the immutable deployed source snapshot.
- `/vercel/sandbox/.notis/skills/<skill>/` is the account's synchronized runtime
  materialization of the app bundle.
- Claude, Codex, and other local-agent skill directories are symlinks or sync
  targets rooted in that account materialization.

Never patch a runtime materialization or add the same workflow to an unrelated
development skill to compensate for a stale sync. Edit the linked app source,
deploy it, publish the reviewed Store source when applicable, and run skill sync.
This keeps executable scripts, skill instructions, and their tests in one app
package while allowing each agent harness to receive its generated copy.

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

Source-owned skills activate with the manifest in the release transaction. Onboarding resolves only installed skills and never refreshes a local snapshot.

App-owned skills and automations remain visible on the global Skills and Automations pages, including independently attached resources. Each app's root sidebar menu includes **Automations** and **Skills**, opening the corresponding collection with `app_id` set to the installed app ID. Query changes update an already-open collection; a selected app stays visible in the filter even when it has no matching resources. Both pages keep an always-visible **App** filter with **All**, one pill per app, and **No app**; this filter is independent from the Skills **Source** dropdown and the Automations **Trigger** dropdown. App-owned rows carry an `App · <app name>` tag. The list APIs derive that presentation metadata from `owner_app_id`. Independently attached resources remain immediate. Source-packaged skills synchronize only from a released app.

#### Skills with supporting files

`skills[].path` is either a Markdown file or a **directory** containing `SKILL.md` plus everything the skill needs:

```typescript
skills: [
  { key: 'new-workspace', path: './skills/new-workspace/', name: 'New workspace' },
]
```

```
skills/new-workspace/
  SKILL.md
  scripts/
    run_job.sh
    upsert_row.py
```

A directory declaration is packaged as the skill's bundle and materialized whole under `/vercel/sandbox/.notis/skills/<name>/`, so `scripts/` reaches the agent exactly as written. Release preparation collects the files from the frozen source snapshot. Installing the app from the Store copies the bundle into the installer's own storage, so scripts travel with the app.

Rules:

- The directory must contain `SKILL.md` at its root; paths must stay inside the project.
- The same exclusions as source packaging apply (`node_modules`, `.notis`, `.git`, `dist`, `.env*`, symlinks).
- A skill's files are capped at 5 MB in total, on top of the 512 KB `SKILL.md` cap.
- The bundle is re-uploaded only when a content hash over the file set changes, so an unchanged skill folder costs nothing on redeploy.
- A Markdown-file declaration stays Markdown-only: source is authoritative, so the sync discards any ZIP a Portal edit had attached to the row.

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

`notis apps verify` reports, as `Store readiness:` warnings, and `notis apps verify --listing` / `notis apps publish` enforce:
- Required listing fields (`title`, `description`, `tagline`, `categories[≥1]`) when the manifest is otherwise complete.
- A valid root `CHANGELOG.md` with at least one Raycast-style release entry.
- Three to six screenshots, exact 2000×1250 PNG dimensions, max size (≤2 MB per screenshot), and descriptive alt text for every image.
- Asset paths stay inside the project root.

`notis apps verify` always enforces, whatever the listing state:
- Every route mounts in the headless harness without render errors.
- Runtime database queries stay inside the app's declared database references, and collection routes actually query their configured collection database. A database may still be packaged for automations or agent workflows without every UI route reading it.
- In `--mode live` only: a route whose runtime calls all failed, or a declared database whose queries never succeeded, fails the route. An app that catches every failed call and renders its error state mounts cleanly, so nothing else would catch it.

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
account that publishes them: the listing owner's `users.first_name` is displayed,
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
- `useHandover`
- `useBackend`

### CLI

The repo-local Notis CLI is the supported interface for app work in a normal repo workspace, primarily in:
- `packages/cli/src/command-specs/apps.js`
- `packages/cli/src/runtime/app-platform.js`

Canonical commands:
- `notis apps init`
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
- `subscribeDatabase()` — a change signal for an app-owned database; data still comes back through `callTool()`
- `handover()` — opens manager chat with app/resource context and an optional starter prompt or declared skill; the app watches its own databases for the result
- `cloudComputerFacts()` — read-only cloud computer facts behind the `cloudComputer: 'read'` capability; it never creates, resumes or commands a sandbox

Two runtime modes matter:
- **Temporary test harness**: explicitly invoked local stub/live verification, separate from Workspace.
- **Portal runtime**: the installed or deployed bundle backed by `/portal_views/runtime_query`

The bridge is HTTP-based for data operations. Cross-surface coordination hooks are only for narrow UI concerns such as resize or navigation, not for primary data access.

You should use the SDK hooks rather than calling the runtime bridge directly. The hooks handle loading states, error handling, and work in both temporary test harnesses and normal Portal runtime.

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

The shared SDK's bulk-action toolbar reports its own element's active state through
the document-scoped `notis:bulk-actions-layout` event. The Portal validates and
measures connected toolbar elements, aggregates their offsets, and owns the global
launcher CSS variable. SDK/app code never writes document-root styles; cleanup
also reports inactive toolbars after their shadow-root content is detached.

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
| `useTool<TArgs, TResult>(name)` | Call a platform tool; identical idempotent reads may opt into in-flight deduping with `call(args, { dedupe: true })` | `const { call } = useTool<{ database_slug: string }, unknown>('LOCAL_NOTIS_DATABASE_GET_DATABASE')` |
| `useDatabaseSubscription(slug, opts?)` | Query an app-owned database and refetch it when its rows change | `const { rows, live, refetch } = useDatabaseSubscription('workspaces')` |
| `useTools()` | List available tools | `const { tools } = useTools()` |
| `useNotis()` | Access app, route, selected collection item, optional exact resource id, and readiness | `const { app, route, collectionItem, resourceId, ready } = useNotis()` |
| `useHandover()` | Hand a piece of work to the Notis manager chat | `const { handover, pending, available } = useHandover()` |
| `useNotisNavigation()` | Navigate between routes/documents, optionally preserving an exact resource | `toRoute('/inbox', { resourceId: post.id })` |
| `useTopBarSearch(opts)` | Bind the current view to the Portal-owned top-bar search input | `const { setLoading } = useTopBarSearch({ value, onChange })` |
| `useCloudComputer()` | Read a few facts about the user's cloud computer | `const { facts } = useCloudComputer()` |
| `useBackend()` | Make direct backend requests | `const { request } = useBackend()` |
| `useCollectionInteractions(opts)` | Standardize active-item focus, multi-selection, marquee selection, shortcuts, and semantic bulk actions | `const collection = useCollectionInteractions({ items: notes, getId: (n) => n.id })` |
| `useMultiSelect(opts)` | Deprecated one-minor compatibility wrapper; migrate to `useCollectionInteractions` | — |
| `useActiveResource(resource)` | Tell Notis which item is focused inside the current view | `useActiveResource({ id: post.slug, kind: 'blog_post', label: post.title })` |
| `useAgentContext()` | Add, update or detach unsent generic context pills | See the [shared context reference](../server/skills/notis-apps/references/context.md) |

#### Focused resources and selected quotes

The route identifies the surface; `useActiveResource()` identifies the item inside it. Apps should publish a stable id, semantic kind, human label, optional URL/revision, compact attributes, and only the current text or Markdown snapshot that would materially help answer a follow-up. The Portal stamps the installed app and view identity onto this context, so an app cannot claim another app's provenance. Publishing context is local state and does not call a tool; the selected snapshot is attached only when the user sends a chat message.

Wrap selectable content in `NotisSelectionBoundary`. Copy still places ordinary `text/plain` on the clipboard, but it also carries a bounded structured quote. When pasted into Notis chat, that quote becomes its own removable context pill instead of being mixed into the user's instructions.

```tsx
const resource = {
  id: post.slug,
  kind: 'blog_post',
  label: post.title,
  revision: String(post.revision),
  snapshot: { format: 'markdown' as const, content: post.markdown },
};

useActiveResource(resource);

return (
  <NotisSelectionBoundary resource={resource}>
    <Markdown value={post.markdown} />
  </NotisSelectionBoundary>
);
```

Snapshots and quotes reach the agent as explicitly untrusted reference data. They provide grounding, never instructions. Keep them current and relevant; use a tool fetch when the freshest record is needed. Resources may include JSON-serializable `additionalContext`. See [Reports and context](reports-and-feedback.md#sdk-feedback-and-context) for lossless large-context delivery and optional comments. Copying from a supported SDK selection and pasting into chat creates a source-aware quote pill; unrelated clipboard text remains message text.

#### Storage-neutral Markdown editing

`MarkdownEditor` supplies the canonical Notis BlockNote document editor while the app keeps ownership of storage. It uses the same blocks, slash menu, formatting toolbar, table capabilities, spacing, and theme as Notis documents. Pass `value` and a revision, then persist through `onSave`. This works for Supabase rows, a third-party CMS, Git-backed files, or a Notis document adapter without teaching the editor about any of those stores.

```tsx
<MarkdownEditor
  resourceKey={post.slug}
  value={post.markdown}
  revision={String(post.revision)}
  autosaveMs={1000}
  onSave={({ markdown, expectedRevision }) =>
    cms.updatePost(post.slug, markdown, expectedRevision)
  }
/>
```

The host debounces autosave, supports Cmd/Ctrl-S, reports dirty/saving state, flushes a dirty draft when the editor unmounts, and returns the next revision from the app callback. Always pass a stable `resourceKey` when the same component position can switch between records; changing it gives each record isolated editor state. Store adapters should use optimistic concurrency (`WHERE revision = expectedRevision`) and reject conflicts rather than silently overwrite newer content. To support local image, video, audio, and file uploads, pass `onUploadFile`; persist the file in the app's own storage and return its durable URL. URL embeds work without that callback. Hosts that do not inject the rich editor fall back to an editable Markdown textarea with the same save contract.

#### Change feed (`useDatabaseSubscription`)

`useDatabaseSubscription(databaseSlug, options?)` is `useDocuments` plus freshness: rows written by a skill, an automation or another device reach an open view without polling. It takes every `useDocuments` option (`filter`, `pageSize`, `offset`, `fetchAll`, `enabled`, `includeContent`) plus `subscribe` (default `true`) to keep the query but drop the feed, and returns `{ documents, rows, loading, error, refetch, live }` — `rows` is an alias of `documents`.

```tsx
const { rows, live, refetch } = useDatabaseSubscription('workspaces', { pageSize: 250 });

return (
  <>
    {!live && <Button onClick={refetch}>Refresh</Button>}
    <WorkspaceTable rows={rows} />
  </>
);
```

What it does and does not do:

- **The event is only a signal.** The change feed carries no rows. When it fires, the hook refetches through `LOCAL_NOTIS_DATABASE_QUERY` on the runtime bridge, so app scoping, tool permissions and billing are exactly what they were before — app code never sees data that did not come back through the bridge.
- **Bursts collapse.** A skill rewriting a table produces one refetch, not one per row (300 ms debounce). Regaining window focus or tab visibility also re-checks, so a view that was backgrounded is correct on return.
- **`live` is honest.** It is true only while a feed is actually attached. Hosts without one — the temporary `apps verify` harness, the screenshot stub, the vite preview — return rows normally with `live === false`. Keep a manual refresh control for those, as above.
- **Only app-owned databases.** The slug is resolved against the databases the app declares; anything else is inert.

#### Handing work over (`useHandover`)

An app displays work; the manager runs it. `useHandover()` is how app code starts a job that is too long or too conversational for a tool call — cloning a repository, setting one up, anything where the agent has to ask questions. The app hands over a message and the manager chat takes it from there, so streaming progress, billing, cancellation and the transcript stay where they already work. Results reach the view through the app's own databases, which is what `useDatabaseSubscription` is for.

```tsx
const { handover, pending, available } = useHandover();

return available ? (
  <Button disabled={pending} onClick={() => { void handover({ prompt: 'Create a workspace on notis to fix X' }); }}>
    Send to Notis
  </Button>
) : (
  <CopyablePrompt prompt="Create a workspace on notis to fix X" />
);
```

`handover({ prompt?, skill?, autoSend? })` resolves to `{ status: 'drafted' | 'sent' }`:

- **`prompt`** is optional. When omitted, the composer opens with the app/database pills plus the current page or active-resource context supplied by the host, so the user can write in their own words. This is appropriate for feedback buttons.
- **`skill`** is a key from `notis.config.ts` -> `skills[].key`. The host rejects a key the app does not declare and a skill that is not installed for the app, so app code can never point the manager at something the user did not get with the app. Omitted, the work is handed over without a skill binding.
- **`autoSend`** is reserved for forward compatibility. Current Portal hosts always open the complete prepared message — `@App @Database… /Skill <prompt>` — for the user to read and send, and resolve `drafted`; they never silently discard mentions or submit on the user's behalf.
- **`available` is honest.** Hosts without a manager chat (the temporary `apps verify` harness, the vite preview) leave `runtime.handover` undefined and `available` false. Keep the app's own fallback — a copyable prompt — for those, as above.

This is the same machinery as the sidebar's **Onboarding** entry, which is `notis.config.ts` -> `onboarding: { skill, prompt }` handed over the same way; `handover()` lifts it out of onboarding so any button in any view can use it.

#### Cloud computer facts (`useCloudComputer`)

Apps that drive the user's cloud computer used to have to *infer* its state. The Conductor app treated a configured repository as proof that `gh auth login` had happened, because a private clone cannot succeed without it — sound, but it cannot show an account name and cannot notice a revoked credential.

`useCloudComputer()` answers two facts directly, behind an install-time capability:

```typescript
defineNotisApp({
  // ...
  capabilities: { cloudComputer: 'read' },
})
```

Declaring `cloudComputer: 'shell'` instead asks for the stronger grant: it implies the
read facts and, once the user consents (`cloud_computer_shell`), reopens
`LOCAL_NOTIS_RUN_SANDBOX_SHELL` and the three sandbox file tools for this app's views —
they are denied to every view otherwise, because shell runs with the sandbox's
full-authority credentials and the file tools reach the same secrets on disk. Declare it
only when the app's core actions genuinely run on the cloud computer, the way the
Conductor app does.

```tsx
const { facts, refresh } = useCloudComputer();
const gh = facts?.available ? facts.cli_auth.gh : null;

return gh?.authenticated
  ? <p>Signed in as {gh.account}</p>
  : <GithubConnect onConnected={refresh} />;
```

The payload is exactly:

```json
{
  "available": true,
  "sandbox": { "exists": true, "status": "running", "provider": "vercel", "created_at": "…", "updated_at": "…" },
  "cli_auth": { "gh": { "authenticated": true, "account": "octocat", "checked_at": "…", "reason": null } }
}
```

Read it the way it is meant:

- **It is a read and only a read.** The declared value is `'read'`; the token persisted on approval is `cloud_computer_read`. There is no create, no resume and no command here — those stay behind `LOCAL_NOTIS_RUN_SANDBOX_SHELL` and the reviewed tool surface matrix.
- **Nothing wakes the VM.** The sandbox is resolved through the read-only readiness path, and `gh auth status` runs *only* when the sandbox is already running, dispatched as internal maintenance so a page render never spends metered Cloud Computer time.
- **`authenticated: null` means unknown, not signed out.** `reason` says why — `no_sandbox`, `sandbox_not_running`, `probe_failed` — and the app should keep whatever fallback it had for that case.
- **`available: false` is a shape, not an error.** A user whose plan has no cloud computer gets `{ available: false, reason: 'cloud_computer_unavailable' }`, as do hosts that cannot answer (the temporary `apps verify` harness, the vite preview).
- **Facts are cached per user for a few minutes.** An app re-renders far more often than a sign-in changes. `refresh()` re-reads, but it can still see the cached answer, so an app that just drove a sign-in itself should trust what it did and not wait for the facts to catch up.
- **Only whitelisted fields cross the bridge.** Sandbox ids, owner tokens, provider errors and the raw `gh` output stay server-side.

#### Cloud worktree dev URLs

The Conductor app can run a repository's recorded dev command inside any of its
worktrees and open the exact authenticated Portal entry point. A user sandbox
has four fixed public Vercel routes, on ports `3000`, `3010`, `3020`, and
`3030`; those are the full route list because `Sandbox.update({ ports })`
replaces rather than extends the existing list. The authenticated Portal bridge
owns that list and returns each port with its `https://…vercel.run` origin.

Every sandbox command receives the compact `NOTIS_CONDUCTOR_DEV_ENDPOINTS`
port-to-origin map plus a backend-signed `NOTIS_CONDUCTOR_DEV_CONTEXT_JWT` that
binds the sandbox owner to those exact four origins. `dev.sh` atomically leases
one entry per worktree under
`/vercel/sandbox/.notis/workspaces/dev-port-leases.json`, exports the familiar
`CONDUCTOR_PORT` plus `CONDUCTOR_PUBLIC_URL`, and treats that port as strict: a
public slot can never silently fall back to an unpublished local port. The
remaining nine ports in the block keep the existing portal/backend/Electron/
docs layout internal to the sandbox. Dead process leases are reclaimed; a live
workspace keeps its slot until its dev process exits.

After the Portal answers its local readiness probe, the worktree writes
mode-`0600` artifacts:

- `.context/portal-entry-link.txt` — the complete stable auto-auth entry URL;
- `.context/conductor-dev.env` — shell exports for `CONDUCTOR_PORT`,
  `CONDUCTOR_PUBLIC_URL`, and `CONDUCTOR_PORTAL_ENTRY_URL`.

The URL is not reconstructed from a port: its query contains a persistent,
worktree-private bearer secret. `dev.sh` passes that secret only to the Portal
process; it is not exported globally or supplied to sibling services. The
Portal route verifies that secret, the backend-signed owner, and
the request's exact assigned origin. It resolves the owner's canonical email
from `user_primary_emails`, then mints a fresh one-time Supabase link on each
browser open. This keeps
one identical PR/comment URL usable across multiple reviewers without reusing a
magic link. Conductor's `workspace.sh dev-status` and `dev-url` validate the URL
and perform a non-consuming `HEAD` probe against its public route. `dev-stop`
removes the published auth artifacts while the `dev.sh` cleanup releases the
public slot. Four parallel worktrees are supported; a fifth fails closed until
one is stopped.

### Collection interactions

`useCollectionInteractions` is the canonical state machine shared by Notis Manager and apps. Import it from `@notis/sdk/interactions` when an entry point only needs interaction behavior. `NotisProvider` installs the scoped `ShortcutProvider`; standalone surfaces may install it directly.

The default contract is deliberately consistent: a plain item click clears checkbox selection and activates the item; checkbox or Cmd/Ctrl-click toggles selection without changing the active item; Shift-click and Shift+Arrow select ranges from the explicit anchor or, when that anchor was cleared, from the active item. Empty-space dragging draws a marquee, J/K or arrows move the active item and reset the next range anchor, Enter opens it, X toggles it, Cmd/Ctrl+A selects the supplied items, and Escape clears. Select All never reaches unloaded rows.

Wire list, table, or grid markup through the controller:

- Spread `getContainerProps()` on the collection container and give it the appropriate list/table/grid ARIA role.
- Spread `getItemProps(id)` on every focusable row or card. It supplies roving `tabIndex`, `aria-selected`, active state, and click/keyboard behavior.
- Spread `getCheckboxProps(id)` into `SelectionCheckbox`.
- Render `SelectionMarquee` and `<MultiSelectActionBar {...collection.getActionBarProps()} />` when their standard chrome fits the app. The controller props bind toolbar shortcuts to this collection, including when sibling app views remain mounted but hidden.
- Supply `isItemDisabled`, shortcut overrides, feature opt-outs, or `resolveNextId` for custom grid direction without rebuilding selection logic. Shift+arrows always expand or contract through the displayed ordering, independent of custom geometry. J/K remain linear `next`/`previous`; Arrow Up/Down reach the resolver as `up`/`down`, and grids can enable Arrow Left/Right with `shortcuts: { left: 'ArrowLeft', right: 'ArrowRight' }`.
- Multi-select is opt-in per view: retain `selectionMode: 'none'` for navigation-only collections. Views own their actions, permissions, confirmations, mutations and errors. Set `enableLongPressSelection: true` to enable touch selection without duplicating gesture handlers.
- Pass items in displayed order, excluding collapsed groups, other pagination pages and filtered-out rows. Offscreen items within the current scrollable collection remain eligible; disabled items do not.
- Keep the keyboard cursor separate from the opened resource. Shift+arrows and selection gestures move and scroll the cursor without opening a detail panel. Use `onActivate` for opening, not an unconditional `onActiveIdChange`; do not overwrite the item prop handlers.
- Set `clearSelectionOnPlainClick: false` only when an app deliberately wants row activation to preserve checkbox selection.
- When more than one collection is mounted, the last focused or pointer-interacted collection owns collection shortcuts. Route, detail, and modal shortcuts retain their normal higher-scope precedence.

Bulk actions use semantic `intent` defaults: archive E, star S, delete #, enable E,
disable D, pause P, resume R, move M, add-to-folder F, complete C, and start-progress P.
Keep the view's label, icon, permissions and mutation handler; omit `shortcut` to use
the default, supply a key to override it, or pass `shortcut: false` to remove it.
Custom actions have no inferred key. Avoid duplicate action keys within one collection.
Product's custom Docs updated, Social done and Cancel status actions use D, S and X;
its selected-action X takes precedence over the controller's ordinary X row toggle.
A visible active toolbar continues to consume its declared action keys while those actions
are disabled or pending, without running them or falling through to global chat/navigation.
Pending actions retain this ownership when collection gestures are temporarily disabled;
the controller retains that reservation if optimistic filtering removes the final selected
row before saving finishes. Explicit shortcut opt-out and modal/view visibility protections
still apply.
The resolved action drives the keycap, `aria-keyshortcuts` and actual binding together.
Keyboard-oriented surfaces show the keycap instead of the icon, independent of width;
coarse-pointer, non-hover touch surfaces show icons instead. Every action should supply
a fallback icon using `currentColor`, without row/status color classes. Toolbar icons
inherit the action foreground; row and detail status colors remain view-owned.
Standalone hosts without `ShortcutProvider` use the same scope, priority and active-owner
arbitration for single-key actions; registration order must not let row toggles consume
a higher-priority toolbar action.

```tsx
import {
  MultiSelectActionBar,
  SelectionCheckbox,
  SelectionMarquee,
  useCollectionInteractions,
} from '@notis/sdk/interactions';
import { TrashIcon as Trash2 } from '@phosphor-icons/react';

const collection = useCollectionInteractions({
  items: notes,
  getId: (n) => n.id,
  onActivate: (note) => open(note),
  actions: [{
    id: 'delete',
    intent: 'delete', // supplies Notis label + # shortcut
    icon: <Trash2 className="h-3.5 w-3.5" />,
    onRun: ({ selectedItems, clearSelection }) =>
      deleteAll(selectedItems).then(clearSelection),
  }],
});

return (
  <>
    <div
      {...collection.getContainerProps()}
      role="listbox"
      aria-multiselectable="true"
      className="grid grid-cols-3 gap-4"
    >
      {notes.map((note) => (
        <div key={note.id} {...collection.getItemProps(note.id)} role="option">
          <SelectionCheckbox
            {...collection.getCheckboxProps(note.id)}
            alwaysVisible={collection.isSelected(note.id)}
          />
          {/* ...card body... */}
        </div>
      ))}
    </div>

    <SelectionMarquee rect={collection.dragRect} />

    <MultiSelectActionBar
      {...collection.getActionBarProps()}
      itemLabel={{ singular: 'note', plural: 'notes' }}
    />
  </>
);
```

Semantic actions (`archive`, `star`, `delete`, or `custom`) receive selected ids/items but remain consumer-owned: the app decides mutation, confirmation, loading, error, and undo behavior. Notis defaults E, S, and # may be replaced or disabled.

Selection, active state, and the range anchor may be controlled independently. Lift `selectedIds`, `activeId`, `anchorId`, and their callbacks when selection should persist across views or detail-panel transitions. The active item is the opened/focused record; checkbox, modifier, range, and marquee gestures do not implicitly open it.

`ShortcutProvider` resolves conflicts once: modal, then detail, active collection, route, and app scope. `useShortcuts` supports chords and timed sequences such as `G I`, ignores repeats by default, and protects typing controls through Shadow-DOM-aware event paths.

Pressing `?` opens the SDK-owned shortcut help dialog. It is generated from the live shortcut registry rather than a second hard-coded list: only enabled commands for the current view and active collection appear, higher-scope conflict winners replace lower-scope commands, and selection-only bulk actions appear and disappear with selection. Give every app shortcut a concise `label` so it is discoverable there. Apps own what commands do—for example, Blog Desk can register validation, delete, and “Give feedback to Notis” actions—while the SDK owns discovery, grouping, keycap display, modal precedence, editable-field protection, and Escape-to-close behavior.

When manager chat adds current-page context to a handover draft, the active resource pill is visually separated from the app/view/database pill group. The pills remain structured composer context; the separator adds no message text.

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
| `secret` | Pointer to a credential held outside the database |

**`secret` is metadata only.** The platform never stores or returns secret material. A secret property holds `{reference, status, metadata}` — the credential's name, its lifecycle state, and non-sensitive details — and every read path replaces even that with a redacted stub (`{present, reference, status, metadata}`). Anything else sent on a write is dropped, and a non-conforming value is stored as `null` rather than kept. There is no value-resolution mechanism yet: declaring a secret property records which credential a row points at, it does not make the credential readable.

> **Deploy order (no migration needed).** The server must ship before any app declares a `secret` property. Older servers normalize unknown property kinds to `rich_text`, so a schema pushed to a pre-`secret` server silently degrades the property to plain text and stores whatever the write path sends verbatim.

---

## CLI Command Reference

The CLI command specifications own the exact options. See the generated
[CLI reference](../packages/cli/README.md). App commands include `init`, `scaffolds`, `pull`, `create`,
`link`, `build`, `verify`, `screenshot`, `deploy`, `publish`, `list`, `doctor`, and ordinary lifecycle commands.

Generated Vite scripts use `--configLoader runner` so the file-linked SDK TypeScript
config loads on supported Node 18/20 runtimes. Scaffolding also normalizes canonical
Vite commands in registry templates; custom or compound shell commands remain unchanged.
For pulled historical source with the canonical `vite build` script, `apps build`
supplies the loader at execution time and leaves the source snapshot unchanged.

## Release-only delivery

Workspace runs released app versions only. Local and cloud agents use the same workflow.
A request to create or edit app source authorizes updating that app in Workspace after checks pass.
Explicit read-only, preview-only or no-deploy requests stop at local artifacts and checks: no remote
app/resource creation or mutation, Workspace preview, deployment or live verification. Store
publication always needs separate explicit approval.

1. Inspect the effective CLI profile and the exact app's current version with `apps list --json`.
   For an existing released app, preserve local edits and pull its exact app ID into the intended
   directory. Retain the profile/app link, deployment version and revision. An unreleased container
   has no source to pull: recover its original local source and edits, or scaffold locally only if
   that source cannot be recovered. Confirm its exact ID, edit permission and personal/team scope,
   then run `apps link <app-id> <source-directory> --expected-version 0` to resume that same container.
   If a release has appeared, preserve local source separately, pull the current release into a fresh
   directory and reapply the intended edits. The link guard compares against the same remote read
   whose version/revision it saves; deploy still rejects a release racing after that read. Do not pull
   missing source or create another remote app to recover a failed first release.
2. Scaffold a new app locally, or edit the pulled source. Run `apps build` and automated
   `apps verify` before new remote creation. Missing browser tooling or failed checks blocks delivery;
   printed URLs and `--no-browser` are not passing verification. Install browser tooling with
   `npm exec --yes --package agent-browser@latest -- agent-browser install`; if needed run
   `npx --yes --package @notis_ai/cli@latest --package agent-browser@latest -- notis apps verify`.
3. Reconcile `apps list --json` and the exact intended name/slug, edit permission and personal/team
   scope. Default to personal only when no team was requested. Reuse a matching editable identity;
   stop on ambiguous matches or conflicting identity/scope. Create only when none exists, using
   `apps create "<exact app name>" .` (or `--team-id <verified team ID>`). Read back the same ID.
   A failed first release leaves a container: reuse it, never duplicate or automatically delete it.
4. Compare existing app-owned schemas. Create only necessary missing databases against that exact
   app ID. Change existing schemas by verified database ID and ownership, and only with backward-
   compatible changes before release. Read back each change. Breaking changes need separate coordination.
   Ordinary note/record edits and existing resource editors remain immediate.
5. Run `apps deploy` against the same linked app. It builds, verifies a frozen source/artifact
   snapshot with stubs, then sends that snapshot to the backend. `--skip-build` accepts only unchanged,
   valid output and still verifies. Do not bypass the backend or create implicitly on deploy.
6. Read back the exact installed app ID, integer version and Portal URL with `apps list --json`.
   Run `apps verify --mode live` and open the installed app in the actual Portal for surface proof.
   A live harness check alone does not prove the deployed bundle rendered in Portal.
7. Report **failed before activation**, **deployed but unverified**, or **outcome unknown** accurately.
   Never blindly replay an uncertain create/deploy response; reconcile its exact identity/version first.
   `apps publish --confirm-ready` is **Publish to Store**, separately approved and listing-gated.
   Workspace delivery is **Update app**, with no Store screenshot/readiness requirement.

Definite activation rejections and pre-activation upload failures become terminal CLI
idempotency results only after owned staging is reconciled. Missing readback, lost claim
ownership, transport failures and uncertain completion remain unresolved; no cleanup or
replay is inferred from an error message. Temporary verification cleanup must succeed
before delivery can report success, and interruption reports retain their activation
outcome even if cleanup fails.

### Restore historical source as a new release

Pull the current release into a fresh checkout first. Retrieve historical source into a different
folder (`apps pull <id> <historical-dir> --source-version <n>`). Replace source in the current checkout
without replacing its `.notis` profile/app link or deployment base. Update `package.json`'s
`notisAppVersion`, check compatibility with current resources, build, verify and deploy as a new
release. Preserve app/database/skill IDs. Never decrement the deployment counter, rewrite snapshots,
or claim to undo user data or external actions.

## Transactional release activation

The backend owns release authorization and activation. Delivery is **prepare → upload → transactional
activation → readback** through the service-role-only `commit_notis_app_release` function.

- Prepare source skills without modifying active contents. Capture exact resource revisions and
  content fields, because an ordinary skill editor may not advance `updated_at`.
- Acquire the existing deployment claim with an exact app-row CAS. Reserve attempt-owned skill paths
  in the same write. Renewal must match the owned revision; bookkeeping never absorbs external edits.
- Upload the frozen bundle and immutable source snapshot with no overwrite. Private skill bundles
  have attempt-unique paths. The claim journals every uploaded path, including the backend manifest.
- Lock source skills before apps, matching ownership-association lock ordering. Revalidate edit scope,
  lifecycle/deletion state, claim/version/expiry, app revision and every prepared source-skill revision.
- Activate manifest/version and skills atomically; preserve stable skill IDs, ownership and membership.
  Tombstone removed source skills. Preserve independently attached resources, automation state,
  capability grants and database contents. Write the final app row after ownership tombstone triggers.
- Upload errors and transaction conflicts preserve the previous active release. Cleanup can reconcile
  a failed claim's current revision only to abort that exact uncommitted attempt, never to activate it.
  Never clean uncertain commits; prove outcome by release ID/version readback first.
- Post-commit cache invalidation, provider work, old unreferenced runtime-bundle cleanup or local CLI
  persistence failure does not turn a committed release into an undeployed result. Source snapshots
  remain immutable; old runtime bundles are not a restore dependency.

The additive migration is `migration/20260905_atomic_app_release.sql` in the shared App/Portal project.
It is compatible with older production code and does not migrate or delete DEV data. Updated clients
use release-only delivery; old DEV clients are unsupported. No compatibility endpoint, recovery
campaign, hosted preview, restore API or new dashboard is introduced.

### Temporary test harness

`packages/cli/src/runtime/app-test-server.js` serves only explicitly selected projects during
`verify`/`screenshot`. It supports stubs, live runtime calls, selected routes and screenshot scenarios.
It has no folder discovery, watcher, Desktop registration, persistent roots, consumer leases or
Workspace mount. Servers and browser sessions close on completion or interruption. `--keep-open`
is explicit temporary triage, not Workspace preview or a passing automatic delivery check.

Workspace navigation, sidebar ordering and runtime authorization use the installed app ID and
manifest. Unreleased containers cannot hydrate runnable runtime descriptors or create resources by
being opened. Local source edits, multiple Desktop instances and restarts cannot change the running
version. Successful releases become visible through normal navigation/refresh; app URL and sidebar
position remain stable.

## Design Guidelines

Notis Apps should feel native to the Portal.

Preferred UI approach:
- **Use scaffolded shadcn components** (`@/components/ui/*`) -- do not hand-roll buttons, cards, or badges.
- **Use Notis theme tokens** -- `bg-background`, `bg-card`, `border-border`, `text-foreground`, `text-muted-foreground`.
- **Use portal shell classes** -- `notis-app-shell` for ordinary pages, `notis-app-split` plus `notis-app-pane-list` / `notis-app-pane-detail` for list-plus-detail pages, `notis-app-surface` for a flat tinted panel, `.list-row` for rows. The design bar in the shipped skill (`server/skills/notis-apps/SKILL.md`, "Design bar") is enforced by `notis apps build` and by the deploy endpoint through `server/config/notis_app_design_rules.json`; the only override is an inline `notis-design-allow` directive with a reason.
- **SDK refresh safety** -- Build refreshes template-owned SDK files before recording source provenance, rejects symlinked SDK targets, and replaces files without mutating outside hard-link targets. A failed refresh invalidates the prior build receipt.
- **Verify gates deploy** -- Standalone `notis apps verify` records `.notis/output/verify.json` as local diagnostics and runs runtime design assertions at 1280px and 390px. `notis apps deploy` always verifies its own frozen source/artifact snapshot before upload, including when reusing build output. A prior report cannot authorize deployment or bypass unavailable browser checks; no environment-variable bypass exists. Verification diagnostics are excluded from the release and its build receipt.
- **Embedded SDK stays current** -- every `apps build`, `verify`, `screenshot`, and `deploy` re-syncs the app's `packages/sdk` copy to the SDK shipped by the running CLI, so apps pick up hook and style updates without manual steps.
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
11. **One release-only delivery gate** -- Local/cloud app create/edit requests authorize Workspace updates after checks. Explicit no-deploy requests and separate Store approval remain binding.

### Unsupported shortcuts

When agents encounter older app instructions, prefer the current platform model in this document.

- `notis apps push` -- there is no push command; use `init -> build -> create/link -> deploy`. `notis apps pull <app-id>` is supported and downloads the persisted source snapshot for an installed app.
- Manual database creation is expected -- create databases through native tools, then declare slug refs in `notis.config.ts`. Use the object form with `seedDocuments: true` only for deliberate starter content that every installer should receive.
- Direct low-level tool calls instead of CLI -- use the CLI
- Raw `views/<slug>/index.js` files -- use standard React pages in `app/`
- Older dual-renderer or iframe-based assumptions

### Anti-patterns -- NEVER do these

- **NEVER assume app deploy creates databases** -- Create or update databases through native Notis tools first, then reference them by slug in `notis.config.ts`.
- **NEVER bypass the supported workflow by manually stitching together low-level save or lint calls** -- Use `notis apps pull`, `notis apps build`, `notis apps verify`, `notis apps create`, `notis apps link`, and `notis apps deploy`.
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
4. **Release-only Workspace acceptance**: two Desktop instances and a browser retain the released version after source edits and restarts. A release updates the same ID, stable route URL and sidebar position through normal refresh/navigation.
5. **Post-deploy verification**: Verify the deployed bundle via `/portal_views/get` -> `runtime_descriptor.bundle.js_url`. The signed bundle URL is the most reliable browser check in dev because it bypasses flaky local auth injection while still exercising the real runtime bridge, tool calls, and referenced databases.

---

## Where To Look In The Repo

Use these files when you need implementation detail after reading this doc:

- [AGENTS.md](../AGENTS.md)
- [server/skills/notis-apps/SKILL.md](../server/skills/notis-apps/SKILL.md)
- [packages/sdk](../packages/sdk)
- [packages/cli/src/command-specs/apps.js](../packages/cli/src/command-specs/apps.js)
- [packages/cli/src/runtime/app-platform.js](../packages/cli/src/runtime/app-platform.js)
- [packages/cli/src/runtime/app-test-server.js](../packages/cli/src/runtime/app-test-server.js)
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


## Instant-view lifecycle and cache ownership

The authenticated layout retains at most three visited app shells, including while Manager, documents or ordinary product pages are selected. Unvisited pages are never mounted speculatively. Same-app navigation changes only the route export inside the existing shell; Store installations retain their sandboxed frame, nonce checks and scoped RPC boundary. Hidden shells cannot publish page context, claim top-bar search, or initiate navigation. Without an active app target every retained shell is hidden and inactive; leaving the authenticated layout or changing the session retires them.

`AppOpeningBoundary` owns the entire host opening sequence (lazy route module, authorized descriptor, bundle and stylesheet). It shows no fake page or dashboard skeleton. A single small indicator appears only after 150 ms of continuous preparation; handing off between stages does not restart that delay. The indicator is a compact 28px pill anchored at the bottom center of the non-scrolling app-view viewport (`SidebarInset`), excluding the sidebar, with safe-area clearance, opaque inverse-theme colors, a 5px Notis-green pulse, and a scaled-down layered overlay shadow. Its label is “Opening”; the recovery state stays compact with “Still opening” and Retry. The pulse respects reduced-motion preferences. It sits above app content without covering the page with a blocking layer. After 20 seconds the indicator offers recovery. Once the real app has mounted, only the app owns missing-data placeholders. Isolated Store frames report render readiness to this same parent boundary; they do not display a second host loader.

While an uncached destination descriptor is pending, the previous route stays mounted and visible but inert. Its resource/item identity and path remain those of the displayed descriptor until the destination commits. This preserves the shell without allowing an old article's controls to act under a new article's context. Warm cached opens and background revalidation do not replace populated content.

`GET /portal_views/get?bootstrap=light` preserves authentication, entitlement, live app access checks, route/tool permissions, selected collection item ancestry, schemas and signed assets. It skips tool discovery and initial data queries. Omit the option for the legacy full bootstrap. `tools.read_cache_scope` shares reads only across routes with identical effective permissions; `access_hash` remains route-specific.

The view bridge runs blocking authentication, entitlement, descriptor hydration/signing and native database reads in worker threads so independent app requests can progress on the event loop. Live access and database-definition checks remain mandatory on cached descriptors. The cached-detail path reads the live app row and its owned database definitions together, with an exact embedded count; missing, malformed or truncated embedded sets fall back to the fully paginated database read. It never caches the live access decision or changes the returned detail payload. Cache invalidation advances an epoch under a short lock; a worker holding an older snapshot cannot repopulate the cache after invalidation. No database I/O runs while that cache lock is held. Generic tool calls also offload connection lookup, billing-user reads and credit-cap evaluation. Financial settlement remains synchronous so cancelling a queued worker cannot skip billing after a paid provider result; access, credit denial and fail-closed billing still complete before a result is returned.

The sidebar's `portal_apps/list` summary read and Portal app authentication/CLI scope checks also run in worker threads, so a concurrent sidebar refresh cannot monopolize the request event loop while a view opens. The existing 10-second, user/options-scoped summary cache retains copy isolation and uses an invalidation epoch: a summary read begun before a mutation cannot repopulate the cache after that mutation. This does not defer authentication or weaken runtime access checks.

App-view database queries include document bodies by default. Lists that only need titles and properties can explicitly use `useDocuments(slug, { includeContent: false })`: the runtime projects metadata columns and returns null body fields, while keeping authorization, filtering, sorting, and pagination unchanged. Metadata and full-content query caches are separate. Open records still use `useDocument`; full-body search must request full content when needed. This opt-in does not change generic database-tool responses or existing apps.

Fully materialized apps reuse their app-owned database rows without consulting legacy unowned databases. App detail shares one fully paginated, request-scoped owned-database read between declared database materialization and interactive metadata. App access is checked first; the snapshot is not retained across requests, newly materialized declared rows are included, and document export remains limited to source-declared databases. Catalog counts use the service-only `notis_app_active_document_counts_v1(text[])` RPC for one exact aggregate over the backend-authorized database IDs; a missing RPC during a rolling rollout falls back to the prior individual counts. Empty databases remain zero and archived rows remain excluded. Native document reads reuse the database snapshot that authorized the document for schema projection instead of performing that same authorization lookup twice; generic document-tool dispatch also runs its blocking read off the event loop.

`internalNavigation.ts` dispatches shared navigation through the save guard; `appViewNavigation.ts` owns persistent installed-app selection. It uses the Next-integrated native History API, with synchronous client-shell selection; non-view routes still use normal router navigation. This avoids a competing RSC transition that can commit an old URL after the new view paints.

Clicked destinations and back/forward navigation start their authorized lightweight descriptor in parallel with the lazy route module. These foreground preparations run at foreground priority, so they are never held behind the speculative queue’s concurrency limit, and they share the same scoped descriptor/asset promises. Isolated apps download their bundle bytes while their sandboxed host boots; they still execute only inside that frame. Host-provided rich-text and Markdown editors load on demand, with an editor-local accessible placeholder, so non-editor views do not wait for editor code.

Retained hosts keep a stable DOM order independently of their LRU order: moving an iframe in the DOM can recreate its browsing context. The isolated host receives theme state from its parent bridge and must never require local/session storage or `allow-same-origin`.

Retained component-host wrappers must preserve a definite `height: 100%` and must not flex-shrink. Otherwise the renderer's percentage-height chain resolves to content height and split layouts stop above the viewport bottom, especially with short skeletons or empty states. Do not position these wrappers: the opening pill anchors to `SidebarInset`.

For split-view sizing changes, check the real Portal with delayed initial reads and again after content resolves, including a resize. From `portal/`, run `node scripts/smokes/check-split-app-viewport.cjs --session <named-browser-session> --app-id <id> --state loading` (then `--state loaded`). The read-only check verifies top, bottom and horizontal viewport boundaries plus desktop pane heights; it fails if the requested loading state is absent. Standalone app-harness screenshots do not prove the Portal's parent-height chain.

The SDK cache reads successful snapshots synchronously, including empty arrays and null documents. `loading` denotes a missing initial response; `isFetching` also covers background refresh. Query keys include exact arguments. The host scopes caches by account/session, API environment, runtime app, bundle version and effective permissions. Query clients retain at most 100 idle entries each, 24 recent app/permission scopes; route detail and asset caches are bounded separately. Active subscriptions pin entries until detached. No persistent offline storage is introduced.

Descriptor and asset reads have a 15-second deadline. SDK cached reads default to a 30-second deadline, expose a scoped error on expiry, and retain any successful snapshot. Deadlines do not replay callbacks or mutations; late results cannot replace a successful retry. A tool call inside a custom read must itself carry `readOnly: true` (the outer `useQuery` option does not implicitly classify nested calls). Prefer `useToolQuery` for a simple tool read; it forwards that classification. An unmarked generic SQL/tool call invalidates app queries after completing, which makes it unsuitable inside a cached read and can invalidate its own result before commit.

Returning to a retained app after the default 30-second freshness window invalidates its mounted reads after paint, including reads inside a Store frame. Cached content stays visible while they refresh; retaining the shell must not bypass refresh merely because its hooks never remounted.

Mounting or navigating to a view honors the descriptor cache's 30-second freshness window. Realtime changes, app changes, asset errors and explicit retry force an authorized descriptor refresh; merely finding cached content does not force a redundant request. This does not change runtime-call authorization or the account, version and permission cache boundaries.

Storage-backed runtime descriptors batch uncached JavaScript and stylesheet signing into one private-bucket request. Existing per-path URL cache expiry is unchanged; configured external URLs bypass signing, cache hits avoid storage calls, and a single miss uses single-file signing. Batch responses are matched by path, not order. A per-file error does not discard other valid URLs; failed/malformed results are not cached, and transport failures do not fan out retries. App authorization still runs before descriptor construction.

Runtime execution discovers only the requested provider family. Its partial descriptor cache is keyed separately from a complete tools/list response, in addition to account, app, route and effective access hash; concurrent requests in the same scope share discovery. This only narrows discovery work: exact declared names, live app access, connected-account scope, surface policy, credit gates and billing remain enforced. App tool discovery/execution omits separate integration-logo metadata requests because app descriptors do not expose those icons; account and label resolution are still live. Other discovery surfaces retain logo metadata and use exact provider slugs for API requests. Runtime detail/route-list reads also skip signing Store screenshot URLs; app-detail and Store consumers retain media signing by default, and runtime bundle JS/CSS URLs still use the authorized signing path.

Writes, realtime and explicit refresh advance generations, so neither the query cache nor transport deduplication may reuse a pre-invalidation response. Access loss and confirmed auth transitions permanently retire old clients and clear evaluated bundle state. Signed URL renewal updates transport without resetting a healthy shell or stylesheet; asset failure requests fresh authorized URLs. Stale bundle completions and old-route Store publishers cannot commit into the current destination.

Installed app changes invalidate authorized descriptors and permission-scoped reads. Local source edits do not publish discovery events or alter mounted release state.

Hover/focus and newest-first chat-link preparation fetch authorized light destination descriptors and asset bytes without evaluating Store code in the Portal. The speculative asset snapshot cache is bounded to 48 entries / 16 MiB and cleared on session/app invalidation. App-owned `useQueryClient().prefetch` calls share a two-slot queue with host preparation, including isolated frames. Only small explicitly read-only requests qualify; full collections, provider sweeps, fan-out aggregates and mutations remain foreground actions.

The shared document/history/save and recent-chat preparation contract is owned by [Continuous internal navigation](portal.md#continuous-internal-navigation).

The canonical UI/authoring contract and cached-read examples live in [the shipped Notis apps skill](../server/skills/notis-apps/SKILL.md#instant-view-loading-contract-required). The CLI scaffold and bundled SDK source mirror that contract. Release the compatible host/SDK before deploying apps that rely on this behavior; this migration itself does not authorize package publication or deployment.


### Loading measurement objectives

Use public UX response-time objectives, not a private competitor account or an assumed Notion SLA:

| Navigation state | First real app skeleton or content | Initial view fully loaded |
| --- | ---: | ---: |
| Cached return | 100 ms | 1,000 ms |
| Uncached app | 1,000 ms | 2,500 ms |

These are engineering targets, not a statement that every app already meets them. The response boundaries are informed by [NN/g's 0.1 s and 1 s guidance](https://www.nngroup.com/articles/response-times-3-important-limits/); [Google's good LCP threshold is 2.5 s at p75](https://web.dev/articles/lcp). Full data readiness is a stronger condition than LCP, so do not present the two metrics as equivalent or claim a Notion comparison from them.

Measure the first app-owned skeleton separately from the host opening indicator. An absent skeleton is N/A, not zero. Record visible app readiness and outstanding/background requests separately; silent revalidation must not erase the fact that cached content was already usable. Errors, missing releases and timeouts are not successful loads. Inventory every manifest route and list apps with no routes explicitly.

Keep browser-download-cold launch, page-session/app-cache-cold navigation and retained cached returns as separate cases. State whether the surrounding shell was settled before navigation, preserve app release/build identities, and use the same protocol before and after. One sample per route is a diagnostic sweep, not repeated-run or field-percentile evidence. Record sample counts and report the slow routes alongside aggregate values.

## Independently authored reports and passive feedback

See [Reports and shared feedback](reports-and-feedback.md) for record-owned SDK artifacts, the report CLI, plain HTML navigation, and the shared opt-in feedback pattern. App views retain their shared implementation across records; reports do not deploy or replace that implementation.
