"""Shared constants for repository scanning and context generation."""

SOURCE_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".mjs",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".scss",
    ".sh",
    ".sql",
    ".swift",
    ".ts",
    ".tsx",
}

TRACKED_EXTENSIONS = SOURCE_EXTENSIONS | {
    ".cjs",
    ".json",
    ".md",
    ".mdx",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}

JS_TS_EXTENSIONS = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}

IGNORED_DIRS = {
    ".codex",
    ".git",
    ".next",
    ".repo-context",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "out",
    "target",
    "tmp",
    "vendor",
}

IGNORED_FILES = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
}

ENTRYPOINT_NAMES = {
    "app.ts",
    "app.tsx",
    "index.ts",
    "index.tsx",
    "index.js",
    "index.jsx",
    "main.ts",
    "main.tsx",
    "main.js",
    "main.jsx",
    "server.ts",
    "server.js",
    "package.json",
}

ROUTE_ENTRYPOINT_NAMES = {
    "layout.tsx",
    "layout.jsx",
    "layout.js",
    "page.tsx",
    "page.jsx",
    "page.js",
    "route.ts",
    "route.js",
}

HOTSPOT_LOC_THRESHOLD = 400
FAN_PERCENTILE = 0.05
MODULE_SOURCE_THRESHOLD = 3
DEFAULT_CONTEXT_DIRNAME = ".repo-context"
LEGACY_CONTEXT_DIRNAME = ".codex/context"

ROLE_DESCRIPTIONS = {
    "api": "Owns service or HTTP-facing contracts.",
    "config": "Defines repository-wide runtime or tooling configuration.",
    "data": "Stores static definitions, fixtures, or generated inputs.",
    "docs": "Explains system behavior and operational decisions.",
    "domain": "Encodes shared business rules, templates, or core logic.",
    "legacy": "Contains older code paths that likely need careful tracing before edits.",
    "routing": "Declares routes, pages, handlers, or request entrypoints.",
    "scripts": "Automates build, maintenance, or analysis workflows.",
    "tests": "Verifies behavior and protects regressions.",
    "ui": "Renders components, pages, or interaction surfaces.",
    "unknown": "Mixed responsibilities; read module and hotspot briefs before editing.",
}

CHANGE_RECIPES = {
    "api": "Change request/response contracts here before touching callers; verify adjacent modules and tests after edits.",
    "config": "Update config here before changing downstream behavior; review entrypoints that load it.",
    "data": "Treat schema or default changes as wide-impact; verify consumers and any generated outputs.",
    "docs": "Sync docs after behavior changes; prefer linking to module briefs instead of duplicating details.",
    "domain": "Edit types, normalization, and shared helpers here before UI layers; validate affected entrypoints.",
    "legacy": "Rebuild context first, read the hotspot brief, then trace dependents before modifying behavior.",
    "routing": "Change route files together with the domain modules they call; verify SEO, metadata, and tests when relevant.",
    "scripts": "Keep side effects narrow and re-run representative commands after changes.",
    "tests": "Update assertions only after understanding the production contract they protect.",
    "ui": "Change the component surface here, then inspect entrypoints and sibling modules that compose it.",
    "unknown": "Start with the closest hotspot file and adjacent modules before touching implementation.",
}
