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

> This section describes the legacy App runtime, kept for accounts not yet moved to
> Spaces until its release-gated retirement. In Spaces, every database is linked to
> at least one Space and has one main view (see
> [View links, main views and agent discovery](#view-links-main-views-and-agent-discovery)),
> and Skills are linked to Spaces (see
> [Legacy App Skill paths removed (R9)](#legacy-app-skill-paths-removed-r9)).

A Notis App is the top-level packaging unit for a product experience inside Notis.

A Notis App:
- is authored as a standard **Vite + React** project using `@notis/sdk`
- is built as an **ES module bundle** (app.js + app.css) via Vite library mode
- is installed into the **Notis Portal** and rendered as a **React component** directly in the portal's React tree
- communicates with the platform through generic SDK hooks (`useTool`, `useTools`, etc.) backed by a `NotisRuntime` provided via React context
- can reference **databases**, package **views/routes**, and work with **documents**
- can bundle **automations** by reference (Skills are linked to Spaces, see
  [Source, links, Skill folders and the lock file](#source-links-skill-folders-and-the-lock-file-r5-decision-10))

Every native database is **owned by exactly one app** (`databases.owner_app_id`,
enforced NOT NULL with an `ON DELETE CASCADE` foreign key to `apps`). Creating a
database through `LOCAL_NOTIS_DATABASE_UPSERT_DATABASE` requires the owning
app's slug or id in the `app` argument; app install/materialization stamps
ownership automatically. App detail includes both databases declared by the
source manifest and databases created interactively for that app. Deleting an
app deletes its databases and their documents. Team/Public publication
snapshots remain manifest-only: interactive runtime databases and their
documents are never copied into a store listing.

Automations use one canonical association contract: an automation's
`owner_app_id` and its owning app's `bundled_automation_ids` membership change
in the same database transaction. Interactive moves use
`/portal_apps/resource-association` (`resource_type: automation` only; Skills
are linked to Spaces, never associated with an App); callers must not edit only
a bundle array because that leaves collection filters and App Details with
conflicting ownership. Resource deletes unlink bundle membership through
database triggers in that same transaction. Store
customization overlays are derived afterward with compare-and-swap retries; a
derived-state warning must never make a committed association or deletion look
like it failed. Persist associations against the installed app ID.

App display names are presentation metadata, not identifiers. The Automations
filter uses the installed app's name, with readable spaced
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
`server/lib/subscription_utils.py`); `apps_external_development` is collapsed
into `apps_builder` and is no longer read.

What is still tiered is not the builder — it is the compute and the resources an
app carries. Letting **Notis** write and deploy the code for you needs the Cloud
Computer (PRO and above). Bundled automations still need PRO+.

Reviewed native App/database tools are different: they declare PostHog `spaces`
for visibility and no App/database plan entitlement. Once their surface allows
them and `spaces` resolves true, they execute without a second App gate. Skills,
automations, and Cloud Computer work invoked during an app workflow still
enforce their own central entitlements.

Two PostHog flags gate these surfaces (`server/lib/feature_flags.py`):

- `spaces` gates Spaces, Apps, native databases, reports, their Manager
  mentions, database automations and the curated Skills that teach them.
- `spaces_store` gates only the Store: the `/store` page and its sidebar entry,
  Publish to Store in a Space's sidebar menu, the Store updates section of the
  Spaces home, the `portal_spaces/store-*` endpoints behind `notis spaces store`
  (the CLI onboarding brief offers that fallback only when `notis spaces store
  list` answers), and the legacy App Store: its endpoints (`portal_app_store`,
  `portal_app_install`, `portal_app_templates`), the publishing routes of
  `portal_apps` (listing assets, publish and editing a submission, behind
  `notis apps publish` and the App page's Publish to Store, View in Store and
  listing checklist, which hide without it), and the Store App tools that
  browse or install (`LOCAL_NOTIS_LIST_PUBLIC_APP_STORE`,
  `LOCAL_NOTIS_INSTALL_APP`, `feature_flag: spaces_store`, which also refuse at
  execution). It is a part of Spaces, so every Store entrypoint also requires
  `spaces` (a native tool's `spaces_store` is evaluated after `spaces`);
  `spaces_store` alone opens nothing. This lets Spaces ship before the Store.
- Managing a legacy App that was already published or installed from the Store
  stays on `spaces`, so an account without the Store keeps it: reading and
  withdrawing submissions, unpublishing, applying, resolving and resetting a
  Store update (and `LOCAL_NOTIS_GET_APP_UPDATE_CONTEXT`,
  `LOCAL_NOTIS_SAVE_APP_UPDATE_RESOLUTION`,
  `LOCAL_NOTIS_RESET_APP_CUSTOMIZATIONS`), and the App page's Store status
  badges, update banner, Unpublish and Reset to Store version. Unpublishing
  therefore always unlocks a published App's visibility.

The retired `store` key gated Apps, databases and the Store together before
this split. Current code never evaluates it: it reads a curated skill row's
`store` as `spaces` (the sync keeps writing `store` there until production runs
the split; see [Notis skills lifecycle](notis-skills-lifecycle.md)) and expands
a local `FEATURE_FLAG_FORCE_ON` of `store` to `spaces,spaces_store`.

After PostHog resolves `spaces=true` (and `spaces_store=true` for the Store),
the Portal may use an active team relationship to scope Team Store listings. A
team relationship never overrides a false, missing, or unavailable PostHog
decision for Spaces or Store UI, tools, or skills.

| App action / Notis tool | Minimum plan | Denied response |
| --- | --- | --- |
| Browse Store and inspect listings | Signed-in user | No billing gate; hidden unless PostHog `spaces` and `spaces_store` allow it |
| Install and run apps | FREE | No billing gate |
| Reviewed native App/database tools | No App entitlement | Hidden unless surface + PostHog `spaces` allow them |
| CLI app source/build/deploy commands | FREE | No billing gate |
| Portal source/build/publish workflows | FREE | No billing gate |
| Six native skill-management tools | FREE | Skills are an all-tier entitlement |
| Nine native automation-management tools | PRO+ (an Editor acting on a linked automation: its owner's plan) | Canonical `automations` entitlement response; `automation_owner_plan_required` for a lapsed owner |
| Cloud Computer shell/files | PRO | Canonical `cloud_computer` entitlement response |
| Notis-builds-it-for-you (sandbox authoring chat) | PRO | Canonical `cloud_computer` entitlement response |

Installing an app materializes the app UI, routes, databases and starter
documents on every tier; Apps carry no Skills (a listing snapshot published
before Skills moved to Spaces keeps its `bundled_skills`, which installs,
duplicates, activation and Store updates ignore). Bundled **automations** remain pending below
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

When the PostHog `spaces` flag is false, missing, or unavailable, the Portal
hides Spaces, the Store and installed app surfaces, direct Store/App routes
redirect to Manager, and Manager neither loads nor accepts database/app/view
mentions. When only `spaces_store` is not true, Spaces and Apps stay and only the
Store entry, the `/store` routes (which redirect to Manager) and Publish to
Store disappear; the server refuses Spaces Store requests with
`spaces_store_unavailable` and legacy App Store requests with `STORE_NOT_ENABLED`.
Active team members and owners follow the same visibility boundary. Their team
relationship scopes shared content only after PostHog resolves the flags true.

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
unstyled HTML and keeps working — see `electron/src/contentSecurityPolicy.ts`. When the
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

### Editor and owner rollout evidence

Existing grant/account creation timestamps are not reliable proof of when an
effective Editor joined a Space. The isolated ownership rollout records the
existing cohort as history-unknown, then observes future committed membership
transitions. A sole baseline survivor predates later admissions; multiple
unknown survivors require explicit historical reconciliation before automatic
owner succession. Do not invent an order from account dates or UUIDs.

Membership chronology is evidence, never another permission source. Current
access still comes from the member graph. Owner succession uses it through
`choose_notis_space_owner_successor`; native preservation must succeed before
irreversible account cleanup (below).

### Sharing, Sites, departures, the bin and account deletion

Everyone with access to a Space is an Editor. Invitations are bound to the
recipient's email and accepted by that account; Team access makes every current
Team member an Editor while they stay in the Team. The owner is the creator,
cannot be removed, and changes only through `owner-transfer` to a current Editor
or through succession at account deletion. Sites are anonymous links to one
Space or page: their actor key is `site:<link_id>`, they reach only declared
actions under a saved grant whose issuer pays, never an agent, Skill or
automation, and turning a Site off revokes it at once.

- **Departures** (`member-remove`, `leave`; `server/lib/space_departures.py`):
  "Keep a copy" defaults on and gives the departing person copies of the pages,
  databases and Skills they lose, with copied automations paused. A resource of
  theirs the Space uses stays usable: the Space switches to a copy
  (`notis_space_switch_to_copy`).
  Resources the departing person still reaches through another Space remain links in their copy, with the
  original identities and main selection. A copied view that no longer holds a database's effective main
  projects its old `create` declaration to an existing portable resource key; it never claims a new main
  or reapplies starter rows. The original source archive remains byte-for-byte intact.
  Packages carry each database's **effective** main view separately from immutable source flags. A copy remaps
  that selection to its own Spaces and bindings; if the original default is outside the selected subtree, export
  chooses an included reachable record view (name then ID). With none, a Keep a copy follows the bin rule
  (`notis_space_bin_keep_mains`): the copied database gets an auto-promoted pending main (`pending: true` in
  `main_views`) in the copy's Space that keeps it (the one holding its main, else its origin, else name then ID),
  under its current main's param (else `main`); no copied view claims it, and the copy's next publish declaring a
  main adopts it. This is how a member keeps another Editor's database that the lost Spaces link but never show.
  Any other export (a Store listing) still fails before creating anything, so its publisher adds a view first.
  The departure dialog names every refusal in EN and FR (`portal/src/lib/spaceDepartures.ts`). Fixed record-context
  bindings exist before copied mains are claimed. Rebound external views receive new immutable binding snapshots;
  incompatible grants are removed, never reused against another database. Store updates track main selection as
  a separate three-way conflict and preserve an installer's default (including an outside view) until resolved.
  Structural copy transactions capture an operation-scoped source job with immutable origin object hashes and
  target revision/ownership. The backend copies original source archives and compiled assets byte-for-byte,
  rebuilds only the target artifact manifest, verifies each target object by readback, and atomically publishes a
  new target revision plus its own source-release journal. Source/owner/binding/schema/main/grant changes fail the
  final CAS; a newer authored revision wins. Missing legacy source remains explicitly pending, never an alias to
  another Space's private source. Retry the same copy request to reconcile an interrupted upload, not a new install.
  A failed source follow-up reports `copy_saved`, `departure_saved`, the saved departure/copy IDs and the original
  request key; it is not a completed copy. Portal retains these top-level error details, locks the committed copy
  choice and retries that same receipt without refreshing away the removed member.
  Account erasure waits for surviving copied-source jobs (including its earlier interrupted copies) to finish.
  This step never restores publisher grants or borrows a recipient's provider identity; provider/custom actions
  still need that person's authorization. First-party native record UI and executable shown lists use the current
  Editor's own native binding authority.

  Pull keeps the archived source bytes and lineage intact, then applies an authoring projection of the current
  effective `params.main` values and copied resource keys to the selected definition using the CLI's static AST
  editor. Imported helpers/sibling views and unrelated files remain untouched. Database structure refresh and
  authoring projection are planned together before any file is written; ambiguous/dynamic definitions fail
  closed. The source read rechecks current main selection after archive I/O, not only when the copy was created.
  A structural SQL receipt alone is not copied-page render proof; the target journal and actual Portal render are
  separate required acceptance evidence.
- **Bin** (`trash`, `restore`, `bin`, `bin-remove`; `server/lib/space_lifecycle.py`):
  a Space moves to the bin with its whole subtree for 30 days and keeps its links
  so a restore is exact; automations created only inside it pause. A record's
  child Space belongs to the record, not to one presentation (A13): binning a
  Space that presents the record's database takes the child only when no live
  Space outside that bin entry presents the same database. Otherwise the child
  stays under its record, reachable through the other presentation, and restoring
  or deleting that entry leaves it alone (`notis_space_bin_tree`). Removal, by
  `clean_database` account maintenance or "Delete now", deletes the Spaces and
  their pages. A database with no other Space link follows the Space into the
  bin, returns on restore, and is deleted when that bin entry is purged. Other
  linked Spaces retain their database. Skills and automations retain the separate
  standalone-preservation policy for the person who binned them.
  Storage objects are removed with receipts.
  Native-source cleanup freezes a versioned exact-object plan before source journals
  are deleted, including unpublished releases. Fully verified objects owned by those
  native releases are eligible in `space-source`/`space-code`; historical App-backed
  archives remain lineage, never deletion authority inferred from a path. Verified
  native releases retained by another copy get a private ownership claim before
  their source rows disappear. Exact historical consumers link that claim to their
  later bin entry. Cleanup rechecks every Space, pending copy and Store reference,
  retires the native namespace, then verifies bytes and absence against that same
  claim. Old unclassified receipts cannot be retroactively converted into claims.
  Surviving
  revisions, Store snapshots and pending copied-source jobs retain their originals.
  Unverified/in-flight declarations stay explicitly blocked with their frozen object
  and verification journals. Purge retires their exact server-owned release namespace
  against late uploads/references, but this fence grants no guessed deletion authority.
  Same-name byte/version/metadata replacements are fenced; access-time-only updates
  remain harmless. Cleanup verifies bytes before deletion, physical absence afterward
  and the exact database receipt. Old path-only receipts require ownership audit;
  they prove neither deletion nor permission to purge a persistent archive.

- **Account deletion** (`server/routers/portal_user_delete`): the handler calls
  `prepare_notis_space_account_deletion` (owned Spaces go to the successor or to
  the bin, the account's resources used by Spaces are transferred or copied,
  departures and revocations run, grants the account issued are disabled with
  `issuer_account_deleted`) and requires `read_notis_space_account_preservation`
  to report the data preserved before the Team preflight; any failure returns
  409 `space_account_preservation_required` before anything irreversible.
  `purge_notis_account_spaces` runs before the account rows are removed.

- **Space Store** (`server/lib/space_store.py`, `store-*` operations,
  `notis spaces store ...`): any current Editor publishes a Space with its
  sub-Spaces and the databases, Skills and automations they list as the next
  version of a listing (a child Space can have its own listing). Team listings
  publish at once for that team; public ones wait for a reviewer (never the
  publisher) and store the package and its diff only, with no external registry
  call. An install is an independent copy through the package engine (structure
  plus explicit starter rows, installer-owned, no grants). An update is three-way
  per package key: what the publisher left unchanged keeps the installer's
  version, publisher-only changes apply, and both-changed keys become conflicts
  that keep local content until `keep_mine` or `take_theirs`. Where a sub-Space
  sits is its own key (`tree:`), three-way on its parent: a publisher move carries
  (through `move_notis_space`) when the installer left the Space where it was, an
  installer's move stays, and both moving it elsewhere is a conflict (the same place
  is not). A move into a Space the copy no longer has stays put and is reported; one
  that would put a Space inside itself becomes a conflict. Each conflict carries the
  name of the installer's copy of the item (`conflict_items`). Unpublishing stops
  new installs and leaves copies untouched. In the Portal, the sidebar Store
  (`/store`) is the Space Store for an account on Spaces (your team and everyone,
  with install, update and unpublish); the App Store there stays only for accounts
  not yet moved, until the legacy runtime's release-gated retirement, and nothing
  redirects between the two. The Spaces home lists only installed copies with an
  update or a conflict to settle.

Rollout: the SQL lives in `migration/pending-production/20260926_spaces_*.sql`
and `20260927_spaces_*.sql` and is installed only on the isolated Spaces project
until the migration plan's acceptance gates pass. Account-deletion tests use
disposable accounts only.

#### Site origin

A Site runs its author's code, so it never runs on the Portal origin, whose localStorage holds the
Portal session and whose script-readable Home Screen cookie carries a refresh token. Site links are
`{DOMAIN_SITES}/s/<key>#<bearer>` (`server/lib/space_site_origin.py`), where `key` is the first 16
hex characters of SHA-256(bearer). Without a separate Site origin (unset, malformed, or sharing a
site with a Portal or API host) Sites are not available: `GET /portal_spaces/sites` answers
`available: false` with no links, and turning a Site on, for a Space or a record, is refused with
`409 sites_not_available` before anything is read or written (`set_space_site` in
`server/lib/space_membership.py`). Turning an existing Site off keeps working, and every Site still
on stays visible with a way to turn it off. The share dialog then no longer mentions publishing in
its description and its Site section shows "Sites aren't available yet" without the switch (with the
switch, to turn it off, when the Space's or the record's own Site is still on). The dialog's section
covers only those Sites (`siteFor` in `portal/src/lib/spaceSharing.ts`): a record-param Site
(`record_key` set) is managed from that record's Share popover. The popover shows "Sites aren't
available yet" without "Create public link" when no Site is on for the record; a record Site still
on shows as shared, without a link to copy, with "Stop sharing" (`site()` in
`portal/src/lib/spaceRecordClient.ts` reports it with a null `url`, as it does a lost link while
Sites are available). "This site's link is unavailable" appears only when a Site is on, Sites are
available and its link could not be derived (a signing-key rotation). A Site host build without a usable Site origin says the site can't open here instead of
asking to reopen the link. Production has no Site origin until the Sites domain is
chosen, and the Main import copies no Site rows, so no Site exists there until then. Production uses
its own registrable domain, never a `notis.ai` subdomain:
localStorage is per origin, but cookies are per domain, so a subdomain could set `Domain=notis.ai`
cookies that reach the Portal and API (cookie tossing, for example a planted Home Screen session)
and would be same-site with them, and the same host shares host-only cookies on every scheme and
port.

Both sides enforce it. `site_origin()` refuses a `DOMAIN_SITES` whose host is, or shares a
registrable domain (eTLD+1 by the Public Suffix List, private section included as browsers apply
it, so `a.vercel.app` and `b.vercel.app` stay separate) with, any Portal or API host, compared by
host whatever the scheme, port or path: `DOMAIN_PORTAL`, `DOMAIN_PORTAL_PUBLIC`,
`NEXT_PUBLIC_APP_URL`, `DOMAIN_WEB_SERVER`, `DOMAIN_WEB_SERVER_PUBLIC`,
`DOMAIN_WEB_SERVER_INTERNAL`, plus `app.notis.ai`, `beta.notis.ai`, `api.notis.ai` and
`api-beta.notis.ai` whatever the configuration. Two loopback hosts (`localhost`, `*.localhost`,
`127.0.0.0/8`, `::1`) pair only in development (`ENV=dev`), and never as the same host. A refused
origin behaves as an unset one (no Site links, no Site CORS) and logs one warning per
configuration. The Portal's `siteOrigin()` (`portal/src/lib/siteOrigin.ts`) applies the same rule
to `NEXT_PUBLIC_SITES_URL` against the same Notis hosts, `NEXT_PUBLIC_APP_URL` and
`NEXT_PUBLIC_SERVER_URL` (not in the Site host build, whose API address is the one its Sites call
anonymously; the API checks its own hosts), pairing loopback hosts only in a development build;
when it refuses, the Portal hands no Site over and the Site host runs none. The list comes from
libraries that bundle it and never fetch it at runtime: `publicsuffixlist` on the API (pinned in
`server/requirements.txt`; bump the pin to refresh the list) and `tldts` in the Portal.

All Sites share the Site origin, so one Site's code must never receive another Site's bearer:

- **One document per Site.** Each Site link has its own path, so opening another Site in a tab is
  always a new document. With one shared path, a Site open in the tab (or one that set its own
  address to that path with `history.replaceState`) would receive the next Site link as a fragment
  change in its own document and read its bearer.
- **The bearer leaves the address at once.** The Site host's first head script
  (`portal/src/site/siteBearer.ts`) moves the bearer into the history entry's classic
  `history.state` and shows `/site?space=&record=&selection=`, which names no Site and carries no
  key. The Navigation API lists other same-origin documents' entries with their URLs (and their
  Navigation API state), never their classic state, so the bearer is never kept in the URL,
  Navigation API state, sessionStorage or localStorage. `/site` never takes a bearer from its
  address. `SpaceSiteHost` reads the bearer once, checks its key and keeps it in every entry it
  pushes, so back, forward and reload work. Copying an open Site's address does not share it: the
  page then says to open the original link again.
- **Nothing shared between bundles.** The Site host exposes React to Site bundles as frozen copies
  on non-writable `window` properties (`portal/src/site/SiteReactGlobals.tsx`), keeps loaded
  bundles in a module-scoped cache instead of `window.__appBundleCache`, and ignores the Portal's
  bundle source preload global (`portal/src/lib/appBundleLoader.ts`).

The parts:

- **Portal `/site`** only hands the address over: a head script in the root layout takes the bearer
  out of the Portal address before analytics or the Portal app start, derives the key with
  WebCrypto and leaves for the Site's own link on the Site origin (same view query).
  `portal/src/app/site/SiteHandoff.tsx` covers Portal-internal navigations, Desktop (system
  browser) and a missing origin or WebCrypto (the page says the link is unavailable). It never
  imports the Site host, `AppViewRenderer` or the bundle loader (`portal/src/app/site/page.test.ts`).
  Existing `{portal}/site#<bearer>` links keep working this way.
- **Site host**: the Portal codebase built with `NOTIS_PORTAL_TARGET=site` (`npm run dev:site`,
  `build:site`, `start:site`; distDir `.next-site*`). Only `*.site.tsx` routes exist there
  (`portal/src/app/s/[key]/page.site.tsx` for links and `portal/src/app/site/page.site.tsx` for
  open views, both `portal/src/site/SpaceSiteHost.tsx`, under the root layout
  `portal/src/app/layout.site.tsx`): no Portal API routes, middleware, rewrites, analytics,
  third-party tags or Desktop code. Its Supabase client never stores a session, and it calls the API
  at `NEXT_PUBLIC_SERVER_URL`. It runs a Site only when the page origin equals its build-time
  `NEXT_PUBLIC_SITES_URL`, never on a hosting alias such as a `*.vercel.app` address. Every
  response sends `frame-ancestors 'none'`, `base-uri 'none'`, `worker-src blob:` (no Service
  Worker can sit in front of other Sites), `X-Frame-Options: DENY`,
  `Cross-Origin-Opener-Policy: same-origin`, `Referrer-Policy: no-referrer` and `nosniff`.
- **API**: `SiteOriginMiddleware` runs before every other middleware (`server/main.py` registers it
  last; `server/tests/test_space_site_origin.py` checks the real app). It answers the Site origin
  only for `POST` on the Site routes (`site-open`, `get`, `children`, `records`, `presentation`,
  `navigate`, `action`, `data`, `schema`, `record-view`, `shown`), with CORS for that origin, no
  credentials, and Authorization and Cookie removed before any other middleware sees them. Any
  other HTTP request from it is `403 site_origin_forbidden`, even where the development CORS
  pattern matches, and every WebSocket handshake from it is refused (close code 1008). The Spaces
  handler also refuses a Site-origin request without its Site token (`site_operation_unavailable`).
  From the Portal origin, Site reads still work, anonymously, only with the token.
- **Local development**: a `dev.sh` stack that starts the Portal also serves the Site host on
  `http://127.0.0.1:<PORTAL_PORT - 20000>` (another host than the `localhost` Portal, so not even
  host-only cookies are shared) and sets `DOMAIN_SITES` and `NEXT_PUBLIC_SITES_URL` to it. A
  headless stack starts no Site host and gives the backend an empty `DOMAIN_SITES`, so it issues no
  Site links. That loopback pair is accepted only in development: the backend runs with `ENV=dev`
  and the default stack serves development builds. A `PORTAL_MODE=prod` stack builds production
  bundles, which refuse it wherever they compare a loopback address: a Portal with a loopback
  `NEXT_PUBLIC_APP_URL` or `NEXT_PUBLIC_SERVER_URL` hands no Site over, and a Site host with a
  loopback `NEXT_PUBLIC_APP_URL` runs none, while the backend still issues Site links.

Remaining risk, which per-Site origins (a wildcard domain on the Public Suffix List) would remove:

- Sites share the origin's storage: one Site's code can read and change what another Site's code
  stored there (localStorage, IndexedDB, Cache Storage, cookies).
- A Site can list the addresses of other Sites' views opened earlier in the same tab (Space and
  record ids and the view selection, never a bearer or a key).
- A Site link whose page was left before its first script ran keeps the bearer in that history
  entry's URL. A Site opened later in the same tab can read it through the Navigation API, unless
  the link was opened with a `no-referrer` policy (the Portal's browser handoff and links between
  Sites are).
- The API's credentialed CORS patterns (`server/lib/api_cors.py`) still match origins other than
  the configured Site origin: `localhost`, `127.0.0.1`, `*.ngrok-free.app` and `*.vercel.app` names
  in the shapes of the `notis-portal` project on team `mind-the-flo`, which the Portal's previews
  use against the Beta API: `notis-portal-mind-the-flo.vercel.app`, commit URLs
  `notis-portal-<9-character hash>-mind-the-flo.vercel.app` and branch URLs
  `notis-portal-git-<branch>-mind-the-flo.vercel.app`, including Vercel's shortened form for a
  long branch (`-git-<cut branch>-<6 hex>-`, which may contain `--`). The pattern matches names,
  not hosts proven to be ours: `<name>.vercel.app` goes to whoever deploys a project of that name
  first, so a project named in one of these shapes elsewhere would match too. The bare
  `notis-portal.vercel.app` (no project of ours) and author URLs
  (`notis-portal-<member>-mind-the-flo.vercel.app`, unused by the previews) are refused; a member
  name of exactly 9 letters or digits has the commit URL shape and is answered. Every other
  `*.vercel.app` name is refused, so the Site host project, which is never named with the
  `notis-portal` prefix (for example `notis-sites`), gets no credentialed CORS on any of its
  hosts. That exposes nothing while the API authenticates only with the Authorization
  header; a cookie-based API credential would need the local and tunnel patterns narrowed first.
  The production Site host keeps its `*.vercel.app` URLs behind Vercel Deployment Protection so
  only its own domain serves it.

### Selected Space source verification during the cutover

Spaces, Apps and SDK reports use the canonical SDK Shadow presentation. The
selected-Space verifier renders through that same component with a synthetic
runtime; no iframe SDK host or postMessage transport remains. Space bundles must
export `SpaceView` exactly. Shadow DOM provides style isolation only, not isolation
from same-origin JavaScript or credentials. Current backend access, declared
actions, record context and receipts remain enforced on the supported API path.

The host separates presentation selection, authenticated session and transport
credential lifetime. Selection or a token refresh within the same login preserves
drafts; a changed account, record, release or access scope retires the old
transport. Source-visible descriptors are separate from the transport's private
authority snapshot. Exact pinned obsolete SDK files are removed during embedded
SDK refresh; modified/additional files are retained for explicit reconciliation.
These implementation boundaries still require source rebuilds and live
Portal/Desktop acceptance before declaring a migrated account ready.

Each database binding in the source-visible descriptor may name a generic
`operations` entry per operation, the adapter that `useNativeDocuments` and
`useNativeMutation` call. It is always one declared, currently granted action:
the only one for that binding and operation, or, when a binding declares several,
the single one whose request is the unconstrained native transport (an open
`{type: "object"}` request or exactly the generic tool's request schema). Narrower
actions on the same binding, such as a one-record body read or a body-only update,
stay callable by their own action ID only. When no single action qualifies (two
unconstrained actions, or only differently constrained ones), the binding exposes
no generic operation and the view calls its actions by ID. Every action keeps its
own grant, input schema and read-only classification; the generic mapping never
merges, guesses or widens them (`server/lib/space_descriptors.py`).

The Spaces protocol is feature-gated independently of the legacy app commands.
Use an exact source key and destination Space when authoring an existing Space:

```bash
notis spaces pull <space-id> ./space-source
notis spaces build . --space overview
notis spaces verify . --space overview --space-id <space-id>
notis spaces deploy . --space overview --space-id <space-id> --request-id <stable-release-key>
```

By default, verification checks authorization for actions outside the reuse map and publication
authorizes actions not supplied by `--reuse-grants`. For a permission-preserving
source update, add `--reuse-grants-only` to verify, preview or deploy and provide the
complete action-key → existing-grant-ID map with `--reuse-grants`. The typed source
request pins `authorization_mode: "reuse_only"` in verification and the immutable
release plan; changing the mode requires a new request ID. Omitted actions retain
their complete declarations but have no grant or runtime capability. No action is
authorized implicitly, including during preview. This mode requires already-bound
databases: prospective database creations/additions are refused because ordinary
promotion would authorize their native actions. Skill/link/version/source CAS and
the final grant, issuer, binding and provider checks still apply.

#### Source, links, Skill folders and the lock file (R5, decision 10)

`notis spaces pull` writes three things next to the source: the Space's links as
`resources.json` (`[{kind, id, alias}]` for databases, Skills and automations;
document links are record links and stay out of the list), every editable linked
Skill as a full bundle under `skills/<alias>/`, and a local lock in
`.notis/space-lock.json` recording the pulled list and, per Skill, its ID,
binding, binding revision, content version and folder hash. The lock is
local-only state like `space-source.json` (`.notis/` is git-ignored by the
scaffold and excluded from every archive); `resources.json` and `skills/` are
not part of the portable definition either: they are regenerated from the
server on pull and never travel in the source archive. A Skill listed without an
editable folder (unreachable link, curated install) is reported and skipped.
If an earlier source snapshot contains an editable linked Skill folder, pull
projects that Skill's verified current head over only the exact downloaded folder.
It checks the local snapshot before atomic replacement, retains unrelated source,
and refuses changed or unsafe local files. Archived Skill bytes never become a
second authoritative head or an implicit Skill edit on the next deployment.

`notis spaces deploy` and `notis spaces preview` compare the working tree with
the lock and send only what changed since the pull: an edited folder becomes a
Skill edit expected at the pulled content version, a new folder under `skills/`
becomes a new Skill linked to the Space under the folder name, a deleted tracked
folder or a removed list entry becomes a link removal (decision 9 when it was the
last reachable link), and a new list entry becomes a link addition with R3
authority. Unchanged folders and entries are skipped, so edits and links made
elsewhere since the pull are kept. The server checks every item against the
live Space before any upload: an item that changed on the server and locally is
named (`space_source_conflict`), the reply points to `notis spaces pull`, and
nothing is changed. A folder cannot rename a Skill (use `notis skills update`),
a list entry cannot rename an alias, and a resource the definition declares
cannot be unlisted by the same release.

An added existing database may be consumed by the same source under its new
alias. Verification checks the publishing Editor's R3 authority on that database
before reading its current native schema, then pins a prospective binding identity
to the Space, actor, base revision, alias and database. It does not attach a link
or create a grant. Sealing preserves those exact pins; native actions that use a
pending binding remain unavailable until promotion, so preview rendering uses
the declared verification fixtures. The existing database's schema is never
rewritten by linking it. An alias collision, lost Editor access or schema change
requires fresh verification, not an implicit retarget or pre-link workaround.

The release plan carries the pending changes and journals each Skill bundle as
a release object (`skill:<alias>`), verified like the source. A sealed candidate
(preview) applies none of them. Promotion, and therefore `deploy`, commits them
in one transaction through the existing writers (`begin/commit_notis_space_skill_edit`,
`begin/commit_notis_native_skill_creation`, `change_notis_resource_links_v2`) right
after the candidate assertion and before the live pointer moves, then records
the outcome in `space_source_releases.applied`. New databases and their bindings
are prepared before the link writers; starter rows and exact native grants are
materialized only after all links exist. A new database's starter relation can
therefore reference an existing database added in the same release. The ordinary
six-argument link writer remains the empty-pin route; pinned binding identities
participate in replay matching. A failure anywhere leaves the
previous release, every Skill and every link unchanged, and a replay by request
ID returns the same `applied` result only for the original actor while they remain
a current Space Editor. After the commit the server publishes one
review report per changed Skill (R6, the same intents `notis skills update`
reviews) and returns the links; a retry returns the same links. The CLI then
rewrites the lock and `resources.json` from the applied result, so the next
deploy diffs against the new baseline; `notis spaces promote <release-id> [dir]`
does the same for a promoted preview.

Verification and deployment render the selected frozen build with **synthetic
fixtures only**. They do not execute native/provider actions to discover what a
view needs. Declare a source-relative `verificationFixtures` JSON file in the
Space definition when its initial rendering invokes actions:

```json
{
  "actions": {
    "load": [{ "inputs": {}, "result": { "rows": [] } }]
  }
}
```

Fixture inputs must exactly match a declared action's input schema and one case;
unknown actions, absent cases and broad tool/request transports fail verification.
Use fictional populated/empty cases, never exported account content or credentials.
The diagnostic records exact source/artifact/fixture/renderer identities; it is
not a reusable approval stamp. Initial deployment verifies its captured bytes.
After an uncertain publication reply, retain the source bytes and request ID so
the original concurrency check and release intent can be reconciled. Containers
report rendering as not applicable rather than a UI pass. Store publication remains
a separate operation and approval boundary.

For a presentation that initially opens a Markdown body, the same fixtures file
may declare `documentBodies: [{ request, result }]`. The request is an exact
`{ operation: "read", binding, recordKey, readAction }`; the result contains
`record_key`, `title`, `revision`, `schema_revision`, and `content_markdown`.
Use fictional record keys and content. The harness checks the declared canonical
native QUERY action and its input schema; it never contacts the API or provides
body Save during offline verification. Exercise saving separately on the isolated
stack, including first-save bootstrap, exact receipt retry and grant revocation.

#### Native provider reads: explicit issuer grants

Native PostForMe support is limited to `LOCAL_POSTFORME_GET_POSTS` and
`LOCAL_POSTFORME_GET_POST`, through the ordinary declared-action/grant APIs.
Authorization resolves exactly one current account from the authorizing Editor's
fixed `platform` and `account_label`, then pins its connection ID and identity.
The caller still needs current Space/action authority; provider access and billing
belong to that saved issuer, never an undeclared owner or a same-label replacement.

- Posts lists declare exactly those selectors, a fixed integer `limit` from 1 to
  50, fixed nonempty unique `status` values (`draft`, `scheduled`, `processing`,
  `processed`), and `offset`. Only offset may be a required integer input with
  explicit minimum/maximum inside 0–10000; a fixed offset also works.
- One-post reads declare exactly the two selectors and `id`. Only ID may be a
  required string input: `minLength` at least 1, `maxLength` at most 200 and
  `pattern: '^[A-Za-z0-9_-]+$'`; a fixed matching ID also works. The exact returned
  post and its structural account association are checked before data is exposed.
- Input envelopes remain closed. No arbitrary native tools, caller-selected
  accounts, feed/results/write operations or account metadata synchronization run
  through this adapter. Connection identity/permission changes or disconnection
  revoke the saved grant; reconnecting does not revive it. Receipts keep existing
  replay, settlement and issuer billing behavior.
- Record Sites cannot invoke these provider reads. Agent renders use declared
  read-only actions; background renders still refuse paid or unknown-cost reads.

Better Stack monitoring supports only `BETTER_STACK_LIST_MONITORS` with fixed
`{page:1,per_page:50}` and `BETTER_STACK_LIST_HEARTBEATS` with fixed `{page:1}`,
with no runtime inputs. The adapter selects exactly one active private issuer-owned
Composio account and pins its connection identity/revision and tool version. It
never creates a session or account label, selects a caller account, or retrieves an
API token. Connection/credential changes fail closed before dispatch and result
projection, including replay. Heartbeat ping URLs and authentication fields are
not exposed; the read result contains only the monitoring fields used by the view.
Ordinary receipt settlement and saved-issuer billing still apply. Record Sites
cannot invoke these reads. Other Better Stack operations need separate adapters.

GitHub GraphQL supports only `GITHUB_RUN_GRAPH_QL_QUERY` with a fixed query
document and typed variables (`server/lib/space_github_reads.py`). Arguments are
exactly `{query, variables}`: `query` is fixed text, never an input, and each
GraphQL variable is either a fixed scalar or one required input. The admitted
subset is one `query` operation (a shorthand `{...}` is normalized to it) whose
root fields are `repository`; non-null `String!`, `ID!`, `Int!` or `Boolean!`
variables without defaults; field selections with aliases and distinct response
names; and arguments that are declared variables or integer literals.
Mutations, subscriptions, several operations, fragments (named or inline),
directives, string/block-string/float/enum/boolean/null/list literals,
list types, introspection fields and reserved root response names
(`data`, `errors`, `extensions`, `results`, `partial`, `successful`, `error`)
are refused, as are documents over 16384 characters, 10 levels or 512 fields.
Expanding the subset requires an explicit behavior test.

Run `compile_github_graphql_template` (or `canonical_document`) before source
packaging: it drops comments and insignificant whitespace/commas, and validation
refuses any other spelling, so the stored canonical text participates in source,
template, grant and invocation digests. A saved grant never admits a changed
document; execution sends exactly the stored text with the rendered variables.
String inputs declare `minLength`/`maxLength` (at most 256), integer inputs
`minimum`/`maximum` inside GraphQL Int, or an `enum`/`const`; the adapter
re-checks rendered values against those schemas before dispatch.

Authorization selects exactly one active private issuer-owned Composio GitHub
OAuth2 account (no viewer, label, API-key or first-match fallback; none or
several refuse with `connection_unavailable`), checks that the pinned tool
version takes a string `query` and object `variables`, and pins the account
identity, tool version and SHA-256 of the canonical document. Token refresh
under the same account is credential maintenance; a new account, owner, auth
configuration, granted scope, disable or revocation fails closed before dispatch
and before receipt projection, including replay. The grant is read-only; the
result contains only the selected response fields (unselected provider fields
are dropped, `partial: true` marks GraphQL errors next to data, and a response
without data is unsuccessful). Receipts, replay, settlement and saved-issuer
billing are unchanged. Record Sites cannot invoke this read, and background
renders refuse it like other provider reads.

`LOCAL_NOTIS_LIST_REMINDERS` is the only native reminder action supported in a
Space. It takes no runtime inputs and fixes an integer `page_size` from 1 to 100
in the approved template. The result belongs to the saved issuer, never the
current viewer, and uses the canonical reminder-list pagination semantics. No
cursor selector, reminder write, schedule, or other native tool is enabled.
Current issuer/viewer authority is rechecked before dispatch and receipt replay;
record Sites cannot invoke it.

#### Viewer reads: explorer Spaces see what the viewer can open

A Space page normally reaches only the resources its Space links, through
declared actions that run with the saved issuer grant. An explorer page (a
database catalogue, a Skill graph) instead declares **viewer reads**: it shows
each signed-in viewer everything that viewer can already open, with that
viewer's own authority. There is no grant, issuer or billing, and no write.

```ts
export default defineSpace({ name: 'Catalog', entry: './view.tsx', viewerReads: ['databases'] });
```

- Families: `databases` allows `list_databases`, `get_database` (schema) and
  `query_database` (rows, count, aggregate or search through the native query
  normalizer); `skills` allows `list_skills` (optionally `include_content`,
  paginated by `after`/`limit`) and `get_skill` (content). Content is read
  with one snapshot per Skill, eight at a time; the SDK's `useViewerSkills`
  starts the next content page from a quick read without content (its cursor),
  at most two content pages and one cursor read at a time so a large inventory
  never takes every API worker, and drops a page whose cursor no longer
  matches. A Space bundles the SDK when it is built; Spaces built with an earlier
  SDK read one page after another, so the Portal's viewer-read bridge reads ahead
  (`spaceSkillPagesAhead.ts`) for lists read to the end: the SDK's own Skill
  pages (every SDK version reads all pages, `limit` 100 with an explicit
  `include_disabled`), and any other list once the Space asked for one of its
  later pages. With such a content page it sends the same page without content
  (the cursor) and starts the next content page from it, hands that page over
  when the Space asks for exactly that cursor within 30 seconds, sends identical
  reads in flight once, and holds at most one page ahead per list. A read started
  before a change the view is told about (its query cache invalidated, by the
  view, its host or a live signal) is never shared with or handed to a read asked
  after it. Each request is an ordinary viewer read with the same checks. A list
  that fits one page costs one extra quick read; a Space that reads only a first
  page of a longer list of its own costs nothing more, while an SDK Skill read
  of a longer list starts its next content page at once. The built manifest
  carries `viewer_reads` sorted; it is absent when none, containers cannot
  declare it, and `spaces verify` returns it as `capabilities.viewerReads` and
  names it in its summary so the reviewer sees it before publishing. It travels
  in Store packages with the manifest.
- Server path: `POST /portal_spaces/viewer-read` with `{space_id, revision,
  operation, input, document_id?, preview_release_id?}`
  (`server/lib/space_viewer_reads.py`). It is not a Site operation: any link
  credential is refused (`site_operation_unavailable`), an anonymous caller gets
  `sign_in_required`. The same `resolve_space_execution` as actions resolves the
  exact live revision or an Editor-gated preview, the viewer must be a current
  Editor (`editor_required`), and the executable revision must declare the
  family (`viewer_read_undeclared`). Unknown or write operations fail with
  `viewer_read_unsupported`; inputs are closed per read (`invalid_viewer_read`).
- Scope: resources come only from the viewer's own inventories
  (`list_notis_database_inventory` and `list_notis_skill_inventory` with
  `p_actor` = viewer): their standalone resources plus those linked in Spaces
  they can open. Links that are not available (R10) are never returned or
  followed; a database or Skill reachable only through them, or belonging to
  someone else, answers `database_unavailable` or `skill_unavailable` (404).
  Schema and rows then go through `describe_native_database` and
  `execute_native_data(operation='query')` as the viewer, so the native resolver
  rechecks access in SQL. Skill content comes from `with_skill_content`: present
  for Skills the viewer can edit, `null` for curated installs and legacy Skills.
- Catalog facts: each `list_databases` entry also carries `updated_at`,
  `documents_count` (stored count, else active documents) and
  `owner_space_id`/`owner_space_name`, the root Space the database came from
  (a converted App), named only when the viewer reaches it through that root or
  owns it; otherwise the root of its first available link, or `null`. These are
  presentation only and come back `null` when they cannot be read. The list
  always rebuilds the inventory; `get_database` and `query_database` reuse the
  viewer's inventory for up to 60 seconds (one rebuild before refusing an ID it
  does not hold), because the resolver rechecks access on every read.
- Runtime: the descriptor lists `viewerReads` only for a signed-in viewer
  (never on a Site). In source, gate on `useViewerReadAvailable(family)` and
  read with `useViewerDatabases()`, `useViewerSkills({ includeContent })` or
  `useViewerRead(operation, input)`; the SDK guard refuses undeclared families.
  Results are cached per viewer through the Space cache scope.
- Offline verification serves them from fixtures:
  `"viewerReads": { "list_databases": [{ "input": {}, "result": { "databases": [] } }] }`,
  only for declared families, with fictional data. To check the live answer as
  yourself, run `notis spaces viewer-read <space-id> <operation> --revision <n>
  [--input '<json>']`.

#### Cloud computer in Spaces (`cloudComputer`)

A Beta App that declared `capabilities.cloudComputer: 'shell'` ran
`LOCAL_NOTIS_RUN_SANDBOX_SHELL` and `LOCAL_NOTIS_UPLOAD_SANDBOX_FILE` from its views once the
viewer consented (`cloud_computer_shell`); that is how Conductor's Check dev, Sync, Archive,
Connect GitHub and environment file upload ran without a conversation. A Space gets the same
power, and no more, through one reviewable declaration (`server/lib/space_cloud_computer.py`):

```ts
export default defineSpace({ name: 'Workspaces', entry: './view.tsx', cloudComputer: 'shell' });
```

- **Declaration.** `read` returns the sanitized facts of `useCloudComputer()`; `shell` adds
  `run` (one non-interactive command) and `upload` (one file, at most 1 MiB, written from the
  browser's bytes, never from a URL). The manifest carries `cloud_computer`; containers cannot
  declare it; `spaces verify` names it in its summary. Source calls it through
  `useCloudComputerShell()` (`level`, `status`, `requestApproval` for either level; `run` and
  `upload` when `available`, that is `shell`) and `useCloudComputer()` (facts, plus
  `requestApproval()`); once the viewer allows it, every mounted facts read runs again. No
  registry tool is reachable by name, and `env`, `diagnostics`, file listing and download are
  not offered (a `cat` through `run` reads what the view needs).
- **Whose computer.** Always the signed-in viewer's own cloud computer, as that viewer, with
  the tool's own `cloud_computer` entitlement, sandbox path and credit checks; never the Space
  owner's or a grant issuer's. Sites, link bearers, CLI-scoped tokens
  (`cloud_computer_portal_only`), agent renders and verification harnesses never get it; the
  viewer must be a current Editor. Dispatch uses Beta's views surface (`portal_views`): a shell
  call syncs the viewer's skills first (Conductor runs `workspaces-shared` scripts), and a file
  write never starts a stopped cloud computer. Out of credits answers `credit_cap_reached`
  (402); a credit check that cannot be read never refuses the run (billing outages fail open,
  #2494). A run whose charge could not be recorded is audited as `billing_failed_after_run` and
  answers `cloud_computer_usage_unrecorded` (502, never run again for that request).
- **Approval.** The viewer approves it for their own cloud computer in a Portal prompt
  (`SpaceCloudComputerApproval`) that names the Space and the level, says who released the code
  it asks for (you, including your agents and the CLI; another person by first name or email;
  copied in from another Space or the Store; or not recorded) and whether it is an unreleased
  preview. The status read carries these facts as `release` (`preview`, `released_by`,
  `copied`) while it is not approved; they inform the person and never decide anything. The
  view can open the prompt with `requestApproval()` but never answer it: the `approve` call lives
  only in host code and runs on a trusted click, the prompt ignores clicks for its first 600 ms
  and focuses "Not now", and a retained Space that is not on screen cannot open it (its request
  answers not approved, and an open prompt closes when the Space leaves the screen). It is saved as a
  Space grant (`space_tool_grants`, issuer = viewer, tool `NOTIS_SPACE_CLOUD_COMPUTER`, template
  `{level, revision, revision_digest}`, a fresh random token per approval), so it is listed with
  `GET grants`, withdrawn with `grant-revoke`, and disabled with the viewer's other grants when
  they lose access or delete their account; allowing the same code again after a withdrawal
  creates a new grant. No Space action can reference it. A refused approval is said in the
  prompt; only lost access (`space_unavailable`, `sign_in_required`, `editor_required`) ends the
  page.
- **Pinned to the code.** An approval is valid only for the exact revision digest the viewer
  approved. Nothing carries it over to other code: not a teammate's release, not the viewer's own
  later release, not one their agents or the CLI published with their account, not a Store update
  or a switch to a copy (both journal a `copy:` release in this Space whose actor is the person
  who applied it), and not a staged or abandoned release. Other code answers
  `cloud_computer_approval_required` (status reason `source_changed`) until the viewer approves it
  again; republishing the approved code itself keeps the approval. Code without a digest can never
  be approved (`cloud_computer_approval_unavailable`).
- **What this protects, and what it does not.** Space source is not a JS sandbox: it runs in the
  Portal realm with the viewer's signed-in session, as Beta Apps did. The prompt, the trusted
  click, the click delay and the pin protect a viewer from code they did not review that reached
  the Space by mistake or in good faith (a teammate's release, a Store update). They are not a
  security boundary against hostile page code: page code in the Portal realm can still forge an
  approval and run commands as the viewer (it holds the viewer's session and can call
  `POST /portal_spaces/cloud-computer` with `approve`, then `run`), exactly as Beta App code can
  grant itself a capability through `/portal_apps/capabilities/grant`. Treat Editor access to a
  Space whose page declares `cloudComputer` as the power to run commands on each viewer's cloud
  computer. Making it a boundary needs a host-only step the server can verify (a confirmation
  outside the Portal tab, such as a Desktop native dialog, or a cross-origin Space runtime).
  Space Sites, which ran their author's code on the Portal origin with a signed-in visitor's
  session, now run on a separate origin on branch `spaces/sites-origin`.
- **Audit and retries.** `POST /portal_spaces/cloud-computer` (`operation`: `status`, `approve`,
  `facts`, `run`, `upload`) writes a `space_cloud_computer_audit` row (Space, revision, viewer,
  approval, request key, command digest and first 500 characters, or upload path and size) before
  dispatch and completes it with the status, exit code and duration. Without that row nothing runs
  (`cloud_computer_audit_unavailable`). File contents are never stored or hashed. Every `run` and
  `upload` carries `request_id`, one key per run: the bridge makes one (`crypto.randomUUID()`)
  unless the page passes its own, and reuses it when the same run is retried after an uncertain
  outcome (no answer, a 5xx). A key that already reached the cloud computer is never dispatched
  again (`cloud_computer_already_ran`, 409, with the recorded `status` and `exit_code`; a unique
  index refuses a concurrent attempt); only a `refused` attempt, which ran nothing, frees its key.
  A run whose usage cannot be recorded after it ran keeps its real status and exit code with
  outcome `billing_failed_after_run`, carries its audit row as the billing recovery key, and
  answers `cloud_computer_usage_unrecorded` (502, `ran: true`, not retryable) without its result.
- **Limits.** Commands up to 16384 characters, `timeout_ms` 1000 to 720000 (default 60000),
  `max_output_length` up to 200000 (default 20000), `cwd` and upload paths normalized inside
  `/vercel/sandbox`, upload `mode` 0 to 0o777, `request_id` 8 to 200 of `A-Z a-z 0-9 . _ : -`.
  Commands, paths and `utf-8` upload content must be valid Unicode text (a lone surrogate is a
  400, `invalid_cloud_computer_request`). Results carry only `status`, `stdout`, `stderr`,
  `exit_code`, `message`, `code`, `truncated` (run) or `status`, `path`, `size` (upload).
- **Still missing.** A Portal place that lists and withdraws the approval: today it is withdrawn
  only with `notis spaces grants revoke`, so the prompt promises only that it ends when any
  other code replaces the approved code or the viewer leaves the Space. Also the Conductor and
  Coding Spaces switching their controls back to direct runs.

#### What a view declares (V4): path, params, shows, memory, chrome, markdown

A view (a Space with a page) declares what it shows and which URL params it takes,
so agents, links and memory can use it without reading its code. `specVersion: 2`
is an optional marker, not an opt-out: `spaces build`, `spaces verify` and deploy fail when any presentation
lacks `path`, `description` (one line) or `memory`, when a param has no description,
when two record params claim `main` for the same database, or when a `shows` filter
names an undeclared database, an unknown param or (at verify, against the linked
schema) an unknown property, an operator that does not fit it or a missing select
option. Omitting the version does not waive any required declaration. The portable
wire schema remains `notis-space/v1`. Containers have no page and reject page-only
fields; their explicit version-2 form requires `path` and `description`, never `memory`.

```ts
export default defineSpace({
  name: 'Tasks', specVersion: 2, path: 'tasks', entry: './view.tsx',
  description: 'Every task, filtered by status.',
  readableContext: 'All tasks. ?status= narrows the list; ?task= opens one task beside it.',
  resources: { tasks: { kind: 'database', key: 'tasks' } },
  params: {
    task: { type: 'record', database: 'tasks', main: true, description: 'The task opened beside the list.' },
    status: { type: 'enum', values: ['inbox', 'done'], description: 'Only tasks in this status.' },
  },
  shows: {
    tasks: { database: 'tasks', open: 'task',
      where: { field: { property: 'Status' }, op: 'equals', value: '{status}' } },
    drafts: { about: 'Draft posts kept in the website database.', services: ['website_db'] },
  },
  memory: { markdown: true, attachments: false, screenshot: false, snapshots: ['on_render'] },
  chrome: 'portal',
});
```

- `path`: up to four lowercase words joined by `/` (`notes`, `seo/keywords`); a word
  never looks like an id. The reserved Portal roots check belongs to the link work (V2).
- `params`: `record`, `enum` (with `values`), `text`, `number`, `date` (`YYYY-MM-DD`)
  or `boolean`, each with a `description`, optional `required` and a type-checked
  `default` (never for record params). A record param names a declared database
  resource; `main: true` makes this view that database's main view (one per database)
  and `slugProperty` names the property that makes the record slug. `record`,
  `assistantThread` and credential-like names (`jwt`, `code`, `state`, `key`, or
  containing token, secret, password, credential, session, auth or api key) are
  refused; the Portal drops those names from Space links. `selection` is an ordinary
  declared param.
- `shows`: `{database, where, open?}` runs the native filter language
  (`{field: {property | property_id | column}, op, value}` with `and`/`or`; see
  `server/lib/native_data_query.py`). Whole-string values `{param}`, `{param.property}`
  (record params), `{record}` and `{record.property}` (the view's single record param,
  else the collection record) are placeholders. A condition whose placeholder has no
  value is left out (optional filters); a multi-valued record property matches any of
  its values. `open` names a record param over the same database. Anything else is
  described as `{about, services?}` and never queried.
- `memory`: `markdown`, `attachments` and `screenshot` booleans plus `snapshots`, a
  list of `'on_render'`, `{scheduled: '<5-field UTC cron with a fixed minute>'}` and
  `{on_change: {debounceSeconds: 60..86400}}`, each at most once (`[]` for none).
  Choose them with the memory guide in the documents-and-views spec; ingestion is V9.
- `chrome`: `portal` (default) or `hidden` (the Portal hides its sidebar and header).
- `markdown`: a source module whose default export `(input: SpaceMarkdownInput) =>
  string` renders the view as Markdown; the build exports it as `SpaceMarkdown` and the
  manifest records `{export_name: 'SpaceMarkdown'}` for renders (V8).

The CLI emits these as `spec_version`, `path`, `params`, `shows`, `memory`, `chrome`
and `markdown` (`spec_version` and the optional fields are absent when not declared;
a presentation always carries `path`, `description` and `memory`);
`server/lib/space_view_manifest.py` re-validates every release, Store package and
copied source (Store installs and Keep a copy), and
`_validate_bindings` checks properties against the linked schemas. The runtime
descriptor carries `params`, `shows` (list names with `database`/`open` and the `params`
names the list's filter reads, or `about`; never filters) and `chrome`.

In source, `useViewParams<typeof definition>()` returns the declared params typed
from the URL (invalid values fall back to their default and are listed in `invalid`;
unknown params such as `?foo=` never reach the view; required ones missing are in
`missing`). `useShown(name, {sorts?, pageSize?, offset?, includeContent?})` runs
exactly the declared list with the current params through `POST /portal_spaces/shown`
(`server/lib/space_view_manifest.py:execute_view_shown`): the signed-in Editor's own
Space authority on the Space's binding, the same live/preview resolver as actions, and
record params authorized like the record context (the record must be in the param's
database and readable, else `space_unavailable`). One list runs in one native read scope:
its binding is resolved once for its description and its query, and one read the list
makes anyway (its description when a condition compares its own field with a record param,
otherwise its binding's resolution) starts while its record params are checked (errors and
their order are unchanged). Inside a render read capture nothing is shared, so nothing is
read early there. The SDK keys a list's rows by the params
its filter reads (`shows[name].params`), so opening another record keeps the rows already
shown instead of reading the list again; the request still sends every param. On a Site the same declared list runs
anonymously through the Space's saved read-only query action for that database, never an
Editor or issuer read, with server-pinned params only (`execute_site_view_shown` in
`server/lib/space_record_ui.py`): a whole-Space Site uses the declared defaults (record params
stay unset, so their conditions are left out), a record Site its pinned record and params. Any
other params, a record context or a missing saved query action are refused (`site_params_pinned`,
`site_record_required`, `site_record_action_required`). `useShown` answers a list this context
cannot read with `error` (never a query that never starts), and the Site host shows a refused
read as an error notice while the Site stays open. Gate optional lists on
`useShownAvailable(name)`. Offline
verification serves lists from fixtures and the page's URL params from the fixture
context: `"context": {"params": {"status": "inbox"}}, "shown": {"tasks": [{"params":
{"status": "inbox"}, "result": {"rows": []}}]}` (exact params, including defaults).

Link an existing native database, Skill or automation into a Space before
publishing source that declares it. Links belong to the resource (R3): its own
update tool changes them, alone or together with a content edit, and a move is
one add plus one remove committed in one transaction. There is no Space-side
include command.

```bash
notis skills links <skill-id> --add '[{"space_id":"<space-id>","space_revision":<revision>}]' --request-id <stable-key>
notis tools exec LOCAL_NOTIS_DATABASE_UPSERT_DATABASE --arguments '{"protocol":1,"operation":"update","target":{"database_id":"<database-id>"},"links":{"add":[{"space_id":"<space-id>","space_revision":<revision>}]},"request_id":"<stable-key>"}'
notis tools exec LOCAL_NOTIS_UPDATE_AUTOMATION --arguments '{"automation_id":"<automation-id>","links":{"add":[{"space_id":"<space-id>","space_revision":<revision>}]},"request_id":"<stable-key>"}'
```

`add` takes the Space's current metadata revision from `notis spaces get`
(separate from its published source revision) and an optional lowercase alias,
derived from the resource name when omitted. `remove` takes a link's
`binding_id` and `binding_revision` from the resource's own `links`
(`notis skills list`, `LOCAL_NOTIS_GET_AUTOMATION`,
`LOCAL_NOTIS_DATABASE_GET_DATABASE`). You must be an Editor of every Space you
touch and able to edit the resource: its standalone owner, or an Editor of a
Space whose link to it is reachable. A database link covers the whole database;
record-only, filtered, preview and named-action capabilities never become
whole-database delegations. A link keeps the same data, schema, creator and
standalone policy, copies no provider grants and transfers no ownership.
An Editor who reaches an automation through a link can find it
(`LOCAL_NOTIS_LIST_AUTOMATIONS` marks it `access.via: space`, `runs_as_owner`), read it and
run it manually (`LOCAL_NOTIS_RUN_AUTOMATION`, Portal Test), but never sees its bearer
capabilities or connection details (webhook path and URL, setup claim token, provider trigger
handles and configurations, delivery account, thread, last error): GET, LIST and UPDATE return an
allowlisted Editor view (`EDITOR_VISIBLE_FIELDS`) while the owner sees everything. The Portal
Automations page stays the owner's, and an Editor's run gives them only its `run_id`. It still runs as its owner: the
owner's identity, connections, delivery channel, plan and billing (A20). The Automations plan
gate is checked on the owner, never the Editor (`automation_owner_plan_required` when the
owner's plan lapses), the intake request records `AutomationInvocation` (owner, invoking
Editor, Space and binding), and an Editor who lost the path gets `automation_not_found`
(`server/lib/automation_access.py`). The Editor's own automations still need their own plan.
Removing the last reachable Skill or automation link keeps that resource standalone
for the remover (an active automation is paused). A database cannot lose its last
Space link: move it with one add plus one remove, or delete it. Every revision
is checked, a stale one fails with nothing changed, and a retry with the same
`request_id` returns the original result. When a content edit and a link change
are sent together, the tool result states exactly which part was applied.

#### View links, main views and agent discovery

Space discovery (`LIST_SPACES`, `GET_SPACE`, `FIND_VIEWS`) includes `space_path`
and `space_breadcrumb` (ordered `{space_id, name}` segments). These describe the
current caller-visible hierarchy, not the manifest's URL `path`. Only ancestors
the caller can open are named; a shared descendant never reveals private parents.
Path segments escape `~` as `~0` and `/` as `~1`, and are not URLs or write targets.
Use the accompanying stable IDs and current revisions for operations.

Skill inventory and successful Skill/automation entity tool results include
`space_paths`: every linked Space the caller can open, each with `space_id`,
`space_path` and `space_breadcrumb`. Automation lists include this context without
`include_links`. `[]` means no visible Space links; `null` with
`space_paths_status: unavailable` means the hierarchy read failed, not standalone.
Names such as `Examples` or `Store catalogue` are useful selection context, not a
rule to discard those resources. A hierarchy-read failure never changes a committed
write into an error. The existing access-filtered view catalogue owns ancestor
visibility; `server/lib/space_paths.py` batches the descriptive result enrichment.

A view-qualified link has the form
`https://app.notis.ai/<path>/<view-slug>-<viewId>/<record-slug>-<recordKey>?<params>`.
Only IDs determine its destination; IDs accept dashed or 32-hex form and builders
emit 32-hex. Words and slugs can change without breaking saved links. A bare record
link opens the database's main view (or its independent presentation override), and
so does a link naming a view the reader can open that has no record param for the
record's database; a view the reader cannot open never falls back.
`server/lib/space_view_resolver.py` owns resolution and server links;
`portal/src/lib/viewLinks.ts` owns Portal links. The Portal resolves a URL under the
current viewer before mounting content, authorizes every record param, drops unknown
params and preserves Portal-only `assistantThread`. Old document/HTML paths are not
aliases: old `/documents`, `/view` and `/share` links, and any other unknown address,
show the localized Portal not-found page (`portal/src/app/not-found.tsx`, EN and FR,
with a link back to Notis) and never redirect. Desktop serves the same page from the
static export's `404.html` for those retired roots (`electron/src/staticPortalFiles.ts`).
Reserved first path words are generated from the Portal route tree by
`scripts/generate-portal-route-roots.mjs`, shared by publish/build checks and Desktop.

Every database has a Space and exactly one effective main view. A published record
param marked `main: true` claims that role transactionally; conflicting claims fail
without naming a private view. Binning a main view's Space lends the main to the first
reachable published record-param view elsewhere (by Space name and ID, marked
`auto_promoted`); with none, the main stays with its Space in the bin and record links
answer a no-default-view response (`database_main_view_unavailable`, 409) whose
`details.linked_spaces` lists only the reader's accessible linked Spaces. The bin also
hands the database's origin to a reachable live link so R10 keeps seeding it. It records
both with the bin entry (`space_bin_main_views`, `space_bin_origins`): a restore returns
the original main and origin while they are still the bin's stand-ins, and a decision
made meanwhile stays (a published main claim, an explicit main move, a copy, or an origin
move or keep). A live Space's published claim may take over a binned Space's main or its
stand-in. Delete now keeps the stand-in, or promotes a published view elsewhere when
the main left with the entry. A pending tool-created database opens
its Space with `view_warning` until that Space declares the reserved main param.

Database tool creation requires `links.add` and `main_view: {space_id, param}` in
the same request. Definition, links and main-view reservation share a transaction
and a receipt. Updates may transfer main to another linked record-param view. A
failed create leaves no database behind. No standalone database destination exists.
A create without `main_view` in one of its added Spaces answers
`database_main_view_required`.

A move into another tree is one update: `links.add` the new Space, `links.remove`
every link in the database's origin tree and `main_view` in the added Space. Only an
Editor of the database and of that Space can do it: the origin passes to that Space
when its link is inserted, and its main view is a pending claim (`view_warning`)
until that Space deploys the param with `main: true`. Without `main_view` the same
update answers `database_last_space`. Native writes accept a related record's key
or row ID in relation values; one they cannot resolve under the caller's access is
`invalid_relation_value` naming the property, never `space_unavailable`. Database
load (statement or lock timeouts) answers the retryable
`space_temporarily_unavailable` (503) instead of PostgreSQL text.

If an update removes its original binding, retry the same request and original
target rather than substituting the new binding. Receipt recovery rechecks the
database and every original, added and main Space against current Editor access;
an old successful receipt never restores revoked access or repeats the move.

Source can instead declare `resources.<alias> = {kind: 'database', create: {name,
schema, starterRows?}}`, using the canonical Store schema with stable property IDs
and at most 100 starter rows. A same-view record param must mark this alias main.
Verify and preview sealing only plan prospective identities; final promotion creates
the database, link, rows, exact native grants and source in one transaction. Later
deploys do not reapply a creation schema or its rows. `spaces pull` refreshes these
declarations from the live schema using source ranges, without evaluating code or
overwriting unrelated exports, comments or binary files. Relative imports and static
object/constant/spread configurations are supported; an unaddressable dynamic
declaration fails before any source rewrite rather than guessing which code to edit.

`LOCAL_NOTIS_FIND_VIEWS` and `notis views find` take exactly one selector:
`record_key`, `database_id`, `space_id`, `url`, or `query`. Results include fresh
view links, matching reasons, bound params and remaining param schemas, ordered
main, executable matches, record-param views, then descriptive possibilities.
Executable matches run the same `shows` filter as the view. LIST_SPACES/GET_SPACE
include description, readable context, path and link. An open Space registers its
view, record and declared params as untrusted page context, never as a permission
grant. The chat composer's page chip names the App on every page of a converted
App (its converted root Space's name, as Beta named the App), and the page's own title in a Space
that never was an App. Every Editor's Spaces list marks each converted root
(`sidebar.legacy_app_id`, from its `space_legacy_aliases` row with kind `app` and route `''`),
whatever their own sidebar layout: the one root alias read the list already makes for the row's
Set up entry (`server/lib/space_setup.py`), never a read per Space opened. A Site role answer
carries no sidebar, so there the chip keeps the page's title. Native write/body replies include the best three views and total count;
navigation is a fresh projection outside the immutable mutation receipt. A failed
projection warns without misreporting an already committed write as failed.

During the isolated account cutover, metadata staging and source release are
separate checkpoints. `server/lib/space_migration_cohort.py` defaults to a dry
run; its journal retains the exact legacy snapshot, stable Space/resource map
and unresolved dependencies. Staging creates no provider grants and never marks
the account ready. Retrying a staged item must preserve any subsequently
published source or Editor changes. Reconcile a changed legacy app before
continuing; do not reset an existing Space to its old snapshot.

The operator may pass a pinned `reconciliation` decision to migration staging.
`space_migration_reconciliation.py` accepts database IDs only through an explicit
saved development-to-installed-app link and exact owner/alias match; it never
falls back to an account-wide slug. Source-verified stale bundled skill IDs may
be omitted only when missing/deleted and absent from current structured source
declarations. Keep other active attached skills. Retain source prefix plus the
verified archive hash, or a canonical relative-path-to-byte-hash inventory for
legacy individual-file source, in the immutable packet. The operator verifies
those bytes and current parent disposition before staging; a hash field alone
is not proof. Original app arrays, database ownership and deleted skills remain
unchanged. Missing source and unresolved aliases remain explicit, not fabricated
dependencies or readiness claims.

Native definition conversion is a separate operator-only checkpoint in
`server/lib/native_database_conversion.py`. Require definition integrity and
actual SQL/display parity on a frozen source/target/document fingerprint before
applying it. The commit drains legacy writers, rechecks whole-resource authority
and the exact packet, then changes only definition/protocol metadata. A busy
conversion attempt returns a retryable conflict rather than waiting behind a
busy structural lock, document writer or target-definition row. Keep the same
verified packet after contention; changed source or data requires fresh parity.
A passed empty-database scan is not evidence for nonempty data. Retain the original packet
for retries; subsequent authoring requires normal native schema operations, not
another conversion. Neither conversion nor staging certifies account readiness.

Staging closes the exact legacy App protocol immediately, even before the whole
account is ready. Install the additive migration journal before deploying its
read gates; a failed cohort read must not enable legacy access. App detail,
source, editing, cached runtime and final provider dispatch use the shared
legacy gate. Workspace-database discovery and legacy Views queries separately
exclude native-v2, non-direct and trashed definitions, including those visible
to an unmigrated App. Legacy navigation aliases resolve current Space access;
they do not authorize old source or account-scoped actions.

The converted root's **App details** menu and bare `/apps/<installed-app-id>`
link retain the original install's version, screenshots, description and release
notes through `portal_spaces/app-details`. This display-only projection requires
both current, unscoped Editor access to that exact root and ownership of the
original installed App. Shared Space access alone never exposes another owner's
install metadata; its old link continues to the accessible Space instead. No
legacy source, resources, publication controls or CRUD capability is returned.
**Uninstall app** uses the normal Space Bin confirmation and revision-checked
subtree lifecycle, with its existing restoration window, never legacy `deleteApp`.
Converted details do not run the old App's ten-second poll or subscriptions.

#### Conversion rules every App follows (round 6)

Beta, the App as installed, is the source of truth. The pure rules live in
`server/lib/space_conversion_rules.py`; the planner (`plan_legacy_app_conversion`)
records some of them on the packet, the release gate applies rules 1, 2, 3 and 5, and
the checked cutover steps live in `server/lib/space_conversion_cutover.py` (dry run by
default, read back after writing). The staging read (`read_notis_space_app_migration`)
carries no legacy source, connections or tool support, so the packet records `None`,
never a default, for every field that needs that evidence.

How a legacy App becomes Spaces for any account: `stage_app_migration`
(`space_migration_cohort.py`) plans the packet and `stage_notis_space_app_migration`
creates the root container, one presentation Space per route (`route_space_id`), the
bindings, membership and route aliases, all with no source (revision 0). A route page
exists only once a rebuilt source is released for its Space through
`server/lib/space_source_release.py` (`notis spaces verify` / `deploy`, the confined
build, candidate staging). That release is where markup, record UI, declared actions
and SQL reads enter a converted page, so it is where the rules run:

- **Automatic, at staging:** rule 6 (root description) and the packet fields of rules 1
  and 3 (`installed_source`, `preserve_markup`, `provider_actions` pending even when
  unconnected), for every account.
- **Automatic, at every release of a converted App route:** rules 1, 2, 3 and 5
  (`server/lib/space_conversion_gate.py`). `verify_space_source` runs the gate and
  returns its decision as `conversion`; `_release_space_source` (publish and stage) runs
  it again before anything is journalled, uploaded or granted, so a caller's
  verification cannot skip it. It applies while the App's `space_migration_items` row is
  `staged` and the account's `space_migrations` row is not `ready`, to the staged route
  Space, a rebuilt route page with its route alias, or one matched by name
  (`rebuilt_route_pages`), until that page has a published revision. The gate holds a page
  while the conversion produces it: once released, the page is converted and every later
  release is its owner's change, so differences the owner approved (French copy, removed
  Set up buttons, Beta-matching fixes) are never re-checked against the installed App, and
  an imported account whose pages were already converted and published keeps releasing them
  while its migration is still staged. The App root, pages the conversion added (`extra:`
  aliases), published route pages, ordinary Spaces and live accounts are not gated. It
  reads the installed release from App storage (`download_app_source` on the packet's
  `installed_source`) and compares the route's own page, the App layout and their
  imports (the whole release when they cannot be traced). A failure is `409 conversion_rules_unmet` with every issue
  (`rule`, `reason`, `tool` or `action`); an unreadable installed release is the
  retryable `409 conversion_source_unavailable`. Nothing is granted or connected.
- **Operator steps:** rules 4, 7, 8 and 9 below.

1. **Installed release** (packet field at staging; release gate, automatic). Each
   presentation carries `installed_source`: a private App's own release
   (`<app id>/v<manifest.version>/`), or for a Store install the publisher release its
   copied manifest names (`source_app_id`, `version`, `<publisher id>/v<n>/`, with the
   listing ids beside it). A Store install whose owner deployed their own release runs that
   release. The release gate reads exactly that release, never a sibling's or the public
   listing's newer one, and refuses (`rule: 1`) Set up buttons, Skill launchers,
   PageHeading, eyebrows, `bg-card` panels and `created_at` sorts the installed route
   lacked (`markup_additions`). An App with no released bundle, or no stored source, has
   nothing to compare: the gate records `installed_release_missing` or
   `installed_source_files_missing` in `notes` and checks rules 3 and 5 only.
   `source_issues` and `audit_converted_app` remain for a rebuild lane that wants the
   same answer before releasing.
2. **In-place selection** (release gate, automatic). The gate decides `record_selection`
   from the installed route's own source: `pane` when it rendered the record body itself
   (`NativeRecordPane`, `ShareControl`, `DocumentEditor` or the SDK `MarkdownEditor`), else
   `in_place` (the record param stays, as the database's main view, and the row is only
   highlighted). An `in_place` page that adds a record pane, Share, document editor or
   body editor is refused (`rule: 2`); a `pane` page keeps its record UI (Notes renders its
   own record body and opens records inside the Space, decision 4). The packet field stays
   `None` because staging reads no source.
3. **Provider tools stay declared** (packet field at staging; release gate, automatic).
   `provider_actions` lists the tools the legacy runtime gave each page: a route's
   `tool_access` declaration (`base.tools`, `base.direct_tools`, `base.preload_tools`)
   replaces the App's `manifest.tools` for that route, as `_resolve_runtime_tool_manifest`
   does; any other route uses `manifest.tools` (`tool_bindings` add no tool). Each entry is
   `pending_owner_approval`; `connected` and `supported` are `None` without evidence and never
   drop an entry. Recording an entry grants nothing: the owner still approves each grant.
   The release gate (`route_provider_reads`, then `undeclared_provider_actions`) refuses a
   page that does not declare a read its installed route used (`rule: 3`): every tool of
   the route's own `tool_access`, and each App-wide tool the route's page or imports name
   (all of them when that source is unknown). Writes wait for review and native database
   tools are database bindings, so neither is required. A declared read whose provider is
   not connected still needs the owner's connection and grant when the release authorizes
   its actions: the page waits for that approval rather than being rebuilt without the read.
4. **Old link selections** (cutover step; resolver live). `selection_routes` lists routes with
   `resourceDeepLinks`. After the page is published, the operator runs
   `record_alias_selection_param`, which stores the declared param receiving `resource` /
   `item` on `space_legacy_aliases.selection_param` (the view manifest's param name pattern,
   underscores allowed). `resolve_space_alias` then carries text ids (Atlas table,
   competitor, submission; Platform Health incident) onto it; a number param receives the
   old value as URL text.
5. **information_schema emulation** (release gate, automatic; the rewrite is the lane's).
   Space reads run as `supabase_read_only_user` (SELECT only). The lane that writes a
   converted Website read into Space source runs `grant_select_visibility` on it (or
   compiles it with `prepare_converted_read`), which adds SELECT as visibility to emulated
   `table_constraints` and `constraint_column_usage` (`pg_constraint` is world readable;
   nothing new is exposed). The release gate runs `information_schema_visibility_issues` on
   every declared action's `query` (string, `$literal` or `$sql` parts) and refuses the
   release (`rule: 5`, with the action name) while one would still hide constraints. The
   gate never rewrites a release: its SQL is part of the source digest and grant template.
6. **Root description** (planner, applied). The root Space takes the App's own description
   (whole sentences up to 300 characters, empty when the App has none), never conversion wording.
7. **Extra pages** (cutover steps). Before an account goes live the operator runs
   `unrecorded_conversion_pages`. Its `route_without_alias` list holds App route pages rebuilt
   after conversion (found by name, as old links and the sidebar find them); they get their
   route alias from `record_route_aliases`, never an extra one, and `record_extra_page_aliases`
   refuses them. Its `extra_candidates` list holds the other pages without an alias (trashed
   ones left out): each page the conversion created gets an `('app', App id,
   'extra:<space id>', space id)` alias from `record_extra_page_aliases`, so the sidebar starts
   it hidden; a page someone added later is left as it is. `route_without_alias` must be empty
   before going live.
8. **Store listings** (cutover step, off). `plan_store_listing_carryover` maps each published App
   listing to its root Space; `carry_store_listings` publishes through the Space Store only
   when `NOTIS_SPACES_STORE_CARRYOVER=on` (off by default, pending decision D20). A team
   listing is refused when the publisher's current team is not the listing's team (the Space
   Store publishes to the current team). A public listing goes back to Store review
   (`review: needs_review`) and is not in the public Store until approved.
9. **Cutover data** (cutover steps). Convert records at cutover and check
   `check_records_current` (the newest record included); `replay_isolated_schema` adds
   properties that exist only on the isolated copy (for example the Rolls Mode, Min, Max,
   Rolled At) before the Space goes live.

The App-row mutation fence shares staging's row lock. Finish or reconcile any
legacy deployment claim (including expired claims) or lifecycle operation before
staging; a later old release cannot claim, modify or delete the retained App.
Use the explicit operator-only migration reader for frozen legacy inventory,
not a request-controlled bypass. Purpose-scoped legacy document credentials
also have restrictive document and sync-metadata fences; only legacy direct
databases and standalone documents retain that protocol. They receive no auth
schema, database-table or authenticated-role privileges. Native records require
the canonical Space/record authority and native collaboration broker.

Joining a native record's live session is kept short without skipping a check. The
Space document editor's record read asks for the collaboration credential
(`record-ui` `read` with payload `{collaboration: true}`, `editorReadAsksCollaboration`;
Sites and read-only editors never send it). The read answers at once, so the note shows
read-only while its credential is on its way. Only for a writable Markdown note (never
HTML pages, reports, files, archived records or action-only bindings) does it carry
`collaboration_receipt`: a 60-second token, signed with its own scoped secret, naming
the signed-in Editor, the published view (Space, revision, record context), the record
and the binding that read checked. The record client asks for the credential with it
right away (`record-ui` `collaboration` with payload `{receipt}`). The receipt stands
only for the record UI read, never for its gates: the server first runs the read's gates
in the read's order (sign-in, the published view, the Editor role, then the preview
refusal), refuses a receipt for another person, view or record, an expired or forged one
(`record_changed`), and has the issuance judge those gates, with the view's declaration
and pinned binding, before it reads anything of the record (`issue_native_collaboration`
`view_gate`, run together with the binding resolution). The issuance then runs every
check of the `collaboration` operation's issuance (exact target, record, published view
and Editor role again). What the receipt saves is the repeated record UI read (`_read`:
description, record query, view projection and rechecks); the issuance still loads the
record and its CRDT state under the exact binding. A refused credential is asked
for once more by the editor's join, without a receipt, which shows why. The
receipt and token stay in the record client, never in the snapshot host components hold.
Record reads started in the same task share one request (the scaffold's
`RecordProperties` and `DocumentEditor`), which asks if any of them does; an editor that
mounts after a plain read already went out reads again with the option, in parallel,
instead of waiting for that read and asking afterwards. When the read brought neither
(an API from before this option, which refuses it and is read again without it), the
editor asks for it while it mounts (`prepareCredential`, `liveEditorRecordKey`). A
read's row projection and its two rechecks (the record still at that revision, the
view's authority unchanged) start together, and the view-context check's two reads
(the Space execution and the binding) run together too; nothing is released until all
of them answered, and their refusals are judged in their original order. A
prepared credential serves the first join only, within 30 seconds; an unused one is
then dropped on a timer, and it passes the same open-Space and signed-in check as a
fresh one. The
sidecar opens the room from the record Python returned with that socket's
`authorize` answer (the same authorization and record `load` returns) instead of
loading it again and does not render the body as Markdown for a join. The socket's
first message, its opening sync request (a plain sync step 1), is answered from that
room without a second Python check when it arrives within 5 seconds of the upgrade
(`JOIN_SYNC_REPLY_MS`, covered by the upgrade's own fresh authorization). The state is
sent once, as that reply, never unasked, so the first sync reply an editor receives
is the one to its own opening request. Every other message the socket sends is still
checked against Python.

Native agent and CLI document-body operations use the same generic CRUD tools
and broker as the Space editor. Discover the exact target and body variants
through `GET_DATABASE` or the selected Space; do not derive an owner's database
target. `QUERY` takes `input:{mode:"document_body",record_key}` and returns the
current Markdown plus record/schema revisions. `UPDATE` replaces the body with
`input:{record_key,expected_revision,content_markdown}` plus the original
`schema_revision` and stable `request_id`. Body and property writes are separate
acknowledged commands, not one atomic update. A declared-action `QUERY` body read
(also the Space `document-body` read) loads the record and its recheck without the
private CRDT state, which only a live room load needs; the Markdown is rendered from
the blocks that read returned.

For a declared action, `target` is the body-capable UPDATE and `read_target` is
its explicit matching QUERY from discovery. Both retain current Space, record,
source and binding authority; a rejected action never falls back to direct
Editor or creator access. Direct Editor/standalone calls omit `read_target` and
use one canonical native target. Anonymous/link body editing is not supported.
Discovery separates Markdown transport from the source declaration's generated
query/BlockNote schema, which is still validated at execution. A property-only
action does not confer body permission.

Direct command credentials pin the original schema and exact target into their
receipt digest, while ordinary collaboration-room credentials retain their
existing protocol. The sidecar cannot substitute a newer schema on commit.
Exact receipt recovery precedes stale-revision checks and fresh Markdown
parsing; saved effects use native receipts (and paired action receipts only in
the declared-action lane). `unchanged` means no effect, not a fabricated receipt.
`document_outcome_unknown` requires the same original command on retry, never a
new request ID or an assumed successful save from the sidecar HTTP response.

Skill cutover follows the exact current `owner_app_id`, not a source URL, name,
or original creator. Legacy lists, citations, runtime inventories and sync pull
exclude Skills owned by a staged App; direct edits and publication reject them.
A failed inventory read is an error, never a successful empty sync. An
authoritative empty inventory removes managed stale mirrors. Skill lists and
sync carry no App ownership annotations (`origin`, `owner_app_id`,
`owner_app_name`, `app_owned`). Authenticated clients cannot read or mutate `app-code/skill-sync/` directly,
including historical keys; checked server hydration serves standalone bundles.
This does not recall bytes or signed URLs already delivered before cutover.

Before a legacy Skill provider/storage operation or team publication, acquire
the exact durable Skill-effect claim, including for standalone Skills. Claims
prevent ownership reassignment and staging while the operation is unresolved.
Release only after a known complete outcome, or before any remote effect began;
cancellation, provider ambiguity and unconfirmed cleanup retain the claim for
reconciliation. Never infer completion from elapsed time or retry the provider
effect to clear a claim. Current Space Skill reads are a separate exact-binding
path; neither retained Skill ownership nor the claim grants Space execution.

Migrated or explicitly native, available, non-curated Skills use one native
definition writer through direct ownership or a Space authoring target:

```bash
notis skills read --target '{"space_id":"<space-id>","binding_id":"<binding-id>"}' --files
notis skills update ./skill-edit.json --request-id <stable-edit-key> --dry-run
```

For a direct read, use `notis skills read <skill-id> --files`. The same update
command accepts either returned target. Space targets retain the Spaces OAuth
scope, protocol and rollout checks; renaming the command does not widen access.
There is no alternate Space Skill command group or authoring-route alias.

The edit file retains the returned `target` and `version`, and supplies either
`skill_md` (preserving every supporting file) or a complete base64 `files` map.
Name/description-only edits may omit both; they preserve the accepted baseline's
effective Markdown and all supporting files, not a newer head discovered during retry.
After checking, repeat without `--dry-run`. Current whole-Space Editor access is
required at read, upload admission, commit, and exact-request replay. Native
content is keyed by the existing Skill ID, so all including Spaces see the same
edit. The legacy row, creator/provenance, personal inventory and provider Skill
versions remain unchanged. Standalone legacy and curated Skills do not acquire
this writer implicitly; a failed Space request never falls back to creator access.

Native bundles use immutable verified objects. Failed reads do not drop helper
files, and failed/uncertain uploads retain their intent for reconciliation; retry
the same request instead of creating another edit. Source verification captures
Skill content versions separately from binding identities. Begin/seal/promotion
reject a changed version; an already-published Space continues to use the live
shared Skill. Skill edits made inside a pulled Space source travel with the
release and are committed by its promotion, together with its link changes and
the new source, in one transaction (see "Source, links, Skill folders and the
lock file" above). Its SQL (`20260927_spaces_source_skills.sql`) was applied to
Main with the Spaces packet on 2026-10-10.

Fresh Space-native Skills use `notis skills create ./skill-create.json
--request-id <stable-key> --dry-run`, then the same request without `--dry-run`.
The file contains `destination:{space_id,alias,revision}`, `name`, optional
`description`, and either `skill_md` or complete base64 `files`. Creation verifies
immutable bytes before committing one new Skill identity, content head and
included binding. It creates neither an App nor provider activation. Reuse the
original request and bytes after a lost reply; a new request is a new intent.

Standalone creation uses `notis skills create ./skill.json --request-id <stable-key>
--dry-run`, then the same command without `--dry-run`. The file contains `name`,
optional `description`, and exactly one of `skill_md` or complete base64 `files`.
The CLI supplies the explicit standalone destination; callers cannot choose an
owner. One actor-owned native identity/head is created without an App, Space,
binding or provider Skill. Listing a standalone Skill in a Space afterwards is a
link change on the Skill (`notis skills links <skill-id> --add '[{"space_id":
"<space-id>","space_revision":<revision>}]' --request-id <stable-key>`, or `links`
on `LOCAL_NOTIS_UPDATE_SKILL`); it requires the destination Space's Editor and
preserves identity, content and the owner's personal settings.

Install the gated native-Skill schema and marker-aware readers together before
enabling creation. `native_skill_resources` owns explicit lifecycle and direct
authority; a null legacy App owner or zero references does not mean standalone.
Space-created identities have no legacy personal owner, and nullable creator
provenance must not block retention by another Editor. This resource-level
boundary is not certification of the whole account-deletion workflow. Existing
standalone legacy Skills require an explicit supported transition, not implicit
content shadowing when they are linked.

Standalone native instructions carry a checked Skill identity, access revision
and content revision/digest, independent of Space membership and provider Skill
IDs. Runtime preparation, fresh provider submission and registry tool dispatch
revalidate accepted references; a changed pin requires a fresh preparation, not
an automatic upgrade to different instructions. Unavailable inventory preserves
existing managed files but blocks fresh shell/delegated execution. Confirmed
empty inventory removes managed mirrors. Retained provider operations continue
receipt/observation recovery without replaying a prompt after access changes.
Public standalone transition remains gated on discovery, citation, authoring
and Desktop sync consumers preserving this identity; private SQL installation
alone is not a supported user transition.

Standalone native content uses `notis skills read <skill-id> --files` and
`notis skills update ./skill-edit.json --request-id <stable-key> --dry-run`, then
the identical update without `--dry-run`. This direct route uses the existing
`notis:read`/`notis:write` OAuth scopes, not Space membership. The edit contains
the returned `{skill_id,access_revision}` target, exact content version and
Markdown or complete files; it cannot retarget an included Space binding.
The Portal editor uses the same versioned writer and retains its request key
after an ambiguous response until canonical readback succeeds. A new-Skill editor
keeps its creation mode/body/key pinned through navigation, locks further content
changes while the outcome is uncertain, and offers **Finish creating**. A flag
change cannot turn that retry into legacy creation. Unsupported
legacy lifecycle/sync/share actions are not native fallbacks.

Agent Skill creation uses a stable `request_id` and an optional explicit
`destination`. Definition updates use `native_content:{target,version,request_id}`;
personal enablement/agent assignments retain the separate
`native_context:{access_revision,settings_revision,request_id}` contract. These
cannot be mixed. Included pre-native content can have revision zero; direct native
heads start at one. Shared destinations/targets require `notis:spaces` in addition
to ordinary external write permission, including inside batched tool calls.
Unknown creation rollout state is not permission to fall back to a provider write.

For native agent `bundle_url` input, a real apply first validates and admits an
exact private file snapshot. Retries check current authority and reuse those bytes
without redownloading an expired URL. A dry-run alone does not persist that snapshot;
it is not a promise that mutable URL contents stay unchanged until apply.

Native agent create/update reviews are private, best-effort reports of the exact
committed intent's before/after files. A separate journal pins one report identity,
renderer candidate and verified immutable objects; uncertain replies do not create
another Skill edit or report. Revoked source authority and trashed/replaced reports
fail closed on replay without recreating the report. Review failure never rolls
back the content commit. Manual Portal edits, background sync and personal-settings
changes do not generate these reports. This is not Store publication or approval.
The current presentation is an independent private Space, with a source-backed published revision and only the
actor's initial Editor anchor. `native_skill_review_intents.document_id`, original candidate/state and old committed
result remain historical identity; `skill_review_space_receipts` adds the current `space_id`, source and exact-byte
object receipts. New reviews never insert standalone documents. The projection converts only the frozen module
export/authoring index, preserving the captured payload, original config and all source files; old staged objects
are read back by hash when a newer renderer cannot reproduce them. The final Space publication uses canonical
source RPCs after all bytes are verified. Current native Skill authority and exact private review source are checked
on every replay; an edited, trashed or deleted review is not silently returned or recreated.

Legacy Skill share-link creation uses the same durable effect claim before
reading source or returning a creation retry. A migrated/native Skill cannot
export its retained legacy body through that endpoint. Existing independent
snapshot links are not retroactively erased. Uncertain inserts recover only the
exact attempted token (or an acknowledged unique-key winner); they do not repeat
the insert or release an unresolved claim.

Selected Space Skills provision supporting files through
`LOCAL_NOTIS_RUN_SANDBOX_SHELL` in the native Notis Cloud Computer's run-scoped
directory. Composio workbenches and Desktop are separate execution environments;
the same-looking filesystem path does not transfer files or authorization to
them. An included Skill grants neither provider credentials nor broader data
access. Its current reference is revalidated before fresh execution.

Protected Spaces navigation uses the view-qualified links described above; a
record is named by its native record key in the last path segment. The record
key is not a provider/external row ID. Deep links still resolve current access, including when a Space was
shared directly beneath a private record. `/spaces/preview` remains a distinct
authenticated preview route. Source uses `useNotisNavigation().toSpace(spaceId,
{ recordKey })`; the host accepts exact identities, not arbitrary URLs or link
credentials. Portable sources declare `navigation: { history: { key: 'history' } }`
in their Space definition and call `await nav.toNamedSpace('history')`. Bind the
instance destination using `notis spaces navigation bind <source-id> --alias
history --target '{"space_id":"<destination-id>"}' --revision <metadata-revision>`.
This edits the next release's bindings, not the live published snapshot. Build,
verify and publish the source to activate it. Bindings are not grants: both source
and destination require current viewer access on every click, including link and
preview context. A fixed record target cannot be overridden into another record
or a whole Space. Removing or changing a draft reference does not redirect old
published source; revoked/deleted destinations become unavailable.

The optional `selection` in `toNamedSpace(alias, { selection })` roundtrips through
the URL and `useNotis().selection` (a `specVersion: 2` view declares `selection` as an
ordinary param and reads it with `useViewParams()`; other declared params ride in the
same query string). It is untrusted UI state, never substituted for
the `record` authorization context, sent as action authority, or used to mount a
second copy of the same Space. The selected source archive keeps portable keys
without including a destination's source. Store packaging must map those keys to
independent installed destinations and reject unresolved external references.

Navigation and native record controls do not imply
Store installation, complete account conversion, or permission to release the
platform; those retain their separate acceptance gates.

Registry publication stamps the runtime manifest with the numeric Store release sequence
and the package `app.release_version`. Earlier Store installs may lack the private-deployment
`manifest.version`; runtime access recognizes their persisted Store
installation receipt only when the running bundle matches the installed baseline. This
compatibility does not activate unreleased private containers or replacement bundle URLs.
App list/detail expose this decision as `runtime_version` for Workspace visibility; it
does not change `current_version` or the private deployment optimistic-lock base.
Runtime route resolution honors explicit `export_name`, current CLI path exports, and the
deterministic underscore-prefixed path exports in existing registry bundles. Multi-route
bundles must resolve a route-specific export; arbitrary minified-export guessing is rejected.

### Legacy App Skill paths removed (R9)

Apps no longer package, associate, clone or manage Skills. `notis.config.ts` rejects `skills` and
`onboarding` (the CLI and the release endpoint both answer `app_skills_moved_to_spaces` before any
claim or upload); put each Skill in `skills/<alias>/` of a Space source instead. Every former App
Skill was converted to a native Skill with the same ID and linked to its migrated Spaces. Store
installs, duplicates, pending-asset activation and Store updates copy automations only, App detail
has no `bundled_skills`, and the App list has no `skills` count. The `skills.owner_app_id` and
`apps.bundled_skill_ids` columns remain as unread legacy data until the deployed-consumer gate
allows schema contraction; `legacy_skill_rows` stays the single boundary reader.

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
| Ship a Skill or a Set up action | A Space source: `skills/<alias>/SKILL.md` and a view button calling `handover({ skill })` |
| Bundle unrelated automations by reference | Portal UI or `update_app` tool |

### Database schema changes

`notis.config.ts` does not define database schema. Create or evolve databases through native Notis database tools, then reference the resulting slugs from the app config. The runtime resolves the real database rows when the app loads. An app-owned database slug is part of the deployed contract: bundles and collection routes may refer to it directly, so schema tools reject changing that slug. Rename the database's display title instead; changing a slug requires a new app package and an explicit migration strategy.

---

## Publishing to the Public App Store

`notis apps deploy` updates a single linked installed app — it's a private operation between the developer and their own account. Store submission is a separate action. The owner can click Publish/Update in App Details, or an agent can run `notis apps publish --confirm-ready` after the user explicitly confirms that the current App Details page is ready. Both surfaces call the same authenticated endpoint and submit the deployed manifest, not un-deployed local files.

### App Details publish flow

1. **Pick visibility.** On the App Details page (`/apps/[appId]`), the owner picks **Personal**, **Team**, or **Public** in the visibility selector. Personal hides the publish CTA — the app is private to the owner. Visibility persists on the `apps` row.
2. **Submit the confirmed listing.** With Team or Public selected, the owner clicks **Publish/Update**, or an agent with explicit approval runs `notis apps publish --confirm-ready`. The CLI checks local listing readiness, confirms `.notis/state.json` matches the current deployed version, blocks duplicate pending reviews, and then sends only `{ app_id }` to `/portal_apps/publish`. The server reads `apps.visibility` and listing metadata from the deployed `manifest.json` (`title`, `tagline`, `categories`, screenshots from `metadata/`, and parsed entries from the root `CHANGELOG.md`). The async publish handler offloads synchronous source uploads and GitHub work to a worker thread, then awaits the same submission result; publication must not block unrelated runtime or sidebar requests.
3. **Publish behavior depends on visibility:**
   - **Team** (`visibility='team'`): instant. Server upserts an `app_store_listings` row with `channel='team'`, `review_status='published'`, and the manifest metadata. Anyone on the team can install it from the Team section of `/store` immediately.
   - **Public** (`visibility='public_store_hidden'`): server opens a PR on `mindtheflo/notis-apps`, assembling the complete editable `apps/<slug>/` source tree plus `notis-listing.json` and Store screenshots. The listing metadata carries a reviewable install snapshot: the exact schema of every source-declared database, only rows from databases with `seedDocuments: true`, and bundled app resources. Registry CI validates source, schemas, seed privacy budgets, screenshot dimensions/size/alt text, type safety, bundle size, and forbidden patterns. On merge it builds the bundle, signs an HMAC payload containing that install snapshot, and POSTs to `/registry_publish`; the handler upserts a fully installable public `app_store_listings` row.
4. **Update presses do the same thing.** The button reads **Update** instead of **Publish** when an active submission already exists. Same channel rules: Team is instant, Public goes through PR review. The submission row in `app_submissions` tracks PR state.
   **What’s New** is the first entry in the latest published `CHANGELOG.md`; **Version History** renders every entry from that same file. Because the latest file is authoritative, editing an older entry and publishing again updates that past Store entry instead of leaving an immutable database copy behind.
5. **Visibility is locked while a listing is live.** Once an active submission exists (pending review or merged), the visibility selector is disabled. The owner must Unpublish before flipping between Team and Public.
6. **Conflict resolution lives at install time, not publish time.** When a Team or Public listing updates, propagation applies the new snapshot automatically to clean installs and compatible customization overlays. Installs with conflicting customizations move to `needs_resolution` and surface the App Details resolution flow through `/portal_apps/update/resolve`; `/portal_apps/update/apply` remains the explicit clean-apply endpoint. The publisher is not asked to resolve installers' conflicts.

Database compensation during a Store update must fence on the actual write response, because database triggers may replace the requested timestamp.

If an installed Public store app is **modified and republished as a new app** (a fork), the backend clears `apps.source_listing_id` on the developer's installed copy after the new submission opens. That copy stops receiving upstream update notifications and owns its new lifecycle. The original listing keeps updating its other installs untouched. See [Forking an existing app](#forking-an-existing-app-1).

### Unpublish

The App Details ⋯ menu offers **Unpublish** when there's an active submission:

- **Pending review**: Unpublish withdraws the submission immediately (`/portal_apps/submissions/withdraw`). Already-installed copies are unaffected (there were none yet).
- **Team listing** (`channel='team'`, `review_status='published'`): Unpublish flips the row to `archived` (or deletes it). Anyone who already installed the team app keeps using it; new installers from the team Store no longer see it.
- **Merged Public listing**: Unpublish opens a *removal PR* on `mindtheflo/notis-apps` deleting `apps/<slug>/`. The listing **stays live in `/store` until the PR merges** — App Details shows a "Removal pending review" badge while the PR is open. On PR merge, registry CI removes the listing (the same handler that adds it on publish — extended to handle deletes). On PR close-without-merge, the badge clears, no DB change, the listing remains live. This mirrors how Raycast handles extension removals.

Already-installed copies of an unpublished app keep working until users uninstall them — un-listing affects discovery and new installs only.

### Screenshot framing

`notis apps screenshot` measures the rendered app rather than assuming it fills
the viewport. For a centred, width-constrained app, the capture follows layout
wrappers only when they contain the entire visible app. Separate headers and
split panes stay together; a single card or column is never chosen from a larger
layout. Short bounded views are captured at their final display resolution and
fitted in full. Long narrow pages use a width-fitted desktop viewport, showing
the first screen instead of shrinking the whole document into a miniature.
The compositor preserves the capture's aspect ratio without further cropping.
The final PNG remains 2000×1250. Explicit focus selectors take precedence;
`--raw` retains the viewport capture without automatic content framing.

Keep generated design previews outside the Portal source tree (for example in
gitignored `.context/`). The Store gallery reads listing media, not local fixture
PNG paths.

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

The release manifest declares `source_storage_format: tar-gzip-v1` for binary source snapshots.
A private `.notis/source-snapshot.json` descriptor in the source bucket owns the format and
archive digest, so source remains readable after old runtime bundles are pruned. These snapshots
store every original source file, including tests and lockfiles,
inside `source.tar.gz`; `metadata/` files also remain directly accessible at their original
paths for signed listing-media URLs. This avoids raw source triggering storage-edge injection
filters without rewriting or excluding code. Pull and Store submission decode the archive
losslessly; snapshots without this descriptor retain the legacy per-file reader. Unknown formats,
corrupt archives, duplicate/unsafe members, and snapshots exceeding 10,000 files or 256 MiB
of decoded source fail closed. Deployment claims journal the descriptor, archive and media object paths,
not the member paths, so failed-release cleanup removes the exact staged objects.

**Reader rollout:** the archive reader must be deployed to every API/worker environment that
can pull or submit an app before archive-format releases are created there. Older platform
builds cannot read the new source format; this is a platform release dependency, not an app
deployment or database migration. Existing snapshots are never rewritten.

App-owned source can be edited in a gitignored worktree directory such as
`.context/`; deployment versions its source independently of this repository.
Do not maintain a second `app-changes/` snapshot solely to version an installed
app. Preserve the app's CLI linkage and build/verification workflow. Changes to
the Notis platform itself still belong in Git and follow the repository release policy.

#### Space-linked Skill source and materializations

A Skill a Space uses has one editable definition: the native Skill itself,
linked to the Space under an alias. `notis spaces pull` writes its complete
bundle to `skills/<alias>/` next to the Space source; after editing it,
`notis spaces deploy` commits the changed Skill folders, link changes and the
source in one transaction (see [Source, links, Skill folders and the lock
file](#source-links-skill-folders-and-the-lock-file-r5-decision-10)). The same
Skill can also be edited directly with `notis skills read|update` or in the
Portal Skill editor; every Space that links it sees the edit.

The other copies are generated materializations, not additional sources:

- `space-source/` releases are immutable published source snapshots.
- `/vercel/sandbox/.notis/skills/<skill>/` is the account's synchronized runtime
  materialization of the Skill bundle.
- Claude, Codex, and other local-agent skill directories are symlinks or sync
  targets rooted in that account materialization.

Never patch a runtime materialization or add the same workflow to an unrelated
development skill to compensate for a stale sync. Edit the Skill (in a pulled
Space source or directly), deploy it, and run skill sync. This keeps executable
scripts, skill instructions, and their tests in one place while allowing each
agent harness to receive its generated copy.

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

It declares no Skills and no onboarding entrypoint: those belong to Space
sources (`skills/<alias>/` and a view button calling `handover({ skill })`).

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

The CLI requires Node.js 22.12.0 or newer; Node 24 LTS is recommended.
This floor follows Commander 15 and also covers the app builder dependencies.
Both installation and the public entry point reject older runtimes before
loading CLI dependencies, even when npm engine warnings are not enforced.
Install lifecycle scripts can be disabled, but the runtime check still applies.
See the generated [CLI setup reference](../packages/cli/README.md#install).

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
- `handover()` — opens manager chat with app/resource context and an optional starter prompt or the alias of a Skill the Space links; the view watches its own databases for the result
  (in a Space, the draft's context chips name the App, then each database the page binds that the person owns and that is not in the bin, as Beta's App handover did. The App is the page's own: the walk goes up through page Spaces the person can open to the first container and names it only when it is an App's top-level Space (it owns a published source or carries a converted App's alias), never a team Space around it; otherwise the page names itself. Every chip carries the same page context, revalidated once at Send)
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
| bundled_skill_ids | uuid[] | Legacy, unread since R9 (Skills are linked to Spaces) |

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
- instant route switching (no document reload)
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

`Dialog` is the SDK-owned native modal; apps own its content and actions. See the [SDK component reference](../server/skills/notis-apps/references/sdk.md) for its props. Browser top-layer rendering keeps it above selection toolbars inside either rendering boundary, and SDK collection shortcuts are suspended within it.

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
| `useNotisNavigation()` | Open a Space view by id with an optional record and declared params, or another route of the app | `toSpace(spaceId, { recordKey: row.record_key })` |
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

Snapshots and quotes reach the agent as explicitly untrusted reference data. They provide grounding, never instructions. Keep them current and relevant; use a tool fetch when the freshest record is needed. Resources may include JSON-serializable `additionalContext`. Copying from a supported SDK selection and pasting into chat creates a source-aware quote pill; unrelated clipboard text remains message text.

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

#### Live updates in Spaces

Spaces get changes made elsewhere (another device, a teammate, an agent outside the open chat, an automation) without polling, through the live-update triggers installed on Main by `20261021_spaces_live_updates.sql` (Spaces packet, applied 2026-10-10). Beta's App feed above listens to `documents` rows, which are not in the `supabase_realtime` publication on Main, so on Beta it only re-reads on focus and every five minutes; Spaces do not use it.

- **Signals, per person.** Triggers send a Realtime Broadcast message on the private topic `notis-live:user:<auth id>`, where `<auth id>` is the Supabase Auth identity the Portal signs in with (the access token's `sub`: `users.auth_user_id` for a linked account, else `user_id`). Event `spaces` goes to each person who can open a Space that was created, renamed, moved, trashed, shared or published: its owner and Editors (`notis_current_space_editors`), the Editors of a moved Space's old parent, and the person or Team (members and owner) a share names, including one that just lost it. A statement that changes more than 20 Spaces tells the owners and the people its shares name only; deleting a Space tells its owner, and its shares, deleted with it, tell the people they name. Event `database` is sent only for a database at least one Space binds (a `space_assets` row; draft and preview releases bind through the same rows), since the Portal listens for a database only through a Space binding: writes to any other database send nothing. It goes to the owner of the bound database whose rows changed and to the owner and Editors of every Space that binds it (owners only past 20 binding Spaces), from the per-statement `space_memory_database_versions` revision, once per database per transaction: each statement pays one existence probe for a binding, and the binding Spaces are read only for the first signal. Each trigger call writes one `realtime.messages` INSERT for all its recipients (one per person, event and payload per transaction), so a Team of any size adds one subtransaction, and every trigger catches its own errors (a WARNING, never a failed write). The only policy on `realtime.messages` admits a signed-in person to their own topic; clients cannot send on it.
- **No physical ids in the browser.** A `database` signal names its database by `sha256('notis-live:' || database_id)`; the Spaces API adds the same token as `bindings[alias].live` to a signed-in Editor's runtime descriptor, owner or teammate (`with_live_tokens` in `server/lib/space_descriptors.py`), never to a Site descriptor or to a Space opened through a link, even by a signed-in person.
- **Re-reads keep the Space's authority.** On a signal the Portal re-reads through the Spaces API and the view's declared actions, so grants and the viewer's access are checked on the server exactly as for any read. The sidebar treats a `spaces` signal like a change made in the Portal (`notifySpacesChanged`); right after the page's own change it only re-reads the list. An open view re-reads its queries when a database it binds changes (300 ms debounce, at most one re-read every two seconds), whether or not its code asks for a feed. Several aliases that bind one database share its token and all follow it.
- **`live` in Space code.** `useNativeDocuments(alias, { subscribe: true })` returns `live: true` while the feed is attached (the runtime's `subscribeDatabase(alias)`); keep a manual reload where it is false (a Site, a link, a host without the feed, or while the channel is down). One channel per person per page is shared by the sidebar and every open view (`portal/src/lib/spaceLiveSignals.ts`). A channel the server closes is opened again (1 s, then doubling up to a minute) and, once joined again, the sidebar and open views re-read what they may have missed. A refused join (the policy is not on the database yet, or the token is rejected) is not retried: the page logs one warning and waits for the next access token. The migration must reach Main before this Portal code reaches Beta or production.

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
- **`skill`** is the alias of a Skill the Space links (`skills/<alias>/` in its source). The host rejects an alias the Space does not link, so view code can never point the manager at a Skill the Space does not list. Omitted, the work is handed over without a Skill binding. Legacy App views hand over the prompt and context only.
  The server reads a Skill the published source declares under `resources` through that revision's frozen binding, and any other Skill the Space links (a `skills/<alias>/` folder, `notis skills create` with a Space destination) through its current link, as the person preparing the draft: any Editor of the Space, not only its owner (`server/lib/space_skill_access.py`). The draft, Send and the run each check it again. A Skill that is unlinked, disabled or unreachable is refused as `skill_unavailable`; only a lost Space is refused as `space_unavailable`.
- **`autoSend`** depends on the host. A Space view always opens the complete prepared message (`@App @Database… /Skill <prompt>`) for the user to read and send, and resolves `drafted`: it never submits on the user's behalf. A legacy App view submits that message only when `handover()` starts during an active user gesture such as a button click; background calls open a draft. The normal chat send path retains progress, cancellation and failed-draft recovery. `sent` requires the host's accepted submission, not merely opening the composer; absent hosts and failed submissions resolve `drafted`.
- **`available` is honest.** Hosts without a manager chat (the temporary `apps verify` harness, the vite preview) leave `runtime.handover` undefined and `available` false. Keep the app's own fallback — a copyable prompt — for those, as above.

A Space's **Set up** button is this same call with its linked onboarding Skill, for example `handover({ skill: 'journal-onboarding', prompt: 'Help me set up my Journal reminders.' })`.
Converted App roots also expose **Set up** in their sidebar row menu. Package
export freezes each included root's setup owner Space, Skill alias and identity,
and prompt; installation remaps included resource IDs and stores that metadata
atomically in the package install ledger. A copy, including one nested below a
catalogue, reads only its own frozen metadata, never the publisher's current App.
UUID references and exact standalone text identifiers are remapped; an embedded
non-UUID source identifier must be rewritten in the source prompt before copying,
not silently retained or replaced as an ambiguous substring.
The exact Skill must still be linked inside the reader's listed copy subtree.
An unlinked, replaced or moved setup Skill gets no entry, and the normal draft
preparation and send path still rechecks the person's current authority.

Older installs have no inferred setup. `repair_notis_space_package_setup` is a
one-time, owner-only repair using the exact saved package digest, reviewed and
already-remapped setup metadata, and its evidence SHA-256. It checks all identities
against the install mapping and current copied subtree/link, rejects known source
IDs left in the prompt, refuses a changed repair, and replays the identical one.
Old install ledgers omit legacy document writer IDs: the approved evidence must
inventory and remap those too; the ledger check alone cannot establish that proof.
Never derive this repair from a mutable
publisher read on sidebar open or synthesize legacy App routing aliases.

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

**Value limits on native writes.** Every native insert and update, including `LOCAL_NOTIS_DATABASE_UPSERT_ROW` and generated `UPSERT_<slug>` writers on a Space database, validates values in `server/lib/native_data_values.py` before its transaction. `text` and `rich_text` values hold up to 2,000,000 characters, the same ceiling as a record body's `content_markdown`, so Skills that store long JSON run summaries or provider receipts keep working after their database moves into Spaces. `title`, `url`, `email` and `phone_number` values, and the `title`, `icon` and `cover` columns, stay at 16,384 characters. An over-long value is refused with `invalid_database_values` and a message naming the limit. The numbers come from production on 2026-10-01: the largest stored `rich_text` value was 1,069,376 characters (a provider receipt; `seo_runs.Summary` held 371,738), p99 was 371, and the largest title was 2,248. Hosted MCP calls keep their 128 KiB argument cap, so values this large arrive through the CLI or in-app agents. No database constraint repeats these limits. Derived copies stay bounded: automation trigger payloads and both memory serializers (Supermemory native documents and Space memory) keep the first 16,384 characters of a longer value with a truncation marker that gives its full length, and in-app agents see at most 12,000 characters of any tool result.

**`secret` is metadata only.** The platform never stores or returns secret material. A secret property holds `{reference, status, metadata}` — the credential's name, its lifecycle state, and non-sensitive details — and every read path replaces even that with a redacted stub (`{present, reference, status, metadata}`). Anything else sent on a write is dropped, and a non-conforming value is stored as `null` rather than kept. There is no value-resolution mechanism yet: declaring a secret property records which credential a row points at, it does not make the credential readable.

> **Deploy order (no migration needed).** The server must ship before any app declares a `secret` property. Older servers normalize unknown property kinds to `rich_text`, so a schema pushed to a pre-`secret` server silently degrades the property to plain text and stores whatever the write path sends verbatim.

---

## CLI Command Reference

The CLI command specifications own the exact options. See the generated
[CLI reference](../packages/cli/README.md). App commands include `init`, `scaffolds`, `pull`, `create`,
`link`, `build`, `verify`, `screenshot`, `deploy`, `publish`, `list`, `doctor`, and ordinary lifecycle commands.

Generated Vite scripts use `--configLoader runner` so the file-linked SDK TypeScript
config loads without relying on native TypeScript loading. New templates use Vite 8
(Node 20.19+ or 22.12+; the repository runtime is Node 24). Scaffolding also normalizes canonical
Vite commands in registry templates; custom or compound shell commands remain unchanged.
For pulled historical source with the canonical `vite build` script, `apps build`
supplies the loader at execution time and leaves the source snapshot unchanged.
The SDK retains `rollupOptions`, Vite 8's compatibility alias, because SDK refresh
also serves historical Vite 5/6/7 app projects. On Vite 8 it adds the upstream
`esmExternalRequirePlugin` for the same external React entry points: bundled
CommonJS dependencies must use ESM imports, not browser-side `require()` calls.
On Vite 8 this plugin alone owns React externalization; listing those entries in
`rollupOptions.external` too would bypass its CommonJS conversion. Historical
Vite versions keep the original external list instead.
The bundle remains one `app.js` ES module plus `app.css`; host and CORS settings
remain caller-owned and are not broadened by the SDK.

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

Deployment-base validation requires both `base_version` (including zero for a new
container) and `expected_updated_at`. `app_deployment_base_required` identifies
missing fields. A successful link from an older CLI does not establish a usable
base: use the CLI build matching the backend, relink the exact unreleased app,
and rebuild/verify its source. Never synthesize a revision, relax the backend
comparison, or recreate the app. A development-checkout CLI can validate a dev
backend without an npm publication; that recovery does not update the published
CLI used by other agents.

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
- Storage upload failures report `app_storage_upload_failed` (502); only an upstream HTTP 409
  reports `app_storage_conflict`. Error details retain the structured upstream status and object
  identity, even when the storage SDK's JSON decoder masks an HTML error. Response bodies,
  request headers, signed URLs, and credentials are not included in those diagnostics.
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
3. **Component rendering** -- All SDK apps and SDK reports render as React components in the same Shadow DOM host, regardless of source or installation provenance. No SDK app iframe runtime.

   **Trust boundary:** Shadow DOM isolates styles, not JavaScript or credentials. A loaded SDK bundle shares the Portal browser context. Backend ownership, declared tools, capabilities, billing, report-action confirmation and resource revisions remain enforced on the supported SDK/API path; they are not a sandbox against arbitrary same-origin bundle JavaScript. Store review and accepted source provenance are therefore code-trust decisions. Plain HTML documents remain separately sandboxed in `HtmlDocumentFrame`; they are not a second SDK runtime.
   The portal mounts each app into a shadow-scoped surface and injects the runtime provider itself.
4. **HTTP bridge for data** -- SDK operations use the authenticated runtime bridge; sizing and navigation stay in the shared host.
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

The authenticated layout retains at most three visited app shells, including while Manager, documents or ordinary product pages are selected. Unvisited pages are never mounted speculatively. Same-app navigation changes only the route export inside the existing shell; Authored apps, Store installations, duplicates and SDK reports all use the same React/Shadow DOM host and scoped runtime bridge. Hidden shells cannot publish page context, claim top-bar search, or initiate navigation. A retained App shell or report that becomes active again restores its top-bar search, as on Beta. Without an active app target every retained shell is hidden and inactive; leaving the authenticated layout or changing the session retires them.

`AppOpeningBoundary` owns the entire host opening sequence (lazy route module, authorized descriptor, bundle and stylesheet). It shows no fake page or dashboard skeleton. A single small indicator appears only after 150 ms of continuous preparation; handing off between stages does not restart that delay. The indicator is a compact 28px pill in the bottom-left column shared with toasts and the connection pill (which stacks above it while this device cannot reach Notis): anchored to the bottom-left corner of the non-scrolling app-view viewport (`SidebarInset`) on desktop, and to the screen at the chat launcher's baseline below 1024 px, with safe-area and keyboard clearance, opaque inverse-theme colors, a 5px Notis-green pulse, and a scaled-down layered overlay shadow. Its label is “Opening”; the recovery state stays compact with “Still opening” and Retry. The pulse respects reduced-motion preferences. It sits above app content without covering the page with a blocking layer. After 20 seconds the indicator offers recovery. Once the real app has mounted, only the app owns missing-data placeholders. Isolated Store frames report render readiness to this same parent boundary; they do not display a second host loader.

While an uncached destination descriptor is pending, the previous route stays mounted and visible but inert. Its resource/item identity and path remain those of the displayed descriptor until the destination commits. This preserves the shell without allowing an old article's controls to act under a new article's context. Warm cached opens and background revalidation do not replace populated content.

`GET /portal_views/get?bootstrap=light` preserves authentication, entitlement, live app access checks, route/tool permissions, selected collection item ancestry, schemas and signed assets. It skips tool discovery and initial data queries. Omit the option for the legacy full bootstrap. `tools.read_cache_scope` shares reads only across routes with identical effective permissions; `access_hash` remains route-specific.

The view bridge runs blocking authentication, entitlement, descriptor hydration/signing and native database reads in worker threads so independent app requests can progress on the event loop. Live access and database-definition checks remain mandatory on cached descriptors. The cached-detail path reads the live app row and its owned database definitions together, with an exact embedded count; missing, malformed or truncated embedded sets fall back to the fully paginated database read. It never caches the live access decision or changes the returned detail payload. Cache invalidation advances an epoch under a short lock; a worker holding an older snapshot cannot repopulate the cache after invalidation. No database I/O runs while that cache lock is held. Generic tool calls also offload connection lookup, billing-user reads and credit-cap evaluation. Financial settlement remains synchronous so cancelling a queued worker cannot skip billing after a paid provider result; access, credit denial and fail-closed billing still complete before a result is returned.

The sidebar's `portal_apps/list` summary read and Portal app authentication/CLI scope checks also run in worker threads, so a concurrent sidebar refresh cannot monopolize the request event loop while a view opens. The existing 10-second, user/options-scoped summary cache retains copy isolation and uses an invalidation epoch: a summary read begun before a mutation cannot repopulate the cache after that mutation. This does not defer authentication or weaken runtime access checks.

App-view database queries include document bodies by default. Lists that only need titles and properties can explicitly use `useDocuments(slug, { includeContent: false })`: the runtime projects metadata columns and returns null body fields, while keeping authorization, filtering, sorting, and pagination unchanged. Metadata and full-content query caches are separate. Open records still use `useDocument`; full-body search must request full content when needed. This opt-in does not change generic database-tool responses or existing apps.

Fully materialized apps reuse their app-owned database rows without consulting legacy unowned databases. App detail shares one fully paginated, request-scoped owned-database read between declared database materialization and interactive metadata. App access is checked first; the snapshot is not retained across requests, newly materialized declared rows are included, and document export remains limited to source-declared databases. Catalog counts use the service-only `notis_app_active_document_counts_v1(text[])` RPC for one exact aggregate over the backend-authorized database IDs; a missing RPC during a rolling rollout falls back to the prior individual counts. Empty databases remain zero and archived rows remain excluded. Native document reads reuse the database snapshot that authorized the document for schema projection instead of performing that same authorization lookup twice; generic document-tool dispatch also runs its blocking read off the event loop.

`internalNavigation.ts` dispatches shared navigation through the save guard; `appViewNavigation.ts` owns persistent installed-app selection. It uses the Next-integrated native History API, with synchronous client-shell selection; non-view routes still use normal router navigation. This avoids a competing RSC transition that can commit an old URL after the new view paints.

Clicked destinations and back/forward navigation start their authorized lightweight descriptor in parallel with the lazy route module. These foreground preparations run at foreground priority, so they are never held behind the speculative queue’s concurrency limit, and they share the same scoped descriptor/asset promises. Every SDK bundle uses the same loader and Shadow DOM mount. Host-provided rich-text and Markdown editors load on demand, with an editor-local accessible placeholder, so non-editor views do not wait for editor code.

Retained hosts keep a stable DOM order independently of their LRU order, preserving the Shadow DOM and mounted React shell. Bundle modules, styles and reads remain scoped by account, environment, app/report identity, release and effective permissions. Per-request cache keys include the route context. A report document's reads are scoped to that document, so moving to another report must not reuse its reads. An app route's reads carry only the app and route, never its deep-linked `?resource=` id, so moving between resources keeps the same cache instead of emptying the view and refetching every read. Tool reads are keyed by their exact arguments; a custom `useQuery` read that depends on the resource must include it in its key, as the [design guide](../server/skills/notis-apps/references/design.md) requires. All SDK bundles receive theme tokens and Portal contexts through the same host. There is no separate iframe host, postMessage SDK bridge or iframe-specific editor overlay.

Space transport lifetime follows current account/source/access/record authority,
not cosmetic selection or chrome callbacks. Selection still updates the frame
and active draft/navigation boundary without remounting its local UI. A
URL-parameter change (a record or param picked inside the view) keeps the
already-resolved same-authority frame mounted, visible and usable with its last
authorized params while the server resolves the new link; the new params then
reach the mounted view in place, through the SDK runtime context. New params
enter only after resolution; refusal removes the old frame, and account, Space,
record or source/access-generation changes do not inherit its local state.
Converted views wrap each page in a record wrapper that reads the picked record
through the Space's declared read-only `lookup_record_<database>` action and shows
only a skeleton until that read has data. So that picking a record never blanks the
page, the host (`usePreparedSpaceParams`, `spaceRecordLookup.ts`) starts that exact
lookup (same action, input and SDK cache key) when the view navigates, alongside the
link check, as a direct read (`queryClient.fetch`, joining a read already in flight),
never through the shared speculative prefetch queue, and holds new params whose lookup is not cached yet for at most four
seconds while it is read; the view keeps its last params meanwhile and then switches
in one step. Only a declared read-only lookup is ever started; params with nothing
to read pass through in the same render.

Each view of a Space is its own retained frame (`PersistentSpaceViews.tsx`, at most
three). A frame shown again after another view of the same App family (its Space and
the sibling views sharing its parent Space) starts with an empty top-bar search: its
app's `onChange('')` runs before the search is restored, as Beta's remount of the
App page did, unless the address it returns to carries that exact search text. Its
data stays warm. Only real navigation counts (`spaceViewReturns.ts`): a frame hidden
while the session is checked again (a token refresh), or shown again after another
App, the Manager or an ordinary page, keeps its search, as Beta's retained App shell did.

Space view opening mirrors the App path. While a view is authorized and read,
the Portal shows only the shared opening indicator; the view's own loading state
is the only skeleton. `spaceViewCache.ts` remembers, per session and for at most
ten minutes, the server's link resolutions, landings and presentations: a
remembered view paints at once and is checked again in the background, and a
presentation whose signed bundle links expire within a minute is read again
rather than mounted. When the Portal opens a link (`resolve-view`), an optional record
param that names no record the person can open (unknown, deleted, private or malformed,
all alike) is left out and listed in `unavailable_params`; the view opens without it and
the Portal says once that the item is no longer available, as Beta opened the list.
Required record params, the record a record link selects, and every other caller of
`resolve_view_target` (renders, memory, agents) keep the strict refusal. An archived
Space opened from an old link shows an Archived badge and, for its Editors, Restore:
`POST /portal_spaces/unarchive {space_id, revision}` (`spaces_service.restore_space`)
runs `restore_notis_space` in one transaction, with the structure lock, Editor check
and revision guard archiving uses. It also restores every descendant (through
`parent_space_id`) archived with the Space, that is carrying its exact `archived_at`:
a converted App archives its top-level Space and each page with one timestamp, so the
whole App comes back, as Beta's restore did. A page archived on its own stays archived.
A metadata update with `archived: false` takes the same path (alone, not combined with
other changes). The page shows the restored Space at once (no second Restore with the
old revision) and reloads; both directions write a `[Spaces audit]` log line.
A first open (and a background preparation) asks
`POST /portal_spaces/open {url}` once instead of resolve-view, then get (once per
default page), then presentation: the server (`server/lib/space_open.py`) runs
those same functions for the same signed-in person, reads the landing of the
Space a single-id link names (or, for a view link with a record, that view with
that record) while the link is checked, and keeps it only when the answer names
exactly that Space and record. A landing's sidebar and, for a Space that shows
itself there (a record, or no default page), its presentation are read together
once `get` answered; a landing read before the link answered reads its
presentation's rows meanwhile but signs its bundle and keeps it only after the
answer named it, so a refused link never signs or returns one. `get_space` reads a
signed-in person's Space grants that an action can name (never cloud computer
approvals) alongside its access check and, when they have at most three live
issuer and record pairs (`EARLY_ISSUER_CHECKS`), checks those issuers alongside the
release and its assets; with more, or for a Site or link read, it checks only the
pairs the published actions name, one after another. An action naming a grant the
early read left out is decided by its own read by id; the same rows and checks
decide its actions. The sidebar layout reads legacy aliases only when the person's
settings hold a legacy layout, then the App's pages with its route lists; an open
reads those settings once, alongside the link check, for every landing it reads.
Only a root Space's open also reads its own root alias (its App and Set up entry).
It follows the person's primary page or the Space's
default, and also answers the default page's own link. The link check runs in one
native read scope (`native_read_memo`): the record a record link names and the
record param it fills are read once, and its record and schema are read together.
For a view-plus-record link, the person's views of the record's database are asked
as soon as its routing hint answers, and the view the link names is asked alongside;
once the hint names the record's database, the record and its schema are read
through that view's binding into the read memo, so the record path answers both
from it (one record read in all). These are the record path's own reads for the
same person, used only when the link does not name a Space; the named view's
refusal check reuses that view's early answer instead of asking again, and it and
the final recheck of the chosen view after every record read still decide. The
early ask of the named view is the one extra catalogue read such a link makes
when its last id turns out to be a Space.
The first open of a page load starts before the Portal boots: a document-head
script (`portal/src/lib/spaceOpenPreload.ts`, like Beta's App view preload) sends
the same request with the stored session's own bearer for a view link (never
with a token within two minutes of expiry, which supabase-js would refresh as
the Portal starts). Once it answers with a presentation, the script also fetches
that bundle's code (`appBundleLoader` takes it by its exact https link) and
preloads its styles. While the Portal still checks the session, a page on a view
link takes that open (`adoptSpaceOpenPreload`, only for the same bearer, link and
API, and with the same limits as below; nothing mounts before the check allows it)
and fetches the Space surface code; a frame mounted after that code loaded renders
it without suspending, so the view shows as soon as the check passes. Taking it
never asks anything (an early open that failed or answered too long ago leaves the
view to ask itself once it mounts), keeps a refusal for the view's first open of
that link (shown without asking again, within the same three seconds), and is not
the view's open: background reads still wait for the view to start, and its first
reads count from when it mounts. `openSpaceLink` takes it only for the same bearer, link and
API: while it is in flight, within the same 20-second limit as any Space
request measured from when it was sent (the script also aborts it then), or
once answered, only within the three seconds a foreground read reuses an
answer. A 4xx it answered keeps its status and error body and is raised as
is, without asking again (an older API's 404 `not_found` falls back to
resolve-view at once); only a network failure, a 5xx or a request past its
limit leaves the Portal to send its own, and a cancelled open stops waiting at
once. A refusal is the link's
refusal; a landing or presentation that fails is left out and the Portal reads
it itself, so its error shows as before. The Portal keeps an answer only when it
is complete and consistent (same Space, record, revision and runtime, usable
bundle links); an API without the call answers 404 `not_found` and the Portal
falls back to resolve-view for that session for five minutes, then tries the
call again. The presentation reads its release, journal and the
re-read of the Space together, signs both bundle files together, and hands out a
bundle link signed in the last 55 minutes again (one-hour links, matching legacy
App views, with at least five minutes left for loading; the browser and asset
cache then reuse the bytes). Only compiled code is signed, not data, and every
open still checks the viewer's current authority. On its way through the API an open
(like every Portal request) waits only for what decides access: a sign-in the
60-second validation cache has not seen yet is checked by Supabase first, and only
then is the linked Notis user read, for the auth user Supabase returned
(`portal_auth`, only the user id unless the user row is needed); a token Supabase
refuses never reaches that service-role read. The log decoration (email, beta)
never holds a request: a missing or expired entry is refreshed in the background,
so a person's first request in a process logs with the user id only. Supabase
connections (PostgREST and the sign-in validation) stay pooled 25 seconds when
idle (`SUPABASE_KEEPALIVE_SECONDS`, half the edge timeout one probe measured,
because these pools also send writes that are never retried), so a page load
within 25 seconds of the last one on a quiet server does not open a new TLS
connection for each parallel read. A record page's presentation is
the Space's record-independent presentation plus that record as context: once
the session holds it for a Space, a record link reads only its landing (`get`,
which the server authorizes per record) alongside the link check, and the Portal
builds the record's presentation only when Space, revision and runtime (access
scope, actions, bindings) are identical and the presentation is not a Site's.
Background reads wait for the open view (`whenSpaceViewsSettled`, at most 60
seconds): for it to land, then for the view's own reads (its lists, actions and
viewer reads, counted by the runtime's `spaceViewFetch`: those started while it
opened or within four seconds after, and every read started while another of them
is in flight or within one second after the last one ended, so a dashboard that
reads its cards in waves holds them until its last card; a view that starts none
within 1.5 seconds lets them go). The sidebar reads a collection page's records
only for rows it shows: once when the row shows (a row shown as the page loads
after the open view's reads; a row the person reveals, by expanding it or the row
it sits in, at once, as Beta's sidebar read an expand, with a placeholder until
the records land), again on a change (a change made here or a live signal, also
one made while the row was not shown: each page's records remember the change
they were read for) and when the person returns to the window (focus, or shown
again after being hidden), at most once a minute per page; never for every
collection of the tree, on a timer or because the list was re-read. Once a view's
reads finished, the one view most likely opened next is prepared in the
background (the next sibling in the person's sidebar order, else the one above,
else the first child; pages hidden by design are skipped): one open request for
its link, landing and
presentation, plus its bundle bytes, never module evaluation or data. An admitted
read can finish under unchanged authority; a late navigation or prepared draft
cannot replace a newer selection. `SpaceNavigationCancelled` is a typed UI
cancellation, not an action failure or receipt. It survives frame serialization;
sources release only the current canceled selection and resynchronize with host
state. Do not classify cancellation by matching an error message or let an older
request clear a newer error. Current authorization and network failures remain
visible, and true authority changes retire old transports/results.

Retained component-host wrappers must preserve a definite `height: 100%` and must not flex-shrink. Otherwise the renderer's percentage-height chain resolves to content height and split layouts stop above the viewport bottom, especially with short skeletons or empty states. Do not position these wrappers: the opening pill anchors to `SidebarInset`.

For split-view sizing changes, check the real Portal with delayed initial reads and again after content resolves, including a resize. From `portal/`, run `node scripts/smokes/check-split-app-viewport.cjs --session <named-browser-session> --app-id <id> --state loading` (then `--state loaded`). The read-only check verifies top, bottom and horizontal viewport boundaries plus desktop pane heights; it fails if the requested loading state is absent. Standalone app-harness screenshots do not prove the Portal's parent-height chain.

The shared Shadow DOM frame supplies a definite content-panel height for every app provenance. App panes opt in to full-height layout; normal document pages retain natural overflow. Verify both top and bottom pane edges, tall-to-short resizing, resource changes and long-content scrolling in the actual Portal, not only a standalone harness.

The SDK cache reads successful snapshots synchronously, including empty arrays and null documents. `loading` denotes a missing initial response; `isFetching` also covers background refresh. Query keys include exact arguments. The host scopes caches by account/session, API environment, runtime app, bundle version and effective permissions. Query clients retain at most 100 idle entries each, 24 recent app/route/report/permission scopes; route detail and asset caches are bounded separately. Active subscriptions pin entries until detached. No persistent offline storage is introduced.

Descriptor and asset reads have a 15-second deadline. SDK cached reads default to a 30-second deadline, expose a scoped error on expiry, and retain any successful snapshot. Deadlines do not replay callbacks or mutations; late results cannot replace a successful retry. A tool call inside a custom read must itself carry `readOnly: true` (the outer `useQuery` option does not implicitly classify nested calls). Prefer `useToolQuery` for a simple tool read; it forwards that classification. An unmarked generic SQL/tool call invalidates app queries after completing, which makes it unsuitable inside a cached read and can invalidate its own result before commit.

Returning to a retained app after the default 30-second freshness window invalidates its mounted reads after paint, for every app provenance. Cached content stays visible while they refresh; retaining the shell must not bypass refresh merely because its hooks never remounted.

Mounting or navigating to a view honors the descriptor cache's 30-second freshness window. Realtime changes, app changes, asset errors and explicit retry force an authorized descriptor refresh; merely finding cached content does not force a redundant request. This does not change runtime-call authorization or the account, version and permission cache boundaries.

Storage-backed runtime descriptors batch uncached JavaScript and stylesheet signing into one private-bucket request. Existing per-path URL cache expiry is unchanged; configured external URLs bypass signing, cache hits avoid storage calls, and a single miss uses single-file signing. Batch responses are matched by path, not order. A per-file error does not discard other valid URLs; failed/malformed results are not cached, and transport failures do not fan out retries. App authorization still runs before descriptor construction.

Runtime execution discovers only the requested provider family. Its partial descriptor cache is keyed separately from a complete tools/list response, in addition to account, app, route and effective access hash; concurrent requests in the same scope share discovery. This only narrows discovery work: exact declared names, live app access, connected-account scope, surface policy, credit gates and billing remain enforced. App tool discovery/execution omits separate integration-logo metadata requests because app descriptors do not expose those icons; account and label resolution are still live. Other discovery surfaces retain logo metadata and use exact provider slugs for API requests. Runtime detail/route-list reads also skip signing Store screenshot URLs; app-detail and Store consumers retain media signing by default, and runtime bundle JS/CSS URLs still use the authorized signing path.

Writes, realtime and explicit refresh advance generations, so neither the query cache nor transport deduplication may reuse a pre-invalidation response. Access loss and confirmed auth transitions permanently retire old clients and clear evaluated bundle state. Signed URL renewal updates transport without resetting a healthy shell or stylesheet; asset failure requests fresh authorized URLs. Stale bundle completions and old-route Store publishers cannot commit into the current destination.

Installed app changes invalidate authorized descriptors and permission-scoped reads. Local source edits do not publish discovery events or alter mounted release state.

Hover/focus and newest-first chat-link preparation fetch authorized light destination descriptors and asset bytes without evaluating Store code in the Portal. The speculative asset snapshot cache is bounded to 48 entries / 16 MiB and cleared on session/app invalidation. App-owned `useQueryClient().prefetch` calls share a two-slot queue with host preparation. Only small explicitly read-only requests qualify; full collections, provider sweeps, fan-out aggregates and mutations remain foreground actions.

The shared document/history/save and recent-chat preparation contract is owned by the Portal navigation code under `portal/src/`.

The canonical UI/authoring contract and cached-read examples live in [the shipped Notis apps skill](../server/skills/notis-apps/references/design.md#instant-view-loading-contract-required). The CLI scaffold and bundled SDK source mirror that contract. Release the compatible host/SDK before deploying apps that rely on this behavior; this migration itself does not authorize package publication or deployment.


### Loading measurement objectives

Use public UX response-time objectives, not a private competitor account or an assumed Notion SLA:

| Navigation state | First real app skeleton or content | Initial view fully loaded |
| --- | ---: | ---: |
| Cached return | 100 ms | 1,000 ms |
| Uncached app | 1,000 ms | 2,500 ms |

These are engineering targets, not a statement that every app already meets them. The response boundaries are informed by [NN/g's 0.1 s and 1 s guidance](https://www.nngroup.com/articles/response-times-3-important-limits/); [Google's good LCP threshold is 2.5 s at p75](https://web.dev/articles/lcp). Full data readiness is a stronger condition than LCP, so do not present the two metrics as equivalent or claim a Notion comparison from them.

Measure the first app-owned skeleton separately from the host opening indicator. An absent skeleton is N/A, not zero. Record visible app readiness and outstanding/background requests separately; silent revalidation must not erase the fact that cached content was already usable. Errors, missing releases and timeouts are not successful loads. Inventory every manifest route and list apps with no routes explicitly.

Keep browser-download-cold launch, page-session/app-cache-cold navigation and retained cached returns as separate cases. State whether the surrounding shell was settled before navigation, preserve app release/build identities, and use the same protocol before and after. One sample per route is a diagnostic sweep, not repeated-run or field-percentile evidence. Record sample counts and report the slow routes alongside aggregate values.

SDK-owned query failures use `packages/sdk/src/queryErrors.ts` (EN + FR). The hooks
format their messages from `runtime.context.locale` when rendering, so changing
language translates an already-cached error without replaying a read. Stable codes
and developer diagnostics remain on the error; server/action refusals retain the
host bridge's translated messages and receipt metadata.

### App scaffold styling

New CLI app scaffolds use Tailwind CSS 4 with `@tailwindcss/postcss`.
`app/globals.css` is the only Tailwind entry point: it explicitly loads
`tailwind.config.ts` and scans app, component, library and bundled SDK sources.
The retained config owns Notis theme tokens and the animation plugin. SDK
`styles.css` is framework-neutral CSS on injected Notis variables; it must not
start a second Tailwind compilation or depend on the consuming app's `@apply`
context. Its shell rules (`*` border colour, `[data-notis-app-root]`,
`.notis-app-shell`, `.notis-app-surface`, row colours, split panes, sections) live
in the native sublayer `@layer components.notis-sdk`, after a repeated Tailwind 4
order statement (`@layer properties, theme, base, components, utilities;`, Tailwind 4's
full order including the `properties` layer of its `--tw-*` fallback reset), so a page's
utilities (`p-4 sm:p-6`, `border-red-500`) override them. In Tailwind 4 apps they also
override preflight, whichever stylesheet loads first; leaving `properties` out would make
it the strongest layer when the SDK stylesheet loads first, and its reset would then beat
utilities (shadows, rings, transforms) in browsers that use the fallback. Tailwind 3 emits
preflight, components and utilities unlayered, and unlayered rules beat every layered
rule: there its preflight (`button` and list resets, `*` border colour) wins over the
shell rules, so a Tailwind 3 app that puts a shell class on a `button`, `ul` or `ol`
restates the background and padding it needs. Never use bare Tailwind-owned
`@layer base` / `@layer components` blocks: Vite processes the SDK import
independently, and Tailwind 3 rejects those blocks without matching `@tailwind`
directives in that same stylesheet (a dotted sublayer name passes through). Keep its canonical `packages/sdk/src/styles.css` and bundled scaffold
copy synchronized. Existing apps may retain their older Tailwind build.
List-row spacing is the one component exception: `.list-row` keeps the Portal/Beta
16px horizontal gutter and 12px vertical padding, even beside `px-*` / `py-*`
utilities. Only that padding is unlayered, with enough specificity to survive either
Tailwind 3 stylesheet order. Shell and section padding, split-pane widths, row
colours and borders still accept responsive page utilities. A deliberate inline
or important padding override can change a row's spacing.
The SDK's `notisTailwindContent` Vite helper registers its sources with an
additional CSS `@source` directive for Tailwind 4 imports. For existing Tailwind 3
`@tailwind` entry points it retains the temporary configuration wrapper. Both
paths preserve the author's configuration and PostCSS plugins; neither rewrites
the app's source files.

## Independently authored reports and passive feedback

SDK reports use this same Shadow DOM renderer with a viewport-height frame and natural vertical scrolling for long pages. They retain their document/revision identity, declared-tool permissions and explicit action confirmation. Host document editors remain unavailable to report code; edits use declared tools. Plain HTML is a separate document format, rendered in `HtmlDocumentFrame`, not a second SDK app runtime.

App views retain their shared implementation across records; reports do not deploy or replace that implementation.

### App stylesheet root parity

Built styles scope document-level defaults to both `:host` (Portal shadow DOM)
and `[data-notis-app-root]` (the standalone verification harness). The harness
mount carries that attribute. Preserve Tailwind theme variables at both roots;
host-only variables silently remove spacing, typography and controls in previews.
Global `html` and `:root` selectors remain forbidden in deployed bundles.

## Embedded SDK build ownership

`packages/sdk/` is the only authored SDK source. The CLI build generates `packages/cli/dist/sdk/`, which is included in the published package and used for scaffolding/refresh. Host-only presentation mounting stays in the canonical SDK and CLI host bundle, not in an app's public embedded SDK. Refresh retires only known unmodified copies; modified extra files remain visible to the normal boundary validator. Do not restore an authored copy under `packages/cli/template/packages/sdk/`. The public CLI mirror receives the canonical `packages/sdk/` source so its builds remain self-contained.

### Record components in Space views (V12)

The Portal injects first-party record UI through `runtime.ui`. Source uses stable native keys, not legacy
Document page URLs:

```tsx
import { DocumentEditor, RecordProperties, HtmlFrame, ReportFrame, ShareControl } from '@notis/sdk';

<DocumentEditor recordKey={item} />
<RecordProperties recordKey={item} />
<HtmlFrame recordKey={item} />
<ReportFrame recordKey={item} />
<ShareControl recordKey={item} />
```

`DocumentEditor` includes database properties by default (`showProperties={false}` when composed separately),
live collaboration, image/file upload, and native file/report viewers. The signed-in Editor's current published
Space must declare and link the record's database. Metadata uses native revision-checked writes; bodies use the
purpose-scoped collaboration service. Credentials, physical bindings and uploads stay in host closures, never
source props. Candidate preview authoring is unavailable until it can use exact declared preview actions.

Inside a Space or app ShadowRoot these components (and the legacy `AppDocumentEditor`) add the Portal's
embedded stylesheet `/embedded/blocknote.css` once to that root. Its compiled Tailwind utilities only match
inside the container the Portal renders around them (class `notis-embedded-ui`, built by
`portal/scripts/embedded-editor-scope.mjs`, specificity unchanged), and the Portal theme variables and base font
sit on that container. The view's own elements keep the view's own stylesheet: a record pane never turns a
view's `md:block` into the Portal's `.hidden`, or its font into the Portal's. A component's `className` always goes
on that container (`portal/src/components/spaces/SpaceEmbeddedScope.tsx`), never inside it, so the view's
stylesheet alone decides it; `HtmlFrame` and `ReportFrame` fill the container their `className` sizes, and an
`HtmlFrame` without one fills the view's own element. Loading and unavailable placeholders, the report opener's
chrome and the HTML frame render inside such a container too, so they are styled in any ShadowRoot.

### Document page (`DocumentPage`)

When a record is the main content of a view (a note, a document), the view renders the whole page with
`<DocumentPage recordKey>` instead of composing `DocumentEditor`, `RecordProperties` and its own title. The
Portal draws Beta's document page inside the Space (`portal/src/components/documents/DocumentPageView.tsx`,
mounted by `SpaceDocumentPage`): breadcrumb ending in the record title, Saving or Saved status, the '...' menu
(always shown, as on Beta: Add cover, disabled while read only, plus the Space's `menuItems`), cover, icon picker,
32px title, the meta strip (Editable or Read only, type, database, created, updated) with the Configure panel
listing the properties, and the collaborative body with
presence, Beta's slash menu (none inside tables), no side menu and no link toolbar, in a 900px column. Title,
icon, cover and properties share one save queue that saves 1.5 s after the last change (Cmd+S at once, guarded
on leave); the page is read only until the live room has synced, as on Beta. The toolbar's visible status stays
Saving, Saved or Read only; joining or reconnecting the live room is an icon with its own label in a fixed slot.
Files open in their viewer under the header; HTML and reports show only the toolbar (breadcrumb, `actions`, Share,
'...' menu) above their frame. Archived and non-writable records get the same page read only, with no live
session. The record UI read requires a signed-in Editor (`space_record_ui._execution`), so a Viewer of the Space
gets the page's error state, not a read-only page, and Sites use their pinned record view.

Inside a Space's ShadowRoot the page's Portal utilities come from `public/embedded/blocknote.css`, unlayered and
one class more specific than the Space's own (`scripts/embedded-editor-scope.mjs`): a Space that ships Tailwind v3
(unlayered utilities and form reset) otherwise replaced them (the column lost its 48px gutter). Content the Space
passes in (`actions`, `aboveBody`, `belowBody`, a `layout`'s own elements) sits under `notis-embedded-slot` and
keeps the Space's styles; the parts a layout places carry the Portal's again.

```tsx
import { DocumentPage, usePrefetchRecord } from '@notis/sdk';

if (params.note) return <DocumentPage recordKey={params.note}
  breadcrumb={[{ label: t.allNotes, onSelect: () => navigation.toSpace(resource.id) }]}
  actions={<TrashButton />} onSaved={() => notes.refetch()} />;
```

Slots: `breadcrumb` (crumbs before the title, or `false`), `actions` (toolbar buttons), `menuItems`,
`aboveBody`, `belowBody`. Toggles: `share` (off by default; turn it on only where Beta shared the record),
`header` (`false`, or `{ cover, icon, title }`), `meta`, `properties` (`'panel'`, `'hidden'` or
`{ include, exclude, order }` by property name), `width` (`standard` 900px, `wide`, `full`), `readOnly`.
Callbacks: `onDirtyChange`, `onSavingChange`, `onSaved({ recordKey, title })` after each confirmed save. `layout`
receives the host-bound parts `{ Toolbar, Header, Meta, Properties, Body }` to rearrange them while one editor
session and one save queue stay in place; with a layout, Meta shows only its strip (the properties render once,
where the layout puts `Properties`) and `aboveBody`/`belowBody` are not drawn. `DocumentPageSkeleton` is the
page-shaped placeholder (same column, gutter, toolbar height and icon row, so nothing shifts);
`usePrefetchRecord()` starts a record's read once a row has been hovered or focused for 150 ms.

Loading follows the instant-view standard. The page's own read (which asks for the collaboration credential)
starts when the view renders it, not after the editor code. A record param that a DocumentPage has rendered is
remembered per Space revision in the browser (param names and the last read-only choice only); a later link
carrying that param starts the record's read and the editor code while the Space's own code loads. An editable
page's early read asks for the collaboration receipt, so mounting the editor does not compete with a plain read.
That opening belongs to this runtime's next page mount only: it is consumed once, including when it finishes
before the editor code loads, and expires after 30 seconds. Writes, body saves and sign-in changes invalidate it. Other record params (a folder, a highlighted
row of a view without a document page) never start a read or the editor code. Until the record is known the page
shows its skeleton, or the first answer of a read already in flight, never blank text. Snapshots are kept per
browser session (person, session, Space, revision, presentation document and preview; never for a Site) for 10
minutes: reopening a record shows it at once, read only, and the page becomes editable only on its own read (a
completed read from another opening never stands in for it; reads still in flight are shared). The page keeps its snapshot current
with what it shows, typed body included; a body save from `DocumentEditor`, a write action, a document body write
or a live change drops the stale snapshots. Saves always check the latest revision with their own read. The
live-editing notice sits in the toolbar status, so joining never moves the body.

Hosts that predate `DocumentPage` render the record with `DocumentEditor` and the breadcrumb, actions and
`menuItems` (as buttons) above it and call `onSaved` (title null) when a save finishes, so a Space can release
before every host has the page; `layout`, header parts and meta are not available there. The CLI refreshes a Space's embedded SDK from the SDK
it ships on every build: until the CLI a Space is built with carries `DocumentPage`, a Space can reach the same
host component through `useNotisRuntime().ui.DocumentPage` with the same fallback (the converted Notes Spaces do
this in `lib/document-page.tsx`) and switch to the SDK import once it ships.

Native body saves separate socket arrival from durable confirmation. The host opts into an arrival-only
sync-step-1 response with trailer `1`, then pins HTTP `collab/flush` to its captured `expected_update` (base64
Yjs update). The sidecar rechecks access, drains earlier accepted updates and verifies the durable document
contains the captured structs and deletions before returning success. A replacement room, failed write or
lost acknowledgment cannot confirm the save; the proof never applies or retries changes. Clients without
the trailer retain the ordered post-commit sync response, so Portal and sidecar upgrades remain compatible.

`HtmlFrame` also accepts `html` for content returned by a declared action. Its opaque-origin sandbox never adds
`allow-same-origin`, and its viewer policy can only tighten the inherited Portal/Site CSP. Record Sites may display
their server-pinned record's native body, properties and HTML through an exact saved canonical native
query action. `DocumentEditor` is a read-only snapshot there: no session JWT, collaboration room, uploads, metadata
writes or sharing controls. The server supplies the record param and saved typed params; browser query/selection
values cannot replace them. Site `useShown` evaluates the declared filter through that saved read grant and record
scope, never Editor or generic database authority. `ShareControl` uses private/shared, copy-link and revoke behavior
for signed-in Editors. Anonymous native file/report viewers remain unavailable until they have exact pinned adapters.

A record Site may select any declared record param, including a noncollection param. The host's Site request carries
`record_key`, the optional explicit `record_param`, the published `revision` and typed `params`; `document_id` retains
its separate collection context. A unique main param selects the default; ambiguity requires an explicit param.
This never turns Notes' `note_folders` collection into the Notes database. The immutable server `record_context`
pins the exact Space, selected param/database/binding/revision/scope, collection context and typed params. The host
receives that pin as `site_record`; source receives only its safe record key, param name and values. Generalized
record Sites do not inherit into children and only execute saved read-only native queries: no provider reads,
generic native CRUD, writable rooms or upload authority. The primary database always intersects the exact record;
other databases require a pinned collection context or an explicitly proven relation scope.

Compatible source redeploys (including presentation/copy changes) retain the Site URL. Changing the selected
param, binding/scope, param schema, collection definition or declared query surface fails closed until an Editor
turns the Site off and republishes it. Disabling still works if the record/source no longer reads. Current record
visibility, issuer access, saved query grants and binding pins are rechecked for every read; source revision alone
never grants access. Existing whole-Space and collection Sites retain their separate explicit-action behavior.

`ReportFrame` renders a database report row's immutable SDK bundle with the parent Space runtime: the old report's
account-wide tool/database grants are not restored. Each report's full artifact identity selects its bundle cache.

`notis spaces init Notes ./notes --database-key notes --path notes` creates an editable collection source with an
`item` record param marked `main`, a declared `shows.items` list with `open: 'item'`, and this default record layout.
It creates local files only; link the database and use the normal selected `--space collection` build/deploy workflow.
The scaffold includes an explicit empty-list verification fixture. Collection labels use the `title` column by
default, or a canonical text/number property ID; display names are not collection storage identities.

Record controls carry their own generated Shadow DOM stylesheet, so authored views do not have to repeat the
host's utility classes. File properties use the existing attachment store through the scoped native host client;
the file is uploaded first, then the user saves the revision-checked property edit.

### Live view rendering (V8)

Full-screen (`chrome: 'hidden'`) views keep the Desktop window's draggable strip
outside their interactive surface. The host exposes `--notis-view-viewport-height`
for a viewport-filling canvas; use `var(--notis-view-viewport-height, 100dvh)` so
the same source fits Desktop and a standalone renderer/Site without overlapping
window controls. Keep the small host exit control's top-right area clear.

`notis views render <view-link> --outputs markdown,screenshot --width 1440` saves a Markdown file and full-height PNG
under a new local `.notis/renders/` directory. `--output-dir` chooses another directory without overwriting existing
files; `notis spaces screenshot <view-link> --width 390` requests only the PNG. `LOCAL_NOTIS_RENDER_VIEW` returns
the same capture to agents, with the PNG as image content rather than base64 prose. Voice requests Markdown only.
This also applies when the native render is called through `COMPOSIO_MULTI_EXECUTE_TOOL`: only successful,
dispatcher-labelled native render slots are projected as images, in result order. Ordinary provider output is
never searched recursively for images. Batches share one 32 MiB PNG budget and retain the normal bounded-text
preview; any image omitted by that aggregate limit is explicitly marked for a separate render.

The current caller's access, source revision and declared record params are pinned in a short-lived read-only
credential. Source receives no account credential, collaboration room or generic write surface. Every read and
capture completion rechecks access; an incomplete or revoked capture releases no files. Paid provider reads run
only for agent renders and use their existing billing; background snapshots refuse them. Source-authored chart
semantics use `RenderChartData`, and a declared `SpaceMarkdown` export can replace generic DOM Markdown.

#### Reads made read only by a pinned argument

An MCP action is read only when the server classifies its tool as a read (upstream
annotations, native overrides; tool-name heuristics only restrict). One narrow,
explicit exception covers a read whose only mutating behavior is one argument: when
the published template pins that argument to the value that keeps it a read, the grant
is labelled read only, so read-only renderers (including the offline render gate) may
call it. Each case is listed per tool in `_PINNED_READS`
(`server/lib/space_provider_actions.py`) with its exact upstream tool name, the
provider's own MCP host, the pinned argument and value, the inputs that may vary and
the arguments that must stay fixed. The public slug only repeats the server name the
person chose, so the connection must also be a remote HTTPS server on that host (no
other port, no credentials in the URL). Today: `LOCAL_MCP_LEMLIST_GET_INBOX_CONVERSATION`
on `app.lemlist.com` with `markAsRead` fixed to `false`, `limit` fixed, and only
`contactId` and `page` as inputs. A pin left variable or missing, any other argument,
another upstream tool or another server keeps the write default. The
label is decided when the grant is issued, so an existing grant changes only once an
Editor authorizes the action again.

#### Declared PostgreSQL reads

Supabase MCP `execute_sql` actions are not read-only merely because their text starts with `SELECT`.
Platform authoring uses `server.lib.space_sql_reads.compile_template` before source packaging to produce
a versioned, canonical read envelope. Its complete SQL participates in source, template, grant and invocation
digests; execution never silently wraps a different query. Changed templates require rebuilding and verifying
the authored source. Unsupported statements remain ordinary actions, unavailable to a read-only renderer.

Default authoring remains the v3 envelope with an 8-second statement timeout. The authoring helper's
explicit `statement_timeout_seconds=30` selects v4: the same read guards and 2-second lock timeout,
with a fixed 30-second statement budget. No other timeout is accepted. Versions 1–3 and their saved
grants retain their exact 8-second bytes; dispatch never upgrades them. The v4 header and timeout
participate in the template digest, so each increased budget requires a new exact issuer grant and
matching verified source publication. Compiling a new template authorizes and executes nothing.

The envelope uses a read-only transaction and a fixed `pg_catalog` search path. Before the application query,
it checks the current role and supported relation, type and index behavior. Only the compiler's reviewed SQL
forms qualify; unsupported functions, casts, explicit sort operators and relation behavior fail closed.
SQL text with a null character, or a SELECT ending in an unterminated `--` comment, never qualifies, and the
relation manifest escapes both comment markers, so PostgreSQL always parses the whole envelope as BEGIN READ ONLY,
settings, guard, the reviewed SELECT and COMMIT.
Compiler acceptance alone is not proof that a particular provider database passes these execution checks.

A read the envelope's statement timeout cancels (57014) fails with the tool's `error_code: read_timeout`
(`with_read_timeout`). The Portal bridge then throws a `SpaceActionError` into the view with the reader's
"This read took too long" message and `code: 'read_timeout'` (kept across isolated frames by
`spaceActionFailureDetails`), instead of the generic action failure, so a view can tell a timeout apart and
retry it (SEO Overview asks again 4 s later, at most twice). Any other failed action keeps the generic message.

Envelope versions retain their original rules; newer authoring does not broaden an older saved grant.
The current version admits reviewed native index expressions and predicates, plus the stock `pg_trgm` 1.6 GIN
contract verified through catalog identity and callbacks—not arbitrary extensions or user-defined functions.
Pure template-validation caching never replaces current grant, connection or provider-catalog checks.

The adapter pins the issuer, original connection identity and exact template, narrowing only the effective
official Supabase transport to `read_only=true` and database features. It does not edit the saved connection
configuration or authorize another project. Receipt replay rechecks current origin and connection authority
without repeating the provider query. PostgreSQL, its provider and privileged schema administrators remain
the trust boundary; this is not a sandbox against a malicious database administrator.

#### Project-pinned PostHog reads

Spaces can declare the connected PostHog EXEC transport with a **typed read**
argument object: `{project_id, query, context, llm_model}` and no runtime inputs.
`space_posthog_reads.py` accepts a bounded fixed SELECT only. It does not accept
`command`, `connectionId`, `sendRawQuery` or a runtime project/query selector.
The ordinary EXEC surface and its upstream annotation remain write-scoped.

The adapter derives a private official MCP URL with the documented `project_id`
query parameter; it never edits the user's saved connection. PostHog pins that
request context and removes project/organization switching. This is not a
pre/post check over a mutable active project. Before authorization or execution,
metadata calls through the **pinned** transport verify the actual project ID and
the current read-only `execute-sql` and `project-get` child schemas. Their hashes,
the exact issuer connection identity, original/effective URL hashes, project ID
and logical template digest are saved in the grant. Project settings and API
tokens returned by metadata are discarded.

Only the adapter derives the physical `call --json execute-sql {"query":...}`
payload. It first checks the logical typed arguments against the durable Space
invocation, then binds that same receipt/actor/issuer/connection to the exact
derived wire payload. Generic dispatch and held-execution checks still compare
the physical payload; unrelated EXEC commands cannot use this read admission.
MCP session keys already include the effective URL, so a project-pinned request
cannot reuse an unscoped session. OAuth maintenance compares the original saved
configuration, not the private URL. Receipt replay checks current saved identity
without making another metadata or analytics request.

CLI and the warm renderer use `packages/view-renderer`; its credential-free host must be built before packaging.
The renderer runs in a separate child of the existing collaboration service behind `/views/render`; it uses an
ephemeral private loopback port, not another worktree port or environment variable. A render process failure does
not restart collaboration rooms. Production browser installation and deployment remain release gates, not a
consequence of a local render. Memory ingestion activation follows the [native index rollout](operations/native-document-index-rollout.md).
