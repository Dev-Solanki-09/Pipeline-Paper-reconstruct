"""
Phase 13.3 — One-Shot LLM Profile Completion.

Invoked strictly when deterministic inference yields fields below confidence threshold τ.
Applies semantic checks, regex catastrophic backtracking guards, and fail-safe fallbacks.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from examforge.ir.schema import ExamDocument
from examforge.llm.types import LLMRequest
from examforge.profiles.infer_rules import ProfileInferenceResult
from examforge.profiles.schema import (
    ExamProfile,
    LanguageProfileConfig,
    NumberingProfileConfig,
    OptionsProfileConfig,
)

logger = logging.getLogger(__name__)

# Heuristic pattern detecting classic catastrophic backtracking risks (e.g. (a+)+, (.*)*)
_DANGEROUS_NESTED_QUANTIFIER = re.compile(r"\([^)]*[\+\*]\)[\+\*]")


def _is_safe_regex(pattern: str, test_inputs: list[str]) -> bool:
    """Validate regex compilation and guard against ReDoS/backtracking."""
    if _DANGEROUS_NESTED_QUANTIFIER.search(pattern):
        logger.warning("Rejected regex due to dangerous nested quantifier: %s", pattern)
        return False

    try:
        compiled = re.compile(pattern)
        # Test on small sample strings to confirm it executes quickly
        for s in test_inputs:
            compiled.search(s)
        return True
    except Exception as e:
        logger.warning("Regex compilation/execution failed: %s (%s)", pattern, e)
        return False


def complete_profile_llm(
    partial_result: ProfileInferenceResult,
    doc: ExamDocument,
    llm_client: Any | None = None,
    timeout_s: float = 2.0,
) -> tuple[ExamProfile, bool]:
    """
    Complete low-confidence profile fields using one-shot LLM call.

    Returns:
        tuple[ExamProfile, bool]: (completed_profile, needs_review_flag)
    """
    # 1. Zero-token shortcut if confidence is already sufficient
    if not partial_result.low_confidence_fields:
        return partial_result.profile, False

    if llm_client is None:
        logger.info("No LLM client provided; flagging profile for human review")
        return partial_result.profile, True

    # 2. Extract representative text snippets from first 2-3 content pages
    sample_texts = [b.text for b in doc.blocks[:15]]
    sample_corpus = "\n".join(sample_texts)

    prompt = (
        f"You are an exam document layout analyzer. Analyze this sample text:\n"
        f"```\n{sample_corpus[:1500]}\n```\n\n"
        f"Identify the missing fields: {partial_result.low_confidence_fields}.\n"
        f"Respond ONLY with a JSON object in this format:\n"
        f"{{\n"
        f'  "numbering_patterns": ["^Q\\\\.?\\\\s*\\\\d+"],\n'
        f'  "option_labels": ["(A)", "(B)", "(C)", "(D)"],\n'
        f'  "languages": ["en"]\n'
        f"}}\n"
    )

    from examforge.llm.types import Message, Role

    req = LLMRequest(
        messages=[Message(role=Role.USER, content=prompt)],
        max_tokens=250,
        temperature=0.0,
        stage_name="profile_scaffolding",
    )

    try:
        resp = llm_client.complete(req)
        raw_text = resp.content.strip()
        # Clean markdown code block if present
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
            raw_text = re.sub(r"\s*```$", "", raw_text)

        data = json.loads(raw_text)
        if not isinstance(data, dict):
            return partial_result.profile, True

        # Validate numbering regexes
        new_patterns = list(partial_result.profile.numbering.patterns)
        if (
            "numbering.patterns" in partial_result.low_confidence_fields
            and "numbering_patterns" in data
        ):
            candidate_pats = data.get("numbering_patterns", [])
            if not isinstance(candidate_pats, list) or not candidate_pats:
                return partial_result.profile, True

            safe_pats = []
            for pat in candidate_pats:
                if not isinstance(pat, str):
                    continue
                if _is_safe_regex(pat, sample_texts):
                    safe_pats.append(pat)
                else:
                    return partial_result.profile, True  # Hostile or dangerous regex!

            if safe_pats:
                new_patterns = safe_pats

        # Validate option labels
        new_options = list(partial_result.profile.options.label_schemes)
        if (
            "options.label_schemes" in partial_result.low_confidence_fields
            and "option_labels" in data
        ):
            candidate_opts = data.get("option_labels", [])
            if isinstance(candidate_opts, list) and candidate_opts:
                new_options = [str(o) for o in candidate_opts]

        # Validate languages
        new_languages = list(partial_result.profile.languages)
        if "languages" in partial_result.low_confidence_fields and "languages" in data:
            lang_codes = data.get("languages", [])
            if isinstance(lang_codes, list) and lang_codes:
                new_languages = [
                    LanguageProfileConfig(code=code, script="Latn" if code == "en" else "Deva")
                    for code in lang_codes
                ]

        updated_profile = ExamProfile(
            id=partial_result.profile.id,
            name=partial_result.profile.name,
            profile_version=partial_result.profile.profile_version,
            maturity="experimental",
            languages=new_languages,
            language_layout=partial_result.profile.language_layout,
            layout=partial_result.profile.layout,
            numbering=NumberingProfileConfig(
                patterns=new_patterns,
                sections=partial_result.profile.numbering.sections,
                reset_policy=partial_result.profile.numbering.reset_policy,
            ),
            options=OptionsProfileConfig(
                label_schemes=new_options,
                count_min=partial_result.profile.options.count_min,
                count_max=partial_result.profile.options.count_max,
                count_typical=partial_result.profile.options.count_typical,
            ),
        )
        return updated_profile, False

    except Exception as e:
        logger.warning("LLM profile completion failed or rejected: %s", e)
        return partial_result.profile, True
