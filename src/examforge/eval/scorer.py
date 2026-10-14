"""ExamDocument evaluation scorer.

Compares hypothesis ExamDocument against ground-truth reference ExamDocument,
producing comprehensive accuracy metrics and an aggregate score.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from examforge.eval.metrics import (
    compute_bbox_iou,
    compute_cer,
    compute_count_match,
    compute_option_accuracy,
    compute_sequence_accuracy,
    compute_table_structure_similarity,
    compute_wer,
)
from examforge.ir.schema import ExamDocument, Question, TextNode


@dataclass
class EvaluationResult:
    """Detailed benchmark evaluation metrics comparing hypothesis to ground truth."""

    sequence_accuracy: float = 1.0
    count_match: float = 1.0
    cer_mean: float = 0.0
    cer_p95: float = 0.0
    wer_mean: float = 0.0
    wer_p95: float = 0.0
    option_accuracy: float = 1.0
    kind_accuracy: float = 1.0
    language_completeness: float = 1.0
    figure_iou_mean: float = 1.0
    figure_iou_ge_90: float = 1.0
    table_similarity: float = 1.0
    aggregate_score: float = 1.0
    total_ref_questions: int = 0
    total_hyp_questions: int = 0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, path: Path | str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)


class ExamScorer:
    """Scores an extracted ExamDocument against ground truth."""

    def score(
        self,
        reference: ExamDocument,
        hypothesis: ExamDocument,
    ) -> EvaluationResult:
        ref_qs = {q.number: q for q in reference.questions}
        hyp_qs = {q.number: q for q in hypothesis.questions}

        ref_nums = [q.number for q in reference.questions]
        hyp_nums = [q.number for q in hypothesis.questions]

        # 1. Sequence & Count
        seq_acc = compute_sequence_accuracy(ref_nums, hyp_nums)
        cnt_match = compute_count_match(len(ref_nums), len(hyp_nums))

        # 2. Text accuracy (CER / WER)
        cers: list[float] = []
        wers: list[float] = []
        option_scores: list[float] = []
        kind_matches: list[float] = []
        lang_complete_scores: list[float] = []

        for num, ref_q in ref_qs.items():
            hyp_q = hyp_qs.get(num)
            if hyp_q is None:
                cers.append(1.0)
                wers.append(1.0)
                option_scores.append(0.0)
                kind_matches.append(0.0)
                lang_complete_scores.append(0.0)
                continue

            # Stem text comparison
            ref_stem = self._extract_stem_text(ref_q)
            hyp_stem = self._extract_stem_text(hyp_q)
            cers.append(compute_cer(ref_stem, hyp_stem))
            wers.append(compute_wer(ref_stem, hyp_stem))

            # Option accuracy
            option_scores.append(compute_option_accuracy(ref_q, hyp_q))

            # Kind accuracy
            kind_matches.append(1.0 if ref_q.kind == hyp_q.kind else 0.0)

            # Language completeness
            has_text = bool(hyp_stem.strip())
            lang_complete_scores.append(1.0 if has_text else 0.0)

        cer_mean = float(np.mean(cers)) if cers else 0.0
        cer_p95 = float(np.percentile(cers, 95)) if cers else 0.0
        wer_mean = float(np.mean(wers)) if wers else 0.0
        wer_p95 = float(np.percentile(wers, 95)) if wers else 0.0
        opt_acc = float(np.mean(option_scores)) if option_scores else 1.0
        kind_acc = float(np.mean(kind_matches)) if kind_matches else 1.0
        lang_comp = float(np.mean(lang_complete_scores)) if lang_complete_scores else 1.0

        # 3. Figure IoU
        fig_ious: list[float] = []
        ref_figs = {f.id: f for f in reference.figures}
        hyp_figs = {f.id: f for f in hypothesis.figures}

        for f_id, ref_f in ref_figs.items():
            hyp_f = hyp_figs.get(f_id)
            if hyp_f is not None and ref_f.bbox and hyp_f.bbox:
                fig_ious.append(compute_bbox_iou(ref_f.bbox, hyp_f.bbox))
            else:
                fig_ious.append(0.0)

        iou_mean = float(np.mean(fig_ious)) if fig_ious else 1.0
        iou_ge_90 = float(np.mean([1.0 if iou >= 0.9 else 0.0 for iou in fig_ious])) if fig_ious else 1.0

        # 4. Tables similarity
        tab_sims: list[float] = []
        if reference.tables and hypothesis.tables:
            min_len = min(len(reference.tables), len(hypothesis.tables))
            for i in range(min_len):
                tab_sims.append(
                    compute_table_structure_similarity(
                        reference.tables[i].rows,
                        hypothesis.tables[i].rows,
                    )
                )
        tab_score = float(np.mean(tab_sims)) if tab_sims else 1.0

        # Composite Aggregate Score (weighted sum of accuracies)
        # Weights: Sequence (0.2), Count (0.1), CER (0.2), Options (0.2), Kind (0.1), Figures (0.1), Tables (0.1)
        text_accuracy = max(0.0, 1.0 - cer_mean)
        aggregate = (
            0.20 * seq_acc
            + 0.10 * cnt_match
            + 0.20 * text_accuracy
            + 0.20 * opt_acc
            + 0.10 * kind_acc
            + 0.10 * iou_mean
            + 0.10 * tab_score
        )

        return EvaluationResult(
            sequence_accuracy=round(seq_acc, 4),
            count_match=round(cnt_match, 4),
            cer_mean=round(cer_mean, 4),
            cer_p95=round(cer_p95, 4),
            wer_mean=round(wer_mean, 4),
            wer_p95=round(wer_p95, 4),
            option_accuracy=round(opt_acc, 4),
            kind_accuracy=round(kind_acc, 4),
            language_completeness=round(lang_comp, 4),
            figure_iou_mean=round(iou_mean, 4),
            figure_iou_ge_90=round(iou_ge_90, 4),
            table_similarity=round(tab_score, 4),
            aggregate_score=round(aggregate, 4),
            total_ref_questions=len(ref_nums),
            total_hyp_questions=len(hyp_nums),
        )

    def _extract_stem_text(self, question: Question) -> str:
        """Extract clean stem text from either ContentNodes or legacy fields."""
        texts = []
        if question.stem:
            for node in question.stem:
                if isinstance(node, TextNode):
                    texts.append(node.texts.get("en", ""))
        elif question.stem_text_en:
            texts.append(question.stem_text_en)
        elif question.stem_en:
            texts.extend(b.text for b in question.stem_en)

        return " ".join(texts).strip()
