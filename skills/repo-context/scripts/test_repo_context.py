#!/usr/bin/env python3
"""End-to-end tests for the repo-context CLI."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent

if str(SCRIPT_DIR) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(SCRIPT_DIR))

from lib.render import file_doc_relpath, module_doc_relpath
from lib.scanner import scan_repository


CLI = SKILL_DIR / "scripts" / "repo_context.py"
POST_EDIT_HOOK = SKILL_DIR / "scripts" / "post_edit_refresh.py"
FIXTURES = SKILL_DIR / "assets" / "fixtures"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(CLI), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def run_post_edit_hook(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(POST_EDIT_HOOK), *args],
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


def make_python_hotspot(path: Path, prefix: str) -> None:
    lines = [path.read_text(encoding="utf-8")]
    for index in range(420):
        lines.append(
            f"\ndef {prefix.lower()}_step_{index}(payload: bytes) -> str:\n"
            f"    return '{prefix.lower()}-{index}:' + str(len(payload))\n"
        )
    path.write_text("".join(lines), encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_root = Path(tmp_dir)
        next_repo = tmp_root / "nextjs-mini"
        legacy_repo = tmp_root / "legacy-service"
        python_repo = tmp_root / "python-service"
        shutil.copytree(FIXTURES / "nextjs-mini", next_repo)
        shutil.copytree(FIXTURES / "legacy-service", legacy_repo)
        shutil.copytree(FIXTURES / "python-service", python_repo)

        make_hotspot(next_repo / "lib" / "paper-export.ts", "Paper")
        make_hotspot(legacy_repo / "src" / "legacy-reporting.js", "Legacy")
        make_python_hotspot(python_repo / "app" / "services" / "payment_gateway.py", "Webhook")

        assert_ok(run_cli("bootstrap", "--root", str(next_repo)), "bootstrap next fixture")
        assert_ok(
            run_cli("bootstrap", "--root", str(legacy_repo), "--out", ".agent-context/repo-context"),
            "bootstrap legacy fixture",
        )
        assert_ok(run_cli("bootstrap", "--root", str(python_repo)), "bootstrap python fixture")

        next_context = next_repo / ".repo-context"
        legacy_context = legacy_repo / ".agent-context" / "repo-context"
        python_context = python_repo / ".repo-context"
        required = ["index.md", "repo-map.md", "manifest.json", "symbol-map.json"]
        for artifact in required:
            if not next_context.joinpath(artifact).exists():
                raise AssertionError(f"Missing artifact in next fixture: {artifact}")
            if not legacy_context.joinpath(artifact).exists():
                raise AssertionError(f"Missing artifact in legacy fixture: {artifact}")
            if not python_context.joinpath(artifact).exists():
                raise AssertionError(f"Missing artifact in python fixture: {artifact}")

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

        hook_changed_before = hotspot_doc.stat().st_mtime_ns
        hook_module_before = lib_module_doc.stat().st_mtime_ns
        hook_unchanged_before = unrelated_module_doc.stat().st_mtime_ns

        with next_repo.joinpath("lib", "paper-export.ts").open("a", encoding="utf-8") as handle:
            handle.write("\nexport function exportJpeg(templateId: string) {\n  return `jpeg:${templateId}`\n}\n")

        assert_ok(
            run_post_edit_hook(
                "--root",
                str(next_repo),
                "--file",
                str(next_repo / "lib" / "paper-export.ts"),
            ),
            "post-edit hook refresh",
        )
        fresh_after_hook = run_cli("check", "--root", str(next_repo), "--fail-on-stale")
        assert_ok(fresh_after_hook, "freshness check after post-edit hook")

        if hotspot_doc.stat().st_mtime_ns == hook_changed_before:
            raise AssertionError("Hotspot brief did not update after post-edit hook refresh")
        if lib_module_doc.stat().st_mtime_ns == hook_module_before:
            raise AssertionError("Affected module brief did not update after post-edit hook refresh")
        if unrelated_module_doc.stat().st_mtime_ns != hook_unchanged_before:
            raise AssertionError("Unrelated module brief changed unexpectedly during post-edit hook refresh")

        legacy_hotspot = legacy_context / file_doc_relpath("src/legacy-reporting.js")
        if not legacy_hotspot.exists():
            raise AssertionError("Expected hotspot brief for legacy reporting file")

        python_hotspot = python_context / file_doc_relpath("app/services/payment_gateway.py")
        if not python_hotspot.exists():
            raise AssertionError("Expected hotspot brief for python payment gateway file")

        python_scope = run_cli("task-scope", "--root", str(python_repo), "--query", "add signature verification to billing webhook")
        assert_ok(python_scope, "task-scope python fixture")
        if "app/router.py" not in python_scope.stdout or "app/services/payment_gateway.py" not in python_scope.stdout:
            raise AssertionError(f"task-scope did not surface expected python files\n{python_scope.stdout}")

        python_manifest = json.loads((python_context / "manifest.json").read_text(encoding="utf-8"))
        project_hints = set(python_manifest.get("project_hints", []))
        if not {"python", "fastapi"}.issubset(project_hints):
            raise AssertionError(f"Expected python/fastapi project hints, got {sorted(project_hints)}")

        custom_repo = tmp_root / "custom-extension"
        write_text(
            custom_repo / "app" / "main.py",
            (
                "from app.shared import helper\n\n"
                "# repo-context-symbol: custom_hook\n"
                "# repo-context-dependency: app/shared.py\n\n"
                "def run() -> str:\n"
                "    return helper()\n"
            ),
        )
        write_text(custom_repo / "app" / "shared.py", "def helper() -> str:\n    return 'ok'\n")
        write_text(custom_repo / "custom.marker", "enabled\n")
        write_text(
            custom_repo / "repo-context" / "analyzers" / "comment_directives.py",
            (
                "from pathlib import Path\n\n"
                "from lib.analyzers import FileAnalysis\n\n"
                "class CommentDirectiveAnalyzer:\n"
                "    name = 'comment-directives'\n\n"
                "    def supports(self, path: Path) -> bool:\n"
                "        return path.suffix.lower() == '.py'\n\n"
                "    def analyze(self, root: Path, path: Path, rel_path: str, text: str, known_files: set[str]) -> FileAnalysis:\n"
                "        symbols = []\n"
                "        dependencies = []\n"
                "        for line in text.splitlines():\n"
                "            if 'repo-context-symbol:' in line:\n"
                "                symbols.append(line.split('repo-context-symbol:', 1)[1].strip())\n"
                "            if 'repo-context-dependency:' in line:\n"
                "                dependencies.append(line.split('repo-context-dependency:', 1)[1].strip())\n"
                "        return FileAnalysis(symbols=symbols, dependencies=dependencies, tokens=symbols + dependencies)\n\n"
                "class MarkerHintAnalyzer:\n"
                "    name = 'custom-marker'\n\n"
                "    def detect(self, root: Path, files: dict[str, dict]) -> list[str]:\n"
                "        return ['custom-python-stack'] if root.joinpath('custom.marker').exists() else []\n\n"
                "def register(registry) -> None:\n"
                "    registry.register_file_analyzer(CommentDirectiveAnalyzer())\n"
                "    registry.register_project_hint_analyzer(MarkerHintAnalyzer())\n"
            ),
        )
        write_text(
            custom_repo / "repo-context" / "analyzers" / "ignored_by_gitignore.py",
            (
                "def register(registry) -> None:\n"
                "    raise RuntimeError('gitignored analyzer should not be loaded')\n"
            ),
        )
        write_text(
            custom_repo / "repo-context" / "analyzers" / "node_modules" / "ignored_nested.py",
            (
                "def register(registry) -> None:\n"
                "    raise RuntimeError('node_modules analyzer should not be loaded')\n"
            ),
        )
        write_text(
            custom_repo / ".gitignore",
            "app/main.py\nrepo-context/analyzers/ignored_by_gitignore.py\n",
        )

        custom_scan = scan_repository(custom_repo)

        custom_main = custom_scan["files"].get("app/main.py")
        if not custom_main:
            raise AssertionError("Expected custom extension repo to track app/main.py")
        if "custom_hook" not in custom_main["symbols"]:
            raise AssertionError(f"Expected custom analyzer symbol merge, got {custom_main['symbols']}")
        if "app/shared.py" not in custom_main["dependencies"]:
            raise AssertionError(f"Expected custom analyzer dependency merge, got {custom_main['dependencies']}")
        if "custom-python-stack" not in custom_scan["project_hints"]:
            raise AssertionError(f"Expected custom project hint, got {custom_scan['project_hints']}")

        strict_repo = tmp_root / "strict-default-dir"
        write_text(strict_repo / "src" / "main.py", "print('ok')\n")
        write_text(strict_repo / ".codex" / "context" / "manifest.json", "{}\n")
        assert_ok(run_cli("bootstrap", "--root", str(strict_repo)), "bootstrap strict default dir fixture")
        if not strict_repo.joinpath(".repo-context", "manifest.json").exists():
            raise AssertionError("Expected bootstrap to write to .repo-context by default")
        if strict_repo.joinpath(".codex", "context", "index.md").exists():
            raise AssertionError("Bootstrap should not write generated artifacts into legacy context directories")

    print("repo-context tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
