# Command and capture guide

## Start Here — Load The Live Tool Surface

For the short native status-check loop, use the examples in SKILL.md. For
unfamiliar operations, Peekaboo's CLI is the source of truth; load only the
relevant command's help before expanding to the full catalog:

```bash
peekaboo <command> --help
peekaboo tools          # broader catalog when the needed command is unknown
peekaboo learn          # full guide only for complex/unfamiliar workflows
```

Most commands support `--json` (alias `--json-output`) for machine parsing —
**prefer it** when you need to act on the result. They share a snapshot cache,
so capture once and reuse snapshot IDs.

## Core Loop: See → Act → Re-see

```bash
# 1. Capture an annotated UI map with element IDs (and a snapshot ID).
peekaboo see --json

# 2. Act on a target by element ID, query, or coordinates.
peekaboo click "Save"        # by query/label
peekaboo type "hello world"  # send text
peekaboo hotkey cmd,s        # modifier combo in one shot

# 3. Re-capture before the next decision — IDs are per-snapshot and the screen
#    changes after every action.
peekaboo see --json
```

Re-`see` after navigation, dialogs, app switches, or any dynamic re-render.
Treat stale element IDs as invalid.

## Command Map

Run `peekaboo learn` / `peekaboo <command> --help` for authoritative flags.

- **Vision & capture:** `see` (annotated UI map + snapshot IDs, optional AI
  analysis), `image` (raw PNG/JPG of screen/window/menubar, `--analyze`),
  `capture` (live/long-running), `list apps|windows|screens|menubar|permissions`.
- **Interaction:** `click`, `type` (`--clear`, `--delay`), `press`, `hotkey`,
  `paste` (atomic clipboard set → Cmd+V → restore), `scroll`, `swipe`, `drag`,
  `move`.
- **Windows / menus / apps / spaces:** `window` (close/minimize/maximize/move/
  resize/focus/list), `space` (list/switch/move-window), `menu`, `menubar`,
  `app` (launch/quit/relaunch/hide/switch/list, `--open <url|path>`), `open`,
  `dock`, `dialog` (click/input/file/dismiss/list).
- **Automation & integration:** `agent` (natural-language automation with
  dry-run planning + resume), `inspect-ui` (accessibility-tree inspection with
  no screenshot), `run` (`.peekaboo.json` scripts), `sleep`, `clean`, `config`,
  `daemon`, `mcp`.

For structured multi-step flows, orchestrate commands inside a
`.peekaboo.json` script run via `peekaboo run --output ...`, rather than
chaining many shell calls.
