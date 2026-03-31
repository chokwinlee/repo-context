"""Repository scanner with JS/TS-enhanced import and export parsing."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .constants import (
    ENTRYPOINT_NAMES,
    FAN_PERCENTILE,
    HOTSPOT_LOC_THRESHOLD,
    IGNORED_DIRS,
    IGNORED_FILES,
    JS_TS_EXTENSIONS,
    MODULE_SOURCE_THRESHOLD,
    ROLE_DESCRIPTIONS,
    ROUTE_ENTRYPOINT_NAMES,
    SOURCE_EXTENSIONS,
    TRACKED_EXTENSIONS,
)
from .utils import count_loc, normalize_import_path, read_text, rel_posix, sha256_text, stable_sorted, tokenize, top_bucket_threshold


IMPORT_PATTERNS = [
    re.compile(r"^\s*import(?:[\s\w{},*]+from\s*)?[\"']([^\"']+)[\"']", re.MULTILINE),
    re.compile(r"^\s*export\s+.*?\s+from\s+[\"']([^\"']+)[\"']", re.MULTILINE),
    re.compile(r"require\(\s*[\"']([^\"']+)[\"']\s*\)"),
    re.compile(r"import\(\s*[\"']([^\"']+)[\"']\s*\)"),
]

EXPORT_PATTERNS = [
    re.compile(r"^\s*export\s+(?:async\s+)?function\s+([A-Za-z0-9_]+)", re.MULTILINE),
    re.compile(r"^\s*export\s+(?:const|let|var)\s+([A-Za-z0-9_]+)", re.MULTILINE),
    re.compile(r"^\s*export\s+class\s+([A-Za-z0-9_]+)", re.MULTILINE),
    re.compile(r"^\s*export\s+(?:type|interface|enum)\s+([A-Za-z0-9_]+)", re.MULTILINE),
    re.compile(r"^\s*export\s+default\s+function\s+([A-Za-z0-9_]+)", re.MULTILINE),
    re.compile(r"^\s*export\s+default\s+class\s+([A-Za-z0-9_]+)", re.MULTILINE),
    re.compile(r"^\s*exports\.([A-Za-z0-9_]+)\s*=", re.MULTILINE),
]

COMPONENT_PATTERN = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?function\s+([A-Z][A-Za-z0-9_]*)", re.MULTILINE)
PACKAGE_JSON_KEYS = ("dependencies", "devDependencies")


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
    return path.name in {"Dockerfile", "Makefile", "package.json", "tsconfig.json"}


def detect_language(path: Path) -> str:
    if path.name == "Dockerfile":
        return "docker"
    if path.name == "Makefile":
        return "make"
    suffix = path.suffix.lower()
    return {
        ".cjs": "javascript",
        ".css": "css",
        ".go": "go",
        ".java": "java",
        ".js": "javascript",
        ".json": "json",
        ".jsx": "javascript",
        ".kt": "kotlin",
        ".md": "markdown",
        ".mdx": "mdx",
        ".mjs": "javascript",
        ".php": "php",
        ".py": "python",
        ".rb": "ruby",
        ".rs": "rust",
        ".scss": "scss",
        ".sh": "shell",
        ".sql": "sql",
        ".swift": "swift",
        ".toml": "toml",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".yaml": "yaml",
        ".yml": "yaml",
    }.get(suffix, "text")


def detect_role(rel_path: str) -> str:
    parts = rel_path.lower().split("/")
    file_name = parts[-1]
    if "legacy" in parts or "legacy" in file_name:
        return "legacy"
    if "test" in file_name or "__tests__" in parts or "tests" in parts:
        return "tests"
    if any(part in {"app", "pages", "routes", "route", "api"} for part in parts):
        return "routing"
    if any(part in {"components", "ui"} for part in parts):
        return "ui"
    if any(part in {"lib", "core", "domain", "services", "generators"} for part in parts):
        return "domain"
    if any(part in {"scripts", "bin"} for part in parts):
        return "scripts"
    if any(part in {"docs", "content"} for part in parts) or file_name.endswith(".md"):
        return "docs"
    if any(part in {"data", "fixtures"} for part in parts):
        return "data"
    if file_name in {"package.json", "tsconfig.json"} or file_name.endswith((".config.js", ".config.ts", ".config.mjs")):
        return "config"
    return "unknown"


def parse_imports(text: str) -> list[str]:
    imports: list[str] = []
    for pattern in IMPORT_PATTERNS:
        imports.extend(pattern.findall(text))
    return stable_sorted(imports)


def parse_exports(text: str) -> list[str]:
    exports: list[str] = []
    for pattern in EXPORT_PATTERNS:
        exports.extend(pattern.findall(text))
    if "export default" in text and "default" not in exports:
        exports.append("default")
    exports.extend(COMPONENT_PATTERN.findall(text))
    return stable_sorted(exports)


def resolve_internal_import(importer_path: str, import_target: str, known_files: set[str]) -> str | None:
    if import_target.startswith(("./", "../")):
        base = normalize_import_path(str(Path(importer_path).parent / import_target))
    elif import_target.startswith(("@/", "~/")):
        base = normalize_import_path(import_target[2:])
    elif import_target.startswith("/"):
        base = normalize_import_path(import_target[1:])
    else:
        return None

    candidates = [base]
    if Path(base).suffix:
        candidates.append(base.rsplit(".", 1)[0])

    extensions = sorted(JS_TS_EXTENSIONS | {".py", ".rb", ".go", ".rs"})
    for prefix in list(candidates):
        for extension in extensions:
            candidates.append(f"{prefix}{extension}")
            candidates.append(f"{prefix}/index{extension}")

    for candidate in candidates:
        normalized = normalize_import_path(candidate)
        if normalized in known_files:
            return normalized
    return None


def detect_frameworks(root: Path, files: dict[str, dict]) -> list[str]:
    frameworks: list[str] = []
    package_json = root / "package.json"
    if package_json.exists():
        try:
            package_data = json.loads(read_text(package_json))
        except json.JSONDecodeError:
            package_data = {}
        deps = {}
        for key in PACKAGE_JSON_KEYS:
            deps.update(package_data.get(key, {}))
        if "next" in deps:
            frameworks.append("nextjs")
        if "react" in deps:
            frameworks.append("react")
        if "vue" in deps:
            frameworks.append("vue")
        if "express" in deps:
            frameworks.append("express")
    if root.joinpath("next.config.js").exists() or root.joinpath("next.config.mjs").exists():
        frameworks.append("nextjs")
    if any(path.startswith("app/") and path.endswith(("page.tsx", "page.jsx")) for path in files):
        frameworks.append("app-router")
    if any(path.endswith(".py") for path in files):
        frameworks.append("python")
    return stable_sorted(frameworks)


def scan_repository(root: Path, includes: list[str] | None = None, excludes: list[str] | None = None) -> dict:
    root = root.resolve()
    files: dict[str, dict] = {}
    source_paths: list[str] = []

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if not should_track(path, root, includes, excludes):
            continue
        rel_path = rel_posix(path, root)
        text = read_text(path)
        language = detect_language(path)
        is_source = path.suffix.lower() in SOURCE_EXTENSIONS or path.name in {"Dockerfile", "Makefile"}
        is_entrypoint = path.name in ENTRYPOINT_NAMES or path.name in ROUTE_ENTRYPOINT_NAMES
        if "/app/" in f"/{rel_path}/" and path.name in ROUTE_ENTRYPOINT_NAMES:
            is_entrypoint = True
        imports = parse_imports(text) if path.suffix.lower() in JS_TS_EXTENSIONS | {".py", ".rb"} else []
        exports = parse_exports(text) if path.suffix.lower() in JS_TS_EXTENSIONS | {".py", ".rb"} else []
        files[rel_path] = {
            "path": rel_path,
            "sha256": sha256_text(text),
            "loc": count_loc(text),
            "language": language,
            "role": detect_role(rel_path),
            "imports": imports,
            "exports": exports[:16],
            "tokens": stable_sorted(tokenize(rel_path) + tokenize(" ".join(exports))),
            "is_entrypoint": is_entrypoint,
            "is_source": is_source,
            "internal_imports": [],
            "fan_in": 0,
            "fan_out": 0,
            "hotspot": False,
            "hotspot_reasons": [],
        }
        if is_source:
            source_paths.append(rel_path)

    known_files = set(files)
    reverse_imports: dict[str, set[str]] = defaultdict(set)
    for rel_path, record in files.items():
        internal_imports: list[str] = []
        for import_target in record["imports"]:
            resolved = resolve_internal_import(rel_path, import_target, known_files)
            if resolved:
                internal_imports.append(resolved)
                reverse_imports[resolved].add(rel_path)
        record["internal_imports"] = stable_sorted(internal_imports)
        record["fan_out"] = len(record["internal_imports"])

    for rel_path, record in files.items():
        record["fan_in"] = len(reverse_imports.get(rel_path, set()))

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
                "exports": [],
                "adjacent_modules": set(),
                "hotspots": [],
                "total_loc": 0,
                "fingerprint_inputs": [],
            },
        )
        module["files"].append(rel_path)
        module["total_loc"] += files[rel_path]["loc"]
        module["fingerprint_inputs"].append(files[rel_path]["sha256"])
        module["exports"].extend(files[rel_path]["exports"])
        if files[rel_path]["is_entrypoint"]:
            module["entrypoints"].append(rel_path)

    for rel_path in source_paths:
        module_path = files[rel_path].get("module")
        for dependency in files[rel_path]["internal_imports"]:
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
        module["exports"] = stable_sorted(module["exports"])[:20]
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

    frameworks = detect_frameworks(root, files)
    hotspot_files = sorted((path for path in source_paths if files[path]["hotspot"]), key=lambda item: (-files[item]["loc"], item))
    entrypoints = sorted(path for path in source_paths if files[path]["is_entrypoint"])

    return {
        "root": str(root),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "frameworks": frameworks,
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
        "top_level_dirs": top_level_summary,
        "role_descriptions": ROLE_DESCRIPTIONS,
    }
