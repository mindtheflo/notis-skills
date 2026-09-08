---
name: notis-desktop-use
description: Use when a task needs to see or control the user's actual Mac desktop — screenshots, reading on-screen UI, clicking, typing, window/menu/app control — through the Peekaboo CLI on the user's local shell.
---

# Notis Desktop Use Skill

Use this skill when a task must operate the user's **real Mac** — capture what
is on screen, inspect a native app's UI, click buttons, type, drive menus, or
move windows. The engine is [Peekaboo](https://peekaboo.sh), a signed,
notarized macOS automation CLI built on a Swift core.

This is **GUI control of the user's own computer**. It is not browser
automation and it is not a sandbox. For web pages use `notis-browser-control`.
For an isolated, reproducible environment use the Vercel Sandbox. Peekaboo
needs the live macOS Aqua session, the screen, and TCC permissions, so it only
runs on the user's `local_shell`.

## Step 0 — Switch to the LOCAL shell FIRST (mandatory)

Peekaboo controls the user's physical Mac, so every command must run on the
**local shell** (the Notis desktop bridge), never the Vercel sandbox. Shell
calls default to `sandbox_shell` — if you skip this step your `peekaboo`
command runs in `/vercel/sandbox`, where Peekaboo does not exist and cannot
touch the Mac.

**Before any `peekaboo` command, call `set_shell_mode` with
`mode: "local_shell"`.**

- If it succeeds, all subsequent shell calls run on the user's Mac. Proceed.
- Your Computer is available on every plan, including Free. If this call
  unexpectedly returns `entitlement_upgrade_required`, report the access-policy
  mismatch and stop; do not turn it into Ultra upgrade guidance. If it returns
  `entitlement_check_unavailable`, ask the user to retry.
- If it returns an error that the Notis desktop app is not connected, tell the
  user to open the Notis desktop app and turn on **Your Computer** (computer
  use) in settings, then stop. Do **not** run `peekaboo` in the sandbox and do
  **not** fall back to the browser tools to fake desktop control.

Never `cd /vercel/sandbox` or assume a sandbox working directory — run
`peekaboo` directly on the local shell.

## Read-only status checks — shortest verified loop

For a named native app, after switching shell mode:

1. Run `peekaboo permissions status --json` once for this session.
   For an inspection of a named app, bring it into view with
   `peekaboo app switch --to "APP NAME" --verify --json` before capture unless
   it is already visibly frontmost. This is navigation within the inspection,
   not permission to edit data. Do not repeatedly capture an unavailable or
   hidden window, or substitute a menu-bar capture for that app's contents.
2. Capture the named app directly: `peekaboo see --app "APP NAME" --json`.
   Request `max_output_length: 200000` on this shell call. Read `data.ui_elements`,
   including static labels with `role: "other"`, and their bounds. Status
   headings can appear near the END of this array, after menus and controls;
   cutting stdout to 30000–50000 characters can silently hide the very status
   text you need. Do not list every running app when the target is known.
3. If those labels establish the requested facts, report them immediately.
   Preserve distinctions between visible status groups and actual running
   agents. State collapsed, off-screen or unverified items explicitly; do not
   infer their status. Inspect further only for a specific missing fact.

Use the command examples here first; consult that command's `--help` if the
installed version rejects a flag or you need an option not shown here. Do not
load the full tool catalog for a simple status check. Avoid duplicate captures
of the same unchanged UI and huge unfiltered JSON dumps.

For smaller text-only inspections, `peekaboo inspect-ui --app-target "APP NAME"
--max-elements 300 --max-depth 20 --json` is available, but its text summary can
omit static status headings. Increasing its depth does not fix that omission.
Notice the different target flags: **`see --app`**, **`inspect-ui --app-target`**.

If accessibility text is insufficient, use the command-and-capture guide.
A successful screenshot command only proves a file was captured: a path in
shell stdout does **not** mean you have seen its pixels. Do not claim visual
verification without an available image-reading tool. Do not use Peekaboo's
`--analyze` as a default workaround; it requires a separately configured AI
provider and adds another model loop. Report any remaining visual limitation.

## Peekaboo is already installed — do not install it

The Notis desktop app installs and manages a pinned Peekaboo for you (it's on
your `PATH`) the moment the user enables computer use. So:

- **Do not** run `brew install`, download releases, or check `~/bin/peekaboo`.
- Just run `peekaboo …` directly once you are on the local shell.

If `peekaboo --version` fails on the local shell, Peekaboo has not finished
installing — tell the user to toggle **Your Computer** off and back on in the
Notis desktop settings (which triggers the install), then retry. Do not try to
install it yourself.

## One plain command per call — no chaining

Run a **single** `peekaboo` invocation per shell call. Do **not** combine it
with `&&`, `||`, `;`, pipes (`|`), redirects, or `cd`. Plain `peekaboo`
commands auto-run on the local shell without an approval prompt; chained or
piped commands lose that and get blocked or prompt the user. Parse output in a
later step with `--json` instead of piping inline.

```bash
# Good — runs immediately:
peekaboo --version
peekaboo see --json

# Bad — chained/piped, will be blocked or prompt:
~/bin/peekaboo --version || peekaboo --version
peekaboo app list --json | python3 -c '...'
```

## Permissions Are Mandatory — Check Before Acting

Peekaboo cannot capture or automate without macOS TCC grants. **Always check
permissions first** and surface missing grants to the user; you cannot grant
them programmatically.

```bash
peekaboo permissions status --json
peekaboo permissions status --all-sources   # compare Bridge host vs local CLI
```

What each capability needs (System Settings → Privacy & Security):

- **Screen Recording** → required for `see`, `image`, and any capture. Enable
  the terminal/IDE/process that runs `peekaboo`. After a Homebrew upgrade,
  re-check that the enabled entry points at the current binary path.
- **Accessibility** → required for clicks, typing, key presses, and window
  control. Enable the same terminals/IDEs.
- **Event Synthesizing** → `peekaboo permissions request-event-synthesizing`
  (add `--no-remote` to request it for the local CLI process). Enables
  process-targeted typing/hotkeys/paste without stealing focus.

If a needed grant is missing, tell the user exactly which toggle to flip and
re-run `peekaboo permissions status --json` before continuing. Do not loop on
failed captures.

### Remote / Background Sessions

On SSH, LaunchAgent, cron, or other background launchd sessions, prefer the
Peekaboo **Bridge** path even when TCC appears granted — CoreGraphics can
report success while returning only the desktop wallpaper or a redacted image.
On remote Macs, Screen Recording may be blocked while clicks and typing still
work through Accessibility; when the target UI is otherwise knowable, continue
with clicks / `inspect-ui` instead of giving up.

## Clicking by coordinates needs `--foreground`

A bare `peekaboo click X,Y` (no target) is **rejected**:
`Background click requires --app/--pid/--window-id or a snapshot; use
--foreground`. So when you click a raw coordinate, focus the window first and
pass `--foreground`:

```bash
peekaboo window focus --app "Dia" --window-id 118166
peekaboo click --coords 672,607 --foreground
```

Prefer clicking by element ID/query when `see`/`inspect-ui` give you one. Use
coordinates only when they don't (see next section).

## Browser / web apps: use screenshots when accessibility is insufficient

Some browser/web-app surfaces expose no useful accessibility text even when
the page is visible. If one targeted inspection is empty or incomplete,
**do not loop on `see`/`inspect-ui`** — switch to an available vision path:

1. Capture the window: `peekaboo image --app "Dia" --window-id <id> --mode window --path /tmp/shot.png --json`
   (get `<id>` from `peekaboo list windows --app "Dia" --json`).
2. Locate the control **visually** in that screenshot.
3. Convert to a screen coordinate: window-capture pixels map to global display
   points offset by the window's top-left origin (from the capture's `bounds` /
   `list windows`). E.g. a window at origin `(0,30)` → image pixel `(672,577)`
   is screen point `(672,607)`.
4. Focus the window and `click --coords X,Y --foreground` (above), then
   re-`image` to confirm the result changed.

Keyboard shortcuts like `space` do **not** reliably control web players (in a
browser, space scrolls the page) — click the actual on-screen play/pause
control instead.

## Safety Rules

- Perform UI actions only within the user's requested task. Read-only inspection
  may focus the named app or expand its read-only status groups, unless the user
  forbids navigation. It does not authorize edits, sends, stopping agents or
  changing settings. Destructive actions need explicit authorization.
- Treat the screen as private. Do not exfiltrate screenshots or on-screen
  content beyond what the task requires, and do not capture and forward
  unrelated windows.
- Avoid actions that trigger irreversible system dialogs (delete confirmations,
  purchases, sends) without explicit user confirmation. When in doubt, capture
  the dialog with `peekaboo dialog list` and ask before clicking.
- Prefer `--no-remote` when testing local TCC behavior; use the Bridge path for
  background/remote captures.

## Anti-Patterns

- Do not run `peekaboo` before calling `set_shell_mode` with `local_shell`. The
  default `sandbox_shell` runs it in `/vercel/sandbox`, where Peekaboo does not
  exist — the command "fails" and looks like a permissions problem when it
  isn't.
- Do not `cd /vercel/sandbox` (or any sandbox path) and do not assume a sandbox
  working directory. Run `peekaboo` directly on the local shell.
- Do not install Peekaboo (no `brew install`, no downloads, no `~/bin` probes).
  The Notis desktop app already installed and manages it on your `PATH`.
- Do not chain `peekaboo` with `&&`, `||`, `;`, pipes, redirects, or `cd`. One
  plain command per call so it auto-runs without prompting.
- Do not bare-coordinate-click (`peekaboo click X,Y`) — it's rejected. Focus the
  window and use `click --coords X,Y --foreground`.
- Do not repeatedly inspect a browser page that exposes no useful accessibility
  text. Use an available image-reading path, or report that limitation.
- Do not rely on `space`/keyboard to play a web video — click the on-screen
  play control.
- Do not skip the permissions check. A missing grant returns wallpaper-only or
  empty captures, not an obvious error.
- Do not reuse element IDs across snapshots, or act without a fresh `see`.
- Use this skill's command examples; consult the relevant command's `--help`
  when an example is rejected or additional flags are needed.
- Do not send unrelated input to the user's machine. Keep navigation within
  the requested inspection; data mutation needs its own authorization.

For command discovery and the screenshot/action loop, read command-and-capture.
Local shell, permissions, fresh screenshots/element IDs, foreground targeting and
user-authorized input remain mandatory regardless of which command you need.

## Task guides

Read only the guide needed for this task from this skill bundle.

- [Command and capture guide](references/command-and-capture.md)
