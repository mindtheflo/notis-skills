---
name: notis-skill-creator
description: Guide for creating effective skills. Use when users want to create a new skill that extends the assistant's capabilities with specialized knowledge, workflows, or tool integrations.
---

# Notis Skill Creator

This skill guides the process of creating new skills from scratch or iterating on existing ones. A skill is a self-contained unit of instructions, references, and optional scripts that extend the assistant's capabilities.

## When to Use This Skill

- User wants to create a new skill (e.g., "Create a skill for X", "I need a skill that does Y")
- User is iterating on or packaging an existing skill
- User asks how to structure, validate, or distribute a skill

## Skill Development Workflow

### Step 1: Define the Skill

Before creating files, clarify:

- **Name** — kebab-case (e.g., `my-skill`, `api-helper`)
- **Description** — One or two sentences: what the skill does and when to use it
- **Scope** — Instructions only, or instructions + scripts/references/assets

### Step 2: Plan the Contents

- **SKILL.md** — Required. Contains YAML frontmatter (`name`, `description`) and the main instructions.
- **scripts/** — Optional. Executable code (Python, Bash, etc.) the assistant can run.
- **references/** — Optional. Documentation or reference files loaded on demand.
- **assets/** — Optional. Templates, images, or other files used in outputs.

### Step 3: Initializing the Skill

At this point, it is time to actually create the skill.

Skip this step only if the skill being developed already exists, and iteration or packaging is needed. In this case, continue to the next step.

When creating a new skill from scratch, create the directory structure manually:

```bash
mkdir -p my-skill/scripts my-skill/references my-skill/assets
```

Then create `my-skill/SKILL.md` with the proper YAML frontmatter:

```markdown
---
name: my-skill
description: "Description of what this skill does and when to use it"
---

# My Skill

## Instructions

(Add your skill instructions here)
```

Create any supporting files in the appropriate directories:

- `scripts/` for executable code (Python, Bash, etc.)
- `references/` for documentation to be loaded on demand
- `assets/` for files used in output (templates, images, etc.)

### Step 4: Writing and Iterating

- Keep instructions clear and actionable. Include when to use the skill, required inputs, and expected outputs.
- Reference scripts or assets by path (e.g., `scripts/helper.py`, `references/glossary.md`).
- Test the skill by having the assistant follow it in a real scenario.

### Step 5: Save or update the exact skill

Discover the native skill tools and read the current installed skill list first.
Resolve the existing skill by exact id, owner and any app binding — never pick the
first name match. An edit updates that id; creation is only for genuinely new skills.

- Single-file creation: use discovered `LOCAL_NOTIS_CREATE_SKILL` with name,
  description and skill_md. Single-file edit: `LOCAL_NOTIS_UPDATE_SKILL` with
  skill_id and only changed fields. Preserve unrelated agent_targets and status.
- Multi-file creation or update: package the complete folder with SKILL.md,
  scripts, references and assets. Use the CLI `--file bundle_url=./skill.zip`
  upload path with the discovered CREATE or UPDATE tool (UPDATE includes skill_id).
  Do not wait for an invented public-URL notification or drop existing resources.
- Curated skills are maintained in their canonical source and published separately;
  normal user-skill updates cannot replace curated content. App-owned source
  changes follow that app's release boundary; editing instructions is not deployment.
- Validate frontmatter, resource paths and intended changes; dry-run the mutation.
  Read back the same id, content and preserved assignments; for bundles verify the
  full resource set. An update must not increase the installed record count.
- Deliver the native skill link. Export a zip to the user only when requested.

## SKILL.md Frontmatter

Every skill must have a SKILL.md with at least:

```yaml
---
name: skill-name
description: "Clear description of what the skill does and when to use it."
---
```

- **name** — kebab-case identifier; used for packaging and display.
- **description** — Shown in skill lists and used for triage; be specific.

## Best Practices

1. **One clear purpose** — Each skill should do one thing well.
2. **Good description** — The description is used to decide when to invoke the skill; make it searchable and precise.
3. **Stable structure** — Use `scripts/`, `references/`, `assets/` consistently so users and tools know where to find things.
4. **Validate before packaging** — Check frontmatter, naming, and that all referenced files exist.

## Notis-Specific Notes

- Product sources live in `server/skills/`; development workflows in `.agents/skills/`.
  Do not edit generated mirrors or vendor caches as the canonical source.
- CLI-owned sync materializes account bundles and manages per-agent links. Automatic
  Desktop sync is optional; local availability is not proven merely by saving a row.
  Preserve target assignments and use the supported sync workflow for the intended
  account. Verify content/materialization and discovery before claiming availability.
- Repo maintainers follow `docs/notis-skills-lifecycle.md` and `docs/skills-sync.md`.
