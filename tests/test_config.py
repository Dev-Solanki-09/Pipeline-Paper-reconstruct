"""Tests for config and spec loading."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from examforge.config import ExamForgeConfig, _deep_merge
from examforge.spec import ModeConfig, Rule, RuleSeverity, Spec


class TestSpec:
    def test_default_has_all_rules(self):
        spec = Spec.default()
        assert len(spec.rules) == 9
        assert "R01_no_furniture" in spec.rules
        assert "R09_unicode" in spec.rules

    def test_blocker_rules(self):
        spec = Spec.default()
        blockers = spec.blocker_rules()
        assert "R01_no_furniture" in blockers
        assert "R09_unicode" not in blockers  # It's warn, not blocker

    def test_hash_deterministic(self):
        s1 = Spec.default()
        s2 = Spec.default()
        assert s1.hash() == s2.hash()

    def test_hash_changes_on_mutation(self):
        s1 = Spec.default()
        s2 = Spec.default()
        s2.rules["R99_custom"] = Rule(severity=RuleSeverity.WARN, check="custom_check")
        assert s1.hash() != s2.hash()

    def test_get_mode(self):
        spec = Spec.default()
        fast = spec.get_mode("fast")
        assert fast.second_engine == "on_flag"
        assert fast.audit_sample == 0.05

        maxm = spec.get_mode("max")
        assert maxm.second_engine == "always"

    def test_load_from_yaml(self, tmp_path: Path):
        spec_data = {
            "spec_version": 1,
            "rules": {
                "R01_test": {"severity": "blocker", "check": "test_check"},
            },
            "modes": {
                "fast": {"engines": ["E1"], "second_engine": "on_flag", "audit_sample": 0.05},
            },
        }
        path = tmp_path / "test.spec.yaml"
        path.write_text(yaml.dump(spec_data))

        spec = Spec.load(path)
        assert len(spec.rules) == 1
        assert spec.rules["R01_test"].check == "test_check"


class TestConfig:
    def test_defaults(self):
        config = ExamForgeConfig()
        assert config.mode == "fast"
        assert config.fail_policy == "fail_page"
        assert not config.debug
        assert not config.agent.enabled

    def test_load_from_yaml(self, tmp_path: Path):
        cfg_data = {
            "mode": "max",
            "debug": True,
            "fail_policy": "fail_fast",
        }
        path = tmp_path / "examforge.yaml"
        path.write_text(yaml.dump(cfg_data))

        config = ExamForgeConfig.load(config_path=path)
        assert config.mode == "max"
        assert config.debug is True
        assert config.fail_policy == "fail_fast"

    def test_overrides(self, tmp_path: Path):
        cfg_data = {"mode": "fast", "debug": False}
        path = tmp_path / "examforge.yaml"
        path.write_text(yaml.dump(cfg_data))

        config = ExamForgeConfig.load(
            config_path=path,
            overrides={"mode": "max", "debug": True},
        )
        assert config.mode == "max"
        assert config.debug is True

    def test_missing_config_file_uses_defaults(self, tmp_path: Path):
        config = ExamForgeConfig.load(
            config_path=tmp_path / "nonexistent.yaml",
        )
        assert config.mode == "fast"


class TestDeepMerge:
    def test_flat(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested(self):
        base = {"a": {"x": 1, "y": 2}, "b": 3}
        override = {"a": {"y": 99, "z": 100}}
        result = _deep_merge(base, override)
        assert result == {"a": {"x": 1, "y": 99, "z": 100}, "b": 3}
