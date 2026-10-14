"""AST guard enforcing that no exam-specific literals are hardcoded in core stages."""

from __future__ import annotations

import ast
import re
from pathlib import Path

FORBIDDEN_WORDS = {"neet", "jee", "upsc", "gate", "cbse", "aiims", "fiitjee"}
ALLOWLIST_FILE = Path(__file__).parent / "allowlists" / "no_hardcoding_allowlist.txt"


def _load_allowlist() -> set[tuple[str, str]]:
    """Load allowed (file_rel_path, pattern) pairs."""
    allowed = set()
    if not ALLOWLIST_FILE.is_file():
        return allowed

    for line in ALLOWLIST_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        entry = line.split("#")[0].strip()
        if ":" in entry:
            fpath, word = entry.split(":", 1)
            fpath_norm = fpath.strip().replace("\\", "/").lower()
            allowed.add((fpath_norm, word.strip().lower()))
    return allowed


def test_no_hardcoded_exam_literals_in_stages():
    """Scan all AST string constants in src/examforge/stages/ for forbidden literals."""
    stages_dir = Path(__file__).parent.parent / "src" / "examforge" / "stages"
    allowlist = _load_allowlist()
    violations: list[str] = []

    for py_file in stages_dir.glob("*.py"):
        rel_path = py_file.relative_to(stages_dir.parent.parent.parent).as_posix().lower()
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))

        # Identify docstring nodes to skip them
        docstring_nodes = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                docstring_nodes.add(id(node.body[0].value))

        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if id(node) in docstring_nodes:
                    continue  # skip docstrings

                val = node.value
                words = set(re.findall(r"\b[a-zA-Z]+\b", val.lower()))
                matched_forbidden = words.intersection(FORBIDDEN_WORDS)

                for w in matched_forbidden:
                    if (rel_path, w) not in allowlist:
                        lineno = getattr(node, "lineno", "?")
                        violations.append(
                            f"{rel_path}:{lineno}: Forbidden literal '{w}' in {val!r}"
                        )

    assert not violations, (
        f"Found {len(violations)} forbidden hard-coded exam literals in core stages:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )
