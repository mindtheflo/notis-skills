## Reminders (dumb message delivery)

A reminder stores a static `message` and delivers it verbatim through a channel — no agent run. Tools: `LOCAL_NOTIS_INSERT_REMINDER`, `LOCAL_NOTIS_UPDATE_REMINDER`, `LOCAL_NOTIS_LIST_REMINDERS`, `LOCAL_NOTIS_DELETE_REMINDER`.

`trigger_type` is `"schedule"` (recurring) or `"one_time"` (single future delivery). Cannot be changed after creation.

Fields:

- `message` (required) — the exact text to send (max 5000 chars). Static only. If it needs computation, it is an automation.
- `trigger_type` (required) — `"schedule"` or `"one_time"`.
- `cron_expression` (schedule only) — standard 5-field cron. **Cannot run more often than once per hour.**
- `expires_at` (one_time only) — ISO 8601 with timezone, in the future.
- `channel` (optional) — `manager`, `whatsapp`, `slack`, `telegram`, `imessage`, `sms`, `email`. Defaults to the channel the user is talking on.
- `channel_account` / `channel_account_id` (optional) — required when the user has more than one account on the target channel. Resolve which account before asking the user for an id.

Recurring reminder:

```json
{
  "trigger_type": "schedule",
  "message": "Stand up and stretch.",
  "cron_expression": "0 14 * * 1-5",
  "channel": "whatsapp"
}
```

One-time reminder:

```json
{
  "trigger_type": "one_time",
  "message": "Leave now for the airport.",
  "expires_at": "2026-06-19T16:30:00-07:00"
}
```

Notes:

- `LOCAL_NOTIS_INSERT_REMINDER` returns the new `reminder_id`, the user's `active_reminders`, and an `llm_prompt` asking you to check for duplicates — actually do that check and delete any duplicates.
- `LOCAL_NOTIS_UPDATE_REMINDER` can change `message`, `channel`, `status` (`active`/`paused`), and `cron_expression`/`expires_at` for the matching type. It cannot change `trigger_type`. For schedule reminders, the next run is managed by cron — do not try to set `expires_at`.
- `LOCAL_NOTIS_DELETE_REMINDER` is a soft delete.

---
