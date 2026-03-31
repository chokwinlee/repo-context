#!/usr/bin/env python3
"""Generate and maintain a progressive context pack for repositories."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lib.drift import build_drift_report
from lib.render import build_context_pack, module_doc_relpath
from lib.scanner import scan_repository
from lib.task_scope import build_task_scope
from lib.utils import dump_json_if_changed, ensure_dir, write_if_changed


def _parse_globs(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    globs: list[str] = []
    for value in values:
        globs.extend(part.strip() for part in value.split(",") if part.strip())
    return globs or None


def _remove_orphans(context_dir: Path, expected_paths: set[str]) -> list[str]:
    removed: list[str] = []
    for folder in ("modules", "files"):
        candidate_dir = context_dir / folder
        if not candidate_dir.exists():
            continue
        for path in candidate_dir.rglob("*.md"):
            rel_path = path.relative_to(context_dir).as_posix()
            if rel_path not in expected_paths:
                path.unlink()
                removed.append(rel_path)
    return removed


def materialize_context(root: Path, scan: dict, mode: str) -> dict:
    context_dir = ensure_dir(root / ".codex" / "context")
    ensure_dir(context_dir / "modules")
    ensure_dir(context_dir / "files")

    docs, symbol_map, manifest = build_context_pack(scan, mode)
    updated_docs: list[str] = []
    for rel_path, content in docs.items():
        if write_if_changed(context_dir / rel_path, content):
            updated_docs.append(rel_path)

    if dump_json_if_changed(context_dir / "symbol-map.json", symbol_map):
        updated_docs.append("symbol-map.json")
    if dump_json_if_changed(context_dir / "manifest.json", manifest):
        updated_docs.append("manifest.json")

    expected_paths = set(docs) | {"manifest.json", "symbol-map.json"}
    removed_docs = _remove_orphans(context_dir, expected_paths)
    return {
        "updated_docs": updated_docs,
        "removed_docs": removed_docs,
        "context_dir": str(context_dir),
        "scan": scan,
    }


def command_bootstrap(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    scan = scan_repository(root, includes=_parse_globs(args.include), excludes=_parse_globs(args.exclude))
    result = materialize_context(root, scan, mode="bootstrap")
    print(f"Context pack bootstrapped at {result['context_dir']}")
    print(f"Tracked files: {scan['stats']['tracked_files']} | Modules: {scan['stats']['modules']} | Hotspots: {scan['stats']['hotspots']}")
    print(f"Updated artifacts: {len(result['updated_docs'])}")
    return 0


def command_refresh(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    scan = scan_repository(root)
    result = materialize_context(root, scan, mode="refresh")
    print(f"Context pack refreshed at {result['context_dir']}")
    print(f"Updated artifacts: {len(result['updated_docs'])}")
    if result["removed_docs"]:
        print("Removed stale artifacts:")
        for rel_path in result["removed_docs"]:
            print(f"- {rel_path}")
    return 0


def command_check(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    report = build_drift_report(root)
    print(f"Context status: {report['status']}")
    if report["issues"]:
        for issue in report["issues"]:
            print(f"- {issue}")
    else:
        print("- Context pack matches the current repository snapshot.")
    return 1 if args.fail_on_stale and report["issues"] else 0


def command_task_scope(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    report = build_drift_report(root)
    if report["status"] != "fresh":
        print("Context pack is missing or stale. Run `repo_context.py bootstrap --root <repo>` or `repo_context.py refresh --root <repo>` first.")
        for issue in report["issues"]:
            print(f"- {issue}")
        return 2

    scope = build_task_scope(root, args.query)
    print(f"Task: {scope['query']}")
    print("Read order:")
    print("- .codex/context/index.md")
    print("- .codex/context/repo-map.md")
    print("Priority modules:")
    for module_path in scope["modules"]:
        print(f"- .codex/context/{module_doc_relpath(module_path)} ({module_path})")
    print("Recommended files for deep reads:")
    for file_path in scope["files"]:
        print(f"- {file_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap = subparsers.add_parser("bootstrap", help="Create the initial context pack.")
    bootstrap.add_argument("--root", required=True, help="Repository root to scan.")
    bootstrap.add_argument("--include", action="append", help="Optional glob(s) to include.")
    bootstrap.add_argument("--exclude", action="append", help="Optional glob(s) to exclude.")
    bootstrap.set_defaults(func=command_bootstrap)

    refresh = subparsers.add_parser("refresh", help="Refresh the context pack in place.")
    refresh.add_argument("--root", required=True, help="Repository root to scan.")
    refresh.set_defaults(func=command_refresh)

    check = subparsers.add_parser("check", help="Detect drift between the repo and its context pack.")
    check.add_argument("--root", required=True, help="Repository root to inspect.")
    check.add_argument("--fail-on-stale", action="store_true", help="Return a non-zero exit code when the pack is stale.")
    check.set_defaults(func=command_check)

    task_scope = subparsers.add_parser("task-scope", help="Rank modules and files for a feature or bugfix task.")
    task_scope.add_argument("--root", required=True, help="Repository root to inspect.")
    task_scope.add_argument("--query", required=True, help="Task description used for ranking.")
    task_scope.set_defaults(func=command_task_scope)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
