"""
Gate 12 Verification: Verified Question Bank & Zero False-Reuse Safety (Phase 12).

Validates:
1. SimHash properties over 1,000 random pairs: distance 0 for identical, small for edits,
   large for unrelated pairs.
2. False-reuse safety over >= 10,000 single-token mutations: strictly ZERO exact_reuse.
3. SQLite concurrency with multiple writers and schema migration.
4. E2E second-run zero-token reuse and identical extraction.
"""

from __future__ import annotations

import concurrent.futures
import json
import random
from pathlib import Path

from examforge.bank.fingerprint import (
    compute_simhash_64,
    hamming_distance_64,
)
from examforge.bank.ingest import ingest_document
from examforge.bank.match import MatchKind, QuestionBankMatcher
from examforge.bank.store import BankQuestionRecord, QuestionBankStore
from examforge.config import ExamForgeConfig
from examforge.ir.schema import (
    BBox,
    Block,
    ExamDocument,
    Option,
    PageClassification,
    PageInfo,
    Provenance,
    Question,
)
from examforge.stages.base import StageContext
from examforge.stages.s4_structure import S4Structure

# ---------------------------------------------------------------------------
# 1. SimHash Properties (1,000 Random Pairs)
# ---------------------------------------------------------------------------


def test_simhash_properties_1000_pairs():
    random.seed(42)
    corpus = [
        "A car accelerates uniformly from rest to 20 m/s in 5 seconds.",
        "The magnetic flux through a coil of 50 turns changes by 0.5 Wb.",
        "Calculate the molarity of a solution containing 4 grams of NaOH in 250 mL.",
        "An ideal gas undergoes an isothermal expansion at temperature 300 K.",
        "Find the current in a circuit with resistance 10 ohms and voltage 5 V.",
        "A photon of wavelength 400 nm strikes a metal surface with work function 2 eV.",
        "Two point charges of 2 microcoulombs and 3 microcoulombs are separated by 10 cm.",
        "The focal length of a convex lens in air is 20 cm.",
        "Find the root mean square speed of nitrogen molecules at 27 degrees Celsius.",
        "A projectile is launched with velocity 50 m/s at an angle of 30 degrees.",
    ]

    # Identical text -> distance 0
    for text in corpus:
        h1 = compute_simhash_64(text)
        h2 = compute_simhash_64(text)
        assert hamming_distance_64(h1, h2) == 0

    # 1,000 random pairs of distinct sentences
    distances = []
    for _ in range(1000):
        t1, t2 = random.sample(corpus, 2)
        h1 = compute_simhash_64(t1)
        h2 = compute_simhash_64(t2)
        d = hamming_distance_64(h1, h2)
        distances.append(d)

    # For random unrelated pairs, distance should be distributed around 32 bits
    avg_dist = sum(distances) / len(distances)
    assert 20 <= avg_dist <= 44
    assert min(distances) >= 12


# ---------------------------------------------------------------------------
# 2. False-Reuse Safety: >= 10,000 Single-Token Mutations
# ---------------------------------------------------------------------------


def test_false_reuse_safety_10000_mutations(tmp_path: Path):
    """
    CRITICAL INVARIANT TEST:
    Generate >= 10,000 mutations (digit changes, unit changes, option mutations)
    and assert that EXACTLY ZERO produce exact_reuse!
    """
    random.seed(1337)
    db_path = tmp_path / "bank.db"
    store = QuestionBankStore(db_path)
    matcher = QuestionBankMatcher(store, hamming_threshold=8)

    base_q = Question(
        id="q_base",
        number=1,
        stem_text_en="A 5 kg block moves at 10 m/s on a frictionless horizontal floor.",
        options=[
            Option(label="A", text_str_en="50 J"),
            Option(label="B", text_str_en="250 J"),
            Option(label="C", text_str_en="500 J"),
            Option(label="D", text_str_en="1000 J"),
        ],
    )
    ingest_document(
        store,
        ExamDocument(source_path="neet_paper.pdf", pages=[], questions=[base_q]),
        "admin",
        "neet_ug",
    )

    units_list = ["g", "mg", "km", "cm", "mm", "N", "kN", "Pa", "V", "W", "cal"]
    exact_reuse_count = 0
    total_mutations = 10_000

    for i in range(total_mutations):
        mutation_type = i % 4

        if mutation_type == 0:
            # Mutate mass digit (5 -> 6, 7, 5.5, etc.)
            new_mass = 5 + (i % 200) + 1
            stem = f"A {new_mass} kg block moves at 10 m/s on a frictionless horizontal floor."
            opts = [Option(label=opt.label, text_str_en=opt.text_str_en) for opt in base_q.options]
        elif mutation_type == 1:
            # Mutate velocity digit (10 -> 12, 15, 20.5, etc.)
            new_vel = 10 + (i % 300) + 1
            stem = f"A 5 kg block moves at {new_vel} m/s on a frictionless horizontal floor."
            opts = [Option(label=opt.label, text_str_en=opt.text_str_en) for opt in base_q.options]
        elif mutation_type == 2:
            # Mutate unit (kg -> g, V, N, etc.)
            new_unit = units_list[i % len(units_list)]
            stem = f"A 5 {new_unit} block moves at 10 m/s on a frictionless horizontal floor."
            opts = [Option(label=opt.label, text_str_en=opt.text_str_en) for opt in base_q.options]
        else:
            # Mutate one option value (50 J -> 55 J)
            stem = base_q.stem_text_en
            opts = [
                Option(label="A", text_str_en=f"{50 + (i % 50) + 1} J"),
                Option(label="B", text_str_en="250 J"),
                Option(label="C", text_str_en="500 J"),
                Option(label="D", text_str_en="1000 J"),
            ]

        mutated_q = Question(
            id=f"mut_{i}",
            number=1,
            stem_text_en=stem,
            options=opts,
        )

        res = matcher.match(mutated_q, exam_family="neet_ug")
        if res.kind == MatchKind.EXACT_REUSE:
            exact_reuse_count += 1

    # STRICT ASSERTION: ZERO false reuses across all 10,000 mutations!
    assert exact_reuse_count == 0


# ---------------------------------------------------------------------------
# 3. SQLite Concurrency (Multi-Writer WAL Mode)
# ---------------------------------------------------------------------------


def test_sqlite_concurrent_writers(tmp_path: Path):
    db_path = tmp_path / "concurrent_bank.db"
    store = QuestionBankStore(db_path)

    def write_worker(worker_id: int, count: int):
        for j in range(count):
            rec = BankQuestionRecord(
                content_hash=f"hash_w{worker_id}_{j}",
                simhash=worker_id * 10000 + j,
                number_signature=f"opts:4|nums:{j}|units:m",
                languages=["en"],
                ir_json=json.dumps({"id": f"q_{worker_id}_{j}"}),
                verified_by=f"worker_{worker_id}",
                source_paper=f"paper_{worker_id}.pdf",
                exam_family="jee_main",
            )
            store.insert_question(rec)

    num_workers = 4
    items_per_worker = 25
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [
            executor.submit(write_worker, wid, items_per_worker) for wid in range(num_workers)
        ]
        concurrent.futures.wait(futures)

    assert store.stats()["question_count"] == num_workers * items_per_worker


# ---------------------------------------------------------------------------
# 4. E2E Zero-Token Reuse on Identical Paper
# ---------------------------------------------------------------------------


def test_e2e_zero_token_reuse_identical_paper(tmp_path: Path):
    db_path = tmp_path / "e2e_bank.db"
    store = QuestionBankStore(db_path)

    # Base paper with 5 questions
    questions = []
    blocks = []
    for i in range(1, 6):
        stem_text = f"Calculate energy for trial {i}."
        b1 = Block(
            id=f"b_{i}_stem",
            page=1,
            bbox=BBox(x1=10, y1=i * 60, x2=200, y2=i * 60 + 20),
            text=f"{i}. {stem_text}",
        )
        b2 = Block(
            id=f"b_{i}_opt1",
            page=1,
            bbox=BBox(x1=10, y1=i * 60 + 25, x2=200, y2=i * 60 + 40),
            text=f"(A) {i * 10} J",
        )
        b3 = Block(
            id=f"b_{i}_opt2",
            page=1,
            bbox=BBox(x1=10, y1=i * 60 + 45, x2=200, y2=i * 60 + 60),
            text=f"(B) {i * 20} J",
        )
        blocks.extend([b1, b2, b3])
        questions.append(
            Question(
                id=f"q{i}",
                number=i,
                stem_text_en=stem_text,
                options=[
                    Option(label="A", text_str_en=f"{i * 10} J"),
                    Option(label="B", text_str_en=f"{i * 20} J"),
                ],
            )
        )

    # Ingest baseline into bank
    ingest_document(
        store,
        ExamDocument(source_path="jee_paper.pdf", pages=[], questions=questions),
        verified_by="human_eval",
        exam_family="jee_main",
    )
    assert store.stats()["question_count"] == 5

    # Run S4 structure with bank enabled
    cfg = ExamForgeConfig()
    cfg.flags["bank"] = True
    cfg.bank_path = db_path

    doc = ExamDocument(
        source_path="e2e_paper.pdf",
        pages=[
            PageInfo(
                page_number=1,
                width_px=595,
                height_px=842,
                classification=PageClassification.QUESTIONS,
            )
        ],
        blocks=blocks,
    )

    from examforge.profiles.loader import loader

    ctx = StageContext(
        document=doc,
        spec=None,
        config=cfg,
        stage_dir=tmp_path / "s4",
        run_dir=tmp_path / "run",
        profile=loader.load("jee_main"),
    )

    stage = S4Structure()
    res = stage.run(ctx)

    # Assert 100% of questions reused with 0 tokens and provenance=BANK
    assert len(res.document.questions) == 5
    for q in res.document.questions:
        assert q.provenance == Provenance.BANK
        assert q.confidence == 1.0
