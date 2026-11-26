---
name: notis-feedback
description: Gather user feedback on an SDK-powered report or Space page through the built-in Cite and Comment on selected text, Space comments in the host Comments panel, app-defined annotations and generic chat context pills.
mcp_resource: true
mcp_tool_patterns: []
---

# Notis Feedback

Use the shared [SDK context pattern](../notis-spaces/references/context.md) and the [Comments](../notis-spaces/references/comments.md) reference owned by `notis-spaces`. If the sibling references are not installed, load the `notis-spaces` skill or its hosted MCP guide by name to access them. Read them before authoring feedback interactions; do not maintain a second report renderer, comment store or feedback contract.

1. Identify the existing report or Space page and the content the user wants reviewed.
2. Selected text on every Space page already offers Cite (a selected-text pill in chat) and, where comments are on, Comment (a comment in the host Comments panel). Add nothing for passage feedback. Do not create a Comments database, comment columns or your own comment box.
3. Add only what the page needs beyond words: pins, zones, items or moments through `useComments` and its comment modes, or an explicit context pill with `useAgentContext()` for a reference that belongs in chat (image coordinates, chart state, the image being reviewed). Context can include arbitrary JSON and explicit attachments; adding a pill sends nothing.
4. Read and answer comments only through `LOCAL_NOTIS_SPACE_COMMENT_THREADS` (`list`, `thread`, `reply`, `answer` and the other operations), never through a database query or a row write. When a person decided your question elsewhere, `answer` it with that decision so it stops waiting. Declare your band name when writing through the CLI; never archive a comment, that is the people's.
5. Use the owning report or Space workflow for building, verification and authorized persistence. Feedback does not authorize executing proposals, deploying a Space or publishing a Store listing.

For a new report, use the [reports guidance](../notis-spaces/references/reports.md) in `notis-spaces`. Plain HTML pages saved in Notis Notes do not support this SDK pattern.
