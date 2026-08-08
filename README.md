# Notis Skills

[![CI](https://github.com/mindtheflo/notis-skills/actions/workflows/ci.yml/badge.svg)](https://github.com/mindtheflo/notis-skills/actions/workflows/ci.yml)
[![skills.sh](https://skills.sh/b/mindtheflo/notis-skills)](https://skills.sh/mindtheflo/notis-skills)

Open-source agent skills for Notis, connected tools, browser and desktop control, app development, automations, and structured database queries.

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
