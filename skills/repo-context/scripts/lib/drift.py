"""Drift detection and context directory resolution."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .constants import DEFAULT_CONTEXT_DIRNAME
from .render import expected_doc_paths
from .scanner import scan_repository
from .utils import display_path


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_context_dir(root: Path, out: str | None = None) -> Path:
    configured = out or os.environ.get("REPO_CONTEXT_OUT")
    if configured:
        candidate = Path(configured)
        return candidate if candidate.is_absolute() else root / candidate

    default_dir = root / DEFAULT_CONTEXT_DIRNAME
    return default_dir


def build_drift_report(
    root: Path,
    includes: list[str] | None = None,
    excludes: list[str] | None = None,
    out: str | None = None,
) -> dict:
    context_dir = resolve_context_dir(root, out=out)
    manifest_path = context_dir / "manifest.json"
    symbol_map_path = context_dir / "symbol-map.json"
    if not manifest_path.exists() or not symbol_map_path.exists():
        return {
            "status": "missing",
            "issues": [f"Missing context pack at `{display_path(context_dir, root)}`. Run `repo_context.py bootstrap --root <repo>`."],
            "scan": None,
            "context_dir": context_dir,
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
            issues.append(f"Missing generated artifact: {display_path(context_dir / rel_path, root)}")

    manifest_docs = set(manifest.get("docs", {}).values())
    for rel_path in sorted(manifest_docs):
        if not context_dir.joinpath(rel_path).exists():
            issues.append(f"Manifest points to missing artifact: {display_path(context_dir / rel_path, root)}")

    return {
        "status": "fresh" if not issues else "stale",
        "issues": issues,
        "scan": scan,
        "context_dir": context_dir,
    }
