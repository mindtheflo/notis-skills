# Notis Skills and MCP

[![CI](https://github.com/mindtheflo/notis-skills/actions/workflows/ci.yml/badge.svg)](https://github.com/mindtheflo/notis-skills/actions/workflows/ci.yml)
[![skills.sh](https://skills.sh/b/mindtheflo/notis-skills)](https://skills.sh/mindtheflo/notis-skills)

Open-source agent skills and public integration metadata for the hosted Notis MCP server.

## Notis MCP

Connect AI agents to Notis memory, skills, automations, and more than 1,000 apps.

- **Endpoint:** `https://mcp.notis.ai/mcp`
- **Transport:** Streamable HTTP
- **Authentication:** OAuth 2.1 with PKCE
- **Website:** [notis.ai](https://www.notis.ai/)
- **Setup guide:** [Connect Notis to your AI agent](https://help.notis.ai/agents/overview)

Compatible MCP clients discover the protected-resource and authorization-server metadata from the endpoint, then open the browser-based Notis authorization flow. The hosted server exposes tools for discovery, validation, reads, approved writes, and connecting additional toolkits.

This repository contains the public skills and integration metadata for the hosted MCP endpoint. It does not contain the private Notis application source code.

## Agent skills

Install the complete collection:

```bash
npx skills add mindtheflo/notis-skills
```

Or choose individual skills from the repository when your agent supports selective installation.

Every `skills/<name>/SKILL.md` is generated from the canonical `server/skills/<name>/SKILL.md` in the private Notis monorepo. New tracked skills are included automatically; do not edit mirrored files directly.

After each push, CI validates every mirrored skill and installs the complete
collection in an ephemeral runner. That install telemetry refreshes the
skills.sh repository index without a manual submission step.

Notis-authored material is MIT licensed. Third-party material retains its
original license; see `THIRD_PARTY_NOTICES.md`.
