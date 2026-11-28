from __future__ import annotations

import ast
import difflib
from pathlib import Path

from .intelligence import MAX_FILE_BYTES, safe_path

BLOCKED_MODULES = {"subprocess", "socket", "ctypes", "multiprocessing", "importlib", "shutil", "requests", "urllib", "http", "pickle"}
BLOCKED_CALLS = {"exec", "eval", "compile", "__import__", "system", "popen", "remove", "unlink", "rmtree"}
REGRESSION_PATH = "tests/test_fixforge_regression.py"


def validate_proposal(root: Path, originals: dict[str, str], proposal: dict, regression_path: str) -> list[dict]:
    edits = proposal.get("edits")
    if not isinstance(edits, list) or not 1 <= len(edits) <= 5:
        raise ValueError("A patch must change between one and five production files")
    regression = proposal.get("regression")
    seen, files = set(), []
    for edit in edits:
        path, content = edit.get("path", ""), edit.get("content")
        safe_path(root, path)
        if path in seen or path not in originals or not path.endswith(".py"):
            raise ValueError("Edits must target distinct indexed Python files")
        if path.startswith("tests/") or any(p.startswith("test") for p in Path(path).parts) or Path(path).name == "conftest.py":
            raise ValueError("Existing tests cannot be modified")
        if not isinstance(content, str) or len(content.encode()) > MAX_FILE_BYTES:
            raise ValueError("Patch content is missing or exceeds size limit")
        if content == originals[path]:
            raise ValueError("Patch does not change production code")
        try:
            _scan(content)
        except SyntaxError as error:
            raise ValueError(f"Proposed production edit is invalid Python at line {error.lineno or '?'}") from None
        seen.add(path)
        files.append(_change(path, originals[path], content, "modified"))
    try:
        validate_regression(regression, originals, regression_path)
    except SyntaxError as error:
        raise ValueError(f"Proposed regression is invalid Python at line {error.lineno or '?'}") from None
    files.append(_change(regression_path, "", regression, "added"))
    return files


def validate_regression(regression: object, originals: dict[str, str], path: str = REGRESSION_PATH) -> None:
    if not isinstance(regression, str) or len(regression.encode()) > MAX_FILE_BYTES:
        raise ValueError("A bounded regression test is required")
    if path in originals:
        raise ValueError("Regression path already exists")
    tree = _scan(regression)
    if not any(isinstance(n, ast.ClassDef) and any(
        (isinstance(b, ast.Attribute) and b.attr == "TestCase") or (isinstance(b, ast.Name) and b.id == "TestCase")
        for b in n.bases) for n in ast.walk(tree)):
        raise ValueError("Regression must define a unittest.TestCase")
    if not any(isinstance(n, ast.FunctionDef) and n.name.startswith("test_") for n in ast.walk(tree)):
        raise ValueError("Regression must define at least one test")
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and n.attr in {"skip", "skipIf", "skipUnless", "expectedFailure", "skipTest"}:
            raise ValueError("Regression tests cannot skip or expect failure")


def _scan(source: str) -> ast.AST:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports = [n.name.split(".")[0] for n in node.names]
        elif isinstance(node, ast.ImportFrom):
            imports = [(node.module or "").split(".")[0]]
        else:
            imports = []
        if set(imports) & BLOCKED_MODULES:
            raise ValueError("Patch uses a disallowed import")
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
            if name in BLOCKED_CALLS:
                raise ValueError(f"Patch uses disallowed call: {name}")
    return tree


def _change(path: str, before: str, after: str, kind: str) -> dict:
    lines = difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                 fromfile=f"a/{path}" if kind != "added" else "/dev/null",
                                 tofile=f"b/{path}")
    diff = "".join(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n" for line in lines)
    lines = diff.splitlines()
    return dict(path=path, before=before, after=after, kind=kind, diff=diff,
                additions=sum(s.startswith("+") and not s.startswith("+++") for s in lines),
                deletions=sum(s.startswith("-") and not s.startswith("---") for s in lines))
