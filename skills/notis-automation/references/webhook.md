### Trigger type: webhook (inbound HTTP)

No trigger config; the tool returns a generated `webhook_url` to POST to. Give that URL to the user.

```json
{
  "trigger_type": "webhook",
  "name": "Lead intake",
  "prompt": "A new lead was posted to this webhook. Enrich it with /lead-intake and add a row to the CRM database."
}
```
