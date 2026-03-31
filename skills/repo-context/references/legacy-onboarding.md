# Legacy Onboarding

Use this flow when the repository is old, weakly documented, or structurally inconsistent.

## First Pass

1. Run `bootstrap`.
2. Read `repo-map.md` and identify top-level directories, entrypoints, and hotspot files.
3. Read the hottest module brief and hotspot file brief before any implementation file.
4. Use `task-scope` for the actual user request before opening more source files.

## What to Look For

- Mixed responsibilities in single files
- Deprecated or legacy-labeled folders
- Wide fan-in utility files
- High fan-out orchestration files
- Sparse tests around critical entrypoints

## Editing Guardrails

- Assume interface changes in hotspot files have broad impact until proven otherwise.
- Prefer narrow changes plus immediate `refresh` instead of long-lived stale context packs.
- If the repo has generated code or checked-in artifacts, refresh after regeneration before reasoning about architecture again.
