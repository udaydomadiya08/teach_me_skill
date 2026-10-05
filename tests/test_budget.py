"""Tests for resource budgeting."""

from teach_a_skill.hardware.budget import BudgetCalculator, ResourceBudget
from teach_a_skill.hardware.tiers import HardwareTier


def test_budget_for_weak_cpu(weak_cpu_profile):
    budget = BudgetCalculator.calculate(weak_cpu_profile)
    assert isinstance(budget, ResourceBudget)
    assert budget.tier == HardwareTier.BASELINE
    assert budget.max_memory_mb <= 2048
    assert budget.preferred_memory_mb < budget.max_memory_mb
    assert budget.max_cpu_percent == 50
    assert budget.preferred_model_class == "micro"


def test_budget_for_gpu_workstation(gpu_workstation_profile):
    budget = BudgetCalculator.calculate(gpu_workstation_profile)
    assert budget.tier == HardwareTier.HIGH
    assert budget.max_memory_mb > 6144
    assert budget.accelerator_available is True
    assert budget.preferred_model_class == "medium"
    assert budget.can_allocate_memory(4000) is True
    assert budget.can_allocate_memory(30000) is False


def test_budget_manual_memory_override(gpu_workstation_profile):
    budget = BudgetCalculator.calculate(
        gpu_workstation_profile,
        memory_limit_override_mb=2048,
    )
    assert budget.max_memory_mb == 2048
    assert budget.preferred_memory_mb <= 1433
