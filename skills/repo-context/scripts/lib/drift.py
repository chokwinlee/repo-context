"""Drift detection for generated context packs."""

from __future__ import annotations

import json
from pathlib import Path

from .render import expected_doc_paths
from .scanner import scan_repository


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_drift_report(root: Path, includes: list[str] | None = None, excludes: list[str] | None = None) -> dict:
    context_dir = root / ".codex" / "context"
    manifest_path = context_dir / "manifest.json"
    symbol_map_path = context_dir / "symbol-map.json"
    if not manifest_path.exists() or not symbol_map_path.exists():
        return {
            "status": "missing",
            "issues": ["Missing context pack. Run `repo_context.py bootstrap --root <repo>`."],
            "scan": None,
        }

    scan = scan_repository(root, includes=includes, excludes=excludes)
    manifest = _load_json(manifest_path)
    symbol_map = _load_json(symbol_map_path)
    issues: list[str] = []

    current_files = scan["files"]
    previous_files = symbol_map.get("files", {})
    for path in sorted(current_files):
        if path not in previous_files:
            issues.append(f"New tracked file without refreshed context: {path}")
            continue
        if current_files[path]["sha256"] != previous_files[path].get("sha256"):
            issues.append(f"Changed file since last context refresh: {path}")
    for path in sorted(previous_files):
        if path not in current_files:
            issues.append(f"Deleted tracked file still present in context pack: {path}")

    expected_docs = set(expected_doc_paths(scan).values()) | {"manifest.json", "symbol-map.json"}
    for rel_path in sorted(expected_docs):
        if not context_dir.joinpath(rel_path).exists():
            issues.append(f"Missing generated artifact: .codex/context/{rel_path}")

    manifest_docs = set(manifest.get("docs", {}).values())
    for rel_path in sorted(manifest_docs):
        if not context_dir.joinpath(rel_path).exists():
            issues.append(f"Manifest points to missing artifact: .codex/context/{rel_path}")

    return {
        "status": "fresh" if not issues else "stale",
        "issues": issues,
        "scan": scan,
    }
