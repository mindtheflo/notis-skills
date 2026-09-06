## The skill-as-business-logic pattern

This is the core of the paradigm: **put logic in a skill, point an automation at it.**

**Creating the skill: use `notis-skill-creator`.** Whenever the business logic needs to live in a new (or updated) skill, follow the `notis-skill-creator` skill — it is the source of truth for the authoring workflow: defining the `name`/`description`, structuring `SKILL.md` (and optional `scripts/`/`references/`/`assets/`), validating the frontmatter, and saving directly into Notis through the owning workflow’s create-or-update branch (preserving the existing exact skill id for updates and the complete bundle). Do not hand-roll skill creation here; defer to `notis-skill-creator` for the details, then come back and wire the automation to it.

Worked example — "Every Monday, summarize last week's closed deals and post to Slack":

1. **Logic → skill.** If no skill covers it, author one by following `notis-skill-creator` and saving it with `LOCAL_NOTIS_CREATE_SKILL`. The skill `SKILL.md` holds the real procedure: which database to query, how to filter to last week's closed deals, and the summary format.
2. **Trigger + delivery → automation.** Create a `schedule` automation whose `prompt` cites the skill, and set the delivery channel on the `channel` field — not in the prompt:

   ```json
   {
     "trigger_type": "schedule",
     "name": "Weekly deal recap",
     "cron_expression": "0 9 * * 1",
     "prompt": "Run /weekly-deal-recap for last week and produce the summary.",
     "channel": "slack",
     "channel_account_id": "channel_slack:acme#T123"
   }
   ```

   The cron carries the "every Monday"; the channel carries "to Slack". The prompt carries neither.
3. **When the trigger fires**, Notis injects the cited skill's full `SKILL.md` as the workflow and executes it, then delivers the output to the configured channel. The automation stayed thin; the logic stayed reusable.

Use the same pattern for webhook, integration, and database automations: the trigger differs, but the `prompt` should still hand off to a skill for any non-trivial work. Reach for an inline prompt only when the action is a single, self-evident instruction.

---
