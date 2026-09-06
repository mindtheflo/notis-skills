### Trigger type: integration (connected app events)

Fires on an external event (new Gmail message, new calendar event, PostForMe social post or account changes, etc.). **Always call `LOCAL_NOTIS_LIST_INTEGRATION_TRIGGERS` first** — it returns providers, connected toolkits, valid `triggerName`s, each trigger's `config_schema`, and the user's `connectedAccountId`s. Never invent a provider, trigger name, or account id; use the exact values it returns. If the toolkit has multiple connected accounts, ask which one. PostForMe supports post created, updated, deleted, publish-result-created, and account-updated events; account-created is intentionally unavailable because integration cards target an existing account.

The trigger catalog is authoritative. Once the event and account are resolved, call `LOCAL_NOTIS_INSERT_AUTOMATION` directly with the returned values. **Do not call `COMPOSIO_SEARCH_TOOLS` between listing triggers and inserting the automation**: PostForMe events are provider webhook events, not Composio action tools, and the native insert tool is already known.

```json
{
  "trigger_type": "integration",
  "name": "Auto-file new emails",
  "prompt": "A new email arrived. Classify it with /email-triage and file the action items.",
  "integration_trigger_config": {
    "provider": "composio",
    "toolkit": "GMAIL",
    "triggers": [
      {
        "provider": "composio",
        "toolkit": "GMAIL",
        "triggerName": "GMAIL_NEW_GMAIL_MESSAGE",
        "config": { "label": "inbox" },
        "connectedAccountId": "ca_xxx"
      }
    ]
  }
}
```

PostForMe example:

```json
{
  "trigger_type": "integration",
  "name": "Notify on new LinkedIn posts",
  "prompt": "Summarize the new social post in one sentence.",
  "channel": "manager",
  "integration_trigger_config": {
    "provider": "postforme",
    "toolkit": "LINKEDIN",
    "triggers": [
      {
        "provider": "postforme",
        "toolkit": "LINKEDIN",
        "triggerName": "social.post.created",
        "connectedAccountId": "spc_xxx",
        "config": {}
      }
    ]
  }
}
```
