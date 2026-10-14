"""
Phase 16.1 — Stage DAG & Dependency Resolver.

Defines StageSpec, dependency-driven DAG ordering, cycle detection,
partial pipeline execution (--from-stage, --to-stage, --only), and
checkpoint cache key computation.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict, deque
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field


class StageSpec(BaseModel):
    """Specification of a pipeline stage in the execution DAG."""

    id: str
    requires: list[str] = Field(default_factory=list)
    provides: list[str] = Field(default_factory=list)
    idempotent: bool = True
    resources: dict[str, Any] = Field(default_factory=dict)
    cache_key_fn: Callable[[Any], str] | None = None


def compute_checkpoint_key(input_hash: str, spec_hash: str, stage_id: str) -> str:
    """
    Checkpoints are keyed by (input_hash + spec_hash + stage_id).
    Unrelated changes do not invalidate checkpoints.
    """
    raw = f"{input_hash}:{spec_hash}:{stage_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


STAGE_ALIASES: dict[str, str] = {
    "s0_probe": "s0_intake",
    "s5_math": "s5_normalize",
    "s5_hindi": "s5_normalize",
}


def resolve_stage_aliases(stages: list[str]) -> list[str]:
    """Resolve aliases in a list of stage IDs, preserving order and removing duplicates."""
    resolved: list[str] = []
    seen = set()
    for s in stages:
        target = STAGE_ALIASES.get(s, s)
        if target not in seen:
            seen.add(target)
            resolved.append(target)
    return resolved


class StageOrderList(list):
    """List with alias resolution support for backwards compatibility."""

    def index(self, value: Any, *args: Any) -> int:
        target = STAGE_ALIASES.get(str(value), value)
        return super().index(target, *args)

    def __contains__(self, value: object) -> bool:
        target = STAGE_ALIASES.get(str(value), value)
        return super().__contains__(target)


DEFAULT_STAGE_ORDER = StageOrderList([
    "s0_intake",
    "s1_profile",
    "s2_clean",
    "s3_parse",
    "s4_structure",
    "s5_normalize",
    "s6_figures",
    "s8_verify",
    "s7_repair",
    "s9_package",
])

STAGE_ORDER = DEFAULT_STAGE_ORDER


class StageDAG:
    """Dependency graph for pipeline stages."""

    def __init__(self, specs: list[StageSpec] | None = None) -> None:
        self.specs: dict[str, StageSpec] = {}
        if specs:
            for s in specs:
                self.add_stage(s)

    def add_stage(self, spec: StageSpec) -> None:
        self.specs[spec.id] = spec

    def get_stage(self, stage_id: str) -> StageSpec | None:
        return self.specs.get(stage_id)

    def detect_cycles(self) -> list[str] | None:
        """
        Detect cycles in the dependency graph using Tarjan's or DFS color algorithm.
        Returns a cycle list if found, else None.
        """
        visited: dict[str, int] = {}  # 0: unvisited, 1: visiting, 2: visited
        stack: list[str] = []

        def dfs(node: str) -> list[str] | None:
            visited[node] = 1
            stack.append(node)

            spec = self.specs.get(node)
            if spec:
                for req in spec.requires:
                    if req not in self.specs:
                        continue
                    if visited.get(req, 0) == 1:
                        # Found cycle
                        cycle_start = stack.index(req)
                        return stack[cycle_start:] + [req]
                    elif visited.get(req, 0) == 0:
                        cycle = dfs(req)
                        if cycle:
                            return cycle

            stack.pop()
            visited[node] = 2
            return None

        for stage_id in self.specs:
            if visited.get(stage_id, 0) == 0:
                cycle = dfs(stage_id)
                if cycle:
                    return cycle
        return None

    def resolve_order(
        self,
        from_stage: str | None = None,
        to_stage: str | None = None,
        only_stage: str | None = None,
    ) -> list[str]:
        """
        Perform topological sort and filter based on partial run flags.
        Raises ValueError if a cycle is detected or invalid stage names are given.
        """
        cycle = self.detect_cycles()
        if cycle:
            raise ValueError(f"Cycle detected in stage DAG: {' -> '.join(cycle)}")

        if only_stage:
            target = STAGE_ALIASES.get(only_stage, only_stage)
            if target not in self.specs:
                raise ValueError(f"Unknown stage '{only_stage}' specified for --only")
            return StageOrderList([target])

        # In-degree computation for topological sort
        in_degree: dict[str, int] = {k: 0 for k in self.specs}
        dependents: dict[str, list[str]] = defaultdict(list)

        for s_id, spec in self.specs.items():
            for req in spec.requires:
                if req in self.specs:
                    in_degree[s_id] += 1
                    dependents[req].append(s_id)

        # Kahn's algorithm
        queue = deque([s_id for s_id, deg in in_degree.items() if deg == 0])
        ordered: list[str] = []

        while queue:
            # Deterministic ordering by stage name if multiple ready
            curr = queue.popleft()
            ordered.append(curr)

            for dep in sorted(dependents[curr]):
                in_degree[dep] -= 1
                if in_degree[dep] == 0:
                    queue.append(dep)

        if len(ordered) != len(self.specs):
            raise ValueError("Dependency resolution failed; possible cyclic dependency")

        # Apply from_stage / to_stage slicing
        start_idx = 0
        end_idx = len(ordered)

        if from_stage:
            eff_from = STAGE_ALIASES.get(from_stage, from_stage)
            if eff_from not in ordered:
                raise ValueError(f"Unknown stage '{from_stage}' specified for --from-stage")
            start_idx = ordered.index(eff_from)

        if to_stage:
            eff_to = STAGE_ALIASES.get(to_stage, to_stage)
            if eff_to not in ordered:
                raise ValueError(f"Unknown stage '{to_stage}' specified for --to-stage")
            end_idx = ordered.index(eff_to) + 1

        if start_idx >= end_idx:
            raise ValueError(
                f"--from-stage '{from_stage}' occurs after --to-stage '{to_stage}' in DAG order"
            )

        return StageOrderList(ordered[start_idx:end_idx])


def get_default_stage_dag() -> StageDAG:
    """Return the standard ExamForge pipeline DAG (Phase O3 reordered and merged)."""
    specs = [
        StageSpec(id="s0_intake", requires=[], provides=["pdf_intake"]),
        StageSpec(id="s1_profile", requires=["s0_intake"], provides=["exam_profile"]),
        StageSpec(id="s2_clean", requires=["s0_intake", "s1_profile"], provides=["cleaned_rasters"]),
        StageSpec(id="s3_parse", requires=["s0_intake", "s2_clean"], provides=["text_blocks", "page_rasters"]),
        StageSpec(id="s4_structure", requires=["s3_parse"], provides=["questions_tree"]),
        StageSpec(id="s5_normalize", requires=["s4_structure"], provides=["canonical_text", "canonical_math"]),
        StageSpec(
            id="s6_figures",
            requires=["s5_normalize"],
            provides=["associated_figures"],
        ),
        StageSpec(id="s8_verify", requires=["s6_figures"], provides=["validation_issues"]),
        StageSpec(id="s7_repair", requires=["s8_verify"], provides=["repaired_questions"]),
        StageSpec(id="s9_package", requires=["s7_repair"], provides=["final_package"]),
    ]
    return StageDAG(specs)
