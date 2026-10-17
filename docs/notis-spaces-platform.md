# Notis Spaces Platform

This is the canonical reference for the Notis Spaces platform: what a Space is, how
Spaces are shared, published as Sites and installed from the Store, how their views,
source, Skills, actions and data work, and the architectural rules that matter when
building, debugging or documenting them. It also keeps the repository development notes
Space work relies on; [Development workflow](development-workflow.md) owns repository
setup, environment files and the dev stack.

Use this together with [server/skills/notis-apps/SKILL.md](../server/skills/notis-apps/SKILL.md):
- this document explains the platform model and contracts
- the skill explains the execution workflow with the CLI

Spaces replaced Notis Apps. A Space converted from an App keeps the App's id, and an old
App link (`/apps/<id>[/<page>]`) opens that Space
([SPC-001](../.agents/skills/tools/notis-specs/specs/spc.md)). There is no App runtime,
App Store, `notis apps` command group or `notis:apps` permission any more; a sign-in that
still asks for `notis:apps` gets it dropped
([SPC-002](../.agents/skills/tools/notis-specs/specs/spc.md)).

### Tool boundaries

| Action | CLI | Portal |
|---|---|---|
| Pull a Space's source, build, verify and publish a new revision | Yes (`notis spaces pull`, `build`, `verify`, `deploy`) | No |
| Seal a preview, then publish or close it | Yes (`notis spaces preview`, `promote`, `abandon`) | No |
| Publish a Space to the Store, install, update or unpublish a listing | Yes (`notis spaces store ...`) | Publish to Store from a Space's sidebar menu; install from the Store page |
| Share a Space, manage its Editors, publish it as a Site, move it to the bin | No | Yes |

Agents have no App tools: in-app agents, the CLI and MCP clients work through the Space
tools (`LOCAL_NOTIS_LIST_SPACES`, `LOCAL_NOTIS_GET_SPACE`, `LOCAL_NOTIS_MANAGE_SPACE` with
its `create`, `rename`, `move`, `trash`, `restore`, `list_bin`, `duplicate`, `list_store`
and `install` operations, `LOCAL_NOTIS_READ_SPACE_SOURCE`,
`LOCAL_NOTIS_WRITE_SPACE_SOURCE`, `LOCAL_NOTIS_BUILD_SPACE_SNAPSHOT` and
`LOCAL_NOTIS_VERIFY_SPACE_SNAPSHOT`).

---

## Table of Contents

1. [What A Space Is](#what-a-space-is)
2. [Core Platform Model](#core-platform-model)
3. [Architecture](#architecture)
4. [Repository Development Workflow](#repository-development-workflow)
5. [Creating and sharing Spaces](#creating-and-sharing-spaces)
6. [The Space Store](#the-space-store)
7. [Main Components](#main-components)
8. [Runtime Bridge](#runtime-bridge)
9. [Data Model](#data-model)
10. [Rendering Model](#rendering-model)
11. [SDK Reference](#sdk-reference)
12. [CLI Command Reference](#cli-command-reference)
13. [Space delivery](#space-delivery)
14. [Design Guidelines](#design-guidelines)
15. [Non-Negotiable Invariants](#non-negotiable-invariants)
16. [Testing](#testing)
17. [Where To Look In The Repo](#where-to-look-in-the-repo)
18. [Agent Guidance](#agent-guidance)
19. [Instant-view lifecycle and cache ownership](#instant-view-lifecycle-and-cache-ownership)
20. [Independently authored reports and passive feedback](#independently-authored-reports-and-passive-feedback)
21. [Embedded SDK build ownership](#embedded-sdk-build-ownership)

---
## What A Space Is

A **Space** is a place with Editors, pages (views), sub-Spaces and the resources it links
(see the [product glossary](product-glossary.md#spaces)). Sharing a Space shares its whole
subtree.

- A **view** is a Space with an interactive presentation. Its source is a Vite + React
  project using `@notis/sdk`: a workspace index declared with `defineSpaces` and one
  `defineSpace` definition per Space (`@notis/sdk/config`), built into a frozen source and
  artifact snapshot by `notis spaces build`.
- Databases, Skills and automations are **linked** to Spaces by reference, never copied.
  Every database is linked to at least one Space and has one main view (see
  [View links, main views and agent discovery](#view-links-main-views-and-agent-discovery)).
  A Skill is linked under an alias (see
  [Source, links, Skill folders and the lock file](#source-links-skill-folders-and-the-lock-file-r5-decision-10));
  every former App Skill became a native Skill with the same id, linked to its converted
  Spaces.
- A Space's source changes reach people only as a published revision (see
  [Space delivery](#space-delivery)).

---

## Core Platform Model

### Subscription entitlement

Building Spaces is available on every tier. Entitlements resolve from the tier map in
`server/lib/plan_entitlements.py`, not from `prices.*` booleans (see
`server/lib/subscription_utils.py`). The builder entitlement keeps its historical key,
`apps_builder`, granted on every tier including FREE; `apps_external_development` is
collapsed into it and is no longer read.

What is still tiered is the compute and the resources a Space carries. Letting **Notis**
write and deploy the code for you needs the Cloud Computer (PRO and above). Automations
still need PRO+.

Reviewed native Space and database tools declare PostHog `spaces` for visibility and no
plan entitlement. Once their surface allows them and `spaces` resolves true, they execute
without a second gate. Skills, automations, and Cloud Computer work invoked during a Space
workflow still enforce their own central entitlements.

Two PostHog flags gate these surfaces (`server/lib/feature_flags.py`):

- `spaces` gates Spaces, native databases, reports, their Manager mentions, database
  automations and the curated Skills that teach them.
- `spaces_store` gates only the Store: the `/store` page and its sidebar entry, Publish to
  Store in a Space's sidebar menu, the Store updates section of the Spaces home, the
  `portal_spaces/store-*` endpoints behind `notis spaces store` (the CLI onboarding brief
  offers that fallback only when `notis spaces store list` answers), and the `list_store`
  and `install` operations of `LOCAL_NOTIS_MANAGE_SPACE`, which refuse at execution
  without it (the tool itself is `feature_flag: spaces`, and its `duplicate` operation
  needs only `spaces`). It is a part of Spaces, so every Store entrypoint also requires
  `spaces`; `spaces_store` alone opens nothing. This lets Spaces ship before the Store.

The retired `store` key gated Spaces, databases and the Store together before this split.
Current code never evaluates it: it reads a curated skill row's `store` as `spaces` (the
sync keeps writing `store` there until production runs the split; see
[Notis skills lifecycle](notis-skills-lifecycle.md)) and expands a local
`FEATURE_FLAG_FORCE_ON` of `store` to `spaces,spaces_store`.

After PostHog resolves `spaces=true` (and `spaces_store=true` for the Store), the Portal
may use an active team relationship to scope Team Store listings. A team relationship
never overrides a false, missing, or unavailable PostHog decision for Spaces or Store UI,
tools, or skills.

| Action / Notis tool | Minimum plan | Denied response |
| --- | --- | --- |
| Browse the Store and inspect listings | Signed-in user | No billing gate; hidden unless PostHog `spaces` and `spaces_store` allow it |
| Reviewed native Space/database tools | No plan entitlement | Hidden unless surface + PostHog `spaces` allow them |
| CLI Space source, build and publish commands | FREE | No billing gate |
| Six native skill-management tools | FREE | Skills are an all-tier entitlement |
| Nine native automation-management tools | PRO+ (an Editor acting on a linked automation: its owner's plan) | Canonical `automations` entitlement response; `automation_owner_plan_required` for a lapsed owner |
| Cloud Computer shell/files | PRO | Canonical `cloud_computer` entitlement response |
| Notis-builds-it-for-you (sandbox authoring chat) | PRO | Canonical `cloud_computer` entitlement response |

Trials mirror the selected plan. After a downgrade, Spaces and their data stay available
and the CLI keeps working; only the resources that carry their own entitlement
(automations, cloud sandbox) lock. Never delete Space data as a subscription side effect.

When the PostHog `spaces` flag is false, missing, or unavailable, the Portal hides Spaces
and the Store, direct Store routes redirect to Manager, and Manager neither loads nor
accepts database or view mentions. When only `spaces_store` is not true, Spaces stay and
only the Store entry, the `/store` routes (which redirect to Manager) and Publish to Store
disappear; the server refuses Spaces Store requests with `spaces_store_unavailable`.
Active team members and owners follow the same visibility boundary. Their team
relationship scopes shared content only after PostHog resolves the flags true.

---

## Architecture

```text
Space source (local workspace or Vercel Sandbox)
  -> defineSpaces index + defineSpace definitions + views + @notis/sdk
  -> notis spaces pull / build / verify / deploy (or preview, then promote)
  -> frozen source and artifact snapshot (one app.js ES module + app.css)

Platform
  -> /portal_spaces/source-publish (or source-stage, then source-promote)
  -> immutable Space source revision
  -> /portal_spaces/open and /portal_spaces/presentation (runtime descriptor, signed bundle URLs)
  -> Portal dynamically imports the bundle
  -> Renders as React component with the NotisRuntime from portal/src/lib/spaceRuntimeBridge.ts
  -> /portal_spaces/action, /portal_spaces/viewer-read and record reads for data
```

The two halves of the bundle travel by different transports, which matters in the
desktop app: `app.js` is fetched and executed from a blob URL, while `app.css` is a
`<link rel="stylesheet">` injected into the view's shadow root. Nothing from the Portal's
own stylesheet crosses that shadow boundary, so if the link fails the view renders as raw
unstyled HTML and keeps working; see `electron/src/contentSecurityPolicy.ts`.

Space source is built with the Notis CLI, locally in a workspace or inside a Vercel
Sandbox. The contract is the same wherever the CLI runs: the agent edits files in the
workspace, then builds, verifies and publishes through `notis spaces` commands.

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
resolve the Conductor Space first and address its databases by exact id;
a same-slug database owned by another Space is never a fallback write target.

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

## Creating and sharing Spaces

A Space's source changes reach people only through a published revision; see
[Space delivery](#space-delivery). The engineering `dev.sh` stack, CLI worktree profiles
and coding-agent bridges stay independent of Space delivery.

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
  (`/store`) is the Space Store (your team and everyone, with install, update and
  unpublish). The Spaces home lists only installed copies with an update or a
  conflict to settle.

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
on stays visible with a way to turn it off. The share panel (the Space view's top bar Share) then
shows "Sites aren't available yet" in each Site row without the switch (with the switch, to turn
it off, while that row's Site is still on). Its first row is the view's own Site, the Space's or its
page's (`siteFor` in `portal/src/lib/spaceSharing.ts`). A record page the view shows with
`DocumentPage` `share` on adds a row for its record-param Site (`record_key` set): while it shows, the
page registers in the view's `RecordShareSlot` (`portal/src/lib/spaceRecordShareSlot.ts`) and drops
its toolbar Share, so the view keeps one Share. The row reads that Site with `recordSiteFor` and
turns it on or off through `site()` in `portal/src/lib/spaceRecordClient.ts`; the view's own page has
one Site, so its row replaces the view's, and the top bar globe shows while any listed Site is on.
When more than one Site matches a page (`recordSites`: its record-param Sites under the param that
opens it, plus an older Site of its own view), its row disables the switch and shows the
`siteRecordAmbiguous` note, and `site()` refuses with the client-only `409 site_record_ambiguous` (the
server's `site_record_param_required` covers other refusals and keeps the generic Site error); when
one of them is an older Site of the view, the view's own row stays so it can still be turned off. A
Space that opens straight onto the view (`landingParents` in `portal/src/lib/spaceLanding.ts`: its chosen page, else its default child,
as `readSpaceLanding` follows them) never shows its own view, so for each one the person edits the
panel starts with a "Share all of {space}" row that turns it to that Space's sharing, with a way back.
The panel's adoption and caught-error measurement contract lives in
`portal/src/lib/spaceShareAnalytics.ts`; those terminal UI attempts are distinct from the committed,
receipt-deduplicated outcomes in `server/lib/space_analytics.py`. New panel series begin at their
verified production cutover; earlier use is unknown, not reconstructed from backend changes.
Any other record-param Site (a `ShareControl`, or a page shown in another Space's view) is managed
from that record's Share popover. The popover shows "Sites aren't
available yet" without "Create public link" when no Site is on for the record; a record Site still
on shows as shared, without a link to copy, with "Stop sharing" (`site()` reports it with a null
`url`, as it does a lost link while Sites are available). "This site's link is unavailable" appears only when a Site is on, Sites are
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

Spaces and SDK reports use the canonical SDK Shadow presentation. The
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

Deleting a Skill through the legacy path (`skills.status = 'deleted'`) removes
its Space links in the same transaction (trigger
`skills_remove_deleted_space_links`; while the Spaces structure lock is busy it
skips with a warning rather than failing the delete). Restoring the Skill does
not restore its links. A link left by an earlier delete has no native Skill
identity, so every release that touched it failed; remove it by binding like any
other link: `notis spaces links list <space-id>` names the binding and its
revision, then `notis spaces links remove <space-id> <binding-id> --revision <n>
--request-id <stable-key>` (`portal_spaces/space-link-remove`) applies the
resource's own link change. For a missing or deleted Skill only a removal is
accepted, by an Editor of that Space; adding a link to it is refused.

Keep the Space reachability helpers (`notis_space_parent_contexts`,
`notis_space_ancestors`, `notis_space_access_path_visible`,
`notis_current_space_editors`, `notis_space_tree_roots`,
`notis_space_record_parent`) in PL/pgSQL. As SQL functions with `SET
search_path` they are never inlined and are planned again at every nested call,
so one source release checking five links ran past the 8 s statement timeout
(57014). PL/pgSQL keeps their plans for the session: the same five links take
about 0.6 s instead of 2 s on a seeded branch.

`notis_space_assets_seeded(uuid[])` repeats the seed rule of
`notis_resource_link_reachability` (the resource's owner is a current Editor of
the link's Space, directly or through the owner's Team, or a Space-owned
resource's link shares a tree root with its origin), so
`notis_space_asset_reachable` and `read_notis_view_catalogue_v2` run the full
graph only for the links it does not return. Change both rules together: every
link it returns must be reachable in the graph. It runs once per check rather
than once per Space, so it stays SQL (a PL/pgSQL copy saved about 0.2 ms a call).

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

#### Provider actions: one sealed issuer grant

A declared action can target any final tool available to its issuer through the
CLI: native tools, Composio integrations, remote `CUSTOM_*` MCP tools and desktop
MCP. Generic bridge, shell, run and agent-control tools are excluded. Spaces keep
`callTool`, raw `request` and `listTools` disabled; source uses `useAction` or
`useActionQuery` and sends only the action ID, typed inputs and source revision.

The template fixes the tool, account selectors and non-input arguments. A literal
`arguments.account` selects a Composio account exactly as the CLI does; without
one, the issuer must have exactly one active account for that toolkit. Registered
Custom MCP servers with `NO_AUTH` instead pin the owned server row and explicitly
select no account; declarations cannot add an account selector to that binding.
Browser inputs cannot select a different tool, account or fixed target. Publishing pins
the grant and template digest; changing either requires new authorization.

The sealed pipe (`server/lib/space_tool_pipe.py`) pins the tool family, schema,
version, connection identity and read-only decision. Each call rechecks current
Space authority, issuer permissions and the issuer's active connection, rebuilds
the arguments and dispatches as the issuer. The viewer remains the receipt actor;
provider access, credit caps and usage billing belong to the issuer. Composio and
Custom MCP use grant-scoped sessions restricted to the grant's toolkit and account
(for a saved MCP server, the account it signs in with now).
Nested generic dispatch remains unavailable inside a Space action.

Generated database writers resolve against the issuer's current database catalog
and pin the resolved database ID as well as the schema, including legacy slug-only
names. Ordinary native query/insert/update/delete transactions keep their existing
authorization path.

Declared writes are available to viewers who can invoke the action. Read-only
renderers and isolated stacks admit only sealed reads; Record Sites keep their
separate native-record action scope. Background renders still refuse paid or
unknown-cost reads. Receipt replay and settlement retain the same exact-request
and current-authority checks without repeating the accepted tool effect.
An accepted paid write retains its result and usage for settlement even if access
is revoked during the provider response; the final projection still withholds it.

Desktop schema discovery on an isolated stack is limited to the exact owned
connection being authorized. Its READ call additionally requires the durable
receipt and grant. The authenticated API-to-broker request carries that authority
bound to one computer and exact request; generic Desktop discovery, calls and
shell commands remain fenced. Use a harmless run-owned stdio fixture for local
acceptance, never an unrelated Desktop server copied into the test database.

Tool-specific read rules preserve the following narrower contracts; they do not
limit the pipe's general final-tool support:

- **PostForMe:** `LOCAL_POSTFORME_GET_POSTS` and `LOCAL_POSTFORME_GET_POST` fix
  `platform` and `account_label` and pin one current issuer account. Lists fix a
  limit from 1–50 and unique statuses (`draft`, `scheduled`, `processing`,
  `processed`); only an integer offset in 0–10000 varies. One-post reads allow
  only a required bounded ID matching `^[A-Za-z0-9_-]+$`. Results are checked
  against the pinned account before projection.
- **Better Stack:** legacy `BETTER_STACK_LIST_MONITORS` (`{page:1,per_page:50}`)
  and `BETTER_STACK_LIST_HEARTBEATS` (`{page:1}`) grants preserve their fixed page,
  connection identity/version and monitoring-field projection, excluding
  heartbeat ping URLs and authentication fields. Other declared tools use the
  generic schema/effect rules.
- **GitHub GraphQL:** the read rule admits one canonical `query` operation with
  `repository` root fields, typed variables and the bounded subset enforced by
  `server/lib/space_github_reads.py`. Compile with
  `compile_github_graphql_template` before packaging; comments/whitespace are
  normalized and the exact document participates in all digests. Mutations,
  fragments, directives, introspection and unsupported literal/type forms do
  not qualify as reads. Results expose only selected fields; provider errors
  alongside data are marked `partial`.
- **Reminders:** existing `LOCAL_NOTIS_LIST_REMINDERS` grants keep their fixed
  `page_size` and no runtime inputs. The native call reads the issuer's reminders,
  with the canonical pagination semantics.

Legacy templates, digests and grant IDs stay fixed. The pipe maps saved provider values to
families and retains the pinned tool version and, except for saved MCP servers, the
pinned account; remote MCP grants resolve through their saved Custom MCP binding.
A changed or revoked identity never falls back to the viewer or a replacement
connection. Remote transport migration and credential cleanup, including the
deployment gate for previously working typed reads, are documented in
[Composio Custom MCP](composio-custom-mcp.md#rollout).

**Connection changes.** A saved MCP server's grant is authorized by which server the
issuer saved, not by the row or the Composio account it signs in with. Its identity
(`notis_space_mcp_record_identity`) covers the owner, address, transport, execution
location, Runs on computer, auth type, static header names and the stdio command,
arguments and variable names. It ignores the row ID and name, header and variable
values, the tool restriction, Test results, sign-in state and tokens, OAuth client
settings, label, description, the Composio binding columns and any later column, so
a Test, a Reconnect, a key rotation, a rename and the nightly refresh keep the grant,
and each call runs with the server's current account and toolkit (a desktop
server's grant keeps its pinned row and upstream tool, so its action name does not
change with the server's name). A pin issued with
a sign-in never runs accountless and a `NO_AUTH` pin never gains one; a lost sign-in
refuses calls until the issuer reconnects. Deleting the server leaves its grants
dormant: calls are refused until the issuer saves the same server again, then
`notis_space_mcp_pinned_connection` resolves the pin to the one row saved after the
newest grant pinned to the deleted row (`read_notis_space_grant_pin_issued_at`). A
copy that already existed is never followed, two new copies refuse until one goes,
and a pinned row that still exists is never replaced by a match. The followed row
must sign in with its own Composio account; it never borrows another one. Changing which server a row is disables legacy `mcp` grants pinned or
re-anchored to it for good (`notis_space_mcp_connection_changed`); sealed pipe
grants are refused while their pinned server identity differs. A Composio toolkit
grant (no saved server) keeps its pinned account; while that account still exists
but has lapsed (expired or revoked), calls are refused. Once it is deleted (a
disconnect or a reconnect), the grant follows only an active account the issuer
connected after the newest grant pinned to the deleted account: the only such account, or the one the
template's account selector names (a selector naming the deleted account's ID
refuses); two candidates refuse, and an account that existed before the grant is
never followed. A PostForMe grant pins one account: a status other than
active refuses calls until that account is active again, while a different account,
a cleared account, a renamed label, changed permissions or a deleted row disables the grant
(`notis_space_postforme_connection_changed`). A disabled grant never comes back;
the Space needs a new authorization.

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

A Space page can run one command or write one file on each viewer's own cloud computer once
that viewer allows it; that is how Conductor's Check dev, Sync, Archive, Connect GitHub and
environment file upload run without a conversation. The power comes from one reviewable
declaration and nothing else (`server/lib/space_cloud_computer.py`); a page without it is
refused with `cloud_computer_undeclared`:

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
  viewer must be a current Editor. Dispatch runs in `server/lib/space_cloud_computer.py`: a shell
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
  Portal realm with the viewer's signed-in session. The prompt, the trusted
  click, the click delay and the pin protect a viewer from code they did not review that reached
  the Space by mistake or in good faith (a teammate's release, a Store update). They are not a
  security boundary against hostile page code: page code in the Portal realm can still forge an
  approval and run commands as the viewer (it holds the viewer's session and can call
  `POST /portal_spaces/cloud-computer` with `approve`, then `run`). Treat Editor access to a
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

An old App page link whose Space no longer opens for this person (binned, or
never shared) opens the App's root Space instead, marked `fallback: 'app_root'`,
with the same access check and without the old selection; a load failure (503)
is never answered this way. To repair the page link itself, the old App's owner,
or an Editor of the Space it opens now (binned included), points it at a live
Space they edit: `notis spaces aliases list --legacy-id <app-id>` shows each
route, its Space and whether that Space is binned, then `notis spaces aliases
repoint --legacy-id <app-id> --route <slug> --space <space-id> --expected-space
<current-space-id> --request-id <stable-key>` (`--dry-run` first; optional
`--selection-param <name>`) calls `repoint_notis_space_legacy_alias` through
`portal_spaces/legacy-alias`. Each request is receipted in
`space_legacy_alias_receipts` and replays; `--expected-space` refuses a link
that moved since it was listed. `extra:` page aliases are not repointed, and the
new Space still checks access for everyone who opens the link.

A converted root has no App details page any more: a bare `/apps/<installed-app-id>`
link opens the converted Space like any other old App link. **Uninstall app** on a
converted root uses the normal Space Bin confirmation and revision-checked subtree
lifecycle, with its existing restoration window.

## The Space Store

`notis spaces deploy` updates one existing Space and never publishes to the Store. Store
publication is a separate, explicitly approved action: Publish to Store from a Space's
sidebar menu, or `notis spaces store publish`, which publishes a Space and its sub-Spaces
as the next version of its listing. `notis spaces store install` installs a listing as
the person's own independent copy, `notis spaces store update` updates an installed copy
while keeping the person's changes (or resolves its conflicts), and
`notis spaces store unpublish` stops new installs. The Store is gated by `spaces_store`
(see [Core Platform Model](#core-platform-model)).

### Space-linked Skill source and materializations

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

## Main Components

### `@notis/sdk`

`packages/sdk/` is the single SDK package for Space view authors.

The package is mirrored automatically to the public
[`mindtheflo/notis-sdk`](https://github.com/mindtheflo/notis-sdk) repository by
`.depot/workflows/sync-public-repositories.yml` after relevant changes reach `beta`. The
monorepo remains the source of truth; public mirror files are generated and must not be
maintained separately. The same workflow mirrors the CLI to `mindtheflo/notis-cli`.

It provides:
- `@notis/sdk` for `NotisProvider`, runtime hooks and record components
- `@notis/sdk/config` for `defineSpaces()` and `defineSpace()`
- `@notis/sdk/vite` for `notisViteConfig()`
- `@notis/sdk/styles.css` for shadow-safe shell styles and base surface classes

Important hooks include:
- `useTool`
- `useTools`
- `useNotis`
- `useNotisNavigation`
- `useTopBarSearch`
- `useHandover`
- `useBackend`

### CLI

The CLI requires Node.js 22.12.0 or newer; Node 24 LTS is recommended. This floor follows
Commander 15 and also covers the Space build dependencies. Both installation and the
public entry point reject older runtimes before loading CLI dependencies, even when npm
engine warnings are not enforced. Install lifecycle scripts can be disabled, but the
runtime check still applies. See the generated
[CLI setup reference](../packages/cli/README.md#install).

The `notis spaces` command group is specified in
`packages/cli/src/command-specs/spaces.js`; see [CLI Command Reference](#cli-command-reference).

### Python backend

The Python backend is the source of truth for Spaces, their source revisions, artifact
serving, runtime enforcement, and database and tool access. Its HTTP surface is
`server/routers/portal_spaces/_1_code/entry.py` (`/portal_spaces/*`), with the behavior in
`server/lib/space_*.py`.

### Portal

The Portal renders Space views as React components directly in its React tree. The
renderer lives in `portal/src/components/apps/AppViewRenderer.tsx` (a historical name; it
renders Spaces only) and `portal/src/components/spaces/`.

The portal is responsible for:
- loading Space navigation and presentation metadata
- dynamically importing the view bundle and rendering the correct component
- supplying the host theme
- keeping view execution isolated from the main portal runtime

---

## Runtime Bridge

Space views do not talk directly to privileged backend internals. The portal owns the runtime (`portal/src/lib/spaceRuntimeBridge.ts`) and injects it into the rendered view subtree with `NotisProvider runtime={runtime}`.

The supported contract is the runtime object exposed through the SDK hooks. Views must not read globals such as `window.__NOTIS_RUNTIME__`.

The runtime provides capabilities like:
- `listTools()`
- `callTool()`
- `request()`
- `subscribeDatabase()` — a change signal for an app-owned database; data still comes back through `callTool()`
- `handover()` — opens manager chat with app/resource context and an optional starter prompt or the alias of a Skill the Space links; the view watches its own databases for the result
  (in a Space, the draft's context chips name the App, then each database the page binds that the person owns and that is not in the bin, as Beta's App handover did. The App is the page's own: the walk goes up through page Spaces the person can open to the first container and names it only when it is an App's top-level Space (it owns a published source or carries a converted App's alias), never a team Space around it; otherwise the page names itself. Every chip carries the same page context, revalidated once at Send)
- `cloudComputerFacts()` — read-only cloud computer facts behind the `cloudComputer: 'read'` capability; it never creates, resumes or commands a sandbox

Two runtime modes matter:
- **Offline verification**: `notis spaces verify` renders the frozen build with offline fixtures, separate from Workspace.
- **Portal runtime**: the published bundle backed by the `/portal_spaces` endpoints

The bridge is HTTP-based for data operations. Cross-surface coordination hooks are only for narrow UI concerns such as resize or navigation, not for primary data access.

You should use the SDK hooks rather than calling the runtime bridge directly. The hooks handle loading states, error handling, and work in both temporary test harnesses and normal Portal runtime.

---

## Data Model

- `databases`: schema lives on the database row. Every database is linked to at least one
  Space and has one main view.
- `documents`: records stored inside databases; `database_id` links to databases with
  `ON DELETE CASCADE`.
- Space membership, links, source revisions, Sites, the bin and the Store are owned by the
  `server/lib/space_*.py` services and described in the Space sections of this document.

Generated database upsert tools are qualified by the immutable database ID, not only by
slug. This prevents two accessible databases with the same display slug from resolving
to the wrong executor. Runtime reads and mutations resolve the database ID first and
reject a document operation bound to a different database tool.

A view does not define database schema. Agents create or update databases through native
database tools, then link them to the Space.

---

## Rendering Model

Space views render as React components directly inside the portal's React tree.

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

## SDK Reference

`Dialog` is the SDK-owned native modal; apps own its content and actions. See the [SDK component reference](../server/skills/notis-apps/references/sdk.md) for its props. Browser top-layer rendering keeps it above selection toolbars inside either rendering boundary, and SDK collection shortcuts are suspended within it.

### Imports

| Import | Purpose |
|--------|---------|
| `@notis/sdk` | `NotisProvider`, runtime hooks |
| `@notis/sdk/config` | `defineSpaces()` for the Space source index and `defineSpace()` for each Space |
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
- **`live` is honest.** It is true only while a feed is actually attached. Hosts without one — the offline `notis spaces verify` harness, the screenshot stub, the vite preview — return rows normally with `live === false`. Keep a manual refresh control for those, as above.
- **Only app-owned databases.** The slug is resolved against the databases the app declares; anything else is inert.

#### Live updates in Spaces

Spaces get changes made elsewhere (another device, a teammate, an agent outside the open chat, an automation) without polling, through the live-update triggers installed on Main by `20261021_spaces_live_updates.sql` (Spaces packet, applied 2026-10-10). Beta's App feed above listens to `documents` rows, which are not in the `supabase_realtime` publication on Main, so on Beta it only re-reads on focus and every five minutes; Spaces do not use it.

- **Signals, per person.** Triggers send a Realtime Broadcast message on the private topic `notis-live:user:<auth id>`, where `<auth id>` is the Supabase Auth identity the Portal signs in with (the access token's `sub`: `users.auth_user_id` for a linked account, else `user_id`). Event `spaces` goes to each person who can open a Space that was created, renamed, moved, trashed, shared or published: its owner and Editors (`notis_current_space_editors`), the Editors of a moved Space's old parent, and the person or Team (members and owner) a share names, including one that just lost it. A statement that changes more than 20 Spaces tells the owners and the people its shares name only; deleting a Space tells its owner, and its shares, deleted with it, tell the people they name. Event `database` is sent only for a database at least one Space binds (a `space_assets` row; draft and preview releases bind through the same rows), since the Portal listens for a database only through a Space binding: writes to any other database send nothing. It goes to the owner of the bound database whose rows changed and to the owner and Editors of every Space that binds it (owners only past 20 binding Spaces), from the per-statement `space_memory_database_versions` revision, once per database per transaction: each statement pays one existence probe for a binding, and the binding Spaces are read only for the first signal. Each trigger call writes one `realtime.messages` INSERT for all its recipients (one per person, event and payload per transaction), so a Team of any size adds one subtransaction, and every trigger catches its own errors (a WARNING, never a failed write). Each policy on `realtime.messages` admits a signed-in person only to their own topic (this feed's, or the Manager's separate `notis-manager:user:<auth id>` reply-wake topic); clients cannot send on either.
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
- **`available` is honest.** Hosts without a manager chat (the offline `notis spaces verify` harness, the vite preview) leave `runtime.handover` undefined and `available` false. Keep the app's own fallback — a copyable prompt — for those, as above.

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

A page that drives the viewer's cloud computer should not have to *infer* its state. Conductor once treated a configured repository as proof that `gh auth login` had happened, because a private clone cannot succeed without it: sound, but it cannot show an account name and cannot notice a revoked credential.

`useCloudComputer()` answers two facts directly, behind the page's reviewable declaration and the viewer's approval:

```typescript
export default defineSpace({ name: 'Workspaces', entry: './view.tsx', cloudComputer: 'read' });
```

Declaring `cloudComputer: 'shell'` instead asks for the stronger access: it implies the
read facts and, once the viewer allows it, adds `run` and `upload` through
`useCloudComputerShell()` (see [Cloud computer in Spaces](#cloud-computer-in-spaces-cloudcomputer)).
A page with `read` cannot run commands, because shell runs with the cloud computer's
full-authority credentials and a file write reaches the same secrets on disk. Declare `shell`
only when the page's core actions genuinely run on the cloud computer, the way Conductor
does.

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

- **It is a read and only a read.** The declared value is `'read'`, and the viewer's approval is saved as a Space grant pinned to the approved code. There is no create, no resume and no command here: commands need `cloudComputer: 'shell'` and `useCloudComputerShell()`.
- **Nothing wakes the VM.** The sandbox is resolved through the read-only readiness path, and `gh auth status` runs *only* when the sandbox is already running, dispatched as internal maintenance so a page render never spends metered Cloud Computer time.
- **`authenticated: null` means unknown, not signed out.** `reason` says why (`no_sandbox`, `sandbox_not_running`, `probe_failed`), and the page should keep whatever fallback it had for that case.
- **`available: false` is a shape, not an error.** A user whose plan has no cloud computer gets `{ available: false, reason: 'cloud_computer_unavailable' }`, as do hosts that cannot answer (the offline `notis spaces verify` harness, the vite preview).
- **Facts are cached per user for a few minutes.** A page re-renders far more often than a sign-in changes. `refresh()` re-reads, but it can still see the cached answer, so a page that just drove a sign-in itself should trust what it did and not wait for the facts to catch up.
- **Only whitelisted fields cross the bridge.** Sandbox ids, owner tokens, provider errors and the raw `gh` output stay server-side.

#### Cloud worktree dev URLs

Conductor can run a repository's recorded dev command inside any of its
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

The CLI command specifications own the exact options: see
`packages/cli/src/command-specs/spaces.js` and the generated
[CLI reference](../packages/cli/README.md). The `notis spaces` group includes `list`,
`get`, `init`, `pull`, `inspect`, `build`, `verify`, `preview`, `promote`, `abandon`,
`deploy`, `action`, `viewer-read`, `links`, `aliases`, `grants`, `navigation bind`,
`resources name` and the `store` commands.

Space builds run the canonical `vite build --configLoader runner` script with the CLI's
own Node executable (`packages/cli/src/runtime/confined-space-build.js`). The bundle is one
`app.js` ES module plus `app.css`.

## Space delivery

Workspace runs published Space revisions only. Local and cloud agents use the same
workflow. A request to create or edit a Space's source authorizes publishing that Space
after checks pass. Explicit read-only, preview-only or no-deploy requests stop at local
artifacts and checks. Store publication always needs separate explicit approval.

1. Read the exact Space with `notis spaces get` and pull its current source into an empty
   directory with `notis spaces pull`, which also writes its linked resources and Skill
   folders (see
   [Source, links, Skill folders and the lock file](#source-links-skill-folders-and-the-lock-file-r5-decision-10)).
2. Edit the source, then run `notis spaces build` and `notis spaces verify`, which renders
   the frozen build with offline fixtures and validates its current action
   authorizations without executing actions.
3. Publish with `notis spaces deploy` against the same Space (`--space-id`), with a
   retry-safe `--request-id`; it updates only that Space and never its siblings or the
   Store. To review first, `notis spaces preview` seals a checked candidate and returns its
   preview link; `notis spaces promote <release-id>` then publishes that exact revision,
   or `notis spaces abandon <release-id>` closes it.
4. Read back the published revision and open the Space in the actual Portal. Report
   **failed before publication**, **published but unverified**, or **outcome unknown**
   accurately, and never blindly replay an uncertain publish; reconcile its exact revision
   first.

## Design Guidelines

Space views should feel native to the Portal.

Preferred UI approach:
- **Use scaffolded shadcn components** (`@/components/ui/*`) -- do not hand-roll buttons, cards, or badges.
- **Use Notis theme tokens** -- `bg-background`, `bg-card`, `border-border`, `text-foreground`, `text-muted-foreground`.
- **Use portal shell classes** -- `notis-app-shell` for ordinary pages, `notis-app-split` plus `notis-app-pane-list` / `notis-app-pane-detail` for list-plus-detail pages, `notis-app-surface` for a flat tinted panel, `.list-row` for rows. The design defaults in the shipped skill (`server/skills/notis-apps/references/design.md`) are enforced by `notis spaces build` through `server/config/notis_app_design_rules.json`; the only override is an inline `notis-design-allow` directive with a reason.
- **Assume the portal provides theme tokens on the view host** -- Space views should feel native by consuming those tokens inside the shadow tree, not by restyling the portal shell.
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

1. **Vite + React only**: no Next.js, no custom server.
2. **ES module bundle**: `notisViteConfig()` produces a library-mode bundle with React externalized.
3. **Component rendering**: every Space view renders as a React component in the same Shadow DOM host. No SDK iframe runtime.

   **Trust boundary:** Shadow DOM isolates styles, not JavaScript or credentials. A loaded SDK bundle shares the Portal browser context. The portal mounts each view into a shadow-scoped surface and injects the runtime provider itself.
4. **HTTP bridge for data**: SDK operations use the authenticated runtime bridge; sizing and navigation stay in the shared host.
5. **Declared access only**: a view reaches only the actions, reads and capabilities its Space declares, enforced server-side (see [What a view declares](#what-a-view-declares-v4-path-params-shows-memory-chrome-markdown) and [Provider actions](#provider-actions-one-sealed-issuer-grant)).
6. **Phosphor icons, not emojis.**
7. **`notis spaces deploy` is not Store publishing**: it updates one Space; Store publication is separately approved.
8. **Portal-owned sidebar trees are structural**: agents must not replace a portal-owned sidebar with custom in-view navigation as a workaround.
9. **Portal globals are unsupported**: views must not rely on `window.__NOTIS_RUNTIME__`, portal DOM hooks, or global DOM portals such as `createPortal(..., document.body)`.

### Anti-patterns: NEVER do these

- **NEVER assume publishing creates databases**: create or update databases through native Notis tools first, then link them.
- **NEVER bypass the CLI workflow by stitching together low-level save calls**: use `notis spaces pull`, `build`, `verify` and `deploy` (or `preview` and `promote`).
- **NEVER treat `notis spaces deploy` as Store approval.**
- **NEVER explore server code or tool schemas to invent an alternative publishing workflow**: use the Notis CLI.
- **NEVER replace a portal-owned sidebar with a custom in-view sidebar because a preview looks wrong**: escalate it as a platform issue.
- **NEVER invent a custom visual language**: views should look like a natural extension of the portal.
- **NEVER hand-roll buttons, cards or badges when the SDK already provides them.**

---

## Testing

1. **Build validation**: `notis spaces build` must succeed without errors.
2. **Offline render verification**: `notis spaces verify` must render the frozen build with offline fixtures and pass its action-authorization checks.
3. **Preview before publishing when reviewing**: `notis spaces preview` returns an authenticated preview link of the sealed candidate.
4. **Post-publication check**: open the published Space in the actual Portal; a passing offline check alone does not prove the published bundle rendered there.

---

## Where To Look In The Repo

Use these files when you need implementation detail after reading this doc:

- [AGENTS.md](../AGENTS.md)
- [server/skills/notis-apps/SKILL.md](../server/skills/notis-apps/SKILL.md)
- [packages/sdk](../packages/sdk)
- [packages/cli/src/command-specs/spaces.js](../packages/cli/src/command-specs/spaces.js)
- [packages/cli/src/runtime/space-platform.js](../packages/cli/src/runtime/space-platform.js)
- [packages/cli/src/runtime/space-source.js](../packages/cli/src/runtime/space-source.js)
- [server/lib/vercel_sandbox.py](../server/lib/vercel_sandbox.py)
- [server/routers/portal_spaces/_1_code/entry.py](../server/routers/portal_spaces/_1_code/entry.py)
- [server/lib/space_presentation.py](../server/lib/space_presentation.py)
- [server/lib/space_navigation.py](../server/lib/space_navigation.py)
- [server/lib/space_store.py](../server/lib/space_store.py)
- [portal/src/components/apps/AppViewRenderer.tsx](../portal/src/components/apps/AppViewRenderer.tsx)
- [portal/src/components/spaces/PersistentSpaceViews.tsx](../portal/src/components/spaces/PersistentSpaceViews.tsx)
- [portal/src/lib/appBundleLoader.ts](../portal/src/lib/appBundleLoader.ts)
- [portal/src/lib/spaceRuntimeBridge.ts](../portal/src/lib/spaceRuntimeBridge.ts)

---

## Agent Guidance

If the task is conceptual, start with this document.

If the task is execution-oriented, read this document first and use the `notis-apps` skill second.

If the code seems to disagree with this document, treat this file as the intended platform contract and verify the specific implementation detail before changing behavior.

## Instant-view lifecycle and cache ownership

`AppOpeningBoundary` owns the entire host opening sequence (lazy route module, authorized descriptor, bundle and stylesheet). It shows no fake page or dashboard skeleton. A single small indicator appears only after 150 ms of continuous preparation; handing off between stages does not restart that delay. The indicator is a compact 28px pill in the bottom-left column shared with toasts and the connection pill (which stacks above it while this device cannot reach Notis): anchored to the bottom-left corner of the non-scrolling app-view viewport (`SidebarInset`) on desktop, and to the screen at the chat launcher's baseline below 1024 px, with safe-area and keyboard clearance, opaque inverse-theme colors, a 5px Notis-green pulse, and a scaled-down layered overlay shadow. Its label is “Opening”; the recovery state stays compact with “Still opening” and Retry. The pulse respects reduced-motion preferences. It sits above app content without covering the page with a blocking layer. After 20 seconds the indicator offers recovery. Once the real app has mounted, only the app owns missing-data placeholders. Isolated Store frames report render readiness to this same parent boundary; they do not display a second host loader.

While an uncached destination descriptor is pending, the previous route stays mounted and visible but inert. Its resource/item identity and path remain those of the displayed descriptor until the destination commits. This preserves the shell without allowing an old article's controls to act under a new article's context. Warm cached opens and background revalidation do not replace populated content.

App-view database queries include document bodies by default. Lists that only need titles and properties can explicitly use `useDocuments(slug, { includeContent: false })`: the runtime projects metadata columns and returns null body fields, while keeping authorization, filtering, sorting, and pagination unchanged. Metadata and full-content query caches are separate. Open records still use `useDocument`; full-body search must request full content when needed. This opt-in does not change generic database-tool responses or existing apps.

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

For split-view sizing changes, check the real Portal with delayed initial reads and again after content resolves, including a resize. From `portal/`, run `node scripts/smokes/check-split-app-viewport.cjs --session <named-browser-session> --app-id <view runtime id> --state loading` (then `--state loaded`). The read-only check verifies top, bottom and horizontal viewport boundaries plus desktop pane heights; it fails if the requested loading state is absent. Standalone app-harness screenshots do not prove the Portal's parent-height chain.

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

The canonical UI/authoring contract and cached-read examples live in [the shipped Notis apps skill](../server/skills/notis-apps/references/design.md#instant-view-loading-contract-required). The CLI scaffold and bundled SDK source mirror that contract. Release the compatible host/SDK before deploying Spaces that rely on this behavior; this migration itself does not authorize package publication or deployment.

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

### Scaffold styling

New CLI scaffolds use Tailwind CSS 4 with `@tailwindcss/postcss`.
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
With `share` on, a page in its own Space's view is listed in the view's top bar Share panel and its toolbar
has no Share (see Site origin); shown in another Space's view, it keeps Share in its toolbar.
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

The pipe classifies the pinned tool schema and effect metadata. A narrow rule may
also prove a read when the template fixes the only mutating argument to its
non-mutating value. `_PINNED_READS` (`server/lib/space_provider_actions.py`) owns
these exact tool, official provider host, fixed argument and allowed-input rules.
For Lemlist inbox conversations, `markAsRead` must be `false`, `limit` stays
fixed, and only `contactId` and `page` may vary. Missing or variable pins, extra
arguments and lookalike hosts keep the write default. Legacy remote tool names
resolve to their final Custom MCP tools; the verified server binding still owns
the host proof. A changed read decision requires a new exact issuer grant.

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

The pipe pins the issuer, exact template and Composio connection. A read-only
Supabase address must be registered as its own Custom MCP toolkit with
`read_only=true` and database features; dispatch cannot rewrite the address of a
Composio-bound connection. Authorize that exact binding before enabling reads.
Receipt replay rechecks current origin and connection authority without repeating
the query. PostgreSQL, its provider and privileged schema administrators remain
the trust boundary, not a sandbox against a malicious administrator.

#### Project-pinned PostHog reads

Spaces can declare the connected PostHog EXEC transport with a **typed read**
argument object: `{project_id, query, context, llm_model}` and no runtime inputs.
`space_posthog_reads.py` accepts a bounded fixed SELECT only. It does not accept
`command`, `connectionId`, `sendRawQuery` or a runtime project/query selector.
The ordinary EXEC surface and its upstream annotation remain write-scoped.

The Composio toolkit must be registered at the exact official MCP address with
the fixed `project_id`; dispatch never derives a different server address. The
read rule validates that binding and the current read-only `execute-sql` and
`project-get` contracts before admitting the fixed query. Project settings and
API tokens returned by metadata are discarded.

Only the server derives `call --json execute-sql {"query":...}`. It checks the
logical arguments against the durable invocation before binding the same
receipt/actor/issuer/connection to the physical payload. Generic dispatch still
compares that exact payload; unrelated EXEC commands do not gain read admission.
Receipt replay checks current binding identity without repeating the query.
An unpinned address needs a separate project-pinned toolkit and authorization;
reconnecting an unpinned address alone does not establish read authority.

CLI and the warm renderer use `packages/view-renderer`; its credential-free host must be built before packaging.
The renderer runs in a separate child of the existing collaboration service behind `/views/render`; it uses an
ephemeral private loopback port, not another worktree port or environment variable. A render process failure does
not restart collaboration rooms. Production browser installation and deployment remain release gates, not a
consequence of a local render. Memory ingestion activation follows the [native index rollout](operations/native-document-index-rollout.md).
