# Maintenance Policy

## When to Refresh

- After major feature work spanning multiple modules
- After refactors, codegen, migrations, or file moves
- After editing a hotspot file
- When `check` reports drift

## CI / Review Use

- Use `python3 "$RCE" check --root <repo> --fail-on-stale` in CI or pre-review checks when the repo adopts this skill.
- Treat stale context as a review signal, not only a local convenience issue.

## Hook Use

- For immediate refresh after every code write, use a host-level post-edit hook that runs `scripts/post_edit_refresh.py`.
- Git hooks are a weaker fallback. They help at `pre-commit`, `post-merge`, or `post-checkout`, but they do not fire after every local file save.
- The current refresh model recomputes scan data globally, then rewrites only the generated artifacts whose rendered content changed.

## Drift Signals

- New tracked files
- Deleted tracked files
- Changed hashes
- Missing generated briefs
- Manifest references that no longer resolve

## Manual Forward Test

When subagent use is allowed, forward-test with a fresh thread using a prompt like:

`Use $repo-context to orient in this repository and propose a safe implementation plan for <task>.`

Do not leak intended answers. The point is to verify that the context pack is sufficient on its own.
