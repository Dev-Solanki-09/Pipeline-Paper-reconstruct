"""
Chemical formula parsing, KaTeX/mhchem formatting, and reaction equation balancing.
"""

from __future__ import annotations

import re

# Periodic table elements
ELEMENTS = {
    "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne",
    "Na", "Mg", "Al", "Si", "P", "S", "Cl", "Ar", "K", "Ca",
    "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn",
    "Ga", "Ge", "As", "Se", "Br", "Kr", "Rb", "Sr", "Y", "Zr",
    "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd", "In", "Sn",
    "Sb", "Te", "I", "Xe", "Cs", "Ba", "La", "Ce", "Pr", "Nd",
    "Pm", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb",
    "Lu", "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt", "Au", "Hg",
    "Tl", "Pb", "Bi", "Po", "At", "Rn", "Fr", "Ra", "Ac", "Th",
    "Pa", "U", "Np", "Pu", "Am", "Cm", "Bk", "Cf", "Es", "Fm",
    "Md", "No", "Lr", "Rf", "Db", "Sg", "Bh", "Hs", "Mt", "Ds",
    "Rg", "Cn", "Nh", "Fl", "Mc", "Lv", "Ts", "Og"
}

STATE_SYMBOLS = {"(s)", "(l)", "(g)", "(aq)"}

# Reaction arrow patterns
REACTION_ARROWS = ["->", "→", "<=>", "⇌", r"\rightarrow", r"\rightleftharpoons"]


def is_chemical_formula(s: str) -> bool:
    """Check if token looks like a chemical formula."""
    if not s:
        return False
    raw = s.strip()

    # Reject text containing spaces between words
    if " " in raw and not any(st in raw for st in STATE_SYMBOLS):
        return False

    # Remove state symbols
    for st in STATE_SYMBOLS:
        raw = raw.replace(st, "")
    # Remove charges
    raw = re.sub(r"\^{?[+-]?\d*[+-]?}?", "", raw)
    raw = re.sub(r"[+-]?\d*[+-]$", "", raw)

    if not raw or raw.isnumeric():
        return False

    # A formula must have at least one uppercase element
    parts = re.findall(r"[A-Z][a-z]?", raw)
    if not parts:
        return False

    # Verify all extracted elements exist in periodic table
    if not all(el in ELEMENTS for el in parts):
        return False

    # Reject purely lowercase English prose words
    if raw.isalpha() and raw.islower():
        return False

    # Common English words that accidentally match element sequences
    english_words = {
        "calculate", "the", "work", "force", "energy", "velocity", "total",
        "power", "mass", "time", "speed", "body", "particle", "which",
        "following", "given", "find", "state", "law", "each", "both"
    }
    if raw.lower() in english_words:
        return False

    # Must contain numbers, parentheses, or multiple distinct elements
    has_subscript = bool(re.search(r"\d", raw))
    has_brackets = any(b in raw for b in "()[]")
    has_charge = bool(re.search(r"[+-]", s))
    if has_subscript or has_brackets or has_charge or len(parts) >= 2 or raw in ELEMENTS:
        return True

    return False


def parse_chemical_formula(formula: str) -> tuple[dict[str, int], int]:
    """
    Parse a chemical formula into atom counts and total charge.

    Returns:
        tuple of (atom_counts_dict, net_charge_int)
    """
    s = formula.strip()

    # Extract charge if present (e.g. Fe^{3+}, Fe3+, SO4^{2-}, SO4^2-, Cl-)
    charge = 0
    charge_m = re.search(r"\^{?([+-]?\d*)([+-])}?$", s)
    if not charge_m:
        charge_m = re.search(r"([+-]?\d*)([+-])$", s)

    if charge_m:
        mag_str = charge_m.group(1).replace("+", "").replace("-", "")
        sign_str = charge_m.group(2)
        mag = int(mag_str) if mag_str else 1
        charge = mag if sign_str == "+" else -mag
        s = s[:charge_m.start()].strip()

    # Clean state symbols
    for st in STATE_SYMBOLS:
        s = s.replace(st, "")

    # Parse nested groups e.g. Ca(OH)2 or K4[Fe(CN)6]
    def _parse_segment(seg: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        # Match element followed by count
        for m in re.finditer(r"([A-Z][a-z]?)(?:_\{?(\d+)\}?|(\d+))?", seg):
            elem = m.group(1)
            cnt_str = m.group(2) or m.group(3) or "1"
            cnt = int(cnt_str)
            counts[elem] = counts.get(elem, 0) + cnt
        return counts

    # Handle parentheses/brackets iteratively
    atom_counts: dict[str, int] = {}
    pattern = re.compile(r"[\(\[]([A-Za-z0-9_]+)[\)\]](?:_\{?(\d+)\}?|(\d+))?")
    while True:
        m = pattern.search(s)
        if not m:
            break
        inner = m.group(1)
        mult = int(m.group(2) or m.group(3) or "1")
        inner_counts = _parse_segment(inner)
        for el, cnt in inner_counts.items():
            atom_counts[el] = atom_counts.get(el, 0) + cnt * mult
        s = s[:m.start()] + s[m.end():]

    # Parse remaining outside brackets
    remaining_counts = _parse_segment(s)
    for el, cnt in remaining_counts.items():
        atom_counts[el] = atom_counts.get(el, 0) + cnt

    return atom_counts, charge


def format_chemical_formula(s: str, use_mhchem: bool = False) -> str:
    """Format chemical formula in KaTeX/mhchem or plain LaTeX."""
    if not s:
        return s

    raw = s.strip()
    if use_mhchem:
        return f"\\ce{{{raw}}}"

    # Extract state symbol if any
    state = ""
    for st in STATE_SYMBOLS:
        if st in raw:
            state = f"\\text{{{st}}}"
            raw = raw.replace(st, "").strip()

    # Extract oxidation state e.g. Fe(III)
    ox_m = re.search(r"\(([I|V|X]+)\)", raw)
    if ox_m:
        ox_str = ox_m.group(0)
        base = raw.replace(ox_str, "").strip()
        return f"\\text{{{base}{ox_str}}}{state}"

    # Plain KaTeX formatting: match elements, groups, and numbers
    tokens = re.findall(r"([A-Z][a-z]*|\d+|\([^)]+\)|\[[^\]]+\])", raw)
    pieces: list[str] = []
    for tok in tokens:
        if tok.isdigit():
            pieces.append(f"_{{{tok}}}")
        else:
            pieces.append(f"\\text{{{tok}}}")

    formatted = "".join(pieces)
    # Merge consecutive \text{A}\text{B} -> \text{AB}
    while re.search(r"\\text\{([^}]+)\}\\text\{([^}]+)\}", formatted):
        formatted = re.sub(r"\\text\{([^}]+)\}\\text\{([^}]+)\}", r"\\text{\1\2}", formatted)

    if not formatted:
        formatted = f"\\text{{{raw}}}"

    return f"{formatted}{state}"


def is_chemical_equation(s: str) -> bool:
    """Check if string is a chemical reaction equation."""
    if not s:
        return False
    return any(arrow in s for arrow in ["->", "→", "<=>", "⇌", r"\rightarrow", r"\rightleftharpoons"])


def format_chemical_reaction(s: str, use_mhchem: bool = False) -> str:
    """Format a chemical reaction equation with LaTeX arrow."""
    if not s:
        return s

    text = s.strip()
    if use_mhchem:
        return f"\\ce{{{text}}}"

    # Standardize arrows
    text = text.replace("<=>", r"\rightleftharpoons").replace("⇌", r"\rightleftharpoons")
    text = text.replace("->", r"\rightarrow").replace("→", r"\rightarrow")

    return text


def _split_side(side_str: str) -> list[tuple[int, str]]:
    """Split reaction side into list of (stoichiometric_coefficient, formula) respecting braces."""
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for ch in side_str:
        if ch in "{[(":
            depth += 1
            current.append(ch)
        elif ch in "}])":
            depth -= 1
            current.append(ch)
        elif ch == "+" and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current).strip())

    species: list[tuple[int, str]] = []
    for t in parts:
        if not t:
            continue
        m = re.match(r"^(\d+)\s*(.*)$", t)
        if m:
            coeff = int(m.group(1))
            formula = m.group(2).strip()
        else:
            coeff = 1
            formula = t.strip()
        species.append((coeff, formula))
    return species


def validate_chemical_equation(equation: str) -> tuple[bool, list[str]]:
    """
    Validate atom and charge balance for chemical reaction equations (Rule R07).

    Returns:
        tuple of (is_balanced_bool, list_of_issue_messages)
    """
    if not is_chemical_equation(equation):
        return True, []

    # Find arrow
    arrow = None
    for arr in ["<=>", "⇌", r"\rightleftharpoons", "->", "→", r"\rightarrow"]:
        if arr in equation:
            arrow = arr
            break

    if not arrow:
        return True, []

    left_str, right_str = equation.split(arrow, 1)
    left_species = _split_side(left_str)
    right_species = _split_side(right_str)

    # Calculate atom counts and charges for left side
    left_atoms: dict[str, int] = {}
    left_charge = 0
    for coeff, form in left_species:
        atoms, chg = parse_chemical_formula(form)
        left_charge += coeff * chg
        for el, cnt in atoms.items():
            left_atoms[el] = left_atoms.get(el, 0) + coeff * cnt

    # Calculate atom counts and charges for right side
    right_atoms: dict[str, int] = {}
    right_charge = 0
    for coeff, form in right_species:
        atoms, chg = parse_chemical_formula(form)
        right_charge += coeff * chg
        for el, cnt in atoms.items():
            right_atoms[el] = right_atoms.get(el, 0) + coeff * cnt

    issues: list[str] = []

    # Check atom balance
    all_elements = set(left_atoms.keys()).union(set(right_atoms.keys()))
    for el in sorted(all_elements):
        cnt_l = left_atoms.get(el, 0)
        cnt_r = right_atoms.get(el, 0)
        if cnt_l != cnt_r:
            issues.append(f"Atom balance mismatch for element '{el}': {cnt_l} on left vs {cnt_r} on right")

    # Check charge balance
    if left_charge != right_charge:
        issues.append(f"Charge balance mismatch: {left_charge} on left vs {right_charge} on right")

    return len(issues) == 0, issues
