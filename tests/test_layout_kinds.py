"""Tests for deterministic question-kind classifier (Phase 6.7)."""

from __future__ import annotations

import pytest

from examforge.ir.schema import Option, QuestionKind
from examforge.layout.kinds import classify_question_kind


class TestQuestionKindClassifier:
    def test_assertion_reason_detection(self):
        stems = [
            "Given below are two statements: one is labelled as Assertion (A) and the other is labelled as Reason (R).",
            "Assertion A: Boiling point of water is 100 C. Reason R: Vapor pressure equals atmospheric pressure.",
            "अभिकथन (A): जल का क्वथनांक 100°C होता है। कारण (R): वाष्प दाब वायुमंडलीय दाब के बराबर होता है।",
        ]
        options = [Option(label="1", text="Both A and R are true")]
        for stem in stems:
            kind = classify_question_kind(stem, options)
            assert kind == QuestionKind.ASSERTION_REASON

    def test_statement_based_detection(self):
        stems = [
            "Given below are two statements:\nStatement I: Momentum is conserved in collisions.\nStatement II: Kinetic energy is always conserved.",
            "कथन I: संवेग हमेशा संरक्षित रहता है।\nकथन II: गतिज ऊर्जा अप्रत्यास्थ टक्कर में संरक्षित रहती है।",
        ]
        options = [Option(label="1", text="Statement I is true but Statement II is false")]
        for stem in stems:
            kind = classify_question_kind(stem, options)
            assert kind == QuestionKind.STATEMENT_BASED

    def test_match_list_detection(self):
        stems = [
            "Match List-I with List-II:\nList-I (Process) | List-II (Law)",
            "सूची-I को सूची-II से सुमेलित कीजिए:\nसूची-I | सूची-II",
            "Match Column A with Column B.",
        ]
        options = [Option(label="A", text="P-1, Q-2, R-3, S-4")]
        for stem in stems:
            kind = classify_question_kind(stem, options)
            assert kind == QuestionKind.MATCH

    def test_numerical_and_integer_detection(self):
        stem_int = "The number of unpaired electrons in Fe2+ is [Integer answer]."
        assert classify_question_kind(stem_int, options=[]) == QuestionKind.INTEGER

        stem_num = "Calculate the maximum velocity in m/s (rounded off to two decimal places)."
        assert classify_question_kind(stem_num, options=[]) == QuestionKind.NUMERICAL

    def test_multi_correct_detection(self):
        stems = [
            "Which of the following statements is/are correct? (One or more than one option may be correct)",
            "For the given reaction, choose the correct statements: (More than one option is correct)",
        ]
        options = [Option(label="A"), Option(label="B"), Option(label="C"), Option(label="D")]
        for stem in stems:
            kind = classify_question_kind(stem, options)
            assert kind == QuestionKind.MULTI_CORRECT

    def test_true_false_detection(self):
        stem = "State True or False for each of the following propositions."
        options = [Option(label="A", text="True"), Option(label="B", text="False")]
        assert classify_question_kind(stem, options) == QuestionKind.TRUE_FALSE

    def test_fill_blank_detection(self):
        stem = "Fill in the blank: The rate of reaction is directly proportional to ________."
        assert classify_question_kind(stem, options=[]) == QuestionKind.FILL_BLANK

    def test_passage_based_detection(self):
        stem = "Based on the paragraph above, calculate the total resistance."
        options = [Option(label="1"), Option(label="2"), Option(label="3"), Option(label="4")]
        assert classify_question_kind(stem, options, has_passage=True) == QuestionKind.PASSAGE_BASED

    def test_confusion_matrix_synthetic_accuracy_above_98_percent(self):
        """Test accuracy across 200 synthetic items across 8 kinds >= 98%."""
        test_data = []

        # 25 Assertion Reason
        for i in range(25):
            test_data.append((f"Assertion A: Proposition {i}. Reason R: Justification {i}.", [Option(label="1")], QuestionKind.ASSERTION_REASON))

        # 25 Statement Based
        for i in range(25):
            test_data.append((f"Statement I: Law {i}. Statement II: Hypothesis {i}.", [Option(label="1")], QuestionKind.STATEMENT_BASED))

        # 25 Match List
        for i in range(25):
            test_data.append((f"Match List-I with List-II for experiment {i}.", [Option(label="1")], QuestionKind.MATCH))

        # 25 Integer
        for i in range(25):
            test_data.append((f"Find the integer value of parameter {i}.", [], QuestionKind.INTEGER))

        # 25 Numerical
        for i in range(25):
            test_data.append((f"Calculate the numerical value of constant {i} in SI units.", [], QuestionKind.NUMERICAL))

        # 25 Multi Correct
        for i in range(25):
            test_data.append((f"Problem {i}. More than one option is correct.", [Option(label="A"), Option(label="B")], QuestionKind.MULTI_CORRECT))

        # 25 Single Correct MCQ
        for i in range(25):
            test_data.append((f"What is the magnitude of force {i}?", [Option(label="A"), Option(label="B"), Option(label="C"), Option(label="D")], QuestionKind.SINGLE_CORRECT))

        # 25 True / False
        for i in range(25):
            test_data.append((f"Proposition {i}: Is this True or False?", [Option(label="A", text="True"), Option(label="B", text="False")], QuestionKind.TRUE_FALSE))

        assert len(test_data) == 200

        correct = 0
        for stem, opts, expected_kind in test_data:
            detected = classify_question_kind(stem, opts)
            if detected == expected_kind:
                correct += 1

        accuracy = correct / len(test_data)
        assert accuracy >= 0.98, f"Accuracy {accuracy:.4f} is below 0.98 threshold ({correct}/{len(test_data)})"
