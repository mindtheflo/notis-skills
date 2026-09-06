## Automations (trigger -> business logic)

An automation runs its `prompt` as a real agent turn when its trigger fires. Tools:

| Tool | Purpose |
|---|---|
| `LOCAL_NOTIS_INSERT_AUTOMATION` | Create an automation |
| `LOCAL_NOTIS_UPDATE_AUTOMATION` | Change fields (not `trigger_type`) |
| `LOCAL_NOTIS_LIST_AUTOMATIONS` | Browse/search existing automations |
| `LOCAL_NOTIS_GET_AUTOMATION` | Read one automation in full |
| `LOCAL_NOTIS_RUN_AUTOMATION` | Fire it now (manual / test run) |
| `LOCAL_NOTIS_LIST_AUTOMATION_RUNS` | See past runs and whether delivery happened |
| `LOCAL_NOTIS_GET_AUTOMATION_RUN` | Inspect one run |
| `LOCAL_NOTIS_DELETE_AUTOMATION` | Remove it |
| `LOCAL_NOTIS_LIST_INTEGRATION_TRIGGERS` | Discover available integration triggers + config schemas (call before building an `integration` automation) |

Common `LOCAL_NOTIS_INSERT_AUTOMATION` fields:

- `prompt` (required) — the instruction the agent runs when the trigger fires (max 5000 chars). Keep it thin, present-tense, single-run; cite a skill for real logic. Follow the two prompt rules above: **no delivery destination, no recurrence wording.**
- `trigger_type` (required) — one of `schedule`, `one_time`, `webhook`, `integration`, `database`. Cannot be changed later.
- `name` (optional) — short label.
- `channel` / `channel_account_id` (optional) — **where the result is delivered**; defaults to the current channel. This is the one and only place delivery is set.
- `keep_context` (optional, default false) — `true` reuses a single pinned thread across runs; `false` starts a fresh thread each run.
- `intelligence_mode` (optional) — `auto` (default), `low`, `medium`, or `high`.

`LOCAL_NOTIS_INSERT_AUTOMATION` returns `automation_id`, the portal URLs, and — for webhooks — the `webhook_url`. Surface those to the user.

### Running, verifying, updating

- `LOCAL_NOTIS_RUN_AUTOMATION` fires immediately (good for a test) and returns a `run_id`.
- `LOCAL_NOTIS_LIST_AUTOMATION_RUNS` shows whether each run produced a delivered message (`delivery_detected`) — use it to confirm an automation actually works.
- `LOCAL_NOTIS_UPDATE_AUTOMATION` changes any field except `trigger_type`; set `status` to `paused`/`active` to disable/enable. Automations synced from a team template (`automation_template_id` present) lock `name` and `prompt` — tell the user to duplicate it to edit.

---
