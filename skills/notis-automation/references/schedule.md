### Trigger type: schedule (recurring)

Standard 5-field cron, minimum interval one hour. The recurrence lives here — keep it out of the prompt. `expires_at` is reserved for one-time automations and must not be set on a recurring schedule. To stop a recurring automation, pause or delete it explicitly.

```json
{
  "trigger_type": "schedule",
  "name": "Weekly deal recap",
  "cron_expression": "0 9 * * 1",
  "prompt": "Compile last week's closed deals using /weekly-deal-recap and produce the summary.",
  "channel": "slack"
}
```

Cron quick reference: `0 * * * *` hourly · `0 9 * * *` daily 09:00 · `0 9 * * 1` Mondays 09:00 · `0 9 * * 1-5` weekdays 09:00. Build a concrete expression — never leave the schedule unresolved.
