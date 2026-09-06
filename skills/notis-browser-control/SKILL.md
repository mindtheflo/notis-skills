---
name: notis-browser-control
description: Use when a task needs browser automation through agent-browser in either a local shell or the Vercel Sandbox, and when the agent must choose the right runtime for that browser work.
---

# Notis Browser Control Skill

Use this skill when a task needs browser automation and the right answer is to
drive a browser with `agent-browser`.

This skill routes to on-demand browser guidance and preserves
Notis-specific runtime rules for:

1. `local_shell` browser control on the user's computer
2. `sandbox_shell` browser control in the Vercel Sandbox

## Core Runtime Rule

Browser automation is a shell workflow.

- Use `sandbox_shell` when the browser can live in the Vercel Sandbox.
- Use `local_shell` when the browser must live on the user's computer.
- There is no visible desktop-control fallback. If Agent Browser cannot access
  the needed local browser session, explain the limitation and ask the user to
  expose the session through the supported local-shell browser workflow.

## Runtime Selection

The browser-control skill and the local `set_shell_mode` path are available on
every plan, including Free. The local path still needs a connected Notis
Desktop bridge. Cloud execution separately needs a server-authorized hosted
runtime; if that runtime is unavailable, keep the local path available and
surface the returned runtime guidance exactly.

Choose `sandbox_shell` when:

- the site is public or can be tested with dedicated credentials
- the task does not need the user's local browser profile, tabs, cookies, or
  extensions
- isolation and reproducibility are more important than the user's current
  browser session
- you are testing a web flow, taking screenshots, extracting content, or running
  a repeatable QA pass

Choose `local_shell` when:

- the task needs the user's actual local browser state
- the task depends on local cookies, local auth, local extensions, or a local
  browser profile
- you need to use profiles discovered on the user's computer
- the browser work must happen on the user's computer rather than in an isolated
  sandbox

## Difference Between Local And Sandbox Browser Control

Local shell browser control:

- runs on the user's actual computer
- uses the persistent `~/.notis-agent-browser/main` profile
- reuses cookies + saved state across runs
- depends on the Notis desktop shell bridge being connected

Sandbox shell browser control:

- runs in an isolated Vercel Sandbox
- starts cookie-empty on every run
- cannot access the user's real browser profile, host keychain, local
  cookies, local tabs, or local extensions
- authenticates per run via the 1Password Service Account flow, a
  per-task credential, or a state file uploaded into the sandbox
- is safer and more reproducible for general web automation
- is the default for repeatable QA, scraping, screenshots, and public app tests

## Anti-Patterns

- Do not invent ad-hoc profile paths. Every Notis run uses
  `~/.notis-agent-browser/main`.
- Do not run any `agent-browser` command without `--profile`. The daemon may
  silently restart with a different empty profile.
- Do not skip `agent-browser state save` at the end of an automation run,
  or immediately after the user signs in.
- Do not drive the user's real Chrome profile, copy their default profile,
  or connect to `9222` against their main browser. Chrome 136+ blocks it
  anyway and it endangers their live session.
- Do not assume a sandbox browser can access local auth state.
- Do not skip `agent-browser skills get core --full` before using the CLI.

Read profile-and-state before browser startup; preserve the canonical profile and
final state save. Then load the local or sandbox guide, never both by default.
Use live CLI help for command syntax instead of loading generic examples unnecessarily.

## Task guides

Read only the guide needed for this task from this skill bundle.

- [Embedded Agent Browser Skill](references/browser-help.md)
- [Canonical Notis Profile And State Persistence](references/profile-and-state.md)
- [Local Shell Browser Control](references/local-browser.md)
- [Sandbox Shell Browser Control](references/sandbox-browser.md)
