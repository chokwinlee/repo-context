#!/usr/bin/env python3
"""Generate and maintain a progressive context pack for repositories."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lib.drift import build_drift_report, resolve_context_dir
from lib.render import build_context_pack, module_doc_relpath
from lib.scanner import scan_repository
from lib.task_scope import build_task_scope
from lib.utils import display_path, dump_json_if_changed, ensure_dir, write_if_changed


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


def materialize_context(root: Path, scan: dict, mode: str, out: str | None = None) -> dict:
    context_dir = ensure_dir(resolve_context_dir(root, out=out))
    ensure_dir(context_dir / "modules")
    ensure_dir(context_dir / "files")

    docs, symbol_map, manifest = build_context_pack(scan, mode, output_dir=display_path(context_dir, root))
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
    result = materialize_context(root, scan, mode="bootstrap", out=args.out)
    print(f"Context pack bootstrapped at {display_path(Path(result['context_dir']), root)}")
    print(f"Tracked files: {scan['stats']['tracked_files']} | Modules: {scan['stats']['modules']} | Hotspots: {scan['stats']['hotspots']}")
    print(f"Updated artifacts: {len(result['updated_docs'])}")
    return 0


def command_refresh(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    scan = scan_repository(root)
    result = materialize_context(root, scan, mode="refresh", out=args.out)
    print(f"Context pack refreshed at {display_path(Path(result['context_dir']), root)}")
    print(f"Updated artifacts: {len(result['updated_docs'])}")
    if result["removed_docs"]:
        print("Removed stale artifacts:")
        for rel_path in result["removed_docs"]:
            print(f"- {rel_path}")
    return 0


def command_check(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    report = build_drift_report(root, out=args.out)
    print(f"Context status: {report['status']} ({display_path(report['context_dir'], root)})")
    if report["issues"]:
        for issue in report["issues"]:
            print(f"- {issue}")
    else:
        print("- Context pack matches the current repository snapshot.")
    return 1 if args.fail_on_stale and report["issues"] else 0


def command_task_scope(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    report = build_drift_report(root, out=args.out)
    if report["status"] != "fresh":
        context_display = display_path(report["context_dir"], root)
        print(
            "Context pack is missing or stale. "
            "Run `repo_context.py bootstrap --root <repo>` or `repo_context.py refresh --root <repo>` first."
        )
        print(f"- Expected context directory: {context_display}")
        for issue in report["issues"]:
            print(f"- {issue}")
        return 2

    scope = build_task_scope(root, args.query, out=args.out)
    context_display = display_path(report["context_dir"], root)
    print(f"Task: {scope['query']}")
    print("Read order:")
    print(f"- {context_display}/index.md")
    print(f"- {context_display}/repo-map.md")
    print("Priority modules:")
    for module_path in scope["modules"]:
        print(f"- {context_display}/{module_doc_relpath(module_path)} ({module_path})")
    print("Recommended files for deep reads:")
    for file_path in scope["files"]:
        print(f"- {file_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap = subparsers.add_parser("bootstrap", help="Create the initial context pack.")
    bootstrap.add_argument("--root", required=True, help="Repository root to scan.")
    bootstrap.add_argument("--out", help="Optional output directory relative to the repo root or absolute.")
    bootstrap.add_argument("--include", action="append", help="Optional glob(s) to include.")
    bootstrap.add_argument("--exclude", action="append", help="Optional glob(s) to exclude.")
    bootstrap.set_defaults(func=command_bootstrap)

    refresh = subparsers.add_parser("refresh", help="Refresh the context pack in place.")
    refresh.add_argument("--root", required=True, help="Repository root to scan.")
    refresh.add_argument("--out", help="Optional output directory relative to the repo root or absolute.")
    refresh.set_defaults(func=command_refresh)

    check = subparsers.add_parser("check", help="Detect drift between the repo and its context pack.")
    check.add_argument("--root", required=True, help="Repository root to inspect.")
    check.add_argument("--out", help="Optional output directory relative to the repo root or absolute.")
    check.add_argument("--fail-on-stale", action="store_true", help="Return a non-zero exit code when the pack is stale.")
    check.set_defaults(func=command_check)

    task_scope = subparsers.add_parser("task-scope", help="Rank modules and files for a feature or bugfix task.")
    task_scope.add_argument("--root", required=True, help="Repository root to inspect.")
    task_scope.add_argument("--out", help="Optional output directory relative to the repo root or absolute.")
    task_scope.add_argument("--query", required=True, help="Task description used for ranking.")
    task_scope.set_defaults(func=command_task_scope)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
