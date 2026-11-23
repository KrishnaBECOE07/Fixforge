from __future__ import annotations

import ast
import hashlib
import os
import re
from pathlib import Path

EXCLUDED = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".fixforge"}
MAX_FILES = 200
MAX_FILE_BYTES = 64_000
MAX_REPO_BYTES = 2_000_000


def safe_path(root: Path, relative: str) -> Path:
    """Reject absolute paths, traversal, Windows drive/ADS syntax, hidden and linked paths."""
    if not relative or "\\" in relative or ":" in relative:
        raise ValueError("Paths must be relative POSIX paths")
    parts = relative.split("/")
    if any(not p or p in {".", ".."} or p.startswith(".") for p in parts):
        raise ValueError("Hidden paths and traversal are forbidden")
    result = root.joinpath(*parts)
    if any(p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction())
           for p in [result, *list(result.parents)[:len(parts)]]):
        raise ValueError("Linked paths are forbidden")
    if not result.resolve().is_relative_to(root.resolve()):
        raise ValueError("Path escapes repository")
    return result


def read_sources(source: Path) -> dict[str, str]:
    if not source.is_dir():
        raise ValueError("Configured repository does not exist")
    files: dict[str, str] = {}
    total = 0
    for directory, dirs, names in os.walk(source, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED and not d.startswith(".")
                         and not Path(directory, d).is_symlink()
                         and not (hasattr(Path(directory, d), "is_junction") and Path(directory, d).is_junction()))
        for name in sorted(names):
            if not name.endswith(".py") or name.startswith("."):
                continue
            path = Path(directory, name)
            if path.is_symlink():
                continue
            relative = path.relative_to(source).as_posix()
            safe_path(source, relative)
            size = path.stat().st_size
            total += size
            if size > MAX_FILE_BYTES or total > MAX_REPO_BYTES or len(files) >= MAX_FILES:
                raise ValueError("Repository exceeds v0.1 limits: 200 Python files / 2 MB / 64 KB per file")
            text = path.read_text(encoding="utf-8")
            files[relative] = text
    if not files:
        raise ValueError("No Python source files found")
    return files


def snapshot(source: Path, destination: Path) -> dict[str, str]:
    files = read_sources(source)
    for relative, text in files.items():
        target = safe_path(destination, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return files


def index_repository(files: dict[str, str], issue: str) -> list[dict]:
    terms = set(re.findall(r"[a-z][a-z0-9_]{2,}", issue.lower()))
    indexed = []
    for path, source in files.items():
        symbols, imports = [], []
        try:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    symbols.append({"name": node.name, "line": node.lineno,
                                    "kind": "class" if isinstance(node, ast.ClassDef) else "function"})
                elif isinstance(node, ast.Import):
                    imports.extend(n.name for n in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.append(node.module)
        except SyntaxError:
            pass
        tokens = set(re.findall(r"[a-z][a-z0-9_]{2,}", (path + " " + source).lower()))
        score = len(terms & tokens) + sum(3 for s in symbols if s["name"].lower() in terms)
        indexed.append(dict(path=path, symbols=symbols, imports=imports,
                            lines=len(source.splitlines()), relevance=score,
                            sha256=hashlib.sha256(source.encode()).hexdigest()))
    return sorted(indexed, key=lambda item: (-item["relevance"], item["path"]))
