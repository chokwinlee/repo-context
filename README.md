# repo-context

`repo-context` is a reusable workflow for code agents working in large, legacy, or weakly documented repositories. It generates and maintains a progressive context pack under `.codex/context/` so an agent can orient quickly, avoid reading the whole repo at once, and keep its architectural context fresh during multi-file work.

This repository currently ships the workflow in a Codex-compatible skill layout, but the underlying model is agent-agnostic: bootstrap repo knowledge, read summaries first, scope the task, then read source deeply only where necessary.

## Why This Exists

Large repositories often degrade agent quality in predictable ways:

- too many large files get pulled into context at once
- architecture knowledge only exists in code, not in reusable summaries
- legacy services require repeated rediscovery before every change
- multi-file refactors invalidate earlier context and increase hallucination risk

`repo-context` addresses that by creating a repo-local knowledge layer before deep code reads.

## What It Creates

For any target repository, the skill writes a context pack under `.codex/context/`:

```text
.codex/context/
├── index.md
├── repo-map.md
├── modules/*.md
├── files/*.md
├── symbol-map.json
└── manifest.json
```

This gives the agent:

- a repo map before implementation reads
- logical module briefs for important directories
- hotspot file briefs for oversized or high-fan-in/fan-out files
- drift detection after source changes
- task scoping for feature work and bugfixes

## Best For

- onboarding into an unfamiliar codebase
- planning multi-file feature work
- legacy-service tracing and safe change scoping
- keeping architectural context fresh during refactors
- reducing prompt bloat before coding

## Agent Model

`repo-context` is designed around a generic code-agent loop:

1. bootstrap repo knowledge
2. read the repo map and module briefs before deep source reads
3. scope the current task to a small set of modules and files
4. refresh the context pack after meaningful code changes

If your agent platform supports skills, tools, prompts, rules, or repo-local knowledge packs, this workflow can be adapted directly.

## Install

This repository is packaged today as a Codex-compatible skill, but the scripts and references can also be reused in other agent systems.

### Option 1: Install From This GitHub Repo

If you use Codex and already have the built-in skill installer helpers:

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo chokwinlee/repo-context \
  --path skills/repo-context
```

### Option 2: Manual Install

```bash
export CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
mkdir -p "$CODEX_HOME/skills"
cp -R skills/repo-context "$CODEX_HOME/skills/repo-context"
```

Restart Codex after installing the skill.

## Use With A Code Agent

The generic usage pattern is:

```text
1. bootstrap the repository context
2. ask the agent to scope the task against that context
3. open only the recommended modules and files
4. refresh after broad edits
```

Example prompts:

- `Bootstrap repo context for this repository, then tell me which modules matter for adding Stripe billing.`
- `Refresh repo context, then scope a fix for the legacy reporting endpoint.`
- `Before planning a refactor of the export pipeline, generate a repo map and hotspot briefs.`

If you are using Codex specifically, you can invoke the packaged skill directly:

```text
Use $repo-context on /path/to/repo first, then scope the task: add PNG export to the editor.
```

## CLI Quick Start

```bash
python3 skills/repo-context/scripts/repo_context.py bootstrap --root /path/to/repo
python3 skills/repo-context/scripts/repo_context.py check --root /path/to/repo --fail-on-stale
python3 skills/repo-context/scripts/repo_context.py task-scope --root /path/to/repo --query "add png export to the editor"
python3 skills/repo-context/scripts/repo_context.py refresh --root /path/to/repo
```

## Repository Layout

```text
repo-context/
├── README.md
├── .gitignore
└── skills/
    └── repo-context/
        ├── SKILL.md
        ├── agents/openai.yaml
        ├── scripts/
        ├── references/
        └── assets/
```

The concrete packaged skill lives at `skills/repo-context`, but the scripts, references, and context-pack workflow are intended to be portable across agent runtimes.

## Validate Locally

```bash
python3 skills/repo-context/scripts/test_repo_context.py
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/repo-context
```

## Current Scope

`repo-context` is optimized for JS/TS repositories first, but it still works on mixed or legacy codebases via language-agnostic scanning, hotspot detection, and repo-structure analysis.
