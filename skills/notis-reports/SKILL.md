---
name: notis-reports
description: Read, create or revise SDK-powered reports in app-owned databases or standalone HTML documents that need no app or database. Inspect saved rendered content with a browser when needed.
feature_flag: store
mcp_resource: true
mcp_tool_patterns: ["LOCAL_NOTIS_SAVE_REPORT", "LOCAL_NOTIS_SAVE_HTML_DOCUMENT"]
---

# Notis Reports

## Shared authoring workflow

SDK reports are app views with independent record-owned implementations, not a separate UI system. For SDK create/edit tasks, follow the canonical [app-view workflow](../notis-apps/SKILL.md#build--inspect--fix--deliver) and read its [Design](../notis-apps/references/design.md) and [Delivery](../notis-apps/references/release.md) guidance. Use the same components, SDK styles, build, preview and visual checks. Report commands wrap that tooling; save the report instead of deploying the app. If sibling references are unavailable, load `notis-apps` by name. A successful build is not visual validation. Plain HTML uses the separate workflow below, not the SDK build or app deployment pipeline.

## Read an existing report

Use ordinary data tools when the saved content answers the question. For live
figures, charts, filters or visual inspection, follow the shared reading guide
under [Notis Apps](../notis-apps/SKILL.md#read-existing-apps-and-resources).
Hosted MCP clients can read it at
`notis://docs/notis-apps/references/reading.md`.
Open the saved report, not a rebuilt preview; its existing tools load as authored.
Reading a report does not mean regenerating or revising it.

## Choose the right surface

- **App view:** one shared SDK implementation presents many database records. Updating the view changes that shared presentation.
- **SDK report — app and database required:** one app-owned database record owns its independently authored SDK implementation. Different reports can have different compositions. Reports use the same SDK and capabilities as app views, and open inside the Portal.
- **HTML — no app or database required:** a standalone user-owned document holds plain self-contained HTML. Optionally file it in an existing app-owned database when the task calls for that. It opens in a new browser tab with the widget and Share, without Portal navigation chrome. No SDK, live Notis tools or SDK feedback integration.

Prefer SDK-powered reports for app-integrated reporting and live Notis tools. Choose standalone HTML for a self-contained deliverable without app/database setup; do not ask the user to create or install an app just to save HTML. Charts, tables, interactive controls and custom layouts work in either format. Choose captured results, live tools, or both according to the task and the surface's capabilities. Never infer historical numbers should refresh automatically.

## Author and save an SDK report

1. Discover the owning app and database and inspect its schema. Let the task determine the destination. If none fits, ask about creating or installing an app; never create a default reports app automatically.
2. Reconcile record identity before creating: a new weekly period normally means a new record; feedback or corrections normally revise the existing one. Follow the database's semantics, not a universal recurring-report rule.
3. For a revision, read the document with `LOCAL_NOTIS_DATABASE_GET_DOCUMENT` and download its short-lived `report_source_url` to recover the saved source archive. Preserve its source and record identity. For a new report, scaffold an SDK report using `notis reports init <name> <dir>`. Author exactly one route using the normal Apps SDK and design patterns. Declare needed tools; they remain bounded by the owning app's permissions. Keep readable report content and structure in a separate context file.
4. Build with `notis reports build <dir>`, then inspect with `notis reports verify <dir>` / `notis reports preview <dir>`. Verify desktop/mobile layout and actual intended interactions. This does not deploy the app.
5. Discover and inspect save/read schemas. `notis reports save <dir> --database-id <id> --title <title> --context-file <file>` builds and verifies before native persistence. Add `--document-id` and a freshly read `--expected-revision` for updates; use `--attach` for an existing record without a view. Use `--properties-file` for schema-keyed properties. Retain the record ID and unrelated properties.
6. Read back record, database, revision, artifact and URL. Inspect the saved native surface. Report persistence and visual verification separately when authenticated rendering is unavailable.
7. Return the native document link. Do not substitute downloads, sandbox exports, raw payloads or app deployment.

Legacy fixed `notis-report/v1` payloads are unsupported. Report revisions replace the current report state; this workflow does not promise an archive of earlier revisions. Separate report records retain separate implementations.

## Author and save HTML

1. Reconcile document identity before creating: corrections revise the existing document; a separate deliverable creates a new one. For a revision, read the document with the discovered `LOCAL_NOTIS_DATABASE_GET_DOCUMENT` tool; despite its name, it also reads standalone documents by ID. Preserve the saved HTML and document identity when revising.
2. Author complete self-contained markup and inspect its layout and intended interactions in a browser. HTML is sandboxed and cannot use the Notis SDK or authenticated Notis tools.
3. Discover and inspect `LOCAL_NOTIS_SAVE_HTML_DOCUMENT`. For standalone creation, supply `operation: create`, `title` and `html`; omit `database_id` and `properties`. No app discovery, database setup or `notis reports` build is needed.
4. To revise, supply `operation: update`, `document_id` and the freshly read `expected_revision` with the title and HTML. To replace an existing non-view document body with HTML, use `attach` and its current revision (zero if absent). Attach clears its old block content. Updates and attachments retain the existing database, if any; they do not move documents.
5. Only when filing HTML in an existing app-owned database, discover that database, inspect its schema and supply `database_id` and any schema-keyed `properties`. Preserve unrelated properties. This is optional, not a prerequisite for HTML.
6. Read back the saved document, HTML, revision and native URL; inspect the saved surface and return its native link. Report persistence and visual verification separately when authenticated rendering is unavailable. Standalone documents are private to their owner unless explicitly shared through Share; no app deployment is involved.

## Optional passive feedback

Feedback is opt-in. Follow [the shared SDK feedback pattern](../notis-apps/references/context.md) when the user wants comments, responses or feedback to bring back to an agent. It is available to app views too and is not an approval workflow.
