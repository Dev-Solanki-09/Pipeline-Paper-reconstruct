"""
Rule 8 Enforcement: AST boundary test verifying that all LLM/VLM/MCP access
goes exclusively through `examforge/llm/`. No other module may import a provider SDK.
"""

from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_LLM_SDKS = {
    "openai",
    "anthropic",
    "google.genai",
    "google.generativeai",
    "groq",
    "litellm",
    "cohere",
    "mistralai",
    "together",
    "replicate",
}


def find_forbidden_imports(file_path: Path) -> list[str]:
    """Parse a python file with AST and report any direct provider SDK imports."""
    violations: list[str] = []
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for sdk in FORBIDDEN_LLM_SDKS:
                    if alias.name == sdk or alias.name.startswith(f"{sdk}."):
                        violations.append(
                            f"{file_path.name}:{node.lineno} imports '{alias.name}' directly"
                        )
        elif isinstance(node, ast.ImportFrom) and node.module:
            for sdk in FORBIDDEN_LLM_SDKS:
                if node.module == sdk or node.module.startswith(f"{sdk}."):
                    violations.append(
                        f"{file_path.name}:{node.lineno} imports from '{node.module}' directly"
                    )
    return violations


def test_rule_8_ast_boundary_enforcement():
    """Verify that NO file outside src/examforge/llm/ imports any LLM provider SDK."""
    src_dir = Path(__file__).parent.parent / "src" / "examforge"
    assert src_dir.exists(), f"Source directory {src_dir} must exist."

    all_violations: list[str] = []
    py_files = list(src_dir.rglob("*.py"))
    assert len(py_files) > 0, "Found zero python files in src/examforge"

    for py_file in py_files:
        # Files inside src/examforge/llm/ are the only permitted location
        if "llm" in py_file.parts:
            continue

        violations = find_forbidden_imports(py_file)
        if violations:
            all_violations.extend(violations)

    assert not all_violations, (
        f"Rule 8 Violation: Found {len(all_violations)} direct provider imports outside "
        f"src/examforge/llm/:\n" + "\n".join(all_violations)
    )


def test_rule_8_detector_catches_violations(tmp_path: Path):
    """Metatest confirming the AST scanner correctly catches forbidden imports."""
    dirty_file = tmp_path / "bad_stage.py"
    dirty_file.write_text(
        "import openai\nfrom anthropic import Anthropic\n",
        encoding="utf-8",
    )
    violations = find_forbidden_imports(dirty_file)
    assert len(violations) == 2
    assert any("openai" in v for v in violations)
    assert any("anthropic" in v for v in violations)
