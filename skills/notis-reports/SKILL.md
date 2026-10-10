---
name: notis-reports
description: Read, create or revise interactive reports as independent Space views, or inspect preserved report rows in their database's main view.
feature_flag: spaces
mcp_resource: true
mcp_tool_patterns: []
---

# Notis Reports

A report is an independently authored view, not a separate UI system. New reports
use an independent Space with their own source, data declarations and memory
policy. A shared collection view presents many database rows; a preserved report
row can keep its independent saved payload and render through `<ReportFrame>` in
that database's main view. Editing one report must not replace an unrelated view. If sibling references are
unavailable in your harness, load `notis-apps` by name.

## Read an existing report

Use native data tools when they answer the question. For live figures, charts,
filters, HTML or visual inspection, load `notis-apps` and follow its
[Read and render](../notis-apps/references/reading.md) guide (hosted MCP:
`notis://docs/notis-apps/references/reading.md`).

Resolve the exact report period and current view link with `LOCAL_NOTIS_FIND_VIEWS`,
then render it with `LOCAL_NOTIS_RENDER_VIEW`. Inspect Markdown and image output.
Reading does not regenerate historical figures or authorize source/data changes.

## Create or revise an interactive report

1. Reconcile identity first. Find the existing report Space or exact database
   record for a requested correction. Preserve the selected identity and revision;
   a similarly named report is not the same artifact.
2. For a new independent report, follow `notis-apps` [View authoring](../notis-apps/references/views.md),
   [Design](../notis-apps/references/design.md) and [Delivery](../notis-apps/references/release.md).
   Declare the report's period/selection as typed params, its real data in `shows`
   or declared actions, clear source context, and a suitable memory policy.
3. Choose captured results, live reads or both according to the user's request.
   Historical results stay captured unless revision was requested. Keep units,
   periods, method and source links visible. Provide `<RenderChartData>` with the
   actual chart values for precise Markdown extraction.
4. Build, verify with fictional fixtures and inspect EN/FR at 390px/1440px. Then
   deploy the checked source within the user's authorization, read back its revision
   and render the actual saved view. A preview is not the deliverable of record.
5. For an existing database report row, keep its database and record key. Discover
   the supported report revision tool, inspect its schema, retain the original
   expected revision/request ID, and verify the updated row through its main view.
   Do not discard its payload or replace the collection's shared source merely to
   revise one report.
6. Return the current view-qualified link and the exact verification boundary.
   Store publication is separate from saving the authorized report Space update.

## Plain HTML

Use the installable **HTML Space** and its linked **Save HTML** Skill. It keeps
original HTML bytes as a native record attachment and opens them full screen with
viewer CSP and per-record Site sharing. If it is not installed, suggest installing
it. The bundled Skill owns row creation, generic file upload, CAS attachment,
readback and explicit sharing; this report guide does not duplicate that workflow.

## Optional passive feedback

Use [Context sharing](../notis-apps/references/context.md) for selected text,
comments or annotations the user wants to bring back to an agent. Feedback is
reference context, not execution approval, and does not itself send a message.
