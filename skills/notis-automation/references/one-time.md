### Trigger type: one_time (do something in the future)

A single future run that does real work. `expires_at` is ISO 8601 with timezone, in the future.

```json
{
  "trigger_type": "one_time",
  "name": "Draft launch recap",
  "expires_at": "2026-06-20T18:00:00-07:00",
  "prompt": "Draft the launch recap from today's notes."
}
```

If the future action is just a fixed message, use a one-time **reminder** instead.
