"""Utility helpers for repository context generation."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


STOPWORDS = {
    "a",
    "an",
    "and",
    "app",
    "for",
    "from",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_text(read_text(path))


def count_loc(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.strip())


def rel_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def slugify_path(value: str) -> str:
    slug = value.replace("\\", "/").strip("/")
    slug = slug.replace("/", "__")
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or "root"


def write_if_changed(path: Path, content: str) -> bool:
    ensure_dir(path.parent)
    existing = read_text(path) if path.exists() else None
    if existing == content:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def dump_json_if_changed(path: Path, data: Any) -> bool:
    return write_if_changed(path, json.dumps(data, indent=2, sort_keys=True) + "\n")


def stable_sorted(items: Iterable[str]) -> list[str]:
    return sorted(dict.fromkeys(item for item in items if item))


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    return [token for token in tokens if len(token) >= 2 and token not in STOPWORDS]


def normalize_import_path(value: str) -> str:
    path = PurePosixPath(value)
    parts: list[str] = []
    for part in path.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def top_bucket_threshold(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values, reverse=True)
    index = max(0, math.ceil(len(ordered) * fraction) - 1)
    return ordered[index]


def short_hash(value: str, length: int = 12) -> str:
    return value[:length]
