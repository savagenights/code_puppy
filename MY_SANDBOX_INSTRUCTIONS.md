# MY_SANDBOX_INSTRUCTIONS.md
Last updated: February 26, 2026

## Purpose of this file
This document explains the exact setup of this forked repository of Code Puppy.
Any agent / developer / future instance working on this project **must read this file first** before making changes, running code, or proposing modifications.

The goal is to keep personal modifications isolated in the `my-sandbox` branch while being able to easily pull in upstream improvements without losing our work.

## Repository basics

- Original repo (upstream): https://github.com/mpfaffenberger/code_puppy
- Our fork (origin):      https://github.com/savagenights/code_puppy
- Local clone path:       E:\_Agentic\code-puppy
- Current branch for all personal work: **my-sandbox**
- Main branch purpose:    Clean mirror of upstream/main (never commit personal work here)

## Current branch state (as of last setup)

- `main`
  - Tracks upstream/main
  - Reset to exactly match upstream commit: 0ff7784 chore: bump version [ci skip]
  - No local commits on main anymore (destructive state was reset)
  - Pushed and up-to-date with origin/main

- `my-sandbox`
  - Created from a clean main after reset
  - Pushed to origin/my-sandbox
  - This is the **only branch** where we should make changes, experiments, custom agents, prompt modifications, feature removals, tool additions, etc.

## Git remotes configuration

origin    https://github.com/savagenights/code_puppy.git (fetch/push)
upstream  https://github.com/mpfaffenberger/code_puppy.git (fetch only)

## Safe sync workflow (must follow this exact sequence)

1. Update main from upstream
   git checkout main
   git fetch upstream
   git reset --hard upstream/main
   git push origin main --force-with-lease

2. Bring upstream changes into sandbox
   git checkout my-sandbox
   git rebase main
   # resolve conflicts → keep our intentional changes where they conflict
   git push origin my-sandbox --force-with-lease

One-liner version (copy-paste friendly):
git fetch upstream && git checkout main && git reset --hard upstream/main && git push origin main --force-with-lease && git checkout my-sandbox && git rebase main

## Running Code Puppy

Two main ways (use the second one when testing our modifications):

A. Run published version (ignores local changes)
   uvx code-puppy
   # or with interactive setup
   uvx code-puppy -i

B. Run our local modified version (what we want most of the time)
   uv sync                # if dependencies changed
   uv run code-puppy
   # or
   uv run code-puppy -i

## Development rules inside this fork

1. NEVER commit directly to main (except trivial sync commits — but even those are discouraged)
2. ALWAYS be on my-sandbox (or a feature branch off my-sandbox) when editing code
3. Use VS Code with folder E:\_Agentic\code-puppy open
4. After any significant change → commit with clear message → push to origin/my-sandbox
5. Before pushing destructive changes (deletions, renames), double-check git status & diff
6. API keys: set as environment variables (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.) or add via /add_model inside the TUI

## History of destructive events (lessons learned)

- At one point almost the entire codebase appeared deleted in working tree (hundreds of files shown as deleted in git status)
- Cause: unknown — possibly accidental bulk rm, git rm -r, or bad reset/checkout
- Resolution: git reset --hard upstream/main + git clean -fd
- Lesson: always verify git status before force-pushing or running aggressive commands

## Goal for modifications

We are using this fork as a **personal sandbox** to:
- Experiment with custom agents / prompts / tools
- Possibly remove unused features
- Add new capabilities
- Test new LLM providers / routing logic
- Keep everything upgradable from upstream

Any agent reading this should assume:
- We want to stay reasonably close to upstream long-term
- But preserve our customizations during rebases/merges
- Conflict resolution priority: keep our version when we intentionally changed something

Happy hacking — protect the sandbox!