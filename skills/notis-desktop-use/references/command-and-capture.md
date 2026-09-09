# Command and capture guide

## Start here — load the live tool surface

For the short native status-check loop, use the examples in SKILL.md. For
unfamiliar operations, load only the relevant command's help before expanding
to the full catalog:

```bash
peekaboo <command> --help
peekaboo tools describe <name>
peekaboo tools
peekaboo learn
```

Prefer `--json` for machine-readable results. Copy snapshot and element IDs
exactly from the latest observation; never fabricate them or assume a cached
snapshot remains actionable after an action. A snapshot belongs to its live
producing host. Keep explicit `--no-remote` or Bridge routing consistent; if
that host cannot reuse the reference, recapture instead of changing boundaries.

## Core loop: see → act → re-see

Run each line as a separate shell call. Replace placeholders with observed
values; these are alternative actions, not a script to run against one snapshot.

```bash
# 1. Capture the requested app, preserving its current focus state.
peekaboo see --app "APP NAME" --json

# 2. Perform ONE task-authorized action using that fresh snapshot.
peekaboo click --on "ELEMENT_ID" --snapshot "SNAPSHOT_ID" --json

# 3. Observe again before deciding on the next action.
peekaboo see --app "APP NAME" --json

# Other action forms, each requiring its own fresh snapshot:
peekaboo type "hello world" --snapshot "FRESH_SNAPSHOT_ID" --json
peekaboo press cmd+s --snapshot "FRESH_SNAPSHOT_ID" --json
```

For typing, first focus the intended field using its element ID, observe again,
then use the new snapshot. Do not use `--accept-dispatched` to turn unverified
text delivery into claimed success. If the task permits foreground input and
background delivery is unsuitable, explicitly target the app/window and add
`--foreground`; do not silently enable it after a refusal.

Inspect `effect` on action results, along with `retry_safe`,
`requires_fresh_observation`, and `error.hint` when present. Dispatched keys or
pointer events can have `success: true` but `effect: unverifiable`; errors can
also follow a partial mutation. Observe before deciding to retry, and verify
the requested application state rather than treating dispatch as completion.
Read-only output may omit `effect`. Partial app-level observations are not
exact-window proof and do not supply mutation authority.

Re-`see` after navigation, dialogs, app switches, or dynamic re-renders.
Treat stale element and snapshot IDs as invalid.

## Command map

Use the managed CLI's help for exact flags. The v4 surface is:

- **Capture:** `see` (element map), `see --no-elements` (pixels only),
  `see --tree --no-screenshot` (AX text only), `capture live`.
- **Discovery:** `app list`, `window list`, `screen list`, `menubar list`,
  `permissions status`.
- **Interaction:** `click --on` or `click --at`, `type`, `press cmd+s`,
  `action AXPress --on`, `paste`, `scroll`, `drag --from --to`, `move`.
- **Windows / menus / apps / spaces:** `window`, `space`, `menu`, `menubar`,
  `app` (launch/quit/relaunch/hide/focus/list), `dock`, `dialog`.
  Focusing an app or window requires explicit `--foreground`.
- **Verification:** `verify` waits for a predicate; exit 0 means satisfied,
  1 unsatisfied, and 2 unknown. Use explicit duration units such as `2s`;
  bare duration values are milliseconds.

For multi-step flows, orchestrate separate plain CLI calls through the local
shell tool. Peekaboo 4 removed `run` and its `.peekaboo.json` script format,
`hotkey`, `image`, and CLI `inspect-ui`. Do not restore those old spellings or
bypass the single-command rule with a shell script. AI analysis and `agent`
require separate provider configuration and are not the default capture path.
