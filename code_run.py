#!/usr/bin/env python3
"""NDJSON sidecar — source-code project detector + language tagger.

For each immediate child folder of `--root`, decide whether it looks like
a source-code project (presence of marker files: package.json,
Cargo.toml, pyproject.toml, go.mod, pom.xml, build.gradle, *.sln, .git,
etc.) and, if so, tag its primary language by extension count over the
project tree (Pygments-aware to pick the right name).

Optional `rename` mode moves the project folder into
`Code/{language}/{name}`.

NDJSON events:
    {"event":"start","root":"..."}
    {"event":"progress","scanned":N,"projects":N,"stage":"<msg>"}
    {"event":"item","path":"...","status":"matched|skipped|error",
        "name":"...","language":"...","markers":["..."],"file_count":N,
        "size_bytes":N,"primary_ext":"...","new_path":"..."?}
    {"event":"complete","total_count":N,"matched_count":N,"renamed_count":N}
    {"event":"error","code":"...","message":"..."}
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
from collections import Counter

# Marker files that strongly signal a project root.
MARKERS = {
    "package.json": "JavaScript",
    "package-lock.json": "JavaScript",
    "yarn.lock": "JavaScript",
    "pnpm-lock.yaml": "JavaScript",
    "tsconfig.json": "TypeScript",
    "Cargo.toml": "Rust",
    "pyproject.toml": "Python",
    "setup.py": "Python",
    "requirements.txt": "Python",
    "Pipfile": "Python",
    "go.mod": "Go",
    "pom.xml": "Java",
    "build.gradle": "Java",
    "build.gradle.kts": "Kotlin",
    "settings.gradle": "Java",
    "Gemfile": "Ruby",
    "composer.json": "PHP",
    "mix.exs": "Elixir",
    "stack.yaml": "Haskell",
    "Project.toml": "Julia",
    "DESCRIPTION": "R",
    "Makefile": "C",
    "CMakeLists.txt": "C++",
    "Podfile": "Swift",
    "Package.swift": "Swift",
    "shard.yml": "Crystal",
    "deno.json": "TypeScript",
    "bun.lockb": "TypeScript",
    ".git": "git",
    ".hg": "hg",
    ".svn": "svn",
}

# Solution / project files (suffix-matched).
SUFFIX_MARKERS = {
    ".sln": "C#",
    ".csproj": "C#",
    ".vbproj": "VB.NET",
    ".fsproj": "F#",
    ".vcxproj": "C++",
    ".xcodeproj": "Swift",
}

# Folders we ignore entirely when counting files in a project.
IGNORE_DIRS = frozenset({
    "node_modules", "vendor", "dist", "build", "target", "out",
    ".git", ".hg", ".svn", ".venv", "venv", "__pycache__", ".idea",
    ".vscode", ".vs", "bin", "obj", "Pods", ".gradle", ".cargo",
    ".next", ".nuxt", "_build",
})

# Extension → display language. Pygments would do this, but our list keeps
# the sidecar lightweight and predictable.
EXT_LANGUAGE = {
    ".py": "Python", ".pyx": "Python", ".pyi": "Python",
    ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".rs": "Rust",
    ".go": "Go",
    ".java": "Java",
    ".kt": "Kotlin", ".kts": "Kotlin",
    ".scala": "Scala",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".vb": "VB.NET",
    ".fs": "F#", ".fsx": "F#",
    ".cpp": "C++", ".cc": "C++", ".cxx": "C++", ".hpp": "C++", ".hxx": "C++", ".hh": "C++",
    ".c": "C", ".h": "C",
    ".m": "Objective-C", ".mm": "Objective-C++",
    ".swift": "Swift",
    ".ex": "Elixir", ".exs": "Elixir",
    ".erl": "Erlang",
    ".hs": "Haskell",
    ".jl": "Julia",
    ".r": "R", ".R": "R",
    ".lua": "Lua",
    ".pl": "Perl", ".pm": "Perl",
    ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell",
    ".ps1": "PowerShell", ".psm1": "PowerShell",
    ".bat": "Batch", ".cmd": "Batch",
    ".dart": "Dart",
    ".cr": "Crystal",
    ".nim": "Nim",
    ".zig": "Zig",
    ".vala": "Vala",
    ".elm": "Elm",
    ".clj": "Clojure", ".cljs": "ClojureScript",
    ".sql": "SQL",
    ".html": "HTML", ".htm": "HTML",
    ".css": "CSS", ".scss": "CSS", ".sass": "CSS", ".less": "CSS",
    ".vue": "Vue",
    ".svelte": "Svelte",
}


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _safe_name(value: str) -> str:
    if not value:
        return "Unknown"
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value))
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned[:180] or "Unknown"


def _detect_project(path: str) -> dict | None:
    """Inspect a folder for marker files; return project info or None."""
    if not os.path.isdir(path):
        return None

    found_markers: list[str] = []
    marker_languages: list[str] = []

    try:
        entries = os.listdir(path)
    except (PermissionError, OSError):
        return None

    for entry in entries:
        if entry in MARKERS:
            found_markers.append(entry)
            marker_languages.append(MARKERS[entry])
        else:
            ext = os.path.splitext(entry)[1].lower()
            for suf, lang in SUFFIX_MARKERS.items():
                if entry.lower().endswith(suf):
                    found_markers.append(entry)
                    marker_languages.append(lang)
                    break

    if not found_markers:
        return None

    # Walk the project to count file extensions for primary language.
    ext_counts: Counter = Counter()
    file_count = 0
    size_total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS
                       and not d.startswith(".")]
        for f in filenames:
            ext = os.path.splitext(f)[1].lower()
            if ext in EXT_LANGUAGE:
                ext_counts[ext] += 1
                file_count += 1
                try:
                    size_total += os.path.getsize(os.path.join(dirpath, f))
                except OSError:
                    pass

    primary_ext = ""
    primary_lang = ""
    if ext_counts:
        primary_ext, _ = ext_counts.most_common(1)[0]
        primary_lang = EXT_LANGUAGE.get(primary_ext, "")

    # Fall back to the marker-implied language if the tree was empty.
    if not primary_lang:
        non_vcs_markers = [m for m in marker_languages
                           if m not in ("git", "hg", "svn")]
        primary_lang = (non_vcs_markers[0] if non_vcs_markers
                        else (marker_languages[0] if marker_languages else "Other"))

    return {
        "name": os.path.basename(path),
        "language": primary_lang,
        "markers": found_markers[:8],
        "file_count": file_count,
        "size_bytes": size_total,
        "primary_ext": primary_ext,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="NDJSON source-code project detector")
    parser.add_argument("--root", required=True)
    parser.add_argument("--mode", choices=["preview", "rename"], default="preview")
    parser.add_argument("--rename-pattern", default="Code/{language}/{name}")
    parser.add_argument("--rename-root", default="")
    args = parser.parse_args()

    if not os.path.isdir(args.root):
        _emit({"event": "error", "code": "root_not_found",
               "message": f"Root not found: {args.root}"})
        return 2

    try:
        children = [os.path.join(args.root, d) for d in os.listdir(args.root)]
    except PermissionError as exc:
        _emit({"event": "error", "code": "permission_denied", "message": str(exc)})
        return 5

    children = [c for c in children if os.path.isdir(c)]
    _emit({"event": "start", "root": args.root, "candidates_found": len(children)})

    state = {"scanned": 0, "matched": 0, "renamed": 0, "last_progress": 0.0}

    for child in children:
        state["scanned"] += 1
        now = time.monotonic()
        if now - state["last_progress"] >= 0.2:
            state["last_progress"] = now
            _emit({"event": "progress",
                   "scanned": state["scanned"],
                   "projects": state["matched"],
                   "stage": os.path.basename(child)[:200]})
        try:
            info = _detect_project(child)
            if info is None:
                continue

            new_path = None
            if args.mode == "rename":
                rel = args.rename_pattern.format(
                    language=_safe_name(info["language"]),
                    name=_safe_name(info["name"]))
                dest_root = args.rename_root or args.root
                new_path = os.path.normpath(os.path.join(dest_root, rel))
                if os.path.abspath(new_path) != os.path.abspath(child):
                    os.makedirs(os.path.dirname(new_path), exist_ok=True)
                    if not os.path.exists(new_path):
                        os.rename(child, new_path)
                        state["renamed"] += 1
                        info["new_path"] = new_path

            state["matched"] += 1
            _emit({"event": "item", "path": child, "status": "matched", **info})

        except Exception as exc:
            _emit({"event": "item", "path": child, "status": "error",
                   "message": f"{type(exc).__name__}: {exc}"})

    _emit({"event": "complete",
           "total_count": state["scanned"],
           "matched_count": state["matched"],
           "renamed_count": state["renamed"]})
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        _emit({"event": "error", "code": "cancelled", "message": "Cancelled."})
        raise SystemExit(130)
    except Exception as exc:
        _emit({"event": "error", "code": "crashed",
               "message": f"{type(exc).__name__}: {exc}",
               "traceback": traceback.format_exc()})
        raise SystemExit(1)
