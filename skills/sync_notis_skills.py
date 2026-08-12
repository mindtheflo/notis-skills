"""
Skills sync CLI: push repo-maintained and anthropics skills to OpenAI.

Repo-maintained skills are zipped from server/skills/<name>/.
Anthropics skills (docx, pdf, pptx, xlsx) are cloned to temp and zipped from there.

Usage:
  python server/skills/sync_notis_skills.py sync [skill ...] --channel dev|beta|production

Requires: OPENAI_API_KEY; SUPABASE_SUBDOMAIN, SUPABASE_SERVICE_KEY (or --skill-ids).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

# Resolve both the server package root and the repository root.
_SERVER_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_REPO_ROOT = os.path.abspath(os.path.join(_SERVER_ROOT, ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from server.lib.curated_skill_channels import (
    CURATED_SKILL_CHANNELS,
    build_curated_skill_channel_update_fields,
)
from server.lib.curated_skill_metadata import (
    feature_flag_from_skill_md,
    required_entitlements_from_skill_md,
    validate_metadata_key,
)
from server.lib.feature_flags import CURATED_SKILL_FEATURE_FLAGS
from server.lib.tool_entitlements import is_known_entitlement


def discover_repo_skills(skills_root: str) -> list[str]:
    names: list[str] = []
    if not os.path.isdir(skills_root):
        return names

    for entry in os.scandir(skills_root):
        if not entry.is_dir():
            continue
        if os.path.isfile(os.path.join(entry.path, "SKILL.md")):
            names.append(entry.name)
    return sorted(names)


# Repo-maintained skills live in server/skills/<name>/; anthropics skills are synced from their repo.
OUR_SKILLS = discover_repo_skills(os.path.join(_SERVER_ROOT, "skills"))
DEFAULT_OUR_SKILLS = {
    name
    # notis-desktop-use is intentionally NOT default: experimental, opt-in,
    # and additionally gated by the desktop_control entitlement.
    for name in ("notis-apps", "notis-automation", "notis-browser-control", "notis-cli", "notis-query")
    if name in OUR_SKILLS
}
ANTHROPICS_SKILL_NAMES = ["docx", "pdf", "pptx", "xlsx"]
ANTHROPICS_REPO_URL = "https://github.com/anthropics/skills.git"


NOTIS_SKILL_CREATOR_NAME = "notis-skill-creator"
UPSTREAM_SKILL_CREATOR_NAME = "skill-creator"
RENAMED_REPO_SKILLS = {
    UPSTREAM_SKILL_CREATOR_NAME: NOTIS_SKILL_CREATOR_NAME,
    # notis-my-computer-use was renamed to notis-desktop-use; this maps the old
    # curated_skills row (keyed on the legacy name) onto the renamed folder so the
    # sync updates the existing OpenAI skill + row name in place rather than
    # orphaning the old one or minting a duplicate.
    "notis-my-computer-use": "notis-desktop-use",
}


def canonical_repo_skill_name(name: str) -> str:
    """Return the current repo-maintained skill name for old aliases."""
    return RENAMED_REPO_SKILLS.get(name, name)


def adapt_skill_md(content: str) -> str:
    """Adapt the upstream skill-creator SKILL.md for Notis (replace init_skill.py/package_skill.py with Notis flow)."""
    old_step3 = """### Step 3: Initializing the Skill

At this point, it is time to actually create the skill.

Skip this step only if the skill being developed already exists, and iteration or packaging is needed. In this case, continue to the next step.

When creating a new skill from scratch, always run the `init_skill.py` script. The script conveniently generates a new template skill directory that automatically includes everything a skill requires, making the skill creation process much more efficient and reliable.

Usage:

```bash
scripts/init_skill.py <skill-name> --path <output-directory>
```

The script:

- Creates the skill directory at the specified path
- Generates a SKILL.md template with proper frontmatter and TODO placeholders
- Creates example resource directories: `scripts/`, `references/`, and `assets/`
- Adds example files in each directory that can be customized or deleted

After initialization, customize or remove the generated SKILL.md and example files as needed."""

    new_step3 = """### Step 3: Initializing the Skill

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
- `assets/` for files used in output (templates, images, etc.)"""

    content = content.replace(old_step3, new_step3)

    old_step5 = """### Step 5: Packaging a Skill

Once development of the skill is complete, it must be packaged into a distributable .skill file that gets shared with the user. The packaging process automatically validates the skill first to ensure it meets all requirements:

```bash
scripts/package_skill.py <path/to/skill-folder>
```

Optional output directory specification:

```bash
scripts/package_skill.py <path/to/skill-folder> ./dist
```

The packaging script will:

1. **Validate** the skill automatically, checking:

   - YAML frontmatter format and required fields
   - Skill naming conventions and directory structure
   - Description completeness and quality
   - File organization and resource references

2. **Package** the skill if validation passes, creating a .skill file named after the skill (e.g., `my-skill.skill`) that includes all files and maintains the proper directory structure for distribution. The .skill file is a zip file with a .skill extension.

If validation fails, the script will report the errors and exit without creating a package. Fix any validation errors and run the packaging command again."""

    current_notis_step5 = """### Step 5: Packaging and Installing

Once development of the skill is complete, package it into a zip file:

```bash
cd /path/to/parent && zip -r my-skill.zip my-skill/
```

Before packaging, validate your skill:
- SKILL.md exists with proper YAML frontmatter (`name` and `description` fields)
- Skill name follows kebab-case (lowercase letters, digits, and hyphens)
- Description clearly explains what the skill does and when to use it

After creating the zip file, ask the user to download it and upload it through the **Notis Skills page** in the portal (Settings > Skills > Upload Skill)."""

    new_step5 = """### Step 5: Save the Skill in Notis

When the user wants a Notis skill created, saved, or updated, save it directly in Notis by default. Do not make the user manually download and upload a zip unless they explicitly ask for an export.

For a simple skill that only needs a `SKILL.md`:

1. Finish the `SKILL.md` content.
2. Call `notis_create_skill` with:
   - `name`
   - `description`
   - `skill_md`

For a multi-file skill that needs `scripts/`, `references/`, or `assets/`:

1. Build the skill folder locally.
2. Package it into a zip:

```bash
cd /path/to/parent && zip -r my-skill.zip my-skill/
```

3. Wait for Notis to surface the generated file's public URL in the shell/file context.
4. Call `notis_create_skill` with:
   - `name`
   - `description`
   - `bundle_url`

Before saving, validate your skill:
- `SKILL.md` exists with proper YAML frontmatter (`name` and `description` fields)
- Skill name follows kebab-case (lowercase letters, digits, and hyphens)
- Description clearly explains what the skill does and when to use it

Only hand the zip file back to the user when they explicitly ask for the bundle itself."""

    content = content.replace(old_step5, new_step5)
    content = content.replace(current_notis_step5, new_step5)
    return content


def zip_skill_dir(skill_dir: str, skill_name: str, adapt_content: str | None = None) -> tuple[str, str | None]:
    """
    Zip a skill directory. Returns (path_to_zip, skill_md_content).
    If adapt_content is UPSTREAM_SKILL_CREATOR_NAME, SKILL.md is passed through adapt_skill_md.
    """
    files = {}
    skill_md_content = None
    for root, _dirs, filenames in os.walk(skill_dir):
        for fname in filenames:
            if fname == "LICENSE.txt":
                continue
            full_path = os.path.join(root, fname)
            rel_path = os.path.relpath(full_path, skill_dir)
            with open(full_path, "rb") as f:
                content = f.read()
            if rel_path == "SKILL.md" or rel_path == "skill.md":
                text = content.decode("utf-8")
                if adapt_content == UPSTREAM_SKILL_CREATOR_NAME:
                    text = adapt_skill_md(text)
                skill_md_content = text
                files["SKILL.md"] = text.encode("utf-8")
            else:
                files[rel_path] = content

    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False, prefix=f"{skill_name}_")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, data in files.items():
            zf.writestr(f"{skill_name}/{path}", data)
    tmp.close()
    return tmp.name, skill_md_content


def get_skills_dir(cli_skills_dir: str | None) -> str:
    """Resolve the skills directory (ours: notis repo skills/)."""
    if cli_skills_dir:
        return os.path.abspath(cli_skills_dir)
    return os.path.join(_SERVER_ROOT, "skills")


def fetch_curated_skills(supabase, skill_names: list[str] | None) -> list[dict]:
    """Return curated_skills rows with name, openai_skill_id, id. Only rows that have openai_skill_id."""
    result = (
        supabase.table("curated_skills")
        .select("id, name, openai_skill_id")
        .not_.is_("openai_skill_id", "null")
        .execute()
    )
    rows = result.data or []
    if skill_names:
        names_set = {canonical_repo_skill_name(name) for name in skill_names}
    else:
        names_set = None

    normalized_rows = []
    for row in rows:
        canonical_name = canonical_repo_skill_name(row["name"])
        if names_set and canonical_name not in names_set:
            continue
        normalized = dict(row)
        normalized["name"] = canonical_name
        normalized_rows.append(normalized)
    return normalized_rows


def fetch_curated_skills_any(supabase, skill_names: list[str]) -> dict[str, dict]:
    """Return curated_skills rows by name (including null openai_skill_id). Returns {name: row}."""
    result = supabase.table("curated_skills").select("id, name, openai_skill_id, description, category, sort_order").execute()
    rows = result.data or []
    names_set = {canonical_repo_skill_name(name) for name in skill_names}
    by_name = {}
    for row in rows:
        canonical_name = canonical_repo_skill_name(row["name"])
        if canonical_name not in names_set:
            continue
        normalized = dict(row)
        normalized["name"] = canonical_name
        by_name[canonical_name] = normalized
    return by_name


def description_from_skill_md(skill_md: str | None, name: str) -> str:
    """Extract description from SKILL.md frontmatter or use default."""
    if not skill_md or "---" not in skill_md:
        return f"Skill: {name}"
    m = re.search(r"description:\s*[\"']?([^\"'\n]+)", skill_md)
    return m.group(1).strip() if m else f"Skill: {name}"


def parse_skill_ids(flag_value: str) -> dict[str, str]:
    """Parse --skill-ids docx:skill_abc,pdf:skill_def into {name: openai_skill_id}."""
    out = {}
    for part in flag_value.split(","):
        part = part.strip()
        if ":" in part:
            name, sid = part.split(":", 1)
            out[name.strip()] = sid.strip()
    return out


def validated_access_metadata(
    name: str,
    skill_md: str | None,
) -> tuple[str | None, list[str]]:
    """Parse and validate access frontmatter before publishing a new version."""
    feature_flag = feature_flag_from_skill_md(skill_md)
    required_entitlements = required_entitlements_from_skill_md(skill_md)
    if feature_flag and (
        not validate_metadata_key(feature_flag)
        or feature_flag not in CURATED_SKILL_FEATURE_FLAGS
    ):
        raise ValueError(
            f"Invalid or unknown feature_flag in {name}/SKILL.md: {feature_flag}"
        )
    invalid_entitlements = [
        entitlement
        for entitlement in required_entitlements
        if not validate_metadata_key(entitlement) or not is_known_entitlement(entitlement)
    ]
    if invalid_entitlements:
        raise ValueError(
            f"Unknown required_entitlements in {name}/SKILL.md: "
            + ", ".join(invalid_entitlements)
        )
    return feature_flag, required_entitlements


async def push_skill(
    name: str,
    openai_skill_id: str,
    zip_path: str,
    skill_md: str | None,
    channel: str,
    openai_api_key: str,
    supabase,
    dry_run: bool,
    source_sha: str | None,
):
    """Create new version, set default, update curated_skills. Returns (success, version or None)."""
    from server.lib.skills_api import create_skill_version, update_skill_default_version

    feature_flag, required_entitlements = validated_access_metadata(name, skill_md)
    if dry_run:
        return True, None

    version_result = await create_skill_version(openai_api_key, openai_skill_id, zip_path)
    if not version_result:
        return False, None
    version = version_result["version"]

    if channel == "production":
        ok = False
        # Delay before setting default (API may need time to index the new version); retry once on failure
        for attempt in range(2):
            await asyncio.sleep(5 if attempt == 0 else 8)
            ok = await update_skill_default_version(openai_api_key, openai_skill_id, str(version))
            if ok:
                break
        if not ok:
            return False, version

    if skill_md and supabase:
        update_fields = build_curated_skill_channel_update_fields(
            channel,
            skill_md=skill_md,
            openai_skill_version=str(version),
            source_sha=source_sha,
            mirror_legacy_production=True,
        )
        # Also sync category in case it was corrected
        if name in ANTHROPICS_SKILL_NAMES:
            update_fields["category"] = "Documents"
        elif name in OUR_SKILLS:
            update_fields["category"] = "Notis"
        update_fields["name"] = name
        # Frontmatter is the source of truth for independent visibility and
        # billing policy. Omitted entitlements normalize to no extra gate;
        # legacy `skills` entries are dropped because Skills are all-tier.
        update_fields["required_feature_flag"] = feature_flag
        update_fields["required_entitlements"] = required_entitlements
        supabase.table("curated_skills").update(update_fields).eq("openai_skill_id", openai_skill_id).execute()
    return True, version


def clone_repo_to_temp(repo_url: str, prefix: str = "skills_") -> str:
    """Shallow clone a git repo. Returns path to repo root."""
    tmp = tempfile.mkdtemp(prefix=prefix)
    subprocess.run(
        ["git", "clone", "--depth", "1", repo_url, tmp],
        check=True,
        capture_output=True,
    )
    return tmp


def clone_anthropics_to_temp() -> str:
    """Shallow clone anthropics/skills. Returns path to repo root (contains skills/)."""
    return clone_repo_to_temp(ANTHROPICS_REPO_URL, "anthropics_skills_")


def collect_anthropics_skill(repo_root: str, skill_name: str) -> tuple[str, str | None]:
    """Zip skill from cloned repo. For upstream skill-creator, apply adapt_skill_md. Returns (zip_path, skill_md)."""
    skill_dir = os.path.join(repo_root, "skills", skill_name)
    if not os.path.isdir(skill_dir):
        raise FileNotFoundError(f"Skill directory not found: {skill_dir}")
    adapt = UPSTREAM_SKILL_CREATOR_NAME if skill_name == UPSTREAM_SKILL_CREATOR_NAME else None
    return zip_skill_dir(skill_dir, skill_name, adapt_content=adapt)


async def run_sync(
    skill_names: list[str] | None,
    from_claude: bool,
    skills_dir: str | None,
    dry_run: bool,
    skill_ids_flag: str | None,
    json_output: bool,
    bootstrap: bool,
    channel: str,
    source_sha: str | None,
) -> int:
    """Run sync. Returns exit code."""
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        print("Error: OPENAI_API_KEY is required", file=sys.stderr)
        return 1

    if channel not in CURATED_SKILL_CHANNELS:
        print(f"Error: unsupported channel '{channel}'", file=sys.stderr)
        return 1

    if skill_names:
        skill_names = [canonical_repo_skill_name(name) for name in skill_names]

    supabase = None
    if not skill_ids_flag:
        try:
            from supabase import create_client
            subdomain = os.getenv("SUPABASE_SUBDOMAIN")
            service_key = os.getenv("SUPABASE_SERVICE_KEY")
            if not subdomain or not service_key:
                print("Error: SUPABASE_SUBDOMAIN and SUPABASE_SERVICE_KEY are required (or use --skill-ids)", file=sys.stderr)
                return 1
            supabase = create_client(f"https://{subdomain}.supabase.co", service_key)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    # Build list of skills to sync
    skills_to_sync = list(OUR_SKILLS)
    if from_claude:
        skills_to_sync = skills_to_sync + list(ANTHROPICS_SKILL_NAMES)
    if skill_names:
        skills_to_sync = [s for s in skills_to_sync if s in skill_names]

    if not skills_to_sync:
        print("No skills to sync (no matching skills).", file=sys.stderr)
        return 0

    # Bootstrap: create in OpenAI and insert/update curated_skills when openai_skill_id is missing
    if bootstrap and supabase:
        curated_by_name = fetch_curated_skills_any(supabase, skills_to_sync)
        curated = []
        for name in skills_to_sync:
            row = curated_by_name.get(name)
            sid = row.get("openai_skill_id") if row else None
            curated.append({"name": name, "openai_skill_id": sid, "id": row["id"] if row else None})
    elif skill_ids_flag:
        id_map = parse_skill_ids(skill_ids_flag)
        id_map = {canonical_repo_skill_name(n): sid for n, sid in id_map.items()}
        curated = [{"name": n, "openai_skill_id": sid, "id": None} for n, sid in id_map.items() if n in skills_to_sync]
    else:
        curated = fetch_curated_skills(supabase, skill_names or None)
        if not curated:
            print("No skills to sync (no curated_skills with openai_skill_id). Use --bootstrap to create them.", file=sys.stderr)
            return 0
        # Filter to only skills we're syncing
        names_set = set(skills_to_sync)
        curated = [c for c in curated if c["name"] in names_set]

    if not curated:
        print("No skills to sync.", file=sys.stderr)
        return 0

    our_dir = get_skills_dir(skills_dir)
    results = []
    temp_zips = []
    anthropics_repo = None
    from server.lib.skills_api import create_skill as openai_create_skill

    try:
        for row in curated:
            name = row["name"]
            openai_skill_id = row.get("openai_skill_id")
            zip_path = None
            skill_md = None

            if name in OUR_SKILLS:
                skill_path = os.path.join(our_dir, name)
                skill_md_path = os.path.join(skill_path, "SKILL.md")
                if not os.path.isfile(skill_md_path):
                    results.append({"name": name, "ok": False, "error": f"Missing {skill_md_path}"})
                    continue
                zip_path, skill_md = zip_skill_dir(skill_path, name, adapt_content=None)
                temp_zips.append(zip_path)
            elif name in ANTHROPICS_SKILL_NAMES:
                if from_claude or (skill_names and name in skill_names):
                    if anthropics_repo is None:
                        anthropics_repo = clone_anthropics_to_temp()
                    zip_path, skill_md = collect_anthropics_skill(anthropics_repo, name)
                    temp_zips.append(zip_path)
                else:
                    results.append({"name": name, "ok": False, "error": "Use --from claude to sync anthropics skills"})
                    continue
            else:
                results.append({"name": name, "ok": False, "error": f"Unknown skill: {name}"})
                continue

            try:
                required_feature_flag, required_entitlements = validated_access_metadata(
                    name,
                    skill_md,
                )
            except ValueError as metadata_error:
                results.append({"name": name, "ok": False, "error": str(metadata_error)})
                continue

            if openai_skill_id:
                success, version = await push_skill(
                    name,
                    openai_skill_id,
                    zip_path,
                    skill_md,
                    channel,
                    openai_api_key,
                    supabase,
                    dry_run,
                    source_sha,
                )
                results.append({"name": name, "ok": success, "version": version})
            else:
                # Bootstrap: create skill in OpenAI, then insert or update curated_skills
                if dry_run:
                    results.append({"name": name, "ok": True, "version": None})
                    continue
                create_result = await openai_create_skill(openai_api_key, zip_path)
                if not create_result:
                    results.append({"name": name, "ok": False, "error": "OpenAI create_skill failed"})
                    continue
                new_id = create_result["skill_id"]
                new_version = create_result.get("version")
                desc = description_from_skill_md(skill_md, name)
                if name in ANTHROPICS_SKILL_NAMES:
                    category = "Documents"
                    sort_order = ANTHROPICS_SKILL_NAMES.index(name) + 1
                else:
                    category = "Notis"
                    sort_order = OUR_SKILLS.index(name) + 10
                is_default = name in ANTHROPICS_SKILL_NAMES or name in DEFAULT_OUR_SKILLS
                channel_fields = build_curated_skill_channel_update_fields(
                    channel,
                    skill_md=skill_md or "",
                    openai_skill_version=str(new_version) if new_version is not None else None,
                    source_sha=source_sha,
                    mirror_legacy_production=True,
                )
                if row.get("id"):
                    supabase.table("curated_skills").update({
                        "name": name,
                        "openai_skill_id": new_id,
                        "description": desc,
                        "category": category,
                        "is_default": is_default,
                        "sort_order": sort_order,
                        "required_feature_flag": required_feature_flag,
                        "required_entitlements": required_entitlements,
                        **channel_fields,
                    }).eq("id", row["id"]).execute()
                else:
                    supabase.table("curated_skills").insert({
                        "name": name,
                        "description": desc,
                        "category": category,
                        "openai_skill_id": new_id,
                        "is_default": is_default,
                        "sort_order": sort_order,
                        "required_feature_flag": required_feature_flag,
                        "required_entitlements": required_entitlements,
                        # Base skill_md is NOT NULL; seed it on every channel so a
                        # brand-new skill can be bootstrapped dev/beta-only (without
                        # this, a first-time non-production bootstrap fails). For
                        # --channel production this is redundant with the mirror.
                        "skill_md": skill_md or "",
                        **channel_fields,
                    }).execute()
                results.append({"name": name, "ok": True, "version": new_version})
    finally:
        for p in temp_zips:
            try:
                os.unlink(p)
            except OSError:
                pass
        if anthropics_repo and os.path.isdir(anthropics_repo):
            shutil.rmtree(anthropics_repo, ignore_errors=True)

    failed = [r for r in results if not r.get("ok")]
    if json_output:
        print(json.dumps({"results": results, "failed": len(failed)}))
    else:
        for r in results:
            if r.get("ok"):
                v = r.get("version", " (dry-run)" if dry_run else "")
                print(f"  {r['name']}: ok" + (f" version={v}" if v else ""))
            else:
                print(f"  {r['name']}: failed - {r.get('error', 'unknown')}", file=sys.stderr)
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Skills sync CLI: push skills to OpenAI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    sync_parser = subparsers.add_parser("sync", help="Push skills to OpenAI (create new versions)")
    sync_parser.add_argument(
        "skills",
        nargs="*",
        help=(
            "Skill names to sync (default: all matching skills for the selected source). "
            f"Repo-maintained: {', '.join(OUR_SKILLS) or 'none found'}. "
            "Anthropics: docx, pdf, pptx, xlsx (use --from claude for external)."
        ),
    )
    sync_parser.add_argument(
        "--from",
        dest="from_source",
        choices=("local", "claude"),
        default="local",
        help="For external skills (anthropics): use --from claude to clone repos and sync.",
    )
    sync_parser.add_argument("--json", action="store_true", help="Output JSON summary")
    sync_parser.add_argument("--skills-dir", help="Override skills directory path")
    sync_parser.add_argument("--dry-run", action="store_true", help="Do not push, only show what would be synced")
    sync_parser.add_argument(
        "--channel",
        choices=CURATED_SKILL_CHANNELS,
        required=True,
        help="Curated skill channel to update in Supabase.",
    )
    sync_parser.add_argument(
        "--source-sha",
        help="Git SHA or other source identifier to store alongside the channel sync metadata.",
    )
    sync_parser.add_argument(
        "--skill-ids",
        metavar="name:id,...",
        help="Fallback: map skill name to openai_skill_id when Supabase unavailable",
    )
    sync_parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="Create skills in OpenAI and insert/update curated_skills when openai_skill_id is missing",
    )
    args = parser.parse_args()
    if args.command != "sync":
        return 0
    return asyncio.run(
        run_sync(
            skill_names=args.skills or None,
            from_claude=(args.from_source == "claude"),
            skills_dir=args.skills_dir,
            dry_run=args.dry_run,
            channel=args.channel,
            source_sha=args.source_sha,
            skill_ids_flag=args.skill_ids,
            json_output=args.json,
            bootstrap=args.bootstrap,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
