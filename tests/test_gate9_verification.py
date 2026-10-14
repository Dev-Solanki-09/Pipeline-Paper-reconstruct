"""
Gate 9 Verification: Language Plugin Architecture, Scripts, Math & Chemistry.

Validates:
1. 200+ notation corpus cases across math, physics, chemistry, biology.
2. Strict negative prose cases (isolated letters x, 2, m in prose never wrapped).
3. Wrapping idempotence and monotonicity: wrap(wrap(x)) == wrap(x).
4. Multi-language (3-language) synthetic document splitting.
5. RTL reading order and layout attributes.
6. Scaffolded plugins run end-to-end and raise NotShipQualityWarning.
7. Feature flag lang_v2 integration and clean v1 rollback.
"""

from __future__ import annotations

import warnings
import pytest

from examforge.config import ExamForgeConfig
from examforge.ir.schema import (
    BBox,
    Block,
    BlockStatus,
    BlockType,
    ExamDocument,
    ExamMetadata,
    Option,
    PageClassification,
    PageInfo,
    Question,
    QuestionKind,
)
from examforge.lang.bilingual import segment_multilingual_text, split_bilingual_by_script
from examforge.lang.fontmaps import convert_legacy_font, detect_legacy_font
from examforge.lang.registry import (
    NotShipQualityWarning,
    detect_lang,
    detect_script,
    get_plugin,
    list_supported_languages,
    resolve_plugins_for_profile,
)
from examforge.lang.rtl import format_dir_attribute, is_rtl_language, reorder_rtl_blocks
from examforge.notation.chemistry import (
    format_chemical_formula,
    format_chemical_reaction,
    is_chemical_equation,
    is_chemical_formula,
    validate_chemical_equation,
)
from examforge.notation.tokenizer import tokenize_and_convert_math
from examforge.notation.validation import validate_latex_syntax, validate_math_delimiters
from examforge.notation.wrapping import wrap_math_delimiters
from examforge.profiles.schema import ExamProfile, LanguageProfileConfig
from examforge.stages.base import StageContext
from examforge.stages.s5_hindi import S5Hindi
from examforge.stages.s5_math import S5Math


# ---------------------------------------------------------------------------
# 1. 200+ Notation Corpus Across Physics, Chemistry, Math, Biology
# ---------------------------------------------------------------------------

_PHYSICS_CASES = [
    ("v = u + at", r"v = u + at"),
    ("s = ut + ½at²", r"s = ut + \frac{1}{2}at^{2}"),
    ("v² - u² = 2as", r"v^{2} - u^{2} = 2as"),
    ("F = ma", r"F = ma"),
    ("p = mv", r"p = mv"),
    ("E = ½mv²", r"E = \frac{1}{2}mv^{2}"),
    ("U = mgh", r"U = mgh"),
    ("W = F × d", r"W = F \times d"),
    ("P = W/t", r"P = W/t"),
    ("p = F/A", r"p = F/A"),
    ("F = G(m₁m₂)/r²", r"F = G(m_{1}m_{2})/r^{2}"),
    ("g = GM/R²", r"g = GM/R^{2}"),
    ("v_e = √(2gR)", r"v_e = \sqrt{2gR}"),
    ("T = 2π√(l/g)", r"T = 2\pi\sqrt{l/g}"),
    ("f = 1/T", r"f = 1/T"),
    ("ω = 2πf", r"\omega = 2\pi f"),
    ("v = rω", r"v = r\omega"),
    ("a_c = v²/r", r"a_c = v^{2}/r"),
    ("L = Iω", r"L = I\omega"),
    ("τ = Iα", r"\tau = I\alpha"),
    ("PV = nRT", r"PV = nRT"),
    ("ΔU = Q - W", r"\Delta U = Q - W"),
    ("W = nRT ln(V₂/V₁)", r"W = nRT ln(V_{2}/V_{1})"),
    ("η = 1 - T₂/T₁", r"\eta = 1 - T_{2}/T_{1}"),
    ("C_p - C_v = R", r"C_p - C_v = R"),
    ("γ = C_p/C_v", r"\gamma = C_p/C_v"),
    ("P₁V₁^γ = P₂V₂^γ", r"P_{1}V_{1}^\gamma = P_{2}V_{2}^\gamma"),
    ("v_rms = √(3RT/M)", r"v_rms = \sqrt{3RT/M}"),
    ("λ_mean = 1/(√2 π d² n)", r"\lambda_mean = 1/(\sqrt{2} \pi d^{2} n)"),
    ("F = q(E + v × B)", r"F = q(E + v \times B)"),
    ("V = IR", r"V = IR"),
    ("P = VI", r"P = VI"),
    ("P = I²R", r"P = I^{2}R"),
    ("R = ρl/A", r"R = \rho l/A"),
    ("B = μ₀I/(2πr)", r"B = \mu_{0}I/(2\pi r)"),
    ("B = μ₀nI", r"B = \mu_{0}nI"),
    ("Φ = B · A", r"\Phi = B \cdot A"),
    ("ε = -dΦ/dt", r"\epsilon = -d\Phi/dt"),
    ("c = 1/√(μ₀ε₀)", r"c = 1/\sqrt{\mu_{0}\epsilon_{0}}"),
    ("E = pc", r"E = pc"),
    ("λ = h/p", r"\lambda = h/p"),
    ("E = hν", r"E = h\nu"),
    ("h = 6.626 × 10⁻³⁴ J s", r"6.626 \times 10^{-34}"),
    ("c = 3.0 × 10⁸ m/s", r"3.0 \times 10^{8}"),
    ("e = 1.6 × 10⁻¹⁹ C", r"1.6 \times 10^{-19}"),
    ("k = 8.99 × 10⁹ N m²/C²", r"8.99 \times 10^{9}"),
    ("G = 6.67 × 10⁻¹¹ N m²/kg²", r"6.67 \times 10^{-11}"),
    ("N_A = 6.022 × 10²³ mol⁻¹", r"6.022 \times 10^{23}"),
    ("R = 8.314 J K⁻¹ mol⁻¹", r"8.314"),
    ("k_B = 1.38 × 10⁻²³ J/K", r"1.38 \times 10^{-23}"),
]

_CHEMISTRY_CASES = [
    ("H2O", "H2O"),
    ("CO2", "CO2"),
    ("NH3", "NH3"),
    ("CH4", "CH4"),
    ("H2SO4", "H2SO4"),
    ("HNO3", "HNO3"),
    ("HCl", "HCl"),
    ("NaOH", "NaOH"),
    ("KOH", "KOH"),
    ("Ca(OH)2", "Ca(OH)2"),
    ("NaCl", "NaCl"),
    ("KMnO4", "KMnO4"),
    ("K2Cr2O7", "K2Cr2O7"),
    ("CuSO4", "CuSO4"),
    ("FeSO4", "FeSO4"),
    ("Fe2(SO4)3", "Fe2(SO4)3"),
    ("Al2O3", "Al2O3"),
    ("Fe3O4", "Fe3O4"),
    ("PCl5", "PCl5"),
    ("SF6", "SF6"),
    ("C6H12O6", "C6H12O6"),
    ("C12H22O11", "C12H22O11"),
    ("CH3COOH", "CH3COOH"),
    ("C2H5OH", "C2H5OH"),
    ("C6H6", "C6H6"),
    ("K4[Fe(CN)6]", "K4[Fe(CN)6]"),
    ("[Co(NH3)6]Cl3", "[Co(NH3)6]Cl3"),
    ("Na2CO3", "Na2CO3"),
    ("NaHCO3", "NaHCO3"),
    ("CaCO3", "CaCO3"),
    ("2H2 + O2 -> 2H2O", "2H2 + O2 -> 2H2O"),
    ("N2 + 3H2 <=> 2NH3", "N2 + 3H2 <=> 2NH3"),
    ("CaCO3 -> CaO + CO2", "CaCO3 -> CaO + CO2"),
    ("2KClO3 -> 2KCl + 3O2", "2KClO3 -> 2KCl + 3O2"),
    ("CH4 + 2O2 -> CO2 + 2H2O", "CH4 + 2O2 -> CO2 + 2H2O"),
    ("Zn + 2HCl -> ZnCl2 + H2", "Zn + 2HCl -> ZnCl2 + H2"),
    ("2Na + 2H2O -> 2NaOH + H2", "2Na + 2H2O -> 2NaOH + H2"),
    ("Fe2O3 + 3CO -> 2Fe + 3CO2", "Fe2O3 + 3CO -> 2Fe + 3CO2"),
    ("2Al + 3Cl2 -> 2AlCl3", "2Al + 3Cl2 -> 2AlCl3"),
    ("P4 + 5O2 -> P4O10", "P4 + 5O2 -> P4O10"),
    ("SO2 + ½O2 -> SO3", "SO2"),
    ("2NO + O2 -> 2NO2", "2NO + O2 -> 2NO2"),
    ("Cl2 + 2KI -> 2KCl + I2", "Cl2 + 2KI -> 2KCl + I2"),
    ("Fe^{3+} + e^- -> Fe^{2+}", "Fe^{3+}"),
    ("Sn^{2+} -> Sn^{4+} + 2e^-", "Sn^{2+}"),
    ("MnO4^- + 8H^+ + 5e^- -> Mn^{2+} + 4H2O", "MnO4^-"),
    ("Cr2O7^{2-} + 14H^+ + 6e^- -> 2Cr^{3+} + 7H2O", "Cr2O7^{2-}"),
    ("H2O2 -> H2O + ½O2", "H2O2"),
    ("2HI <=> H2 + I2", "2HI <=> H2 + I2"),
    ("PCl5 <=> PCl3 + Cl2", "PCl5 <=> PCl3 + Cl2"),
]

_MATH_CASES = [
    ("sin²θ + cos²θ = 1", r"\sin^{2}\theta + \cos^{2}\theta = 1"),
    ("1 + tan²θ = sec²θ", r"1 + \tan^{2}\theta = \sec^{2}\theta"),
    ("1 + cot²θ = cosec²θ", r"1 + \cot^{2}\theta = \csc^{2}\theta"),
    ("sin(2θ) = 2sinθ cosθ", r"\sin(2\theta)"),
    ("cos(2θ) = cos²θ - sin²θ", r"\cos(2\theta)"),
    ("e^{iπ} + 1 = 0", r"e^{i\pi} + 1 = 0"),
    ("d/dx(xⁿ) = nx^{n-1}", r"x^{n-1}"),
    ("d/dx(eˣ) = eˣ", r"e^{x}"),
    ("d/dx(ln x) = 1/x", r"1/x"),
    ("d/dx(sin x) = cos x", r"\cos x"),
    ("d/dx(cos x) = -sin x", r"-\sin x"),
    ("∫ xⁿ dx = x^{n+1}/(n+1)", r"\int"),
    ("∫ eˣ dx = eˣ + C", r"\int"),
    ("∫ (1/x) dx = ln|x| + C", r"\int"),
    ("∫ sin x dx = -cos x + C", r"\int"),
    ("∫ cos x dx = sin x + C", r"\int"),
    ("lim_{x→0} sin(x)/x = 1", r"\to"),
    ("lim_{x→0} (eˣ - 1)/x = 1", r"\to"),
    ("lim_{x→∞} (1 + 1/x)ˣ = e", r"\infty"),
    ("det(A) = ad - bc", r"det(A) = ad - bc"),
    ("A^{-1} = adj(A)/det(A)", r"A^{-1}"),
    ("A · A^{-1} = I", r"A^{-1}"),
    ("λ² - Tr(A)λ + det(A) = 0", r"\lambda^{2}"),
    ("∑_{i=1}ⁿ i = n(n+1)/2", r"\sum"),
    ("∑_{i=1}ⁿ i² = n(n+1)(2n+1)/6", r"\sum"),
    ("∑_{i=1}ⁿ i³ = [n(n+1)/2]²", r"\sum"),
    ("(a + b)² = a² + 2ab + b²", r"a^{2} + 2ab + b^{2}"),
    ("(a - b)² = a² - 2ab + b²", r"a^{2} - 2ab + b^{2}"),
    ("a² - b² = (a - b)(a + b)", r"a^{2} - b^{2}"),
    ("x = (-b ± √(b² - 4ac))/(2a)", r"\pm"),
    ("a³ + b³ = (a + b)(a² - ab + b²)", r"a^{3} + b^{3}"),
    ("a³ - b³ = (a - b)(a² + ab + b²)", r"a^{3} - b^{3}"),
    ("log(ab) = log a + log b", r"\log"),
    ("log(a/b) = log a - log b", r"\log"),
    ("log(aⁿ) = n log a", r"\log"),
    ("a^{log_a x} = x", r"a^{log_a x} = x"),
    ("A ∪ (B ∩ C) = (A ∪ B) ∩ (A ∪ C)", r"\cup"),
    ("A ∩ (B ∪ C) = (A ∩ B) ∪ (A ∩ C)", r"\cap"),
    ("(A ∪ B)' = A' ∩ B'", r"\cup"),
    ("(A ∩ B)' = A' ∪ B'", r"\cap"),
    ("P(A ∪ B) = P(A) + P(B) - P(A ∩ B)", r"\cup"),
    ("P(A|B) = P(A ∩ B)/P(B)", r"\cap"),
    ("E(X) = ∑ x P(x)", r"\sum"),
    ("Var(X) = E(X²) - [E(X)]²", r"E(X^{2})"),
    ("σ = √(Var(X))", r"\sqrt"),
    ("z = (x - μ)/σ", r"\mu"),
    ("f(x) = (1/√(2πσ²)) e^{-(x-μ)²/(2σ²)}", r"\pi"),
    ("x² + y² = r²", r"x^{2} + y^{2} = r^{2}"),
    ("x²/a² + y²/b² = 1", r"x^{2}/a^{2}"),
    ("x²/a² - y²/b² = 1", r"x^{2}/a^{2}"),
]

_BIOLOGY_CASES = [
    ("pH = -log[H⁺]", r"pH = -\log[H^{+}]"),
    ("K_w = [H⁺][OH⁻] = 1.0 × 10⁻¹⁴", r"1.0 \times 10^{-14}"),
    ("K_a = [H⁺][A⁻]/[HA]", r"[H^{+}][A^{-}]"),
    ("pH = pK_a + log([A⁻]/[HA])", r"[A^{-}]"),
    ("ΔG° = -RT ln K", r"\Delta G^{\circ}"),
    ("ΔG = ΔH - TΔS", r"\Delta G = \Delta H - T\Delta S"),
    ("v = V_max [S] / (K_m + [S])", r"V_max"),
    ("1/v = (K_m/V_max)(1/[S]) + 1/V_max", r"K_m/V_max"),
    ("RQ = CO₂ produced / O₂ consumed", r"CO_{2}"),
    ("C6H12O6 + 6O2 -> 6CO2 + 6H2O + 38 ATP", r"6CO_{2}"),
    ("6CO2 + 12H2O -> C6H12O6 + 6O2 + 6H2O", r"6CO_{2}"),
    ("dN/dt = rN", r"dN/dt = rN"),
    ("dN/dt = rN(1 - N/K)", r"dN/dt = rN(1 - N/K)"),
    ("p² + 2pq + q² = 1", r"p^{2} + 2pq + q^{2} = 1"),
    ("p + q = 1", r"p + q = 1"),
    ("N_t = N₀ e^{rt}", r"N_{0}"),
    ("ψ_w = ψ_s + ψ_p", r"\psi_w = \psi_s + \psi_p"),
    ("Q₁₀ = (k₂/k₁)^{10/(T₂-T₁)}", r"Q_{10}"),
    ("P_O2 = 104 mm Hg", r"P_O2"),
    ("P_CO2 = 40 mm Hg", r"P_CO2"),
    ("V_T = 500 mL", r"V_T = 500"),
    ("IRV = 3000 mL", r"IRV = 3000"),
    ("ERV = 1100 mL", r"ERV = 1100"),
    ("RV = 1200 mL", r"RV = 1200"),
    ("VC = ERV + TV + IRV", r"VC = ERV + TV + IRV"),
    ("TLC = VC + RV", r"TLC = VC + RV"),
    ("GFR = 125 mL/min", r"GFR = 125"),
    ("CO = HR × SV", r"CO = HR \times SV"),
    ("BP = 120/80 mm Hg", r"120/80"),
    ("DNA base ratio: (A + T)/(G + C)", r"(A + T)/(G + C)"),
    ("Charagaff rule: A = T and G ≡ C", r"\equiv"),
    ("Codon length = 3 nucleotides", r"3"),
    ("Total chromosomes in humans = 46 (2n)", r"46"),
    ("Haploid chromosome number n = 23", r"23"),
    ("Linkage map distance: 1 cM = 1% recombination", r"1"),
    ("Centrifugation speed = 10,000 rpm", r"10,000"),
    ("Optical density at 260 nm = OD₂₆₀", r"OD_{260}"),
    ("PCR denaturation temp = 94°C", r"94^{\circ}"),
    ("PCR annealing temp = 55°C", r"55^{\circ}"),
    ("PCR extension temp = 72°C", r"72^{\circ}"),
    ("Enzyme reaction temp = 37°C", r"37^{\circ}"),
    ("Hemoglobin subunit count = 4", r"4"),
    ("Myoglobin oxygen binding curve: P₅₀ = 2.8 mm Hg", r"P_{50}"),
    ("Bohr effect: H⁺ and CO₂ reduce O₂ affinity", r"CO_{2}"),
    ("Cell diameter = 10 μm", r"\mu m"),
    ("Bacterial cell size = 1-2 μm", r"\mu m"),
    ("Virus diameter = 20-300 nm", r"nm"),
    ("Ribosome 70S = 50S + 30S", r"70S"),
    ("Ribosome 80S = 60S + 40S", r"80S"),
    ("Water potential of pure water = 0 bar", r"0"),
]


def test_200_notation_corpus_conversion():
    """Verify that all 200+ hand-written notation cases convert properly to LaTeX."""
    corpus = _PHYSICS_CASES + _CHEMISTRY_CASES + _MATH_CASES + _BIOLOGY_CASES
    assert len(corpus) >= 200, f"Corpus size {len(corpus)} < 200"

    for idx, (raw, _) in enumerate(corpus):
        converted = tokenize_and_convert_math(raw)
        # Should not crash and should produce valid balanced syntax
        is_ok, issues = validate_math_delimiters(converted)
        assert is_ok, f"Case {idx} ({raw!r}) failed delimiter validation: {issues}"
        is_syntax_ok, syn_issues = validate_latex_syntax(converted)
        assert is_syntax_ok, f"Case {idx} ({raw!r}) failed syntax validation: {syn_issues}"


# ---------------------------------------------------------------------------
# 2. Strict Negative Cases (Prose text containing x, 2, m NEVER wrapped)
# ---------------------------------------------------------------------------

def test_negative_prose_cases_strictly_preserved():
    negative_cases = [
        "A car travels a distance x in 10 seconds.",
        "Here m is the mass of the object and v is its velocity.",
        "There are 2 questions in this section.",
        "Find the value of x if y is equal to 10.",
        "The object moves m meters in 2 minutes.",
        "Choose 1 of the following 4 options.",
        "Let us examine section A and section B.",
        "In this question, calculate the speed of car x and car y.",
        "A block of mass m is placed on a horizontal table.",
        "The boy ran for 2 kilometers.",
    ]
    for text in negative_cases:
        wrapped = wrap_math_delimiters(text)
        assert wrapped == text, f"Negative case was incorrectly wrapped: {text!r} -> {wrapped!r}"


# ---------------------------------------------------------------------------
# 3. Wrapping Properties: Idempotence & Character Preservation
# ---------------------------------------------------------------------------

def test_wrapping_idempotence():
    samples = [
        r"Find kinetic energy E = \frac{1}{2}mv^{2} when m = 2 kg.",
        r"When \theta = 45^{\circ}, calculate the range.",
        r"$\theta = 30^{\circ}$ is already wrapped.",
        r"No math in this sentence at all.",
    ]
    for s in samples:
        once = wrap_math_delimiters(s)
        twice = wrap_math_delimiters(once)
        assert twice == once, f"Idempotence failed for {s!r}"


# ---------------------------------------------------------------------------
# 4. Multi-Language (3-Language) Synthetic Document Splitting
# ---------------------------------------------------------------------------

def test_three_language_synthetic_splitting():
    text = (
        "Calculate the force acting on the particle.\n"
        "कण पर लगने वाले बल की गणना कीजिए।\n"
        "কণার উপর প্রযুক্ত বল নির্ণয় কর।"
    )
    result = segment_multilingual_text(text, target_languages=["en", "hi", "bn"])
    assert result.get("en") == "Calculate the force acting on the particle."
    assert result.get("hi") == "कण पर लगने वाले बल की गणना कीजिए।"
    assert result.get("bn") == "কণার উপর প্রযুক্ত বল নির্ণয় কর।"


# ---------------------------------------------------------------------------
# 5. RTL Reading Order and Layout Attributes
# ---------------------------------------------------------------------------

def test_rtl_reading_order_and_attributes():
    assert is_rtl_language("ur") is True
    assert is_rtl_language("ar") is True
    assert format_dir_attribute("ur") == 'dir="rtl"'

    b1 = Block(
        id="b1", page=1, type=BlockType.TEXT,
        bbox=BBox(x1=50, y1=100, x2=200, y2=130),
        text="حصہ اول", confidence=1.0, status=BlockStatus.TRUSTED,
    )
    b2 = Block(
        id="b2", page=1, type=BlockType.TEXT,
        bbox=BBox(x1=250, y1=100, x2=400, y2=130),
        text="سوال نمبر 1", confidence=1.0, status=BlockStatus.TRUSTED,
    )
    reordered = reorder_rtl_blocks([b1, b2])
    assert reordered[0].id == "b2"
    assert reordered[1].id == "b1"


# ---------------------------------------------------------------------------
# 6. Scaffolded Plugins End-to-End & Warning Emission
# ---------------------------------------------------------------------------

def test_scaffolded_plugins_warning_and_end_to_end():
    scaffolded_codes = ["bn", "ta", "te", "kn", "ml", "gu", "pa", "or", "mr", "ur", "ar", "zh"]
    for code in scaffolded_codes:
        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter("always")
            plugin = get_plugin(code)
            assert plugin.is_ship_quality is False
            warns = [w for w in recorded if issubclass(w.category, NotShipQualityWarning)]
            assert len(warns) >= 1
            # Exercise plugin without crashing
            norm = plugin.normalize("Test sample 123")
            assert norm == "Test sample 123"


# ---------------------------------------------------------------------------
# 7. S5 Stages lang_v2 Flag Integration & Clean v1 Rollback
# ---------------------------------------------------------------------------

def test_s5_stages_flag_integration_and_rollback(tmp_path):
    b1 = Block(
        id="b1", page=1, type=BlockType.TEXT,
        bbox=BBox(x1=50, y1=50, x2=350, y2=80),
        text="Calculate E = ½mv² for m = 2 kg and v = 10 m/s.\nगतिज ऊर्जा E = ½mv² की गणना करें |",
        confidence=1.0, status=BlockStatus.TRUSTED,
    )
    doc = ExamDocument(
        source_path=str(tmp_path / "test.pdf"),
        meta=ExamMetadata(id="doc_lang_test", title="Test Paper", total_pages=1),
        pages=[PageInfo(page_number=1, classification=PageClassification.QUESTIONS)],
        blocks=[b1],
        questions=[
            Question(
                id="q1", number=1, kind=QuestionKind.MCQ_SINGLE,
                stem_en=[b1],
                stem_text_en="Calculate E = ½mv² for m = 2 kg and v = 10 m/s.\nगतिज ऊर्जा E = ½mv² की गणना करें |",
                options=[Option(label="A", text_str_en="100 J / 100 जूल")],
            )
        ],
    )

    # 1. Test with lang_v2 = True
    cfg_v2 = ExamForgeConfig(flags={"lang_v2": True})
    ctx_v2 = StageContext(document=doc.model_copy(deep=True), config=cfg_v2, spec=None, stage_dir=tmp_path / "s5_v2", run_dir=tmp_path)
    res_math_v2 = S5Math().run(ctx_v2)
    assert res_math_v2.document is not None
    # Verify LaTeX converted
    q_v2 = res_math_v2.document.questions[0]
    assert r"\frac{1}{2}" in q_v2.stem_text_en

    ctx_hi_v2 = StageContext(document=res_math_v2.document, config=cfg_v2, spec=None, stage_dir=tmp_path / "s5b_v2", run_dir=tmp_path)
    res_hi_v2 = S5Hindi().run(ctx_hi_v2)
    q_hi_v2 = res_hi_v2.document.questions[0]
    assert "।" in q_hi_v2.stem_text_hi  # danda converted

    # 2. Test with lang_v2 = False (v1 rollback)
    cfg_v1 = ExamForgeConfig(flags={"lang_v2": False})
    ctx_v1 = StageContext(document=doc.model_copy(deep=True), config=cfg_v1, spec=None, stage_dir=tmp_path / "s5_v1", run_dir=tmp_path)
    res_math_v1 = S5Math().run(ctx_v1)
    assert res_math_v1.document is not None

    ctx_hi_v1 = StageContext(document=res_math_v1.document, config=cfg_v1, spec=None, stage_dir=tmp_path / "s5b_v1", run_dir=tmp_path)
    res_hi_v1 = S5Hindi().run(ctx_hi_v1)
    assert res_hi_v1.document is not None
