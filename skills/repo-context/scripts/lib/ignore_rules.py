"""Ignore-rule helpers for controlled directory discovery."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path

from .constants import IGNORED_DIRS, IGNORED_FILES


@dataclass(frozen=True)
class GitIgnoreRule:
    pattern: str
    negated: bool
    directory_only: bool
    anchored: bool

    def matches(self, rel_path: str, is_dir: bool) -> bool:
        if not rel_path:
            return False

        normalized = rel_path.strip("/")
        if not normalized:
            return False

        if self.directory_only:
            prefixes = _directory_prefixes(normalized, is_dir)
            return any(_match_pattern(prefix, self.pattern, self.anchored) for prefix in prefixes)
        return _match_pattern(normalized, self.pattern, self.anchored)


@dataclass
class IgnoreMatcher:
    root: Path
    rules: list[GitIgnoreRule]

    def is_ignored(self, path: Path, is_dir: bool | None = None) -> bool:
        rel_path = path.relative_to(self.root).as_posix()
        inferred_is_dir = is_dir if is_dir is not None else path.is_dir()
        ignored = False

        for part in Path(rel_path).parts:
            if part in IGNORED_DIRS:
                return True

        if not inferred_is_dir and path.name in IGNORED_FILES:
            return True

        for rule in self.rules:
            if rule.matches(rel_path, inferred_is_dir):
                ignored = not rule.negated
        return ignored


def build_ignore_matcher(root: Path) -> IgnoreMatcher:
    root = root.resolve()
    return IgnoreMatcher(root=root, rules=_load_gitignore_rules(root))


def _load_gitignore_rules(root: Path) -> list[GitIgnoreRule]:
    gitignore_path = root / ".gitignore"
    if not gitignore_path.exists():
        return []

    rules: list[GitIgnoreRule] = []
    for raw_line in gitignore_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        negated = line.startswith("!")
        if negated:
            line = line[1:].strip()
        if not line:
            continue

        anchored = line.startswith("/")
        if anchored:
            line = line[1:]

        directory_only = line.endswith("/")
        if directory_only:
            line = line.rstrip("/")

        line = line.strip()
        if not line:
            continue

        rules.append(
            GitIgnoreRule(
                pattern=line,
                negated=negated,
                directory_only=directory_only,
                anchored=anchored,
            )
        )
    return rules


def _directory_prefixes(rel_path: str, is_dir: bool) -> list[str]:
    parts = Path(rel_path).parts
    if not parts:
        return []

    stop = len(parts) if is_dir else len(parts) - 1
    prefixes: list[str] = []
    for index in range(stop):
        prefixes.append(Path(*parts[: index + 1]).as_posix())
    return prefixes


def _match_pattern(rel_path: str, pattern: str, anchored: bool) -> bool:
    candidates = [rel_path]
    if not anchored:
        parts = Path(rel_path).parts
        if "/" not in pattern:
            candidates.extend(parts)
        else:
            candidates.extend(Path(*parts[index:]).as_posix() for index in range(1, len(parts)))
    return any(fnmatch.fnmatchcase(candidate, pattern) for candidate in candidates)
