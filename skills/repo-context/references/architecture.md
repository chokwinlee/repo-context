# Architecture

`repo-context` is organized around a generic scan pipeline with optional analyzers.

## Layers

1. File inventory
   - Select tracked files.
   - Main scan does not use root `.gitignore` as a hard exclusion layer.
   - Hash contents.
   - Record LOC, language, and coarse role hints.

2. Analyzer pass
   - Per-file analyzers may add symbols, dependency edges, entrypoint hints, and project markers.
   - Repo-level analyzers may add project hints from manifests and file patterns.
   - Analyzer output is additive; the core pipeline should still function when no analyzer recognizes a file.
   - The default implementation is a registry.
   - The registry auto-loads project-local analyzers from `repo-context/analyzers/`.
   - Discovery respects ignore rules: built-in ignored directories plus root `.gitignore`.

3. Structural synthesis
   - Detect modules from directory density and entrypoint placement.
   - Compute fan-in, fan-out, hotspots, and adjacent modules.
   - Preserve deterministic ordering so refreshes only rewrite changed artifacts.

4. Rendering contract
   - Render `index.md`, `repo-map.md`, `modules/*.md`, and hotspot briefs from the same generic scan model.
   - Emit `symbol-map.json` and `manifest.json` for machine-readable reuse and freshness checks.

## Design Rules

- Keep the core model language-neutral: prefer `symbols`, `dependencies`, `project_hints`, and `project_markers` over ecosystem-specific names.
- Put language or framework assumptions behind analyzers, not inside module detection or rendering.
- Unknown ecosystems should still get useful context through structure, roles, hotspots, and repo topology.
- Add new analyzers by extending the analyzer layer, not by branching the renderer or CLI behavior.

## Extension Pattern

```python
from pathlib import Path

from lib.analyzers import FileAnalysis

class MyFileAnalyzer:
    name = "my-file-analyzer"

    def supports(self, path: Path) -> bool:
        return path.suffix == ".py"

    def analyze(self, root: Path, path: Path, rel_path: str, text: str, known_files: set[str]) -> FileAnalysis:
        return FileAnalysis(symbols=["custom_symbol"])


def register(registry) -> None:
    registry.register_file_analyzer(MyFileAnalyzer())
```

Save that module under `repo-context/analyzers/` and `scan_repository()` will load it automatically unless the file or directory is ignored.
