#!/usr/bin/env python3
"""Refresh repo-context after file edits.

Use this as a host-level post-edit hook when your agent or editor supports
running a command after write operations.

Example for Claude Code:
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/post_edit_refresh.py --file \"$FILE_PATH\""
          }
        ]
      }
    ]
  }
}

Git hooks are still useful for commit boundaries, but they cannot guarantee a
refresh after every local file edit. This script is meant for immediate
post-edit recalculation.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lib.drift import build_drift_report, resolve_context_dir
from lib.scanner import scan_repository
from lib.utils import display_path
from repo_context import _parse_globs, materialize_context


def _candidate_roots(path: Path) -> list[Path]:
    start = path if path.is_dir() else path.parent
    return [start, *start.parents]


def _looks_like_repo_root(path: Path) -> bool:
    return path.joinpath(".git").exists() or path.joinpath(".repo-context").exists() or path.joinpath(".codex", "context").exists()


def _resolve_root(root_arg: str | None, file_arg: str | None) -> Path:
    candidates: list[Path] = []
    if root_arg:
        return Path(root_arg).expanduser().resolve()

    if file_arg:
        file_path = Path(file_arg).expanduser()
        if not file_path.is_absolute():
            file_path = (Path.cwd() / file_path).resolve()
        candidates.extend(_candidate_roots(file_path))

    candidates.extend(_candidate_roots(Path.cwd()))
    for candidate in candidates:
        if _looks_like_repo_root(candidate):
            return candidate.resolve()

    raise SystemExit("Unable to determine repository root. Pass --root explicitly.")


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", help="Repository root. Auto-detected when omitted.")
    parser.add_argument("--file", help="Edited file path. Falls back to host-provided path when available.")
    parser.add_argument("--out", help="Optional context output directory relative to root or absolute.")
    parser.add_argument("--include", action="append", help="Optional glob(s) to include.")
    parser.add_argument("--exclude", action="append", help="Optional glob(s) to exclude.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    root = _resolve_root(args.root, args.file)
    context_dir = resolve_context_dir(root, out=args.out).resolve()

    if args.file:
        file_path = Path(args.file).expanduser()
        if not file_path.is_absolute():
            file_path = (Path.cwd() / file_path).resolve()
        if _is_within(file_path, context_dir):
            print(f"Skipping repo-context refresh for generated artifact: {display_path(file_path, root)}")
            return 0

    includes = _parse_globs(args.include)
    excludes = _parse_globs(args.exclude)
    report = build_drift_report(root, includes=includes, excludes=excludes, out=args.out)
    if report["status"] == "fresh":
        print(f"Repo context already fresh at {display_path(context_dir, root)}")
        return 0

    scan = report["scan"] or scan_repository(root, includes=includes, excludes=excludes)
    mode = "bootstrap" if report["status"] == "missing" else "refresh"
    result = materialize_context(root, scan, mode=mode, out=args.out)

    action = "bootstrapped" if mode == "bootstrap" else "refreshed"
    print(f"Context pack {action} at {display_path(Path(result['context_dir']), root)}")
    print(f"Updated artifacts: {len(result['updated_docs'])}")
    if result["removed_docs"]:
        print(f"Removed stale artifacts: {len(result['removed_docs'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
