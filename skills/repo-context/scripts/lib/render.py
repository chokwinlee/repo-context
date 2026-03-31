"""Render context pack artifacts from scan results."""

from __future__ import annotations

from pathlib import Path

from .constants import CHANGE_RECIPES, ROLE_DESCRIPTIONS
from .utils import short_hash, slugify_path, stable_sorted, tokenize


def module_doc_relpath(module_path: str) -> str:
    return f"modules/{slugify_path(module_path)}.md"


def file_doc_relpath(file_path: str) -> str:
    return f"files/{slugify_path(file_path)}.md"


def expected_doc_paths(scan: dict) -> dict[str, str]:
    docs = {"index.md": "index.md", "repo_map.md": "repo-map.md"}
    docs.update({f"module:{module_path}": module_doc_relpath(module_path) for module_path in scan["modules"]})
    docs.update({f"file:{file_path}": file_doc_relpath(file_path) for file_path in scan["hotspot_files"]})
    return docs


def _responsibility_for_module(module: dict, scan: dict) -> str:
    role = module["role"]
    entrypoints = module["entrypoints"]
    if entrypoints:
        lead = Path(entrypoints[0]).name
        return f"{ROLE_DESCRIPTIONS.get(role, ROLE_DESCRIPTIONS['unknown'])} Primary entrypoint: `{lead}`."
    return ROLE_DESCRIPTIONS.get(role, ROLE_DESCRIPTIONS["unknown"])


def _module_keywords(module: dict, scan: dict) -> list[str]:
    tokens: list[str] = []
    for file_path in module["files"]:
        tokens.extend(scan["files"][file_path]["tokens"])
    return stable_sorted(tokens)[:12]


def render_module_brief(module: dict, scan: dict) -> str:
    lines = [f"# Module: `{module['path']}`", "", "## Summary", ""]
    lines.append(f"- Role: `{module['role']}`")
    lines.append(f"- Responsibility: {_responsibility_for_module(module, scan)}")
    lines.append(f"- Scope: {module['file_count']} source files, {module['total_loc']} non-empty LOC")
    lines.append(f"- Fingerprint: `{short_hash(module['fingerprint'])}`")
    if module["hotspots"]:
        lines.append(
            f"- Hotspots: {', '.join(f'[`{path}`](../{file_doc_relpath(path)})' for path in module['hotspots'][:5])}"
        )
    lines.extend(["", "## Read First", ""])
    for entrypoint in module["entrypoints"][:5]:
        lines.append(f"- `{entrypoint}`")
    if not module["entrypoints"]:
        for file_path in module["files"][:5]:
            lines.append(f"- `{file_path}`")
    lines.extend(["", "## Export Surface", ""])
    if module["exports"]:
        for export_name in module["exports"][:12]:
            lines.append(f"- `{export_name}`")
    else:
        lines.append("- No explicit export symbols detected; rely on file paths and callers.")
    lines.extend(["", "## Invariants", ""])
    lines.append(f"- {CHANGE_RECIPES.get(module['role'], CHANGE_RECIPES['unknown'])}")
    if module["adjacent_modules"]:
        lines.append(
            f"- Coordinate with adjacent modules when changing public surface: {', '.join(f'`{item}`' for item in module['adjacent_modules'][:8])}."
        )
    if _module_keywords(module, scan):
        lines.append(f"- Repeated concepts: {', '.join(f'`{token}`' for token in _module_keywords(module, scan))}.")
    lines.extend(["", "## Adjacent Modules", ""])
    if module["adjacent_modules"]:
        for adjacent in module["adjacent_modules"][:10]:
            lines.append(f"- [`{adjacent}`](../{module_doc_relpath(adjacent)})")
    else:
        lines.append("- No cross-module imports detected from this module.")
    lines.extend(["", "## Files", ""])
    for file_path in module["files"][:12]:
        marker = " hotspot" if scan["files"][file_path]["hotspot"] else ""
        lines.append(f"- `{file_path}` ({scan['files'][file_path]['loc']} LOC,{marker.strip() or ' regular'})")
    return "\n".join(lines) + "\n"


def render_hotspot_brief(file_record: dict, scan: dict, dependents: list[str]) -> str:
    lines = [f"# Hotspot File: `{file_record['path']}`", "", "## Summary", ""]
    lines.append(f"- Role: `{file_record['role']}`")
    lines.append(f"- LOC: {file_record['loc']}")
    lines.append(f"- Fingerprint: `{short_hash(file_record['sha256'])}`")
    lines.append(f"- Why hot: {', '.join(file_record['hotspot_reasons'])}")
    if file_record.get("module"):
        lines.append(f"- Module: [`{file_record['module']}`](../{module_doc_relpath(file_record['module'])})")
    lines.extend(["", "## Export Surface", ""])
    if file_record["exports"]:
        for export_name in file_record["exports"][:12]:
            lines.append(f"- `{export_name}`")
    else:
        lines.append("- No explicit export symbols detected.")
    lines.extend(["", "## Internal Dependencies", ""])
    if file_record["internal_imports"]:
        for dependency in file_record["internal_imports"][:10]:
            lines.append(f"- `{dependency}`")
    else:
        lines.append("- No internal imports detected.")
    lines.extend(["", "## Dependents", ""])
    if dependents:
        for dependent in dependents[:10]:
            lines.append(f"- `{dependent}`")
    else:
        lines.append("- No internal dependents detected.")
    lines.extend(["", "## Edit Guidance", ""])
    lines.append(f"- {CHANGE_RECIPES.get(file_record['role'], CHANGE_RECIPES['unknown'])}")
    if file_record["fan_in"]:
        lines.append(f"- Fan-in is `{file_record['fan_in']}`; treat interface edits as potentially wide-impact.")
    if file_record["fan_out"]:
        lines.append(f"- Fan-out is `{file_record['fan_out']}`; inspect internal dependencies before refactoring.")
    return "\n".join(lines) + "\n"


def render_repo_map(scan: dict) -> str:
    lines = ["# Repo Map", "", "## Summary", ""]
    frameworks = ", ".join(f"`{item}`" for item in scan["frameworks"]) if scan["frameworks"] else "`unknown`"
    lines.append(f"- Framework hints: {frameworks}")
    lines.append(f"- Tracked files: {scan['stats']['tracked_files']} (`{scan['stats']['source_files']}` source)")
    lines.append(f"- Modules: {scan['stats']['modules']}")
    lines.append(f"- Hotspots: {scan['stats']['hotspots']}")
    lines.extend(["", "## Top Directories", ""])
    for directory in scan["top_level_dirs"][:12]:
        lines.append(
            f"- `{directory['path']}`: {directory['file_count']} tracked files, {directory['source_count']} source files, {directory['loc']} LOC"
        )
    lines.extend(["", "## Entry Points", ""])
    for path in scan["entrypoints"][:15]:
        lines.append(f"- `{path}`")
    if not scan["entrypoints"]:
        lines.append("- No standard entrypoints detected.")
    lines.extend(["", "## Hot Files", ""])
    for path in scan["hotspot_files"][:12]:
        lines.append(
            f"- [`{path}`](./{file_doc_relpath(path)}): {scan['files'][path]['loc']} LOC, {', '.join(scan['files'][path]['hotspot_reasons'])}"
        )
    if not scan["hotspot_files"]:
        lines.append("- No hotspot files crossed the default thresholds.")
    lines.extend(["", "## Change Recipes", ""])
    present_roles = stable_sorted(module["role"] for module in scan["modules"].values())
    for role in present_roles[:8]:
        lines.append(f"- `{role}`: {CHANGE_RECIPES.get(role, CHANGE_RECIPES['unknown'])}")
    return "\n".join(lines) + "\n"


def render_index(scan: dict) -> str:
    lines = ["# Context Pack Index", "", "## Read Order", ""]
    lines.append("- Start with [`repo-map.md`](./repo-map.md).")
    lines.append("- Open the most relevant module brief next.")
    lines.append("- Read hotspot file briefs before opening large implementation files.")
    lines.append("- Re-run `repo_context.py refresh --root <repo>` after major edits.")
    lines.extend(["", "## Modules", ""])
    for module_path, module in sorted(scan["modules"].items(), key=lambda item: (-item[1]["total_loc"], item[0]))[:24]:
        keyword_tokens = _module_keywords(module, scan)
        keyword_suffix = f" | keywords: {', '.join(keyword_tokens[:6])}" if keyword_tokens else ""
        lines.append(
            f"- [`{module_path}`](./{module_doc_relpath(module_path)}): role `{module['role']}`, {module['file_count']} files{keyword_suffix}"
        )
    lines.extend(["", "## Hotspot Files", ""])
    if scan["hotspot_files"]:
        for file_path in scan["hotspot_files"][:12]:
            lines.append(f"- [`{file_path}`](./{file_doc_relpath(file_path)})")
    else:
        lines.append("- No hotspot file briefs are currently required.")
    return "\n".join(lines) + "\n"


def build_context_pack(scan: dict, mode: str) -> tuple[dict[str, str], dict, dict]:
    docs: dict[str, str] = {
        "index.md": render_index(scan),
        "repo-map.md": render_repo_map(scan),
    }

    reverse_imports: dict[str, list[str]] = {}
    for file_path, file_record in scan["files"].items():
        for dependency in file_record["internal_imports"]:
            reverse_imports.setdefault(dependency, []).append(file_path)

    for module_path, module in scan["modules"].items():
        docs[module_doc_relpath(module_path)] = render_module_brief(module, scan)
    for file_path in scan["hotspot_files"]:
        docs[file_doc_relpath(file_path)] = render_hotspot_brief(
            scan["files"][file_path],
            scan,
            sorted(reverse_imports.get(file_path, [])),
        )

    manifest = {
        "version": 1,
        "mode": mode,
        "generated_at": scan["generated_at"],
        "frameworks": scan["frameworks"],
        "thresholds": scan["thresholds"],
        "stats": scan["stats"],
        "docs": expected_doc_paths(scan),
        "freshness": {
            "status": "fresh",
            "tracked_files": scan["stats"]["tracked_files"],
        },
    }

    symbol_map = {
        "version": 1,
        "generated_at": scan["generated_at"],
        "frameworks": scan["frameworks"],
        "thresholds": scan["thresholds"],
        "files": scan["files"],
        "modules": scan["modules"],
        "hotspot_files": scan["hotspot_files"],
        "entrypoints": scan["entrypoints"],
        "top_level_dirs": scan["top_level_dirs"],
    }
    return docs, symbol_map, manifest
