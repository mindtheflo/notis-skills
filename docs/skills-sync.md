# Skills Sync

This is the canonical reference for Notis skill sync mechanics.

Use this doc when the work is about:

- publishing repo-maintained skills from `server/skills` to OpenAI and `curated_skills`
- understanding channel-specific curated skill metadata for dev, beta, and production
- debugging CLI-owned sync between Portal-managed skills and local agent folders
- changing how local skills are pushed, pulled, written, deleted, or symlinked

For product lifecycle decisions such as whether a skill is custom, curated, community, or synced, start with [Notis Skills Lifecycle](./notis-skills-lifecycle.md).

## Two Sync Paths

Notis has two separate skill sync systems:

- Curated skill publishing sync: `server/skills/sync_notis_skills.py` packages repo-maintained and selected upstream skills, creates or versions OpenAI skills, and updates channel fields in `curated_skills`.
- CLI local-agent sync: the npm CLI owns the engine that mirrors a signed-in user's Portal skills into local folders and maintains agent-specific symlinks for Notis, Claude Code, Cursor, and Codex. Electron bundles that same engine and acts only as its long-running scheduler.

Do not mix these paths:

- Curated publishing sync is an operator/deployment workflow for shared catalog skills.
- CLI local-agent sync is the end-user workflow for installed skills on one authenticated local account.

Public distribution is a third, read-only output rather than another runtime
sync path. `.github/workflows/sync-public-repositories.yml` mirrors every
tracked `server/skills/<name>/` folder to
[`mindtheflo/notis-skills`](https://github.com/mindtheflo/notis-skills) after a
push to `beta`. The monorepo stays canonical; the public repository is replaced
from generated tracked-file snapshots and must not be edited directly. This
layout exposes every skill as `skills/<name>/SKILL.md` for skills.sh indexing.
The generated public repository CI validates the full collection and performs
an ephemeral all-skills install after each push. skills.sh uses that install
telemetry to refresh its cached repository index, so newly mirrored skills do
not require a manual indexing task.

## Curated Publishing Sync

Repo-maintained product skills live in `server/skills/<name>/` with `SKILL.md` at the skill root.

The publishing CLI is:

```bash
python3 server/skills/sync_notis_skills.py sync [skill ...] --channel dev|beta|production
```

Required environment:

- `OPENAI_API_KEY`
- `SUPABASE_SUBDOMAIN` and `SUPABASE_SERVICE_KEY`, unless `--skill-ids` is used

Important flags:

- `--channel dev|beta|production` chooses which channel-specific fields are updated. A run only ever writes the fields for the one channel you pass (production also mirrors the legacy base fields — see [Channel Fields](#channel-fields)).
- `--bootstrap` creates missing OpenAI skills and inserts or updates `curated_skills` rows when `openai_skill_id` is missing. **Required for the first publish of a brand-new skill** (which has no `curated_skills` row yet); after that, plain `sync` versions the existing skill. Bootstrap works on any channel — the insert seeds the `NOT NULL` base `skill_md` so a first publish can go straight to `dev` or `beta` without touching production. **CI never bootstraps** (see [Automated Sync](#automated-sync-github-actions)).
- `--from claude` includes the upstream document skills from `anthropics/skills`: `docx`, `pdf`, `pptx`, and `xlsx`.
- `--skill-ids name:skill_id,...` syncs against explicit OpenAI skill ids without querying Supabase.
- `--source-sha <sha>` records the source commit alongside the channel sync metadata.
- `--dry-run` builds the intended sync plan without writing to OpenAI or Supabase.

The script discovers repo-maintained skills dynamically: **every `server/skills/<name>/` folder that contains a `SKILL.md`** (`discover_repo_skills`). Adding a new skill folder makes it syncable with no script edit. A subset — `DEFAULT_OUR_SKILLS` in the script — is marked `is_default = true` on bootstrap, which auto-installs it for eligible users; experimental/opt-in skills are intentionally left out of that set.

### Access metadata

A curated skill can declare independent visibility and billing requirements in
its `SKILL.md` frontmatter:

- `feature_flag: <key>` syncs to `required_feature_flag` and hides the skill
  unless PostHog returns true.
- `required_entitlements: [...]` syncs to `required_entitlements`. Omission is
  `[]`, and legacy `skills` entries are dropped because Skills ship on every
  tier. Missing access to a declared additional capability keeps the catalog
  entry locked and excludes the skill from install, sync pull, and runtime
  injection.

The baseline `skills` entitlement applies to the complete per-user sync pull,
including custom, community, local, and curated installs. Since the 2026-08
pricing re-cut that baseline is satisfied on **every tier, including FREE**, so
sync is always allowed for a signed-in user; the resolution path and its
failure modes below are unchanged and still load-bearing for outages.
Per-curated-skill requirements are additional constraints; they do not replace
the baseline.

The sync validates both fields against canonical metadata before publishing a
new OpenAI version. See [Notis Skills Lifecycle → Gate a curated skill on a
PostHog flag](./notis-skills-lifecycle.md#gate-a-curated-skill-on-a-posthog-flag)
for the full mechanism and deploy ordering.

### Channel Fields

Curated skill content is channel-scoped through `server/lib/curated_skill_channels.py`.

The sync script writes these fields on `curated_skills`:

- `skill_md_<channel>`
- `openai_skill_version_<channel>`
- `openai_skill_source_sha_<channel>`
- `openai_skill_synced_at_<channel>`

Production sync also mirrors the legacy base fields:

- `skill_md`
- `openai_skill_version`

Runtime resolution (`resolve_curated_skill_channel`) picks the channel:

- `dev` when the server is running in a development environment
- `beta` for beta users
- `production` otherwise

Then `hydrate_curated_skill_row` uses that channel's field **if set**, otherwise falls back to the base `skill_md` / `openai_skill_version`. Two consequences worth internalizing:

- The base `skill_md` column is `NOT NULL`, so every curated skill always has base content that production users fall back to. Bootstrap seeds it on every channel; production sync also mirrors it.
- **Channels scope *content*, not *access*.** A channel never hides a skill from a cohort — visibility is controlled by the feature flag (`required_feature_flag`) and `is_default`, not by which channel fields are populated. "Release to beta only" in the access sense means gating on a beta-scoped flag, not syncing only the beta channel.

### Publishing Rules

When syncing an existing curated skill, the script:

1. Packages the skill folder as a zip rooted at the skill name.
2. Creates a new OpenAI skill version.
3. Sets the OpenAI default version only for the `production` channel.
4. Updates the channel-specific `curated_skills` fields.

When bootstrapping a missing curated skill, the script:

1. Creates the OpenAI skill.
2. Stores the returned `openai_skill_id`.
3. Writes the channel-specific `skill_md` and version fields, plus the base
   `skill_md` (so the `NOT NULL` constraint is satisfied on any channel),
   `required_feature_flag`, `required_entitlements`, `category`, `is_default`,
   and `sort_order`.

For upstream `skill-creator`, the sync script renames it to `notis-skill-creator` and adapts the upstream packaging instructions to the Notis create-skill flow.

### Automated Sync (GitHub Actions)

`.github/workflows/sync-curated-skills.yml` runs the publishing CLI in CI. It **never passes `--bootstrap`**, so it only versions skills that already exist in `curated_skills` (a brand-new skill must be bootstrapped manually once first).

Repo skills are discovered dynamically in the workflow too — it scans `server/skills/*/SKILL.md` (mirroring the CLI), so a new skill folder is picked up with no workflow edit.

Channel is determined by trigger:

| Trigger | Channel(s) | Source content |
| --- | --- | --- |
| Push to `beta` (paths under `server/skills/**`) | `beta` | `beta` branch head |
| Push to `production` (same path filter) | `production` | `production` branch head |
| Manual dispatch, `target_channel: dev` | `dev` | **the branch the dispatch is run from** |
| Manual dispatch, `beta` / `production` | that channel | that channel's branch head |
| Manual dispatch, `all` | `beta` + `production` (never `dev`) | each branch head |

`dev` is **manual-only** — it is never reachable from a push and is excluded from `all`. Use it to publish the version you are iterating on to the dev channel (resolved only by the dev backend) from a feature branch, without touching beta or production. A manual `dev` run must specify which skills via the `skills` input (or `force`), since there is no push diff to infer from.

So the normal promotion path is: publish to `dev` manually while working → merge to `beta` (auto-syncs the beta channel) → merge to `production` (auto-syncs the production channel).

### Publishing Verification

Focused test coverage lives in:

```bash
python3 -m unittest server/tests/test_sync_notis_skills.py
python3 -m unittest server/tests/test_curated_skill_channels.py
```

For broader Notis test selection and smoke workflows, use `.agents/skills/tools/notis-tests/SKILL.md`.

## Local-Agent Sync

The CLI owns local-agent sync. `notis skills sync` works without Desktop and a
manual run always reconciles account skills. Electron runs the same CLI-owned
engine with repeat semantics at startup, after authentication, after
resume/unlock, and every five minutes while it is running. Only those repeating
runs honor the account's `sync_enabled` preference.

The preference defaults to `false` when no settings row exists. After the user
explicitly enables it, repeating Desktop runs refresh account skills. When it
is off, the repeating invocation exits before pulling, gathering, deleting,
writing, or relinking skills for the current account. It still removes
Notis-managed agent links that point into a different account's mirror, so an
account switch cannot expose the previous account's skills. Neither account's
mirror is changed. Manual CLI sync remains available.

The CLI also owns three base skills: `notis-apps`, `notis-query`, and
`notis-cli`. Every CLI launch refreshes their canonical copies under
`~/.notis/skills/base/` from the package and links all three into the supported
agent roots. They do not participate in account sync, feature-flag filtering,
target selection, cloud deletion, or the automatic-sync preference.

Base and account reconciliation share one atomic filesystem lock under
`~/.notis/skills/`. It serializes Desktop refreshes with manual CLI syncs,
including across processes. Owner leases are written atomically; an unchanged
stale lock is atomically moved to a retained content-addressed quarantine
instead of deleted at the shared pathname. This
prevents transient link/state writes from being misread as user deletions.

Key files:

- `packages/cli/src/runtime/base-skills.js` - base-skill installation, updates, backups, and links
- `packages/cli/src/runtime/skill-sync/index.ts` - end-to-end account-sync orchestration
- `packages/cli/src/runtime/skill-sync/cloud-client.ts` - Portal sync API client
- `packages/cli/src/runtime/skill-sync/local-scanner.ts` - top-level local skill gather, dedupe, hashing, bundle creation, scoped writes, and sync state
- `packages/cli/src/runtime/skill-sync/symlink-manager.ts` - Notis, Claude Code, Cursor, and Codex account-skill link reconciliation
- `packages/cli/scripts/build-scaffolds.js` - copies canonical base skills from `server/skills`, bundles the TypeScript sync engine, and builds the immutable coding-agent hook runtime for npm
- `electron/src/cli-skill-sync.ts` - Desktop invocation of the webpack-bundled CLI-owned sync engine; Forge also packages the three canonical base-skill folders as read-only resources

Server endpoints live in `server/routers/portal_skills/_1_code/entry.py`:

- `POST /portal_skills/sync-settings`
- `POST /portal_skills/sync-pull`
- `POST /portal_skills/sync-push`
- `PATCH /portal_skills/agent-targets`

### Local Scope

The CLI derives the active sync scope from `user_id` in the authenticated
`sync-settings` response. That server-returned Notis id is canonical because a
Desktop Supabase session and a purpose-scoped CLI OAuth token can use different
`sub` values for the same account. JWT `sub` remains only an older-server
fallback during rollout. The Portal endpoints accept both bearer types.

Notis-managed skill mirrors and sync metadata are stored under:

```text
~/.notis/skills/users/<notisUserId>/skills
~/.notis/skills/users/<notisUserId>/.notis-sync.json
~/.notis/skills/users/<notisUserId>/.notis-gathered-skills.json
```

Before each account scan, the CLI gathers direct child skill folders or symlinks with a `SKILL.md` from these top-level local agent roots:

```text
~/.agents/skills
~/.codex/skills
~/.cursor/skills
~/.claude/skills
```

Real top-level skill folders are moved into the active user's Notis-managed mirror. Top-level symlinks are treated as valid skills when their target has a `SKILL.md`; the mirror entry is created as a symlink, preserving the chain back to the original target.

Gathering is continuous, not a one-time first-sync migration. This lets Notis adopt newly created top-level local skills on later desktop syncs and push them to the cloud as normal local skills.

Duplicate same-name skills collapse to one canonical scoped copy with this deterministic priority:

1. Existing Notis-managed scoped mirror
2. `~/.agents/skills`
3. `~/.codex/skills`
4. `~/.cursor/skills`
5. `~/.claude/skills`

Duplicate real folders that are not chosen as canonical are moved to:

```text
~/.notis/skills/skill-dedupe-backups/<timestamp>/
```

Local folders whose names match installed cloud curated skills are backed up instead of pushed as duplicate user-owned skills.

Plugin, cache, builtin, marketplace, temp, worktree, and backup roots are intentionally out of scope for this gather step. For example, nested Codex `.system` skills and plugin cache skills remain owned by their agent or plugin manager.

### Agent Targets

Each synced skill has `agent_targets` metadata:

```ts
{
  notis: boolean;
  claude_code: boolean;
  cursor: boolean;
  codex: boolean;
}
```

When `agent_targets` is missing, all four targets default to `true`.

The CLI reconciles account-skill links into:

```text
~/.agents/skills
~/.codex/skills
~/.claude/skills
~/.cursor/skills
```

Only Notis-managed account-skill links are rewritten or removed. CLI-owned base links are preserved. If a non-symlink entry blocks an account skill, the CLI leaves it in place and skips that link.

### CLI Account-Sync Flow

`runSkillSync(serverUrl, jwt, dependencies, options)` performs this sequence:

1. Fetch sync settings from `POST /portal_skills/sync-settings`.
2. Use its server-verified `user_id` as the canonical local scope, falling back to JWT `sub` only for an older server that does not return it.
3. Remove Notis-managed agent links that point into another account's mirror. For an Electron repeating invocation with `sync_enabled` false, stop here without changing either account mirror or current-account links.
4. Pull Portal skills from `POST /portal_skills/sync-pull` and exclude the three CLI-owned base names.
5. When the verified id differs from JWT `sub`, gather the former auth-sub mirror into the canonical mirror and reuse matching prior sync state, backing up conflicts.
6. Gather top-level local skills into the scoped mirror and dedupe conflicts, while treating the base root as externally managed.
7. Scan scoped local skills, excluding base skills, and compute folder hashes.
8. Push changed local non-curated skills through `POST /portal_skills/sync-push`.
9. Pull again after a push so local state matches the server.
10. Delete account skills that were previously synced but no longer exist in the cloud response. Base skills are never deletion candidates.
11. Download or write account skills whose server hash differs from unchanged local state.
12. Reconcile account-skill links from `agent_targets` without removing base links.
13. Persist account-only `.notis-sync.json` state.

Curated skills can be pulled and linked locally when they are installed for the user, but local changes to curated skill folders are not pushed back to the server. The push planner skips local folders whose names match cloud curated skills and only updates non-curated user skills.

### Pull Semantics

`sync-pull` returns the user's `skills` rows except:

- rows with `status: "deleted"`
- curated installs whose `curated_skill_id` is no longer visible after feature-flag filtering

The baseline Skills entitlement is still resolved before any user skill rows are
returned. No current tier is denied, but the fail-closed resolver remains
load-bearing for access-system failures.

- A forced definitive denial returns HTTP `403`; it is not a successful empty
  pull and does not authorize the CLI to remove mirrors or links. The CLI
  also rejects the legacy successful-empty denial envelope without changing
  local state.
- An unavailable entitlement check returns retryable HTTP `503`
  `entitlement_check_unavailable`. The CLI makes no local changes and retries
  later. Neither denial nor outage is interpreted as a successful sync.

For curated installs, the backend resolves live content from `curated_skills` at request time. That keeps installed curated skills pointed at the shared template and channel-specific content.

For bundle-backed skills, the backend hydrates bundle files from storage when possible. If bundle hydration fails, the response marks `bundle_hydration_failed` so the CLI can fall back to the available cloud skill payload.

### Push Semantics

`sync-push` accepts local non-curated skills and stores them as user-owned `skills` rows with `source: "local"`.

For each local skill, the backend:

1. Normalizes the bundle or builds one from `SKILL.md`.
2. Creates or versions the OpenAI skill.
3. Uploads the skill bundle to storage.
4. Writes `skill_md`, `skill_folder_hash`, `skill_bundle_storage_path`, and metadata to `skills`.
5. Sets the OpenAI default version after updating an existing skill.

Existing local skills with unchanged folder hashes are not re-versioned. The backend may still backfill missing bundle storage or refresh metadata.

### Safe Local Writes

The CLI writes cloud skills atomically:

- bundle downloads are extracted into a temporary directory first
- existing skill directories are moved aside as backups during replacement
- backups are restored if promotion fails
- bundle file paths are validated to prevent writes outside the skill directory

Skill names are sanitized before being used as local path segments.

## Debug Checklist

When a skill does not appear locally:

1. For automatic Desktop refresh, confirm `sync_enabled` through `POST /portal_skills/sync-settings`. For a manual CLI run, this setting is intentionally ignored.
2. Confirm the user has a visible active `skills` row.
3. Confirm `agent_targets` includes the expected local agent.
4. Confirm `sync-settings.user_id` names the expected Notis account; compare bearer `sub` only when diagnosing the older-server fallback.
5. Check the scoped mirror under `~/.notis/skills/users/<notisUserId>/skills`.
6. Check `.notis-sync.json` and `.notis-gathered-skills.json` in the same user scope.
7. Check whether a non-symlink entry blocks the desired path in `~/.codex/skills`, `~/.claude/skills`, or `~/.cursor/skills`.
8. Check `~/.notis/skills/skill-dedupe-backups/` if a same-name local folder was not selected as canonical.

For one of the three base skills, skip the cloud-row and target checks: verify
the current CLI package contains `dist/base-skills/<name>/SKILL.md`, then inspect
`~/.notis/skills/base/<name>` and the agent-root link.

When curated content looks stale:

1. Confirm the relevant channel fields in `curated_skills`.
2. Confirm `resolve_curated_skill_channel` chooses the expected channel for the environment and user.
3. For production, confirm the OpenAI default version was updated.
4. Re-run the focused sync tests before changing channel-resolution behavior.
