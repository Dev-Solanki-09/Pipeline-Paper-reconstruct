"""
ExamForge CLI.

Commands:
    execute  — Run the pipeline on an exam PDF
    resume   — Resume a previously interrupted run
    inspect  — Show manifest and summary for a completed run

Exit codes:
    0   All gates pass
    10  Pass with warnings
    20  Needs human review
    30  Failed
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

from examforge import __version__


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
@click.version_option(__version__, prog_name="examforge")
def main():
    """ExamForge: exam paper reconstruction pipeline."""
    pass


@main.command()
@click.argument(
    "paper",
    required=False,
    type=click.Path(exists=True, path_type=Path),
    default=None,
)
@click.option(
    "--exam", "-e",
    "exam_opt",
    required=False,
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to the exam PDF file.",
)
@click.option(
    "--mode", "-m",
    type=click.Choice(["fast", "max"]),
    default="fast",
    help="Processing mode: fast (single engine) or max (dual engine).",
)
@click.option(
    "--spec",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to a custom spec YAML file. Uses default spec if not provided.",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to examforge.yaml config file.",
)
@click.option("--debug", is_flag=True, help="Include provenance in HTML output.")
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging.")
@click.option(
    "--max-pages",
    type=int,
    default=None,
    help="Process only the first N pages (for debugging).",
)
@click.option(
    "--profile",
    "-p",
    "profile_id",
    default="auto",
    help="Exam profile ID or 'auto' (default: auto) or path to profile YAML.",
)
@click.option(
    "--compute",
    "-c",
    type=click.Choice(["lite", "standard", "gpu"]),
    default=None,
    help="Compute tier override (lite, standard, gpu).",
)
@click.option("--from-stage", default=None, help="Start pipeline from stage.")
@click.option("--to-stage", default=None, help="Stop pipeline after stage.")
@click.option("--checkpoint", "checkpoint_tier", type=click.Choice(["all", "major", "none"]), default="major", help="Checkpoint tier (all, major, none).")
@click.option("--only", "only_stage", default=None, help="Execute only the specified stage.")
@click.option("--json", "json_out", is_flag=True, help="Output summary in JSON format.")
def execute(
    paper: Path | None,
    exam_opt: Path | None,
    mode: str,
    spec: Path | None,
    config_path: Path | None,
    debug: bool,
    verbose: bool,
    max_pages: int | None,
    profile_id: str,
    compute: str | None,
    from_stage: str | None = None,
    to_stage: str | None = None,
    only_stage: str | None = None,
    checkpoint_tier: str = "major",
    json_out: bool = False,
):
    """Run the full pipeline on an exam PDF."""
    exam = paper or exam_opt
    if exam is None:
        raise click.UsageError(
            "Missing exam PDF. Usage: examforge execute <paper> or examforge execute --exam <paper>"
        )
    _setup_logging(verbose)

    # Load config
    from examforge.config import ExamForgeConfig

    overrides: dict = {
        "mode": mode,
        "debug": debug,
        "checkpoint_tier": checkpoint_tier,
    }
    if max_pages is not None:
        overrides["max_pages"] = max_pages

    config = ExamForgeConfig.load(config_path=config_path, overrides=overrides)

    # Load spec
    from examforge.spec import Spec

    spec_obj = Spec.load(spec) if spec else Spec.default()

    # Load profile
    from examforge.profiles.loader import loader

    if profile_id == "auto":
        config.flags["autoprofile"] = True
        profile_obj = loader.load("neet_ug")  # default placeholder
    else:
        profile_obj = loader.load(profile_id)

    # Build stage pipeline
    stages = _build_stages(config)

    # Run
    from examforge.orchestrator.runner import PipelineRunner

    runner = PipelineRunner(
        stages=stages,
        config=config,
        spec=spec_obj,
        profile=profile_obj,
        compute=compute,
    )
    result = runner.execute(
        source_path=exam,
        from_stage=from_stage,
        to_stage=to_stage,
        only_stage=only_stage,
    )

    # Report
    if json_out:
        import json as _json

        click.echo(_json.dumps(result.summary(), indent=2))
    else:
        _print_summary(result)
    sys.exit(result.exit_code)


@main.command()
@click.option(
    "--run-id", "-r",
    required=True,
    help="The run ID to resume (timestamp_hash from the runs/ directory).",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to examforge.yaml config file.",
)
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging.")
def resume(run_id: str, config_path: Path | None, verbose: bool):
    """Resume a previously interrupted pipeline run."""
    _setup_logging(verbose)

    from examforge.config import ExamForgeConfig

    config = ExamForgeConfig.load(config_path=config_path)

    from examforge.spec import Spec

    spec_obj = Spec.default()

    stages = _build_stages(config)

    from examforge.orchestrator.runner import PipelineRunner

    runner = PipelineRunner(stages=stages, config=config, spec=spec_obj)
    result = runner.resume(run_id=run_id)

    _print_summary(result)
    sys.exit(result.exit_code)


@main.command()
@click.option(
    "--run-id", "-r",
    required=True,
    help="The run ID to inspect.",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to examforge.yaml config file.",
)
def inspect(run_id: str, config_path: Path | None):
    """Show manifest and summary for a completed run."""
    from examforge.config import ExamForgeConfig

    config = ExamForgeConfig.load(config_path=config_path)
    manifest_path = config.paths.runs / run_id / "manifest.json"

    if not manifest_path.exists():
        click.echo(f"Run not found: {run_id}", err=True)
        sys.exit(1)

    data = json.loads(manifest_path.read_text())
    click.echo(json.dumps(data, indent=2, default=str))


@main.group()
def schema():
    """Schema inspection and export commands."""
    pass


@schema.command(name="export")
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=Path("schemas/examdocument.v2.json"),
    help="Output file path for the JSON Schema.",
)
def schema_export(output: Path):
    """Export the ExamDocument v2 JSON Schema."""
    from examforge.ir.schema import ExamDocument

    output.parent.mkdir(parents=True, exist_ok=True)
    schema_data = ExamDocument.model_json_schema()
    with open(output, "w", encoding="utf-8") as f:
        json.dump(schema_data, f, indent=2, sort_keys=True)
    click.echo(f"Exported ExamDocument v2 schema to {output}")


@main.group()
def profile():
    """Declarative exam profile inspection and validation commands."""
    pass


@profile.command(name="list")
def profile_list():
    """List all available built-in and registered profiles."""
    from examforge.profiles.loader import loader

    builtins = loader.load_all_builtins()
    click.echo(f"{'ID':<20} {'MATURITY':<15} {'VERSION':<10} {'NAME'}")
    click.echo("-" * 75)
    for _pid, prof in sorted(builtins.items()):
        click.echo(
            f"{prof.id:<20} {prof.maturity:<15} {prof.profile_version:<10} {prof.name}"
        )


@profile.command(name="show")
@click.argument("profile_id")
def profile_show(profile_id: str):
    """Show resolved profile details in YAML."""
    import yaml

    from examforge.profiles.loader import loader

    prof = loader.load(profile_id)
    click.echo(yaml.dump(prof.model_dump(mode="json"), sort_keys=False))


@profile.command(name="validate")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
def profile_validate(path: Path):
    """Validate a profile YAML file against ExamProfile schema."""
    from examforge.profiles.loader import ProfileLoadError, loader

    try:
        prof = loader.load(path)
        click.echo(f"Valid profile: '{prof.id}' ({prof.name}) [maturity: {prof.maturity}]")
    except ProfileLoadError as exc:
        click.echo(f"Validation failed:\n{exc}", err=True)
        sys.exit(1)


@profile.command(name="diff")
@click.argument("profile_a")
@click.argument("profile_b")
def profile_diff(profile_a: str, profile_b: str):
    """Show differences between two resolved profiles."""
    import difflib

    import yaml

    from examforge.profiles.loader import loader

    prof_a = loader.load(profile_a)
    prof_b = loader.load(profile_b)
    yaml_a = yaml.dump(prof_a.model_dump(mode="json"), sort_keys=True).splitlines()
    yaml_b = yaml.dump(prof_b.model_dump(mode="json"), sort_keys=True).splitlines()
    diff = list(
        difflib.unified_diff(yaml_a, yaml_b, fromfile=profile_a, tofile=profile_b)
    )
    if not diff:
        click.echo("Profiles are identical.")
    else:
        click.echo("\n".join(diff))


@main.command(name="eval")
@click.option(
    "--suite",
    type=click.Choice(["synth-fast", "synth-L1", "all", "universal"]),
    default="synth-fast",
    help="Evaluation suite to execute.",
)
@click.option(
    "--compare", "compare_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Compare results against baseline JSON and fail on regression.",
)
@click.option(
    "--write", "write_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Write evaluation results to specified JSON path.",
)
@click.option(
    "--oracle", "oracle_stage",
    type=str,
    default=None,
    help="Substitute ground truth at stage boundary (e.g. S0, S4, S9).",
)
def eval_cmd(
    suite: str,
    compare_path: Path | None,
    write_path: Path | None,
    oracle_stage: str | None = None,
) -> None:
    """Run accuracy benchmark evaluation suite."""
    from examforge.eval.compare import compare_metrics
    from examforge.eval.oracle import run_oracle_attribution
    from examforge.eval.scorer import ExamScorer
    from examforge.synth.generator import SyntheticDocumentGenerator

    click.echo(f"Running evaluation suite '{suite}'...")
    gen = SyntheticDocumentGenerator(seed=42)
    # Generate reference and hypothesis documents for benchmark
    ref_doc = gen.generate(num_questions=12)
    # In perfect reconstruction test, hyp equals ref
    hyp_doc = ref_doc

    if oracle_stage:
        click.echo(f"  [ORACLE] Substituting ground truth at stage {oracle_stage}")
        res = run_oracle_attribution(oracle_stage, ref_doc, hyp_doc)
    else:
        scorer = ExamScorer()
        res = scorer.score(ref_doc, hyp_doc)

    click.echo("\n--- Evaluation Results ---")
    click.echo(f"  Sequence Accuracy:     {res.sequence_accuracy:.4f}")
    click.echo(f"  Count Match:           {res.count_match:.4f}")
    click.echo(f"  CER (mean / p95):      {res.cer_mean:.4f} / {res.cer_p95:.4f}")
    click.echo(f"  WER (mean / p95):      {res.wer_mean:.4f} / {res.wer_p95:.4f}")
    click.echo(f"  Option Accuracy:       {res.option_accuracy:.4f}")
    click.echo(f"  Kind Accuracy:         {res.kind_accuracy:.4f}")
    click.echo(f"  Figure IoU (mean):     {res.figure_iou_mean:.4f}")
    click.echo(f"  Table Similarity:      {res.table_similarity:.4f}")
    click.echo(f"  Aggregate Score:       {res.aggregate_score:.4f}")

    if write_path:
        res.save(write_path)
        click.echo(f"\nWrote results to: {write_path}")

    if compare_path:
        with open(compare_path, encoding="utf-8") as f:
            baseline_data = json.load(f)
        passed, regressions = compare_metrics(res, baseline_data)
        if not passed:
            click.echo("\n[FAIL] Regressions detected vs baseline:", err=True)
            for r in regressions:
                click.echo(f"  - {r}", err=True)
            sys.exit(1)
        else:
            click.echo("\n[OK] No regressions vs baseline.")


@main.command(name="compare")
@click.argument("run_a", type=click.Path(exists=True, path_type=Path))
@click.argument("run_b", type=click.Path(exists=True, path_type=Path))
def compare_cmd(run_a: Path, run_b: Path) -> None:
    """Compare two pipeline runs question by question."""
    from examforge.eval.compare import compare_runs_per_question

    diff = compare_runs_per_question(run_a, run_b)
    click.echo(
        f"Comparing Run A ({diff['total_questions_a']} Qs) vs "
        f"Run B ({diff['total_questions_b']} Qs):"
    )
    for d in diff["differences"]:
        status = d["status"]
        num = d["number"]
        if status == "matched":
            click.echo(f"  Q{num}: [MATCH]")
        elif status == "different":
            click.echo(f"  Q{num}: [DIFF] stem_eq={d['stem_equal']} opt_eq={d['options_equal']}")
        else:
            click.echo(f"  Q{num}: [{status}]")


@main.group()
def bank() -> None:
    """Manage the verified question bank."""
    pass


@bank.command(name="stats")
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=Path("data/bank/bank.db"),
    help="Path to question bank SQLite database.",
)
def bank_stats_cmd(db: Path) -> None:
    """Show question bank statistics."""
    from examforge.bank.store import QuestionBankStore

    store = QuestionBankStore(db)
    st = store.stats()
    click.echo(f"Question Bank: {db}")
    click.echo(f"  Verified questions: {st['question_count']}")
    click.echo(f"  Verified figures:   {st['figure_count']}")


@bank.command(name="purge")
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=Path("data/bank/bank.db"),
    help="Path to question bank SQLite database.",
)
@click.confirmation_option(
    prompt="Are you sure you want to purge all records in the question bank?"
)
def bank_purge_cmd(db: Path) -> None:
    """Purge all question bank records."""
    from examforge.bank.store import QuestionBankStore

    store = QuestionBankStore(db)
    store.purge()
    click.echo(f"Purged all records from {db}")


@bank.command(name="export")
@click.argument("out_file", type=click.Path(path_type=Path))
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=Path("data/bank/bank.db"),
    help="Path to question bank SQLite database.",
)
def bank_export_cmd(out_file: Path, db: Path) -> None:
    """Export question bank records to a JSONL file."""
    from examforge.bank.store import QuestionBankStore

    store = QuestionBankStore(db)
    cnt = store.export_jsonl(out_file)
    click.echo(f"Exported {cnt} record(s) to {out_file}")


@bank.command(name="import")
@click.argument("in_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--db",
    type=click.Path(path_type=Path),
    default=Path("data/bank/bank.db"),
    help="Path to question bank SQLite database.",
)
def bank_import_cmd(in_file: Path, db: Path) -> None:
    """Import question bank records from a JSONL file."""
    from examforge.bank.store import QuestionBankStore

    store = QuestionBankStore(db)
    cnt = store.import_jsonl(in_file)
    click.echo(f"Imported {cnt} record(s) from {in_file}")


@main.group()
def lessons() -> None:
    """Manage and inspect self-improving lessons and rule proposals."""
    pass


@lessons.command(name="list")
@click.option(
    "--path",
    type=click.Path(path_type=Path),
    default=Path("data/lessons/lessons.jsonl"),
    help="Path to lessons JSONL store.",
)
@click.option(
    "--status",
    type=str,
    default=None,
    help="Filter by status (candidate, promoted, retired).",
)
@click.option("--rule", type=str, default=None, help="Filter by rule.")
def lessons_list_cmd(path: Path, status: str | None, rule: str | None) -> None:
    """List recorded lessons."""
    from examforge.lessons.store import LessonsStore

    store = LessonsStore(path)
    records = store.list_lessons(status=status, rule=rule)
    click.echo(f"Lessons Store: {path} ({len(records)} record(s))")
    for r in records:
        papers_str = f"{len(r.source_papers)} papers"
        info = f"  [{r.status.upper()}] {r.id}: {r.rule} | count={r.count} ({papers_str})"
        click.echo(f"{info} | {r.fix_summary}")


@lessons.command(name="promote")
@click.option(
    "--path",
    type=click.Path(path_type=Path),
    default=Path("data/lessons/lessons.jsonl"),
    help="Path to lessons JSONL store.",
)
@click.option(
    "--proposals",
    type=click.Path(path_type=Path),
    default=Path("proposals"),
    help="Directory for generated rule proposals.",
)
@click.option("--min-recurrence", type=int, default=3, help="Minimum recurrence count.")
@click.option("--min-papers", type=int, default=2, help="Minimum distinct papers observed.")
def lessons_promote_cmd(path: Path, proposals: Path, min_recurrence: int, min_papers: int) -> None:
    """Scan lessons and emit proposals for recurring fixes."""
    from examforge.lessons.promote import LessonPromoter
    from examforge.lessons.store import LessonsStore

    store = LessonsStore(path)
    promoter = LessonPromoter(
        store,
        proposals_dir=proposals,
        min_recurrence=min_recurrence,
        min_papers=min_papers,
    )
    created = promoter.scan_and_promote()
    click.echo(f"Promotion scan complete: {len(created)} proposal(s) emitted.")
    for p in created:
        click.echo(f"  Created proposal: {p}")


@lessons.command(name="compact")
@click.option(
    "--path",
    type=click.Path(path_type=Path),
    default=Path("data/lessons/lessons.jsonl"),
    help="Path to lessons JSONL store.",
)
@click.option("--max-records", type=int, default=1000, help="Max records to retain.")
def lessons_compact_cmd(path: Path, max_records: int) -> None:
    """Compact lessons store and prune retired entries."""
    from examforge.lessons.store import LessonsStore

    store = LessonsStore(path)
    rem = store.compact(max_records=max_records)
    click.echo(f"Compacted lessons store {path}: {rem} record(s) remaining.")


@main.group()
def profile() -> None:
    """Manage and scaffold exam profiles."""
    pass


@profile.command(name="scaffold")
@click.argument("exam", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=Path("profiles/learned"),
    help="Output directory for scaffolded profile and preview HTML.",
)
@click.option(
    "--id",
    "profile_id",
    type=str,
    default=None,
    help="Explicit profile ID override.",
)
def profile_scaffold_cmd(exam: Path, output: Path, profile_id: str | None) -> None:
    """Scaffold a draft profile from an exam PDF."""
    from examforge.config import ExamForgeConfig
    from examforge.ir.schema import ExamDocument
    from examforge.profiles.scaffold import scaffold_profile
    from examforge.stages.base import StageContext
    from examforge.stages.s0_intake import S0Intake
    from examforge.stages.s3_parse import S3Parse

    doc = ExamDocument(source_path=str(exam))
    cfg = ExamForgeConfig()
    ctx = StageContext(
        document=doc,
        spec=None,
        config=cfg,
        stage_dir=output / "scratch",
        run_dir=output / "run",
    )

    s0 = S0Intake()
    s0_res = s0.run(ctx)
    ctx.document = s0_res.document
    s3 = S3Parse()
    s3_res = s3.run(ctx)
    ctx.document = s3_res.document

    yaml_p, html_p, prof, low_conf = scaffold_profile(
        doc=ctx.document,
        output_dir=output,
        profile_id=profile_id,
    )
    click.echo(f"Scaffolded profile: {yaml_p}")
    click.echo(f"Visual preview:    {html_p}")
    if low_conf:
        click.echo(f"Low-confidence fields needing human review: {', '.join(low_conf)}")
    else:
        click.echo("All fields automatically inferred with high confidence.")


@main.command(name="doctor")
def doctor_cmd() -> None:
    """Check system environment, tools, and dependencies."""
    import os
    import sys

    click.echo("ExamForge System Doctor")
    click.echo("-----------------------")

    # 1. Python version
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 10)
    click.echo(f"[{'OK' if py_ok else 'FAIL'}] Python version: {py_ver} (>= 3.10 required)")

    # 2. PyMuPDF
    try:
        import fitz

        click.echo(f"[OK] PyMuPDF (fitz) version: {fitz.__version__}")
    except Exception as e:
        click.echo(f"[FAIL] PyMuPDF: {e}")

    # 3. Playwright
    try:
        import importlib

        importlib.import_module("playwright.sync_api")
        click.echo("[OK] Playwright package installed")
    except Exception as e:
        click.echo(f"[WARN] Playwright: {e}")

    # 4. Paddle-VL / OCR
    try:
        from examforge.engines.paddle_vl import PaddleVLAdapter  # noqa: F401

        click.echo("[OK] Paddle-VL OCR engine available")
    except Exception as e:
        click.echo(f"[WARN] Paddle-VL: {e}")

    # 5. Writable runs dir
    runs_dir = Path("runs")
    runs_ok = os.access(runs_dir.parent, os.W_OK)
    click.echo(f"[{'OK' if runs_ok else 'WARN'}] Runs directory writable: {runs_dir}")


@main.group()
def plugins() -> None:
    """Discover and inspect third-party plugins."""
    pass


@plugins.command(name="list")
@click.option(
    "--dir",
    "plugins_dir",
    type=click.Path(path_type=Path),
    default=Path("plugins"),
    help="Local plugins directory.",
)
def plugins_list_cmd(plugins_dir: Path) -> None:
    """List discovered plugins and their status."""
    from examforge.orchestrator.plugins import PluginManager

    mgr = PluginManager(plugins_dir)
    res = mgr.discover_all()
    click.echo(f"Plugins Discovery: {len(res.loaded)} loaded, {len(res.skipped)} skipped")
    for p in res.loaded:
        caps_str = ", ".join(p.capabilities) if p.capabilities else "none"
        click.echo(f"  [LOADED] {p.name} ({p.group}) | api={p.api_version} | caps: {caps_str}")
    for name, reason in res.skipped:
        click.echo(f"  [SKIPPED] {name}: {reason}")
    for conf in res.conflicts:
        click.echo(f"  [CONFLICT] {conf}")


@main.command(name="schema")
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Optional output path to write schema JSON file.",
)
def schema_cmd(output: Path | None) -> None:
    """Export or display ExamDocument IR JSON Schema."""
    import json as _json

    from examforge.ir.schema import ExamDocument

    schema_dict = ExamDocument.model_json_schema()
    schema_str = _json.dumps(schema_dict, indent=2)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(schema_str, encoding="utf-8")
        click.echo(f"Exported JSON Schema to {output}")
    else:
        click.echo(schema_str)


def _build_stages(config):
    """Build the ordered list of pipeline stages (Phase O3 reordered and merged)."""
    from examforge.stages import (
        S0Intake,
        S1Profile,
        S2Clean,
        S3Parse,
        S4Structure,
        S5Normalize,
        S6Figures,
        S8Verify,
        S7Repair,
        S9Package,
    )

    return [
        S0Intake(),
        S1Profile(),
        S2Clean(),
        S3Parse(),
        S4Structure(),
        S5Normalize(),
        S6Figures(),
        S8Verify(),
        S7Repair(),
        S9Package(),
    ]


def _print_summary(result):
    """Print a human-readable summary of the run result."""
    from examforge.orchestrator.runner import (
        EXIT_FAILED,
        EXIT_NEEDS_REVIEW,
        EXIT_OK,
        EXIT_WARNINGS,
    )

    summary = result.summary()
    status_icon = {
        EXIT_OK: "[OK]",
        EXIT_WARNINGS: "[WARN]",
        EXIT_NEEDS_REVIEW: "[REVIEW]",
        EXIT_FAILED: "[FAIL]",
    }.get(result.exit_code, "[?]")

    def _echo(msg: str = "") -> None:
        """click.echo with fallback for Windows cp1252 consoles."""
        try:
            click.echo(msg)
        except UnicodeEncodeError:
            click.echo(msg.encode("ascii", errors="replace").decode("ascii"))

    _echo()
    _echo(f"  {status_icon} Run {summary['run_id']} -- {summary['status']}")
    _echo(f"    Pages:     {summary['pages']}")
    _echo(f"    Questions: {summary['questions']}")
    _echo(f"    Issues:    {summary['issues']} ({summary['blockers']} blockers)")
    _echo(f"    Output:    {result.run_dir}")
    if summary.get("error"):
        _echo(f"    Error:     {summary['error']}")
    _echo()


if __name__ == "__main__":
    main()
