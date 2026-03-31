# repo-context

`repo-context` is a portable skill for code agents working in large, legacy, or weakly documented repositories.

It builds a repo-local context pack so an agent can orient itself, scope work before deep file reads, and refresh that knowledge after code changes.

## Compatibility

This repository follows the open [`SKILL.md`](https://github.com/anthropics/agent-skills-standard) pattern used across modern agent tooling. The packaged skill is designed to be usable anywhere that supports repository-scoped skills or promptable skill folders.

It is intended for tools and directories that support portable skills, including Agent Skills Standard-compatible environments and similar agent runtimes.

## Included Skill

| Skill | Description |
| --- | --- |
| `repo-context` | Build and maintain a progressive repo context pack with repo maps, module briefs, hotspot briefs, drift checks, and task scoping. |

## What It Generates

By default, `repo-context` writes a progressive context pack to `.repo-context/` inside the target repository:

```text
.repo-context/
├── index.md
├── repo-map.md
├── modules/*.md
├── files/*.md
├── symbol-map.json
└── manifest.json
```

The output directory can be overridden with `--out` when the host agent or project already has a preferred memory or artifacts directory.

## Why It Exists

Large repositories usually break agent quality in the same ways:

- too many implementation files get loaded at once
- architecture knowledge only exists in code, not reusable summaries
- legacy services have to be rediscovered before every change
- multi-file refactors make earlier context stale

`repo-context` adds a lightweight knowledge layer before implementation reads so agents can work progressively instead of reading the whole repository up front.

## When To Use It

- onboarding into an unfamiliar codebase
- planning non-trivial multi-file work
- tracing legacy services before changes
- generating a repo map or hotspot analysis
- refreshing architecture context during refactors

## Installation

### Skills CLI

```bash
npx skills add chokwinlee/repo-context --skill repo-context
```

### Manual

Copy `skills/repo-context/` into the local or project skill directory used by your agent.

```bash
git clone https://github.com/chokwinlee/repo-context.git
cp -R repo-context/skills/repo-context /path/to/<agent-skills-dir>/repo-context
```

## Usage

Typical workflow:

1. bootstrap repository context
2. check whether the pack is stale
3. scope the task against the generated map and briefs
4. read only the recommended modules and files
5. refresh after broad edits

Example prompts:

- `Bootstrap repo context for this repository, then tell me which modules matter for adding Stripe billing.`
- `Refresh repo context, then scope a fix for the legacy reporting endpoint.`
- `Before planning a refactor of the export pipeline, generate a repo map and hotspot briefs.`

## CLI Quick Start

```bash
python3 skills/repo-context/scripts/repo_context.py bootstrap --root /path/to/repo
python3 skills/repo-context/scripts/repo_context.py check --root /path/to/repo --fail-on-stale
python3 skills/repo-context/scripts/repo_context.py task-scope --root /path/to/repo --query "add png export to the editor"
python3 skills/repo-context/scripts/repo_context.py refresh --root /path/to/repo
python3 skills/repo-context/scripts/repo_context.py bootstrap --root /path/to/repo --out .agent-context/repo-context
```

## Repository Layout

```text
repo-context/
├── README.md
└── skills/
    └── repo-context/
        ├── SKILL.md
        ├── agents/openai.yaml
        ├── scripts/
        └── references/
```

The published skill lives at `skills/repo-context`.

## Local Validation

```bash
python3 skills/repo-context/scripts/test_repo_context.py
python3 -m py_compile skills/repo-context/scripts/repo_context.py skills/repo-context/scripts/test_repo_context.py skills/repo-context/scripts/lib/*.py
```

## Current Scope

`repo-context` is optimized for JS/TS repositories first, but it still works on mixed or legacy codebases through language-agnostic scanning, hotspot detection, and repo-structure analysis.

## License

MIT
