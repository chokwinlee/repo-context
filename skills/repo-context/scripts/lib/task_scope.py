"""Task scoping helpers built on top of a fresh context pack."""

from __future__ import annotations

import json
from pathlib import Path

from .utils import tokenize


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_task_scope(root: Path, query: str) -> dict:
    context_dir = root / ".codex" / "context"
    symbol_map = _load_json(context_dir / "symbol-map.json")
    query_tokens = tokenize(query)
    modules = symbol_map.get("modules", {})
    files = symbol_map.get("files", {})

    module_scores: list[tuple[float, str]] = []
    for module_path, module in modules.items():
        searchable = " ".join(
            [
                module_path,
                module.get("role", ""),
                " ".join(module.get("files", [])),
                " ".join(module.get("exports", [])),
            ]
        ).lower()
        score = 0.0
        for token in query_tokens:
            if token in module_path.lower():
                score += 5
            if token in searchable:
                score += 2
        score += len(module.get("entrypoints", [])) * 0.2
        score += len(module.get("hotspots", [])) * 0.1
        if score > 0:
            module_scores.append((score, module_path))

    if not module_scores:
        module_scores = [
            (module.get("total_loc", 0), module_path)
            for module_path, module in modules.items()
        ]

    module_scores.sort(key=lambda item: (-item[0], item[1]))
    top_modules = [module_path for _, module_path in module_scores[:5]]

    file_scores: list[tuple[float, str]] = []
    for file_path, file_record in files.items():
        if file_record.get("module") not in top_modules and not file_record.get("hotspot"):
            continue
        searchable = " ".join(
            [
                file_path,
                file_record.get("role", ""),
                " ".join(file_record.get("exports", [])),
                " ".join(file_record.get("internal_imports", [])),
            ]
        ).lower()
        score = 0.0
        for token in query_tokens:
            if token in file_path.lower():
                score += 4
            if token in searchable:
                score += 1.5
        score += file_record.get("fan_in", 0) * 0.1
        score += file_record.get("fan_out", 0) * 0.05
        if score > 0:
            file_scores.append((score, file_path))

    if not file_scores:
        file_scores = [
            (files[file_path].get("loc", 0), file_path)
            for file_path in files
            if files[file_path].get("module") in top_modules
        ]

    file_scores.sort(key=lambda item: (-item[0], item[1]))
    top_files = [file_path for _, file_path in file_scores[:8]]
    return {
        "query": query,
        "tokens": query_tokens,
        "modules": top_modules,
        "files": top_files,
    }
