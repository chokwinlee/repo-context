# repo-context

Publishable repository for the `repo-context` Codex skill.

## What It Does

`repo-context` generates and maintains a repo-local progressive context pack under `.codex/context/` so an agent can:

- bootstrap architecture context before deep code reads
- detect hotspot files and logical modules
- scope feature work to a small set of relevant files
- check for stale context after source changes
- refresh only the affected generated artifacts

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

The actual skill lives at `skills/repo-context`.

## Local Validation

```bash
python3 skills/repo-context/scripts/test_repo_context.py
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/repo-context
```

## Local Usage

```bash
python3 skills/repo-context/scripts/repo_context.py bootstrap --root /path/to/repo
python3 skills/repo-context/scripts/repo_context.py check --root /path/to/repo --fail-on-stale
python3 skills/repo-context/scripts/repo_context.py task-scope --root /path/to/repo --query "add png export to the editor"
python3 skills/repo-context/scripts/repo_context.py refresh --root /path/to/repo
```

## Publishing Notes

- Push this repository to GitHub or another git host.
- Install from the skill path `skills/repo-context`.
- The repository is intentionally single-skill and does not add extra files inside the skill folder beyond the required publishing assets already present there.
