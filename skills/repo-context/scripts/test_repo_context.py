#!/usr/bin/env python3
"""End-to-end tests for the repo-context CLI."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent

if str(SCRIPT_DIR) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(SCRIPT_DIR))

from lib.render import file_doc_relpath, module_doc_relpath


CLI = SKILL_DIR / "scripts" / "repo_context.py"
FIXTURES = SKILL_DIR / "assets" / "fixtures"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(CLI), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def assert_ok(result: subprocess.CompletedProcess[str], label: str) -> None:
    if result.returncode != 0:
        raise AssertionError(f"{label} failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")


def make_hotspot(path: Path, prefix: str) -> None:
    lines = [path.read_text(encoding="utf-8")]
    for index in range(420):
        lines.append(
            f"export function {prefix}Section{index}(value) {{\n  return `{prefix.lower()}-${index}:${{value}}`\n}}\n"
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_root = Path(tmp_dir)
        next_repo = tmp_root / "nextjs-mini"
        legacy_repo = tmp_root / "legacy-service"
        shutil.copytree(FIXTURES / "nextjs-mini", next_repo)
        shutil.copytree(FIXTURES / "legacy-service", legacy_repo)

        make_hotspot(next_repo / "lib" / "paper-export.ts", "Paper")
        make_hotspot(legacy_repo / "src" / "legacy-reporting.js", "Legacy")

        assert_ok(run_cli("bootstrap", "--root", str(next_repo)), "bootstrap next fixture")
        assert_ok(run_cli("bootstrap", "--root", str(legacy_repo)), "bootstrap legacy fixture")

        next_context = next_repo / ".codex" / "context"
        legacy_context = legacy_repo / ".codex" / "context"
        required = ["index.md", "repo-map.md", "manifest.json", "symbol-map.json"]
        for artifact in required:
            if not next_context.joinpath(artifact).exists():
                raise AssertionError(f"Missing artifact in next fixture: {artifact}")
            if not legacy_context.joinpath(artifact).exists():
                raise AssertionError(f"Missing artifact in legacy fixture: {artifact}")

        hotspot_doc = next_context / file_doc_relpath("lib/paper-export.ts")
        lib_module_doc = next_context / module_doc_relpath("lib")
        unrelated_module_doc = next_context / module_doc_relpath("app")
        if not hotspot_doc.exists():
            raise AssertionError("Expected hotspot brief for lib/paper-export.ts")

        scope = run_cli("task-scope", "--root", str(next_repo), "--query", "add png export to editor page")
        assert_ok(scope, "task-scope next fixture")
        if "lib/paper-export.ts" not in scope.stdout or "app/editor/page.tsx" not in scope.stdout:
            raise AssertionError(f"task-scope did not surface expected files\n{scope.stdout}")

        unchanged_before = unrelated_module_doc.stat().st_mtime_ns
        changed_before = hotspot_doc.stat().st_mtime_ns
        module_before = lib_module_doc.stat().st_mtime_ns

        with next_repo.joinpath("lib", "paper-export.ts").open("a", encoding="utf-8") as handle:
            handle.write("\nexport function exportPng(templateId: string) {\n  return `png:${templateId}`\n}\n")

        stale = run_cli("check", "--root", str(next_repo), "--fail-on-stale")
        if stale.returncode == 0:
            raise AssertionError(f"Expected stale check to fail\n{stale.stdout}")

        assert_ok(run_cli("refresh", "--root", str(next_repo)), "refresh next fixture")
        fresh = run_cli("check", "--root", str(next_repo), "--fail-on-stale")
        assert_ok(fresh, "freshness check after refresh")

        if hotspot_doc.stat().st_mtime_ns == changed_before:
            raise AssertionError("Hotspot brief did not update after source change")
        if lib_module_doc.stat().st_mtime_ns == module_before:
            raise AssertionError("Affected module brief did not update after source change")
        if unrelated_module_doc.stat().st_mtime_ns != unchanged_before:
            raise AssertionError("Unrelated module brief changed unexpectedly during refresh")

        legacy_hotspot = legacy_context / file_doc_relpath("src/legacy-reporting.js")
        if not legacy_hotspot.exists():
            raise AssertionError("Expected hotspot brief for legacy reporting file")

    print("repo-context tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
