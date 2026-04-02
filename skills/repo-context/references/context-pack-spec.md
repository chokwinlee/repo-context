# Context Pack Spec

## Output Location

Write generated artifacts to a neutral repo-local directory with this strict precedence:

1. `--out`
2. `REPO_CONTEXT_OUT`
3. `<repo>/.repo-context/`

There is no fallback to legacy directories.

## Required Files

- `index.md`: agent entrypoint and read order.
- `repo-map.md`: top-level repo overview, entrypoints, hotspots, and change recipes.
- `modules/*.md`: one brief per detected logical directory.
- `files/*.md`: briefs only for hotspot files.
- `symbol-map.json`: machine-readable file/module graph, hashes, LOC, dependencies, symbols, hotspot flags, and project hints.
- `manifest.json`: generation metadata, thresholds, freshness summary, expected artifact list, and project hints.

## Read Order

1. `index.md`
2. `repo-map.md`
3. Relevant module briefs from `modules/`
4. Relevant hotspot briefs from `files/`
5. Actual source files only after the previous four layers are exhausted

## Content Rules

- Keep markdown summary-first.
- Prefer contracts, entrypoints, dependencies, project markers, and change guidance over implementation detail.
- Do not dump long code excerpts.
- Keep hotspot briefs limited to files that cross the active thresholds.
- Keep generated content deterministic enough that unchanged modules do not rewrite on refresh.

## Freshness Contract

- `manifest.json` and `symbol-map.json` represent the last scanned source snapshot.
- `check` must compare the current repo state against stored hashes.
- `refresh` must rebuild the pack in place and remove stale generated briefs when needed.
