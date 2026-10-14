"""
Delimiter balance, brace matching, and KaTeX compatibility validation.
"""

from __future__ import annotations

import re


def validate_math_delimiters(text: str) -> tuple[bool, list[str]]:
    """
    Validate that $ and $$ math delimiters are properly balanced.

    Returns:
        tuple of (is_valid_bool, list_of_issue_messages)
    """
    if not text:
        return True, []

    issues: list[str] = []

    # Check for double-dollar pairs
    # Replace $$ with a placeholder to isolate single dollars
    placeholder_text = re.sub(r"\$\$(.*?)\$\$", " ", text, flags=re.DOTALL)

    # Check if any unmatched $$ remain
    if "$$" in placeholder_text:
        issues.append("Unclosed double-dollar ($$) display math delimiter")

    # Check remaining single dollars
    single_dollars = placeholder_text.count("$")
    if single_dollars % 2 != 0:
        issues.append(f"Odd number of dollar delimiters ({single_dollars}) in text")

    return len(issues) == 0, issues


def validate_latex_syntax(text: str) -> tuple[bool, list[str]]:
    """
    Validate LaTeX brace balance and basic syntax structure.

    Returns:
        tuple of (is_valid_bool, list_of_issue_messages)
    """
    if not text:
        return True, []

    issues: list[str] = []

    # 1. Check brace matching depth
    depth = 0
    for idx, ch in enumerate(text):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                issues.append(f"Unexpected closing brace '}}' at character offset {idx}")
                break

    if depth > 0:
        issues.append(f"Unclosed opening brace '{{' (depth={depth})")

    # 2. Check \begin{} and \end{} matching
    begins = re.findall(r"\\begin\{([^}]+)\}", text)
    ends = re.findall(r"\\end\{([^}]+)\}", text)
    if begins != ends:
        issues.append(f"Mismatched LaTeX environments: begins={begins}, ends={ends}")

    return len(issues) == 0, issues
