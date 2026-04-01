# Scanning Heuristics

## File Selection

- Track common source files plus operational text/config files.
- Ignore build outputs, vendored dependencies, and generated context directories such as `.repo-context/`.
- Allow optional include/exclude globs during `bootstrap`.

## Analyzer-Driven Hints

- Keep the scan core language-agnostic; analyzer modules may add symbols, dependency edges, entrypoint hints, or project hints.
- Auto-discover project analyzers from `repo-context/analyzers/`.
- Skip analyzer files inside ignored areas such as `.git/`, `.venv/`, `node_modules/`, build output folders, and root `.gitignore` matches.
- Advanced callers can still inject a custom registry directly when they need non-default composition.
- Built-in analyzers currently cover JS/TS, Python, and Ruby source files.
- Manifest and lockfile analyzers add repo-level hints from files such as `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, `Gemfile`, and `composer.json`.
- Unknown languages still participate in role detection, module grouping, hotspot scoring, and drift checks.

## Built-In Language Rules

- JS/TS: parse `import`, `export`, `require`, and dynamic `import()` statements; detect component-like symbols when function names are PascalCase; resolve relative paths and simple repo-root aliases like `@/`.
- Python: parse top-level functions/classes and import statements; resolve relative imports and common package paths.
- Ruby: parse `require`/`require_relative`, plus top-level class/module/method declarations.

## Module Detection

- Generate a module brief when a directory has at least `3` descendant source files.
- Also generate a module brief when a directory contains or nests a detected entrypoint.
- Assign each source file to the nearest qualifying module directory.

## Hotspot Detection

- Mark a file as a hotspot when `LOC > 400`.
- Also mark a file as a hotspot when fan-in or fan-out lands in the top `5%` of source files.
- Carry the exact hotspot reasons into `symbol-map.json` and the file brief.

## Role Classification

- `api`: `api/`, `handlers/`, `controllers/`, `endpoints/`
- `routing`: `app/`, `pages/`, `routes/`, `router/`
- `ui`: `components/`, `ui/`, `views/`, `templates/`
- `domain`: `lib/`, `core/`, `services/`, `internal/`, `pkg/`, `models/`
- `scripts`: `scripts/`, `bin/`, `tools/`, `hack/`
- `tests`: `tests/`, `spec/`, `__tests__/`, `*.test.*`, `*.spec.*`
- `docs`: `docs/`, `content/`, markdown-heavy areas
- `config`: repo manifests, tool config files, CI folders, and root runtime config
- `legacy`: path segments or files explicitly labeled `legacy`

## Stability Preference

- Keep summaries deterministic.
- Recompute full scan data, but only rewrite artifacts whose rendered content changed.
