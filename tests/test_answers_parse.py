"""Tests for answer key parsing in multiple styles."""

from __future__ import annotations

import pytest

from examforge.answers.parse_key import (
    ParsedKeyEntry,
    parse_answer_key_grid,
    parse_answer_key_inline,
    parse_answer_key_table,
    parse_answer_key_text,
)


class TestAnswerKeyParsing:
    def test_parse_inline_keys(self):
        sample = (
            "Question 1: What is velocity?\nAns. (3)\n"
            "Question 2: What is force?\nAnswer: (B)\n"
            "Question 3: Calculate power.\nAns: 4.5\n"
        )
        entries = parse_answer_key_inline(sample)
        assert len(entries) == 3
        assert entries[0].question_number == 1
        assert entries[0].raw_answer == "3"
        assert entries[1].question_number == 2
        assert entries[1].raw_answer == "B"
        assert entries[2].question_number == 3
        assert entries[2].numeric_value == 4.5

    def test_parse_dense_grid(self):
        sample = "1-A 2-C 3-D 4-B 5-A 6-C 7-D 8-B 9-A 10-C"
        entries = parse_answer_key_grid(sample)
        assert len(entries) == 10
        assert entries[0].question_number == 1
        assert entries[0].options == ["A"]
        assert entries[9].question_number == 10
        assert entries[9].options == ["C"]

    def test_parse_two_column_table(self):
        table_rows = [
            ["Q.No", "Answer"],
            ["1", "A"],
            ["2", "B"],
            ["3", "3.14 - 3.16"],
            ["4", "Bonus"],
        ]
        entries = parse_answer_key_table(table_rows)
        assert len(entries) == 4
        assert entries[0].question_number == 1
        assert entries[0].options == ["A"]
        assert entries[2].question_number == 3
        assert entries[2].numeric_range == (3.14, 3.16)
        assert entries[3].question_number == 4
        assert entries[3].is_bonus is True

    def test_parse_devanagari_numerals_key(self):
        sample = "१-ख २-ग ३-क ४-घ"
        entries = parse_answer_key_grid(sample)
        assert len(entries) == 4
        assert entries[0].question_number == 1
        # 'ख' represents option B (second option)
        assert entries[0].raw_answer == "ख"
        assert entries[1].question_number == 2
        assert entries[1].raw_answer == "ग"

    def test_parse_multi_correct_answers(self):
        sample = "1: A, C\n2: (B), (D)\n3: A or B"
        entries = parse_answer_key_text(sample)
        assert len(entries) == 3
        assert set(entries[0].options) == {"A", "C"}
        assert set(entries[1].options) == {"B", "D"}
        assert set(entries[2].options) == {"A", "B"}

    def test_parse_numeric_ranges(self):
        sample = "Q21: 3.14 - 3.16\nQ22: 25\nQ23: 10.5 to 11.0"
        entries = parse_answer_key_text(sample)
        assert len(entries) == 3
        assert entries[0].numeric_range == (3.14, 3.16)
        assert entries[1].numeric_value == 25.0
        assert entries[2].numeric_range == (10.5, 11.0)

    def test_parse_dropped_and_bonus(self):
        sample = "10: Dropped\n11: Bonus\n12: None"
        entries = parse_answer_key_text(sample)
        assert len(entries) == 3
        assert entries[0].is_dropped is True
        assert entries[1].is_bonus is True
        assert entries[2].is_dropped is True
