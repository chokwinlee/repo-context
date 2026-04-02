---
name: repo-context
description: Build and maintain a repo-local progressive context pack for large, legacy, or weakly documented codebases, especially when plain file discovery may miss relevant paths behind `.gitignore`. Use when an agent needs a repo map, hotspot analysis, module/file briefs, legacy-service onboarding, or better context discipline before non-trivial multi-file work and refactors.
---

# Repo Context

Create `.repo-context/` before deep code reads in repositories that are large, stale, or structurally unclear. Prefer the generated context pack over loading many implementation files at once.

Context location precedence is strict:

1. `--out`
2. `REPO_CONTEXT_OUT`
3. `<repo>/.repo-context/`

Do not infer or reuse any legacy fallback directory.

## Gitignore Caveat

Bare `rg`, `rg --files`, and many host file pickers respect `.gitignore`. That is the wrong default when important implementation files live in generated, vendored, or otherwise gitignored paths.

- For repo-wide discovery, prefer `repo_context.py` as the source of truth instead of ad hoc file listing.
- If you must inspect raw files before the context pack exists, use `rg -uu` or an equivalent no-ignore mode, not bare `rg`.
- The main repo-context scan intentionally looks past root `.gitignore` for context inputs, while project-local analyzer auto-discovery under `repo-context/analyzers/` still honors ignored paths.

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
python3 scripts/post_edit_refresh.py --root /path/to/repo --file /path/to/edited-file
```

## Hook Automation

- If the host supports post-edit command hooks, wire `scripts/post_edit_refresh.py` to every code write.
- Prefer post-edit hooks over Git hooks when you need refreshes after each modification, not only at commit time.
- `post_edit_refresh.py` may run after every edit because rendering already avoids rewriting unchanged artifacts.

## Operating Rules

- Always prefer context-pack generation to ad hoc whole-repo reading.
- Never rely on bare `rg` or `rg --files` for repo inventory; they usually hide `.gitignore`d paths.
- When the host supports hooks, attach `post_edit_refresh.py` to edit/write events so the pack stays fresh automatically.
- Treat `index.md` and `repo-map.md` as the default entrypoint for orientation.
- Read hotspot briefs before opening large implementation files.
- Keep writes isolated to `.repo-context/` by default; use `--out` when the target project already has a better artifact or memory directory.
- Use `refresh` after major refactors, codegen, or broad search-and-replace edits.
- Use `rg -uu` for one-off raw searches when you need files that normal repo discovery would hide.

## References

- Context pack contract and read order: `references/context-pack-spec.md`
- Architecture split and extension model: `references/architecture.md`
- Scanning rules and hotspot heuristics: `references/scanning-heuristics.md`
- First-pass workflow for old services: `references/legacy-onboarding.md`
- Drift, refresh, and CI policy: `references/maintenance-policy.md`
