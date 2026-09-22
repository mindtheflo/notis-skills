---
name: notis-reports
description: Read, create or revise standalone live SDK reports and plain HTML documents. Neither requires an app or database. Inspect saved rendered content with a browser when needed.
feature_flag: store
mcp_resource: true
mcp_tool_patterns: ["LOCAL_NOTIS_SAVE_REPORT", "LOCAL_NOTIS_SAVE_HTML_DOCUMENT"]
---

# Notis Reports

## Shared authoring workflow

SDK reports are standalone documents with independent live app-view implementations, not a separate UI system. For SDK create/edit tasks, follow the canonical [app-view workflow](../notis-apps/SKILL.md#build--inspect--fix--deliver) and read its [Design](../notis-apps/references/design.md) and [Delivery](../notis-apps/references/release.md) guidance. Use the same components, SDK styles, build, preview and visual checks. Report commands use that tooling with a report build profile; save the document instead of deploying an app. If sibling references are unavailable, load `notis-apps` by name. A successful build is not visual validation. Plain HTML uses the separate workflow below, not the SDK build or app deployment pipeline.

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
- **SDK report — no app or database required:** one private user-owned document owns its independently authored live SDK implementation. Different reports can have different compositions. Reports use the same SDK and capabilities as app views, and open inside the Portal.
- **HTML — no app or database required:** a standalone user-owned document holds plain self-contained HTML. Optionally file it in an existing app-owned database when the task calls for that. It opens in a new browser tab with the widget and Share, without Portal navigation chrome. No SDK, live Notis tools or SDK feedback integration.

Prefer SDK-powered reports for live Notis tools and view behavior. Choose HTML for plain self-contained markup without the SDK. Never create/install an app or a database merely to save either format. Charts, tables, interactive controls and custom layouts work in either format. Choose captured results, live tools, or both according to the task and the surface's capabilities. Never infer historical numbers should refresh automatically.

## Author and save an SDK report

1. Reconcile document identity before creating. Search existing reports for the same task; corrections revise the existing document. Do not choose a database destination or create/install an app.
2. For a revision, read `LOCAL_NOTIS_DATABASE_GET_DOCUMENT` and download its short-lived `report_source_url`. Preserve document identity. For a new report, use `notis reports init <name> <dir>`; the scaffold sets `kind: 'report'` and has no owned resources.
3. Author one route with the normal SDK and view design patterns. Discover and declare exact tool names. Optional existing data sources use `databaseAccess: [{ id, access: 'read' | 'write' }]`, not `databases`. Reads use normal view hooks; writes/sends require user actions and the trusted host confirmation. Do not add a report-specific persistence or refresh system. Reports are private; no sharing or bundled skills/automations.
4. Keep readable structure and data-source context in a separate file; do not present this saved text as current live values. Build with `notis reports build <dir>`, then verify/preview with the normal tooling. Inspect layout and intended interactions. No app deployment is involved.
5. Discover and inspect save/read schemas. `notis reports save <dir> --title <title> --context-file <file>` builds and verifies before persistence. Updates add `--document-id` and a freshly read `--expected-revision`. There are no database/properties/attach flags.
6. Read back identity, null database, revision, artifact, source and URL. Verify live reads and user actions on the saved Portal surface. `reports verify --mode live --document-id <id> --expected-revision <n>` can exercise saved read permissions; its headless harness never authorizes mutations. Report persistence and visual validation separately when authenticated rendering is unavailable.
7. Return the native document link. Saving changes that report only. Use `notis-report/v3`; older report formats are unsupported, with no migration path or promise of a revision archive.

## Author and save HTML

1. Reconcile document identity before creating: corrections revise the existing document; a separate deliverable creates a new one. For a revision, read the document with the discovered `LOCAL_NOTIS_DATABASE_GET_DOCUMENT` tool; despite its name, it also reads standalone documents by ID. Preserve the saved HTML and document identity when revising.
2. Author complete self-contained markup and inspect its layout and intended interactions in a browser. HTML is sandboxed and cannot use the Notis SDK or authenticated Notis tools.
3. Discover and inspect `LOCAL_NOTIS_SAVE_HTML_DOCUMENT`. For standalone creation, supply `operation: create`, `title` and `html`; omit `database_id` and `properties`. No app discovery, database setup or `notis reports` build is needed.
4. To revise, supply `operation: update`, `document_id` and the freshly read `expected_revision` with the title and HTML. To replace an existing non-view document body with HTML, use `attach` and its current revision (zero if absent). Attach clears its old block content. Updates and attachments retain the existing database, if any; they do not move documents.
5. Only when filing HTML in an existing app-owned database, discover that database, inspect its schema and supply `database_id` and any schema-keyed `properties`. Preserve unrelated properties. This is optional, not a prerequisite for HTML.
6. Read back the saved document, HTML, revision and native URL; inspect the saved surface and return its native link. Report persistence and visual verification separately when authenticated rendering is unavailable. Standalone documents are private to their owner unless explicitly shared through Share; no app deployment is involved.

## Optional passive feedback

Feedback is opt-in. Follow [the shared SDK feedback pattern](../notis-apps/references/context.md) when the user wants comments, responses or feedback to bring back to an agent. It is available to app views too and is not an approval workflow.
