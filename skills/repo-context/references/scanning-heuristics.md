# Scanning Heuristics

## File Selection

- Track common source files plus operational text/config files.
- Ignore build outputs, vendored dependencies, and `.codex/context/`.
- Allow optional include/exclude globs during `bootstrap`.

## JS/TS Enhanced Parsing

- Parse `import`, `export`, `require`, and dynamic `import()` statements.
- Detect entrypoints from `page.tsx`, `layout.tsx`, `route.ts`, `main.*`, `server.*`, and `package.json`.
- Detect component-like exports when function names are PascalCase.
- Resolve internal imports for relative paths and simple repo-root aliases like `@/`.

## Module Detection

- Generate a module brief when a directory has at least `3` descendant source files.
- Also generate a module brief when a directory contains or nests a detected entrypoint.
- Assign each source file to the nearest qualifying module directory.

## Hotspot Detection

- Mark a file as a hotspot when `LOC > 400`.
- Also mark a file as a hotspot when fan-in or fan-out lands in the top `5%` of source files.
- Carry the exact hotspot reasons into `symbol-map.json` and the file brief.

## Role Classification

- `routing`: `app/`, `pages/`, `routes/`, `api/`
- `ui`: `components/`, `ui/`
- `domain`: `lib/`, `core/`, `services/`, `generators/`
- `scripts`: `scripts/`, `bin/`
- `tests`: `tests/`, `__tests__/`, `*.test.*`
- `docs`: `docs/`, `content/`, markdown-heavy areas
- `config`: repo and tool config files
- `legacy`: path segments or files explicitly labeled `legacy`

## Stability Preference

- Keep summaries deterministic.
- Recompute full scan data, but only rewrite artifacts whose rendered content changed.
