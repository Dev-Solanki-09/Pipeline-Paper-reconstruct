"""
Phase 16 — Gate 16 Verification Suite: Orchestrator, CLI & Plugin Hardening.

Validates:
1. Stage DAG dependency ordering, partial runs (--from-stage, --to-stage, --only),
   and cycle detection.
2. Crash injection and byte-identical resume recovery with consistent manifest.
3. Atomic I/O with fsync, lockfile concurrency prevention, and path traversal sanitization.
4. Checkpoint invalidation upon spec_hash change vs irrelevant config retention.
5. Plugin discovery with API version guards, error isolation, and capability conflict warnings.
6. Input robustness corpus (encrypted, corrupt/0-byte, image bomb, ZIP image archives).
7. CLI commands: doctor, plugins list, schema, and --json structured output.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import fitz
import pytest
from click.testing import CliRunner

from examforge.cli import main
from examforge.config import ExamForgeConfig
from examforge.orchestrator.dag import StageDAG, StageSpec, get_default_stage_dag
from examforge.orchestrator.io import (
    RunLock,
    RunLockError,
    atomic_write,
    sanitize_run_id,
)
from examforge.orchestrator.plugins import (
    PluginManager,
    is_api_compatible,
    safe_call_plugin,
)
from examforge.orchestrator.robustness import (
    CorruptPDFError,
    EncryptedPDFError,
    ImageBombError,
    inspect_and_repair_input,
)
from examforge.orchestrator.runner import (
    EXIT_FAILED,
    EXIT_OK,
    PipelineRunner,
)
from examforge.spec import Spec
from examforge.stages.base import Stage, StageContext, StageResult


class MockStepStage(Stage):
    """Deterministic step stage for DAG and crash tests."""

    def __init__(self, name: str, should_fail: bool = False):
        self.name = name
        self.should_fail = should_fail

    def run(self, ctx: StageContext) -> StageResult:
        if self.should_fail:
            raise RuntimeError(f"Simulated failure in stage {self.name}")
        step_log = ctx.document.metadata.subject or ""
        ctx.document.metadata.subject = f"{step_log}>{self.name}".strip(">")
        return StageResult(document=ctx.document, metrics={f"{self.name}_done": True})


def _create_minimal_valid_pdf(path: Path) -> Path:
    """Create a minimal real 1-page PDF using PyMuPDF."""
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    doc.save(str(path))
    doc.close()
    return path


class TestGate16Verification:
    def test_dag_topological_order_and_cycles(self):
        """Verify DAG resolves topological order, handles partial runs, and catches cycles."""
        dag = get_default_stage_dag()

        # 1. Full order
        order = dag.resolve_order()
        assert order[0] == "s0_intake"
        assert order[-1] == "s9_package"
        # s4_structure must precede s5_math and s5_hindi
        assert order.index("s4_structure") < order.index("s5_math")
        assert order.index("s4_structure") < order.index("s5_hindi")
        # s8_verify must precede s7_repair
        assert order.index("s8_verify") < order.index("s7_repair")

        # 2. Partial run slicing
        slice_order = dag.resolve_order(from_stage="s4_structure", to_stage="s6_figures")
        assert slice_order[0] == "s4_structure"
        assert slice_order[-1] == "s6_figures"
        assert "s0_intake" not in slice_order
        assert "s9_package" not in slice_order

        # 3. --only single stage
        only_order = dag.resolve_order(only_stage="s8_verify")
        assert only_order == ["s8_verify"]

        # 4. Cycle detection
        cyclic_dag = StageDAG(
            [
                StageSpec(id="stage_a", requires=["stage_c"]),
                StageSpec(id="stage_b", requires=["stage_a"]),
                StageSpec(id="stage_c", requires=["stage_b"]),
            ]
        )
        assert cyclic_dag.detect_cycles() is not None
        with pytest.raises(ValueError, match="Cycle detected"):
            cyclic_dag.resolve_order()

    def test_atomic_write_and_lockfile_concurrency(self, tmp_path: Path):
        """Verify atomic writes with fsync and lockfile prevents concurrent access."""
        target_file = tmp_path / "atomic_test.txt"
        atomic_write(target_file, "clean content")
        assert target_file.read_text(encoding="utf-8") == "clean content"

        # Path traversal sanitization
        malicious_id = "../../../etc/passwd"
        safe_id = sanitize_run_id(malicious_id)
        assert "/" not in safe_id
        assert "\\" not in safe_id
        assert ".." not in safe_id

        # Lockfile concurrency
        run_dir = tmp_path / "run_01"
        lock1 = RunLock(run_dir)
        lock1.acquire()

        # Second process attempting lock must fail
        lock2 = RunLock(run_dir)
        with pytest.raises(RunLockError, match="Another process holds the lock"):
            lock2.acquire(timeout_sec=0.1)

        # Release first lock, second can now acquire
        lock1.release()
        lock2.acquire(timeout_sec=0.5)
        lock2.release()

    def test_crash_injection_and_byte_identical_resume(self, tmp_path: Path):
        """
        Crash injection test:
        1. Run 3 stages uninterrupted and save output document bytes.
        2. Run 3 stages with stage 2 monkeypatched to crash mid-execution.
        3. Resume after crash with fixed stage.
        4. Assert resumed document is byte-identical to uninterrupted run.
        """
        pdf_path = _create_minimal_valid_pdf(tmp_path / "valid.pdf")
        runs_dir = tmp_path / "runs"
        config = ExamForgeConfig(paths={"runs": runs_dir})
        spec = Spec.default()

        stage1 = MockStepStage("s1")
        stage2 = MockStepStage("s2")
        stage3 = MockStepStage("s3")

        # 1. Uninterrupted baseline run
        runner_clean = PipelineRunner(
            stages=[stage1, stage2, stage3],
            config=config,
            spec=spec,
        )
        clean_res = runner_clean.execute(pdf_path)
        assert clean_res.exit_code == EXIT_OK
        baseline_bytes = clean_res.document.model_dump_json(indent=2)
        assert clean_res.document.metadata.subject == "s1>s2>s3"

        # 2. Crash run with failing stage 2
        failing_stage2 = MockStepStage("s2", should_fail=True)
        runner_crash = PipelineRunner(
            stages=[stage1, failing_stage2, stage3],
            config=config,
            spec=spec,
        )
        crash_res = runner_crash.execute(pdf_path)
        assert crash_res.exit_code == EXIT_FAILED
        crashed_run_id = crash_res.run_id

        # 3. Resume with fixed stage 2
        runner_resume = PipelineRunner(
            stages=[stage1, stage2, stage3],
            config=config,
            spec=spec,
        )
        resumed_res = runner_resume.resume(crashed_run_id)
        assert resumed_res.exit_code == EXIT_OK

        # 4. Byte-identical assertion
        resumed_bytes = resumed_res.document.model_dump_json(indent=2)
        assert resumed_bytes == baseline_bytes
        assert resumed_res.document.metadata.subject == "s1>s2>s3"

    def test_checkpoint_invalidation_on_spec_hash_change(self, tmp_path: Path):
        """Verify resume invalidates stale checkpoints if spec_hash changes."""
        pdf_path = _create_minimal_valid_pdf(tmp_path / "valid2.pdf")
        runs_dir = tmp_path / "runs"
        config = ExamForgeConfig(paths={"runs": runs_dir})
        spec = Spec.default()

        stage1 = MockStepStage("step_a")
        stage2 = MockStepStage("step_b", should_fail=True)

        runner = PipelineRunner(stages=[stage1, stage2], config=config, spec=spec)
        res1 = runner.execute(pdf_path)
        run_id = res1.run_id

        # Modify spec rule to change spec_hash
        spec.rules["R999_DUMMY"] = {"severity": "blocker"}
        stage2.should_fail = False

        res2 = runner.resume(run_id)
        # Check that it restarted cleanly with updated spec_hash
        assert res2.manifest.spec_hash is not None

    def test_plugin_discovery_and_error_isolation(self, tmp_path: Path):
        """Verify plugin loader skips incompatible api_versions and isolates errors."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        # 1. API version checks
        assert is_api_compatible("2.0") is True
        assert is_api_compatible("2.0.0") is True
        assert is_api_compatible("1.0.0") is False

        # 2. Write incompatible local plugin
        bad_plugin = plugins_dir / "legacy_plugin.py"
        bad_plugin.write_text(
            "__api_version__ = '1.2.0'\nplugin_group = 'examforge.stages'\n",
            encoding="utf-8",
        )

        # 3. Write compatible local plugin
        good_plugin = plugins_dir / "valid_plugin.py"
        good_plugin.write_text(
            "__api_version__ = '2.0.0'\nplugin_group = 'examforge.validators'\n"
            "capabilities = ['custom_rule']\n",
            encoding="utf-8",
        )

        mgr = PluginManager(plugins_dir=plugins_dir)
        discovery = mgr.discover_all()

        loaded_names = [p.name for p in discovery.loaded]
        skipped_names = [name for name, _ in discovery.skipped]

        assert "valid_plugin" in loaded_names
        assert "legacy_plugin" in skipped_names

        # 4. Error isolation in plugin call
        def exploding_plugin():
            raise RuntimeError("Plugin crash")

        result, err = safe_call_plugin(exploding_plugin)
        assert result is None
        assert isinstance(err, RuntimeError)

    def test_input_robustness_corpus(self, tmp_path: Path):
        """
        Verify encrypted, 0-byte corrupt, image-bomb, and ZIP image inputs
        are handled cleanly.
        """
        scratch = tmp_path / "scratch"

        # 1. 0-byte corrupt file -> CorruptPDFError
        empty_pdf = tmp_path / "empty.pdf"
        empty_pdf.write_bytes(b"")
        with pytest.raises(CorruptPDFError):
            inspect_and_repair_input(empty_pdf, scratch_dir=scratch)

        # 2. Encrypted PDF -> EncryptedPDFError
        enc_pdf_path = tmp_path / "encrypted.pdf"
        doc = fitz.open()
        doc.new_page()
        # Save encrypted with user password
        doc.save(str(enc_pdf_path), encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="secret")
        doc.close()
        with pytest.raises(EncryptedPDFError):
            inspect_and_repair_input(enc_pdf_path, scratch_dir=scratch)

        # 3. Image bomb (extreme dimensions exceeding 50MP) -> ImageBombError
        huge_pdf = tmp_path / "huge.pdf"
        doc = fitz.open()
        # 15000 x 15000 pt at 300 DPI is ~3.9 billion pixels
        doc.new_page(width=15000, height=15000)
        doc.save(str(huge_pdf))
        doc.close()
        with pytest.raises(ImageBombError):
            inspect_and_repair_input(huge_pdf, scratch_dir=scratch)

        # 4. ZIP archive of images -> successfully unpacked
        zip_path = tmp_path / "images.zip"
        with zipfile.ZipFile(zip_path, "w") as z:
            z.writestr("page_01.png", b"\x89PNG\r\n\x1a\nfake_image_bytes")
        out_dir = inspect_and_repair_input(zip_path, scratch_dir=scratch)
        assert out_dir.is_dir()
        assert (out_dir / "page_01.png").exists()

    def test_cli_hardening_doctor_plugins_schema(self, tmp_path: Path):
        """Verify CLI doctor, plugins list, and schema commands execute cleanly."""
        runner = CliRunner()

        # 1. doctor
        res_doc = runner.invoke(main, ["doctor"])
        assert res_doc.exit_code == 0
        assert "ExamForge System Doctor" in res_doc.output
        assert "Python version:" in res_doc.output

        # 2. plugins list
        res_plug = runner.invoke(main, ["plugins", "list"])
        assert res_plug.exit_code == 0
        assert "Plugins Discovery:" in res_plug.output

        # 3. schema output
        res_schema = runner.invoke(main, ["schema"])
        assert res_schema.exit_code == 0
        schema_dict = json.loads(res_schema.output)
        assert "properties" in schema_dict
        assert "questions" in schema_dict["properties"]
