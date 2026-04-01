"""Repository scanner with a generic core and registry-driven analyzers."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .analyzers import AnalyzerRegistry, prepare_analyzer_registry
from .constants import (
    CONFIG_SUFFIXES,
    FAN_PERCENTILE,
    HOTSPOT_LOC_THRESHOLD,
    IGNORED_DIRS,
    IGNORED_FILES,
    MODULE_SOURCE_THRESHOLD,
    PROJECT_MARKER_NAMES,
    ROLE_DESCRIPTIONS,
    SOURCE_EXTENSIONS,
    TRACKED_EXTENSIONS,
)
from .utils import count_loc, rel_posix, sha256_text, stable_sorted, tokenize, top_bucket_threshold


def _matches_any(rel_path: str, patterns: Iterable[str]) -> bool:
    return any(Path(rel_path).match(pattern) for pattern in patterns)


def should_track(path: Path, root: Path, includes: list[str] | None, excludes: list[str] | None) -> bool:
    if any(part in IGNORED_DIRS for part in path.parts):
        return False
    if path.name in IGNORED_FILES:
        return False
    rel_path = rel_posix(path, root)
    if excludes and _matches_any(rel_path, excludes):
        return False
    if includes:
        return _matches_any(rel_path, includes)
    if path.suffix.lower() in TRACKED_EXTENSIONS:
        return True
    return path.name in PROJECT_MARKER_NAMES or path.name.endswith(CONFIG_SUFFIXES)


def detect_language(path: Path) -> str:
    if path.name == "Dockerfile":
        return "docker"
    if path.name == "Makefile":
        return "make"
    if path.suffix.lower() == ".gradle" or path.name.endswith(".gradle.kts"):
        return "gradle"
    suffix = path.suffix.lower()
    return {
        ".c": "c",
        ".cc": "cpp",
        ".cfg": "config",
        ".cjs": "javascript",
        ".conf": "config",
        ".cpp": "cpp",
        ".cs": "csharp",
        ".css": "css",
        ".env": "config",
        ".go": "go",
        ".html": "html",
        ".ini": "config",
        ".java": "java",
        ".js": "javascript",
        ".json": "json",
        ".jsx": "javascript",
        ".kt": "kotlin",
        ".kts": "kotlin",
        ".lock": "lockfile",
        ".m": "objective-c",
        ".md": "markdown",
        ".mdx": "mdx",
        ".mjs": "javascript",
        ".php": "php",
        ".properties": "config",
        ".py": "python",
        ".rb": "ruby",
        ".rs": "rust",
        ".scala": "scala",
        ".scss": "scss",
        ".sh": "shell",
        ".sql": "sql",
        ".swift": "swift",
        ".toml": "toml",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".txt": "text",
        ".xml": "xml",
        ".yaml": "yaml",
        ".yml": "yaml",
    }.get(suffix, "text")


def detect_role(rel_path: str) -> str:
    parts = rel_path.lower().split("/")
    file_name = parts[-1]
    if "legacy" in parts or "legacy" in file_name or "deprecated" in parts:
        return "legacy"
    if "test" in file_name or "spec" in file_name or "__tests__" in parts or any(part in {"tests", "spec", "specs"} for part in parts):
        return "tests"
    if any(part in {"api", "controllers", "endpoints", "handlers"} for part in parts):
        return "api"
    if any(part in {"app", "pages", "route", "routes", "router"} for part in parts):
        return "routing"
    if any(part in {"components", "templates", "ui", "views"} for part in parts):
        return "ui"
    if any(part in {"core", "domain", "internal", "lib", "models", "pkg", "services"} for part in parts):
        return "domain"
    if any(part in {"bin", "hack", "scripts", "tools"} for part in parts):
        return "scripts"
    if any(part in {"content", "docs"} for part in parts) or file_name.endswith(".md"):
        return "docs"
    if any(part in {"data", "fixtures", "migrations", "seed"} for part in parts):
        return "data"
    if (
        file_name in PROJECT_MARKER_NAMES
        or file_name.endswith(CONFIG_SUFFIXES)
        or file_name in {"Dockerfile", "Makefile", "Procfile"}
        or any(part in {".github", ".circleci", "config"} for part in parts)
    ):
        return "config"
    return "unknown"


def scan_repository(
    root: Path,
    includes: list[str] | None = None,
    excludes: list[str] | None = None,
    registry: AnalyzerRegistry | None = None,
    discover_project_analyzers: bool = True,
) -> dict:
    root = root.resolve()
    analyzer_registry = prepare_analyzer_registry(root, registry=registry, discover_local=discover_project_analyzers)
    files: dict[str, dict] = {}
    source_paths: list[str] = []

    tracked_paths: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if should_track(path, root, includes, excludes):
            tracked_paths.append(path)

    known_files = {rel_posix(path, root) for path in tracked_paths}
    for path in tracked_paths:
        rel_path = rel_posix(path, root)
        text = path.read_text(encoding="utf-8", errors="ignore")
        language = detect_language(path)
        is_source = path.suffix.lower() in SOURCE_EXTENSIONS or path.name in {"Dockerfile", "Makefile"}
        hints = analyzer_registry.analyze_file(root, path, rel_path, text, known_files)
        files[rel_path] = {
            "path": rel_path,
            "sha256": sha256_text(text),
            "loc": count_loc(text),
            "language": language,
            "role": detect_role(rel_path),
            "imports": hints.imports,
            "symbols": hints.symbols,
            "tokens": stable_sorted(tokenize(rel_path) + hints.tokens),
            "is_entrypoint": hints.is_entrypoint,
            "is_project_marker": hints.is_project_marker,
            "is_source": is_source,
            "dependencies": hints.dependencies,
            "fan_in": 0,
            "fan_out": len(hints.dependencies),
            "hotspot": False,
            "hotspot_reasons": [],
        }
        if is_source:
            source_paths.append(rel_path)

    reverse_dependencies: dict[str, set[str]] = defaultdict(set)
    for rel_path, record in files.items():
        for dependency in record["dependencies"]:
            reverse_dependencies[dependency].add(rel_path)

    for rel_path, record in files.items():
        record["fan_in"] = len(reverse_dependencies.get(rel_path, set()))

    source_values = [files[path]["fan_in"] for path in source_paths]
    fan_in_threshold = top_bucket_threshold(source_values, FAN_PERCENTILE)
    source_values = [files[path]["fan_out"] for path in source_paths]
    fan_out_threshold = top_bucket_threshold(source_values, FAN_PERCENTILE)

    recursive_source_counts: dict[str, int] = defaultdict(int)
    entrypoint_dirs: set[str] = set()
    for rel_path in source_paths:
        rel_dir = Path(rel_path).parent
        for parent in [rel_dir, *rel_dir.parents]:
            parent_str = parent.as_posix()
            if parent_str in {".", ""}:
                continue
            recursive_source_counts[parent_str] += 1
        if files[rel_path]["is_entrypoint"]:
            for parent in [rel_dir, *rel_dir.parents]:
                parent_str = parent.as_posix()
                if parent_str in {".", ""}:
                    continue
                entrypoint_dirs.add(parent_str)

    candidate_modules = {
        directory
        for directory, count in recursive_source_counts.items()
        if count >= MODULE_SOURCE_THRESHOLD
    } | entrypoint_dirs
    candidate_modules = {module for module in candidate_modules if module}
    ordered_modules = sorted(candidate_modules, key=lambda value: (value.count("/"), value))

    def primary_module_for(rel_path: str) -> str | None:
        parent = Path(rel_path).parent
        matches = [module for module in ordered_modules if parent == Path(module) or Path(module) in parent.parents]
        if not matches:
            return None
        return sorted(matches, key=lambda value: (value.count("/"), value), reverse=True)[0]

    modules: dict[str, dict] = {}
    for rel_path in source_paths:
        module_path = primary_module_for(rel_path)
        files[rel_path]["module"] = module_path
        if not module_path:
            continue
        module = modules.setdefault(
            module_path,
            {
                "path": module_path,
                "role": detect_role(module_path),
                "files": [],
                "entrypoints": [],
                "symbols": [],
                "adjacent_modules": set(),
                "hotspots": [],
                "total_loc": 0,
                "fingerprint_inputs": [],
            },
        )
        module["files"].append(rel_path)
        module["total_loc"] += files[rel_path]["loc"]
        module["fingerprint_inputs"].append(files[rel_path]["sha256"])
        module["symbols"].extend(files[rel_path]["symbols"])
        if files[rel_path]["is_entrypoint"]:
            module["entrypoints"].append(rel_path)

    for rel_path in source_paths:
        module_path = files[rel_path].get("module")
        for dependency in files[rel_path]["dependencies"]:
            target_module = files.get(dependency, {}).get("module")
            if module_path and target_module and target_module != module_path:
                modules[module_path]["adjacent_modules"].add(target_module)

    for rel_path in source_paths:
        record = files[rel_path]
        reasons: list[str] = []
        if record["loc"] > HOTSPOT_LOC_THRESHOLD:
            reasons.append(f"loc>{HOTSPOT_LOC_THRESHOLD}")
        if fan_in_threshold and record["fan_in"] >= fan_in_threshold and record["fan_in"] > 0:
            reasons.append(f"fan-in top {int(FAN_PERCENTILE * 100)}%")
        if fan_out_threshold and record["fan_out"] >= fan_out_threshold and record["fan_out"] > 0:
            reasons.append(f"fan-out top {int(FAN_PERCENTILE * 100)}%")
        record["hotspot"] = bool(reasons)
        record["hotspot_reasons"] = reasons
        if record["hotspot"] and record.get("module") in modules:
            modules[record["module"]]["hotspots"].append(rel_path)

    for module in modules.values():
        module["files"] = sorted(module["files"])
        module["entrypoints"] = sorted(module["entrypoints"])
        module["symbols"] = stable_sorted(module["symbols"])[:20]
        module["adjacent_modules"] = sorted(module["adjacent_modules"])
        module["hotspots"] = sorted(module["hotspots"])
        module["file_count"] = len(module["files"])
        module["fingerprint"] = sha256_text("".join(sorted(module["fingerprint_inputs"])))
        module.pop("fingerprint_inputs", None)

    top_level_dirs: dict[str, dict] = defaultdict(lambda: {"file_count": 0, "source_count": 0, "loc": 0, "roles": []})
    for rel_path, record in files.items():
        top_level = rel_path.split("/", 1)[0]
        top_level_dirs[top_level]["file_count"] += 1
        top_level_dirs[top_level]["loc"] += record["loc"]
        top_level_dirs[top_level]["roles"].append(record["role"])
        if record["is_source"]:
            top_level_dirs[top_level]["source_count"] += 1

    top_level_summary = []
    for directory, stats in sorted(top_level_dirs.items(), key=lambda item: (-item[1]["loc"], item[0])):
        top_level_summary.append(
            {
                "path": directory,
                "file_count": stats["file_count"],
                "source_count": stats["source_count"],
                "loc": stats["loc"],
                "role": stable_sorted(stats["roles"])[0] if stats["roles"] else "unknown",
            }
        )

    project_hints = analyzer_registry.detect_project_hints(root, files)
    hotspot_files = sorted((path for path in source_paths if files[path]["hotspot"]), key=lambda item: (-files[item]["loc"], item))
    entrypoints = sorted(path for path in source_paths if files[path]["is_entrypoint"])
    project_markers = sorted(path for path, record in files.items() if record["is_project_marker"])

    return {
        "root": str(root),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_hints": project_hints,
        "frameworks": project_hints,
        "thresholds": {
            "hotspot_loc": HOTSPOT_LOC_THRESHOLD,
            "fan_percentile": FAN_PERCENTILE,
            "module_source_threshold": MODULE_SOURCE_THRESHOLD,
            "fan_in_threshold": fan_in_threshold,
            "fan_out_threshold": fan_out_threshold,
        },
        "stats": {
            "tracked_files": len(files),
            "source_files": len(source_paths),
            "modules": len(modules),
            "hotspots": len(hotspot_files),
        },
        "files": files,
        "modules": modules,
        "hotspot_files": hotspot_files,
        "entrypoints": entrypoints,
        "project_markers": project_markers,
        "top_level_dirs": top_level_summary,
        "role_descriptions": ROLE_DESCRIPTIONS,
    }
