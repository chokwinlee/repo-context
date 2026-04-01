"""Extensible analyzer registry for file hints and project hints."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
    tomllib = None  # type: ignore[assignment]

from .constants import (
    ANALYZER_DISCOVERY_DIRS,
    ANALYZER_MODULE_SUFFIX,
    CONFIG_SUFFIXES,
    ENTRYPOINT_DIR_HINTS,
    ENTRYPOINT_NAMES,
    JS_TS_EXTENSIONS,
    PROJECT_MARKER_NAMES,
    PYTHON_EXTENSIONS,
    ROUTE_ENTRYPOINT_NAMES,
    RUBY_EXTENSIONS,
)
from .ignore_rules import build_ignore_matcher
from .utils import normalize_import_path, read_text, stable_sorted, tokenize


JS_IMPORT_PATTERNS = [
    re.compile(r"^\s*import(?:[\s\w{},*]+from\s*)?[\"']([^\"']+)[\"']", re.MULTILINE),
    re.compile(r"^\s*export\s+.*?\s+from\s+[\"']([^\"']+)[\"']", re.MULTILINE),
    re.compile(r"require\(\s*[\"']([^\"']+)[\"']\s*\)"),
    re.compile(r"import\(\s*[\"']([^\"']+)[\"']\s*\)"),
]

JS_SYMBOL_PATTERNS = [
    re.compile(r"^\s*export\s+(?:async\s+)?function\s+([A-Za-z0-9_]+)", re.MULTILINE),
    re.compile(r"^\s*export\s+(?:const|let|var)\s+([A-Za-z0-9_]+)", re.MULTILINE),
    re.compile(r"^\s*export\s+class\s+([A-Za-z0-9_]+)", re.MULTILINE),
    re.compile(r"^\s*export\s+(?:type|interface|enum)\s+([A-Za-z0-9_]+)", re.MULTILINE),
    re.compile(r"^\s*export\s+default\s+function\s+([A-Za-z0-9_]+)", re.MULTILINE),
    re.compile(r"^\s*export\s+default\s+class\s+([A-Za-z0-9_]+)", re.MULTILINE),
    re.compile(r"^\s*exports\.([A-Za-z0-9_]+)\s*=", re.MULTILINE),
]

COMPONENT_PATTERN = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?function\s+([A-Z][A-Za-z0-9_]*)", re.MULTILINE)
RUBY_REQUIRE_PATTERNS = [
    re.compile(r"^\s*require_relative\s+[\"']([^\"']+)[\"']", re.MULTILINE),
    re.compile(r"^\s*require\s+[\"']([^\"']+)[\"']", re.MULTILINE),
]
RUBY_SYMBOL_PATTERNS = [
    re.compile(r"^\s*class\s+([A-Z][A-Za-z0-9_:]*)", re.MULTILINE),
    re.compile(r"^\s*module\s+([A-Z][A-Za-z0-9_:]*)", re.MULTILINE),
    re.compile(r"^\s*def\s+(?:self\.)?([a-zA-Z0-9_!?=]+)", re.MULTILINE),
]
REQUIREMENT_NAME_PATTERN = re.compile(r"^\s*([A-Za-z0-9_.-]+)")

JS_HINTS = {
    "express": "express",
    "next": "nextjs",
    "nestjs": "nestjs",
    "react": "react",
    "svelte": "svelte",
    "vue": "vue",
}
PYTHON_HINTS = {
    "celery": "celery",
    "django": "django",
    "fastapi": "fastapi",
    "flask": "flask",
}
RUBY_HINTS = {
    "rails": "rails",
    "sinatra": "sinatra",
}
PHP_HINTS = {
    "laravel/framework": "laravel",
    "symfony/framework-bundle": "symfony",
}
GO_HINTS = {
    "github.com/gin-gonic/gin": "gin",
    "github.com/labstack/echo": "echo",
}
RUST_HINTS = {
    "actix-web": "actix-web",
    "axum": "axum",
    "rocket": "rocket",
}
IGNORED_LANGUAGE_HINTS = {"config", "json", "lockfile", "markdown", "mdx", "text", "toml", "yaml"}


@dataclass
class FileAnalysis:
    imports: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    tokens: list[str] = field(default_factory=list)
    is_entrypoint: bool = False
    is_project_marker: bool = False

    def merge(self, other: "FileAnalysis") -> "FileAnalysis":
        return FileAnalysis(
            imports=stable_sorted([*self.imports, *other.imports]),
            symbols=stable_sorted([*self.symbols, *other.symbols]),
            dependencies=stable_sorted([*self.dependencies, *other.dependencies]),
            tokens=stable_sorted([*self.tokens, *other.tokens]),
            is_entrypoint=self.is_entrypoint or other.is_entrypoint,
            is_project_marker=self.is_project_marker or other.is_project_marker,
        )


class FileAnalyzer(Protocol):
    name: str

    def supports(self, path: Path) -> bool: ...

    def analyze(self, root: Path, path: Path, rel_path: str, text: str, known_files: set[str]) -> FileAnalysis: ...


class ProjectHintAnalyzer(Protocol):
    name: str

    def detect(self, root: Path, files: dict[str, dict]) -> list[str]: ...


@dataclass
class AnalyzerRegistry:
    file_analyzers: list[FileAnalyzer] = field(default_factory=list)
    project_hint_analyzers: list[ProjectHintAnalyzer] = field(default_factory=list)

    def clone(self) -> "AnalyzerRegistry":
        return AnalyzerRegistry(
            file_analyzers=list(self.file_analyzers),
            project_hint_analyzers=list(self.project_hint_analyzers),
        )

    def register_file_analyzer(self, analyzer: FileAnalyzer) -> None:
        self.file_analyzers.append(analyzer)

    def register_project_hint_analyzer(self, analyzer: ProjectHintAnalyzer) -> None:
        self.project_hint_analyzers.append(analyzer)

    def analyze_file(self, root: Path, path: Path, rel_path: str, text: str, known_files: set[str]) -> FileAnalysis:
        result = FileAnalysis(
            is_entrypoint=detect_entrypoint(path, rel_path),
            is_project_marker=is_project_marker(path),
        )
        for analyzer in self.file_analyzers:
            if analyzer.supports(path):
                result = result.merge(analyzer.analyze(root, path, rel_path, text, known_files))
        return result

    def detect_project_hints(self, root: Path, files: dict[str, dict]) -> list[str]:
        hints: list[str] = []
        for analyzer in self.project_hint_analyzers:
            hints.extend(analyzer.detect(root, files))
        return stable_sorted(hints)


@dataclass(frozen=True)
class SuffixFileAnalyzer:
    name: str
    suffixes: frozenset[str]
    parse: Callable[[str], tuple[list[str], list[str]]]
    resolve_dependency: Callable[[str, str, set[str]], str | None]

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in self.suffixes

    def analyze(self, root: Path, path: Path, rel_path: str, text: str, known_files: set[str]) -> FileAnalysis:
        raw_imports, symbols = self.parse(text)
        dependencies = [
            resolved
            for dependency in raw_imports
            if (resolved := self.resolve_dependency(rel_path, dependency, known_files))
        ]
        return FileAnalysis(
            imports=stable_sorted(raw_imports),
            symbols=stable_sorted(symbols)[:24],
            dependencies=stable_sorted(dependencies),
            tokens=stable_sorted(tokenize(" ".join(symbols)) + tokenize(" ".join(raw_imports))),
        )


@dataclass(frozen=True)
class LanguageInventoryProjectHintAnalyzer:
    name: str = "language-inventory"

    def detect(self, root: Path, files: dict[str, dict]) -> list[str]:
        hints = [record["language"] for record in files.values() if record["language"] not in IGNORED_LANGUAGE_HINTS]
        if any(path.startswith("app/") and Path(path).name.startswith("page.") for path in files):
            hints.append("app-router")
        return stable_sorted(hints)


@dataclass(frozen=True)
class PathPresenceProjectHintAnalyzer:
    name: str
    paths: tuple[str, ...]
    hints: tuple[str, ...]

    def detect(self, root: Path, files: dict[str, dict]) -> list[str]:
        if any(root.joinpath(candidate).exists() for candidate in self.paths):
            return list(self.hints)
        return []


@dataclass(frozen=True)
class ManifestProjectHintAnalyzer:
    name: str
    paths: tuple[str, ...]
    base_hints: tuple[str, ...]
    loader: Callable[[Path], list[str]]

    def detect(self, root: Path, files: dict[str, dict]) -> list[str]:
        hints: list[str] = []
        for candidate in self.paths:
            path = root / candidate
            if path.exists():
                hints.extend(self.base_hints)
                hints.extend(self.loader(path))
        return stable_sorted(hints)


def is_project_marker(path: Path) -> bool:
    return path.name in PROJECT_MARKER_NAMES or path.name.endswith(CONFIG_SUFFIXES)


def detect_entrypoint(path: Path, rel_path: str) -> bool:
    if path.name in ENTRYPOINT_NAMES or path.name in ROUTE_ENTRYPOINT_NAMES:
        return True
    parts = Path(rel_path).parts
    if parts and parts[0] in ENTRYPOINT_DIR_HINTS and path.suffix:
        return True
    if "/app/" in f"/{rel_path}/" and path.name in ROUTE_ENTRYPOINT_NAMES:
        return True
    return False


def analyze_file_hints(
    root: Path,
    path: Path,
    rel_path: str,
    text: str,
    known_files: set[str],
    registry: AnalyzerRegistry | None = None,
) -> dict:
    analysis = (registry or DEFAULT_ANALYZER_REGISTRY).analyze_file(root, path, rel_path, text, known_files)
    return {
        "imports": analysis.imports,
        "symbols": analysis.symbols,
        "dependencies": analysis.dependencies,
        "tokens": analysis.tokens,
        "is_entrypoint": analysis.is_entrypoint,
        "is_project_marker": analysis.is_project_marker,
    }


def detect_project_hints(root: Path, files: dict[str, dict], registry: AnalyzerRegistry | None = None) -> list[str]:
    return (registry or DEFAULT_ANALYZER_REGISTRY).detect_project_hints(root, files)


def build_default_analyzer_registry() -> AnalyzerRegistry:
    registry = AnalyzerRegistry()
    registry.register_file_analyzer(
        SuffixFileAnalyzer(
            name="js-ts",
            suffixes=frozenset(JS_TS_EXTENSIONS),
            parse=_parse_js_file,
            resolve_dependency=_resolve_js_dependency,
        )
    )
    registry.register_file_analyzer(
        SuffixFileAnalyzer(
            name="python",
            suffixes=frozenset(PYTHON_EXTENSIONS),
            parse=_parse_python_file,
            resolve_dependency=_resolve_python_dependency,
        )
    )
    registry.register_file_analyzer(
        SuffixFileAnalyzer(
            name="ruby",
            suffixes=frozenset(RUBY_EXTENSIONS),
            parse=_parse_ruby_file,
            resolve_dependency=_resolve_ruby_dependency,
        )
    )

    registry.register_project_hint_analyzer(LanguageInventoryProjectHintAnalyzer())
    registry.register_project_hint_analyzer(
        ManifestProjectHintAnalyzer(
            name="node-package-json",
            paths=("package.json",),
            base_hints=("node",),
            loader=_package_json_hints,
        )
    )
    registry.register_project_hint_analyzer(
        ManifestProjectHintAnalyzer(
            name="python-pyproject",
            paths=("pyproject.toml",),
            base_hints=("python",),
            loader=_pyproject_hints,
        )
    )
    registry.register_project_hint_analyzer(
        ManifestProjectHintAnalyzer(
            name="python-requirements",
            paths=("requirements.txt",),
            base_hints=("python",),
            loader=_requirements_hints,
        )
    )
    registry.register_project_hint_analyzer(
        PathPresenceProjectHintAnalyzer(
            name="django-manage",
            paths=("manage.py",),
            hints=("django", "python"),
        )
    )
    registry.register_project_hint_analyzer(
        ManifestProjectHintAnalyzer(
            name="rust-cargo",
            paths=("Cargo.toml",),
            base_hints=("rust",),
            loader=_cargo_hints,
        )
    )
    registry.register_project_hint_analyzer(
        ManifestProjectHintAnalyzer(
            name="go-mod",
            paths=("go.mod",),
            base_hints=("go",),
            loader=_go_mod_hints,
        )
    )
    registry.register_project_hint_analyzer(
        ManifestProjectHintAnalyzer(
            name="ruby-gemfile",
            paths=("Gemfile",),
            base_hints=("ruby",),
            loader=_gemfile_hints,
        )
    )
    registry.register_project_hint_analyzer(
        ManifestProjectHintAnalyzer(
            name="php-composer",
            paths=("composer.json",),
            base_hints=("php",),
            loader=_composer_hints,
        )
    )
    registry.register_project_hint_analyzer(
        PathPresenceProjectHintAnalyzer(
            name="jvm-build",
            paths=("pom.xml", "build.gradle", "build.gradle.kts"),
            hints=("java",),
        )
    )
    return registry


def prepare_analyzer_registry(root: Path, registry: AnalyzerRegistry | None = None, discover_local: bool = True) -> AnalyzerRegistry:
    prepared = (registry or DEFAULT_ANALYZER_REGISTRY).clone()
    if discover_local:
        discover_project_analyzers(root, prepared)
    return prepared


def discover_project_analyzers(root: Path, registry: AnalyzerRegistry) -> list[str]:
    matcher = build_ignore_matcher(root)
    loaded_modules: list[str] = []
    for directory in ANALYZER_DISCOVERY_DIRS:
        discovery_dir = root / directory
        if not discovery_dir.exists() or not discovery_dir.is_dir():
            continue
        if matcher.is_ignored(discovery_dir, is_dir=True):
            continue
        for module_path in _discover_analyzer_module_paths(discovery_dir, root, matcher):
            _load_analyzer_module(module_path, registry)
            loaded_modules.append(module_path.relative_to(root).as_posix())
    return loaded_modules


def _discover_analyzer_module_paths(discovery_dir: Path, root: Path, matcher) -> list[Path]:
    module_paths: list[Path] = []
    for path in sorted(discovery_dir.rglob(f"*{ANALYZER_MODULE_SUFFIX}")):
        if not path.is_file():
            continue
        if path.name == "__init__.py":
            continue
        if any(part in {"__pycache__"} for part in path.parts):
            continue
        parent_ignored = any(matcher.is_ignored(parent, is_dir=True) for parent in [path.parent, *path.parent.parents] if parent != root and root in parent.parents)
        if parent_ignored:
            continue
        if matcher.is_ignored(path, is_dir=False):
            continue
        module_paths.append(path)
    return module_paths


def _load_analyzer_module(module_path: Path, registry: AnalyzerRegistry) -> None:
    module_name = f"_repo_context_plugin_{hashlib.sha1(str(module_path).encode('utf-8')).hexdigest()}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load analyzer module: {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    register = getattr(module, "register", None)
    if callable(register):
        register(registry)

    file_analyzers = getattr(module, "FILE_ANALYZERS", ())
    for analyzer in file_analyzers:
        registry.register_file_analyzer(analyzer)

    project_hint_analyzers = getattr(module, "PROJECT_HINT_ANALYZERS", ())
    for analyzer in project_hint_analyzers:
        registry.register_project_hint_analyzer(analyzer)

def _parse_js_file(text: str) -> tuple[list[str], list[str]]:
    imports: list[str] = []
    for pattern in JS_IMPORT_PATTERNS:
        imports.extend(pattern.findall(text))

    symbols: list[str] = []
    for pattern in JS_SYMBOL_PATTERNS:
        symbols.extend(pattern.findall(text))
    if "export default" in text and "default" not in symbols:
        symbols.append("default")
    symbols.extend(COMPONENT_PATTERN.findall(text))
    return stable_sorted(imports), stable_sorted(symbols)


def _parse_python_file(text: str) -> tuple[list[str], list[str]]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [], []

    imports: list[str] = []
    symbols: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.append(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    symbols.append(target.id)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = ("." * node.level) + (node.module or "")
            if node.module:
                imports.append(base)
            for alias in node.names:
                if alias.name == "*":
                    continue
                if base:
                    imports.append(f"{base}.{alias.name}")
                else:
                    imports.append(alias.name)

    return stable_sorted(imports), stable_sorted(symbols)


def _parse_ruby_file(text: str) -> tuple[list[str], list[str]]:
    imports: list[str] = []
    for pattern in RUBY_REQUIRE_PATTERNS:
        imports.extend(pattern.findall(text))

    symbols: list[str] = []
    for pattern in RUBY_SYMBOL_PATTERNS:
        symbols.extend(pattern.findall(text))
    return stable_sorted(imports), stable_sorted(symbols)


def _resolve_js_dependency(importer_path: str, dependency: str, known_files: set[str]) -> str | None:
    if dependency.startswith(("./", "../")):
        base = normalize_import_path(str(Path(importer_path).parent / dependency))
    elif dependency.startswith(("@/", "~/")):
        base = normalize_import_path(dependency[2:])
    elif dependency.startswith("/"):
        base = normalize_import_path(dependency[1:])
    else:
        return None
    return _resolve_known_path(base, known_files, extensions=sorted(JS_TS_EXTENSIONS | {".json"}), package_index_names=("index",))


def _resolve_python_dependency(importer_path: str, dependency: str, known_files: set[str]) -> str | None:
    if dependency.startswith("."):
        level = len(dependency) - len(dependency.lstrip("."))
        module = dependency[level:]
        parent = Path(importer_path).parent
        base_parts = list(parent.parts)
        if level > 1:
            base_parts = base_parts[: max(0, len(base_parts) - (level - 1))]
        if module:
            base_parts.extend(module.split("."))
        base = "/".join(base_parts)
    else:
        base = dependency.replace(".", "/")
    return _resolve_known_path(base, known_files, extensions=sorted(PYTHON_EXTENSIONS), package_index_names=("__init__",))


def _resolve_ruby_dependency(importer_path: str, dependency: str, known_files: set[str]) -> str | None:
    if dependency.startswith(("./", "../")):
        base = normalize_import_path(str(Path(importer_path).parent / dependency))
    else:
        base = normalize_import_path(dependency)
    return _resolve_known_path(base, known_files, extensions=sorted(RUBY_EXTENSIONS), package_index_names=())


def _resolve_known_path(base: str, known_files: set[str], extensions: list[str], package_index_names: tuple[str, ...]) -> str | None:
    normalized = normalize_import_path(base)
    candidates = [normalized]
    if Path(normalized).suffix:
        candidates.append(normalized.rsplit(".", 1)[0])

    expanded: list[str] = []
    for candidate in candidates:
        expanded.append(candidate)
        for extension in extensions:
            expanded.append(f"{candidate}{extension}")
            for package_index_name in package_index_names:
                expanded.append(f"{candidate}/{package_index_name}{extension}")

    for candidate in stable_sorted(expanded):
        if candidate in known_files:
            return candidate
    return None


def _package_json_hints(path: Path) -> list[str]:
    try:
        data = json.loads(read_text(path))
    except json.JSONDecodeError:
        return []

    dependencies: dict[str, str] = {}
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        dependencies.update(data.get(key, {}))
    return stable_sorted(JS_HINTS[name] for name in dependencies if name in JS_HINTS)


def _pyproject_hints(path: Path) -> list[str]:
    raw_text = read_text(path)
    if tomllib is None:
        return _dependency_names_to_hints(_quoted_dependencies(raw_text), PYTHON_HINTS)

    try:
        data = tomllib.loads(raw_text)
    except (tomllib.TOMLDecodeError, TypeError):
        return _dependency_names_to_hints(_quoted_dependencies(raw_text), PYTHON_HINTS)

    dependencies: list[str] = []
    project = data.get("project", {})
    dependencies.extend(project.get("dependencies", []))
    for group in project.get("optional-dependencies", {}).values():
        dependencies.extend(group)

    poetry = data.get("tool", {}).get("poetry", {})
    poetry_dependencies = poetry.get("dependencies", {})
    if isinstance(poetry_dependencies, dict):
        dependencies.extend(poetry_dependencies)

    return _dependency_names_to_hints(dependencies, PYTHON_HINTS)


def _requirements_hints(path: Path) -> list[str]:
    return _dependency_names_to_hints(path.read_text(encoding="utf-8").splitlines(), PYTHON_HINTS)


def _cargo_hints(path: Path) -> list[str]:
    raw_text = read_text(path)
    if tomllib is None:
        return _dependency_names_to_hints(_quoted_dependencies(raw_text), RUST_HINTS)

    try:
        data = tomllib.loads(raw_text)
    except (tomllib.TOMLDecodeError, TypeError):
        return _dependency_names_to_hints(_quoted_dependencies(raw_text), RUST_HINTS)

    dependencies = list(data.get("dependencies", {}).keys())
    return _dependency_names_to_hints(dependencies, RUST_HINTS)


def _go_mod_hints(path: Path) -> list[str]:
    dependencies: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith(("module ", "go ", "replace ", "exclude ", "//")):
            continue
        if line.startswith("require "):
            line = line[len("require ") :]
        dependency = line.split()[0]
        if dependency not in {"(", ")"}:
            dependencies.append(dependency)
    return _dependency_names_to_hints(dependencies, GO_HINTS)


def _gemfile_hints(path: Path) -> list[str]:
    dependencies: list[str] = []
    pattern = re.compile(r"^\s*gem\s+[\"']([^\"']+)[\"']", re.MULTILINE)
    dependencies.extend(pattern.findall(path.read_text(encoding="utf-8")))
    return _dependency_names_to_hints(dependencies, RUBY_HINTS)


def _composer_hints(path: Path) -> list[str]:
    try:
        data = json.loads(read_text(path))
    except json.JSONDecodeError:
        return []
    dependencies = list(data.get("require", {}).keys()) + list(data.get("require-dev", {}).keys())
    return _dependency_names_to_hints(dependencies, PHP_HINTS)


def _dependency_names_to_hints(dependencies: list[str], hint_map: dict[str, str]) -> list[str]:
    hints: list[str] = []
    for dependency in dependencies:
        match = REQUIREMENT_NAME_PATTERN.match(dependency)
        name = match.group(1).lower() if match else dependency.lower()
        if name in hint_map:
            hints.append(hint_map[name])
    return stable_sorted(hints)


def _quoted_dependencies(text: str) -> list[str]:
    return re.findall(r"[\"']([^\"']+)[\"']", text)


DEFAULT_ANALYZER_REGISTRY = build_default_analyzer_registry()
