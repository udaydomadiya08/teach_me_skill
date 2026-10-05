"""Phase 10 execution benchmark: latency, throughput, and resource measurements."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from teach_a_skill.execution.actions import ActionTranslator
from teach_a_skill.execution.engine import ExecutionEngine
from teach_a_skill.execution.environment import SyntheticEnvironmentAdapter
from teach_a_skill.execution.grounding import SemanticGroundingEngine
from teach_a_skill.execution.models import (
    ActionType,
    EnvironmentElement,
    ExecutionPolicy,
)
from teach_a_skill.execution.planner import ExecutionPlanner
from teach_a_skill.execution.safety import ExecutionSafetyPolicy
from teach_a_skill.skill.models import (
    GroundingRequirement,
    GroundingStrategy,
    SkillActionType,
    SkillIR,
    SkillStep,
)


@dataclass
class ExecutionBenchmarkReport:
    """Performance benchmark results for Phase 10."""

    environment_observation_ms: float = 0.0
    grounding_per_step_ms: float = 0.0
    plan_creation_ms: float = 0.0
    dry_run_execution_ms: float = 0.0
    total_benchmark_ms: float = 0.0
    steps_benchmarked: int = 0
    grounding_success_rate: float = 0.0
    memory_estimate_mb: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def print_summary(self) -> None:
        print("\n=== Phase 10 Execution Benchmark ===")
        print(f"Environment observation:  {self.environment_observation_ms:.2f} ms")
        print(f"Grounding per step:       {self.grounding_per_step_ms:.2f} ms")
        print(f"Plan creation:            {self.plan_creation_ms:.2f} ms")
        print(f"Dry-run execution:        {self.dry_run_execution_ms:.2f} ms")
        print(f"Total benchmark:          {self.total_benchmark_ms:.2f} ms")
        print(f"Steps benchmarked:        {self.steps_benchmarked}")
        print(f"Grounding success rate:   {self.grounding_success_rate:.1%}")


def _build_benchmark_skill(num_steps: int = 10) -> SkillIR:
    """Build a synthetic Skill IR for benchmarking."""
    steps = []
    for i in range(num_steps):
        steps.append(
            SkillStep(
                step_id=f"step_{i}",
                ordinal=i,
                action_type=SkillActionType.SELECT,
                target=f"Button {i}",
                description=f"Click on Button {i}",
                grounding=GroundingRequirement(
                    target_name=f"Button {i}",
                    semantic_label=f"Button {i}",
                    preferred_strategy=GroundingStrategy.ACCESSIBILITY,
                ),
            )
        )

    return SkillIR(
        skill_id="benchmark_skill",
        name="Benchmark Skill",
        description="A synthetic skill for benchmarking",
        intent_type="task_completion",
        goal="Complete benchmark actions",
        steps=steps,
    )


def _build_benchmark_environment(num_elements: int = 20) -> SyntheticEnvironmentAdapter:
    """Build a synthetic environment for benchmarking."""
    elements = []
    for i in range(num_elements):
        elements.append(
            EnvironmentElement(
                element_id=f"elem_{i}",
                role="button",
                label=f"Button {i}",
                pixel_x=100 + (i % 5) * 200,
                pixel_y=100 + (i // 5) * 100,
                pixel_width=80,
                pixel_height=30,
                application="BenchmarkApp",
            )
        )
    return SyntheticEnvironmentAdapter(
        elements=elements,
        active_app="BenchmarkApp",
        active_window="Benchmark Window",
    )


def run_execution_benchmark(num_steps: int = 10) -> ExecutionBenchmarkReport:
    """Run Phase 10 execution benchmark."""
    total_start = time.monotonic()
    report = ExecutionBenchmarkReport()

    skill = _build_benchmark_skill(num_steps)
    env = _build_benchmark_environment(num_elements=num_steps * 2)
    grounding = SemanticGroundingEngine()
    translator = ActionTranslator()
    safety = ExecutionSafetyPolicy()
    planner = ExecutionPlanner(
        environment=env,
        grounding_engine=grounding,
        action_translator=translator,
        safety_policy=safety,
    )
    engine = ExecutionEngine(planner=planner, safety_policy=safety)

    # 1. Environment observation
    obs_start = time.monotonic()
    snapshot = env.observe()
    report.environment_observation_ms = (time.monotonic() - obs_start) * 1000

    # 2. Grounding
    grnd_start = time.monotonic()
    results = grounding.ground_all_steps(skill.steps, snapshot)
    grnd_elapsed = (time.monotonic() - grnd_start) * 1000
    report.grounding_per_step_ms = grnd_elapsed / max(1, len(skill.steps))
    report.grounding_success_rate = sum(1 for r in results if r.grounded) / max(1, len(results))

    # 3. Plan creation
    plan_start = time.monotonic()
    plan = planner.create_plan(skill, ExecutionPolicy.DRY_RUN)
    report.plan_creation_ms = (time.monotonic() - plan_start) * 1000

    # 4. Dry-run execution
    exec_start = time.monotonic()
    session = engine.create_session(skill, ExecutionPolicy.DRY_RUN)
    session = engine.execute(session)
    report.dry_run_execution_ms = (time.monotonic() - exec_start) * 1000

    report.steps_benchmarked = num_steps
    report.total_benchmark_ms = (time.monotonic() - total_start) * 1000

    return report
