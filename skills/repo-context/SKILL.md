---
name: repo-context
description: Build and maintain a repo-local progressive context pack for large, legacy, or weakly documented codebases. Use when an agent needs a repo map, hotspot analysis, module/file briefs, legacy-service onboarding, or better context discipline before non-trivial multi-file work and refactors.
---

# Repo Context

Create `.repo-context/` before deep code reads in repositories that are large, stale, or structurally unclear. Prefer the generated context pack over loading many implementation files at once. Override the location with `--out` when your agent runtime or repo convention needs a different directory.

## Workflow

1. Bootstrap if the repo does not have `.repo-context/`.
2. Run `check` before relying on an existing pack.
3. Run `refresh` after meaningful repo edits or when `check` reports drift.
4. Run `task-scope` with the user task before opening large files.
5. Read `index.md`, then `repo-map.md`, then only the relevant module and hotspot briefs.

## Commands

```bash
python3 scripts/repo_context.py bootstrap --root /path/to/repo
python3 scripts/repo_context.py refresh --root /path/to/repo
python3 scripts/repo_context.py check --root /path/to/repo --fail-on-stale
python3 scripts/repo_context.py task-scope --root /path/to/repo --query "add png export to editor"
python3 scripts/repo_context.py bootstrap --root /path/to/repo --out .agent-context/repo-context
```

## Operating Rules

- Always prefer context-pack generation to ad hoc whole-repo reading.
- Treat `index.md` and `repo-map.md` as the default entrypoint for orientation.
- Read hotspot briefs before opening large implementation files.
- Keep writes isolated to `.repo-context/` by default; use `--out` when the target project already has a better artifact or memory directory.
- Use `refresh` after major refactors, codegen, or broad search-and-replace edits.

## References

- Context pack contract and read order: `references/context-pack-spec.md`
- Architecture split and extension model: `references/architecture.md`
- Scanning rules and hotspot heuristics: `references/scanning-heuristics.md`
- First-pass workflow for old services: `references/legacy-onboarding.md`
- Drift, refresh, and CI policy: `references/maintenance-policy.md`
