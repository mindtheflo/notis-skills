---
name: notis-automation
description: Use when the user wants to schedule, automate, trigger, or be reminded of anything — "remind me…", "every morning…", "in two hours…", "when a new Gmail arrives", "when this record changes", "post a weekly summary". Decides between a reminder, an automation, and a skill, and builds the correct payloads.
mcp_resource: true
mcp_tool_patterns: ["LOCAL_NOTIS_*REMINDER*", "LOCAL_NOTIS_*AUTOMATION*", "LOCAL_NOTIS_LIST_INTEGRATION_TRIGGERS"]
mcp_references: ["references/reminders.md", "references/automation-common.md", "references/schedule.md", "references/one-time.md", "references/webhook.md", "references/integration.md", "references/database.md", "references/skill-business-logic.md"]
---

# Notis Automation Skill

Use this skill whenever the user wants something to happen later, on a schedule, or in response to an event. It covers the three Notis building blocks and how they fit together:

- **Skills** hold the **business logic** — the reusable "what to do".
- **Automations** are the **glue**: they link a **trigger** to business logic. They are also how you make Notis **do something in the future**.
- **Reminders** are **dumb**: they deliver a fixed message at a time or on a schedule. No reasoning, no tools, no computed content.

The single most important job of this skill is to **pick the right primitive**, then build a valid payload for it.

## Tool names

These are native Notis tools. When their canonical `LOCAL_NOTIS_*` names are available in the current tool set, call them directly. Do not send an already-available native automation or reminder tool through `COMPOSIO_SEARCH_TOOLS` or wrap it in `COMPOSIO_MULTI_EXECUTE_TOOL`; discovery is only for a capability that is not loaded. Always call native tools by their canonical names:

| Area | Canonical tools |
|---|---|
| Reminders | `LOCAL_NOTIS_INSERT_REMINDER`, `LOCAL_NOTIS_UPDATE_REMINDER`, `LOCAL_NOTIS_LIST_REMINDERS`, `LOCAL_NOTIS_DELETE_REMINDER` |
| Automations | `LOCAL_NOTIS_INSERT_AUTOMATION`, `LOCAL_NOTIS_UPDATE_AUTOMATION`, `LOCAL_NOTIS_LIST_AUTOMATIONS`, `LOCAL_NOTIS_GET_AUTOMATION`, `LOCAL_NOTIS_RUN_AUTOMATION`, `LOCAL_NOTIS_LIST_AUTOMATION_RUNS`, `LOCAL_NOTIS_GET_AUTOMATION_RUN`, `LOCAL_NOTIS_DELETE_AUTOMATION`, `LOCAL_NOTIS_LIST_INTEGRATION_TRIGGERS` |
| Skills | `LOCAL_NOTIS_CREATE_SKILL`, `LOCAL_NOTIS_LIST_SKILLS`, `LOCAL_NOTIS_UPDATE_SKILL`, `LOCAL_NOTIS_INSTALL_SKILL`, `LOCAL_NOTIS_DISABLE_SKILL`, `LOCAL_NOTIS_DELETE_SKILL` |
| Databases (for `database` triggers) | `LOCAL_NOTIS_DATABASE_LIST_DATABASES`, `LOCAL_NOTIS_DATABASE_GET_DATABASE` |

## The paradigm

```
trigger  ->  automation  ->  business logic (often a skill)
time     ->  reminder     ->  static message
```

- A **trigger** is anything that should start work: a clock (cron), a future moment (one-time), an inbound HTTP call (webhook), an external integration event (new email, new calendar event), or a change to a Notis database record.
- An **automation** binds a trigger to a `prompt` that the Notis agent actually runs (a full agent turn). The prompt is the glue, not the place to dump a long procedure.
- A **skill** is where the real, reusable procedure lives. When the work is non-trivial or will be reused, put the steps in a skill and have the automation's prompt **cite that skill** (`/skill-name`). Keep automation prompts thin; keep logic in skills.
- A **reminder** is for when there is literally nothing to compute — the user just wants a nudge with fixed text.

### Choose the primitive

| The user wants... | Use | Why |
|---|---|---|
| A fixed nudge at a time or on a schedule ("remind me to call the dentist at 5pm") | **Reminder** | No reasoning needed — just deliver the exact text |
| Work to run on a schedule, on an event, or via a webhook ("every Monday summarize last week's deals", "reply when a new Gmail arrives") | **Automation** | A trigger must run business logic |
| To run a one-off task in the future ("in two hours, draft the recap") | **Automation** with `trigger_type: "one_time"` | "Do something later" that involves work is still an automation |
| A future message with fixed text and no computation ("at 6pm tonight, message me 'leave for the airport'") | **Reminder** with `trigger_type: "one_time"` | Future, but still just a static message |
| The procedure to be reusable across many triggers/threads | A **skill** (cited by the automation) | Business logic belongs in a skill |

Rules of thumb:

- If the action needs the agent to think, read or write a database, call any tool, fetch anything, or produce computed text → **automation**, never a reminder.
- "In the future" alone does not mean reminder. A future task with work is a **one-time automation**; a future fixed message is a **one-time reminder**.
- If you find yourself writing a long step-by-step procedure inside an automation `prompt`, stop and move it into a skill, then cite the skill from the prompt.

Before creating anything, **list what already exists** (`LOCAL_NOTIS_LIST_REMINDERS`, `LOCAL_NOTIS_LIST_AUTOMATIONS`) so you do not create a duplicate, and confirm the trigger and the action with the user in plain language.

---

## Two rules for writing automation prompts

These two mistakes break automations. Always follow them.

### 1. Never put the delivery destination in the prompt

Where the automation's response goes is set by the `channel` (and `channel_account_id`) field — **not** the prompt. The automation's output is delivered to that channel automatically.

- Do **not** write "send this to me on WhatsApp", "post the summary to Slack", "email me the result", or "reply in this thread" in the prompt.
- The prompt describes **only the work and the output to produce**. Delivery is configured separately.

```
Bad  prompt:  "Summarize yesterday's sales and post it to my Slack."
Good prompt:  "Summarize yesterday's sales."     (with channel: "slack")
```

### 2. Never put scheduling / recurrence wording in the prompt

The schedule lives in the **trigger** (the cron expression / one-time timestamp). The prompt runs *once* each time the trigger fires. If the prompt says "every morning", "each Monday", "daily", or "set this up to run…", the agent may interpret it as an instruction to **create another automation** — causing a recursive loop instead of doing the work.

- Write the prompt as a single, present-tense action to perform **right now**.
- Leave all timing/frequency to the trigger.

```
Bad  prompt:  "Every morning, send me a digest of new emails."
Good prompt:  "Compile a digest of emails received since yesterday."   (with cron: "0 8 * * *")
```

---

## House rules

- **Plain language to the user.** Talk about "a reminder", "a weekly automation", "the Slack channel", "the Tasks database" — not tool names, `trigger_type` values, or raw JSON. Build and validate the payloads internally.
- **Delivery is the channel, never the prompt.** Set where output goes via `channel`/`channel_account_id`. Keep "send to…", "post to…", "email me…", "reply in thread" out of the automation `prompt`.
- **No recurrence wording in the prompt.** The schedule lives in the trigger. A prompt that says "every morning" or "set up a daily…" risks the agent creating another automation instead of doing the work. Write the prompt as one present-tense action.
- **Discover before you ask.** Resolve picker-backed values yourself before asking the user: channel account (when multiple), integration toolkit/trigger/connected account (`LOCAL_NOTIS_LIST_INTEGRATION_TRIGGERS`), and database id + property ids (`LOCAL_NOTIS_DATABASE_LIST_DATABASES` / `LOCAL_NOTIS_DATABASE_GET_DATABASE`). One match → confirm; several → offer the choices; none → ask or defer.
- **Never invent identifiers.** Integration providers, `triggerName`s, `connectedAccountId`s, `database_id`s, and `property_id`s must come from discovery, not memory.
- **Resolve the schedule.** A schedule trigger needs a concrete cron expression; a one-time trigger needs a real future timestamp with timezone. Do not create a scheduled item with the timing unresolved.
- **Dedupe.** List existing reminders/automations first and remove duplicates rather than stacking near-identical ones.
- **Confirm, then create.** Recap the trigger and the action in one short plain-language line, get a yes, create it, then surface the portal URL (and webhook URL, if any).
- **Right primitive.** Static message → reminder. Work on a trigger → automation. Reusable logic → skill cited by the automation. When in doubt between a one-time reminder and a one-time automation, ask whether the future action is fixed text or actual work.

For an automation, read automation-common plus its one trigger guide. For a fixed
message, read reminders only. Reusable procedures use skill-business-logic.

## Task guides

Read only the guide needed for this task. Relative links resolve in the skill bundle.
For hosted MCP, fetch the matching `notis://docs/notis-automation/references/<file>.md` URI
with resources/read or the available Notis resource-fetch tool; the root resource
also rewrites these links to their published URIs.

- [Reminders (dumb message delivery)](references/reminders.md)
- [Automations (trigger -> business logic)](references/automation-common.md)
- [Trigger type: schedule (recurring)](references/schedule.md)
- [Trigger type: one_time (do something in the future)](references/one-time.md)
- [Trigger type: webhook (inbound HTTP)](references/webhook.md)
- [Trigger type: integration (connected app events)](references/integration.md)
- [Trigger type: database (Notis record change)](references/database.md)
- [The skill-as-business-logic pattern](references/skill-business-logic.md)
