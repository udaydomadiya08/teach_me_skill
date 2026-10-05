"""Unified learning, outcome analysis, and skill improvement subsystem."""

from teach_a_skill.learning.benchmark import (
    LearningBenchmarkRunner,
    Phase13BenchmarkResults,
)
from teach_a_skill.learning.candidate import (
    CandidateBuilder,
    ShadowEvaluator,
    VersionComparator,
)
from teach_a_skill.learning.detector import (
    FailurePatternDetector,
    VariationDetector,
)
from teach_a_skill.learning.models import (
    CandidateSkillVersion,
    EnvironmentVariation,
    ExecutionRecord,
    FailurePattern,
    ImprovementProposal,
    LearningAudit,
    LearningBudget,
    LearningExperiment,
    PerformanceMetrics,
    PromotionMode,
    PromotionPolicy,
    SkillPerformanceProfile,
    VariationType,
    VersionChangeType,
)
from teach_a_skill.learning.promotion import (
    PromotionManager,
    PromotionPolicyViolationError,
    RollbackManager,
)
from teach_a_skill.learning.proposal import ImprovementGenerator
from teach_a_skill.learning.store import LearningStore
from teach_a_skill.learning.tracker import (
    OutcomeAnalyzer,
    PerformanceTracker,
)
from teach_a_skill.learning.validator import LearningValidator

__all__ = [
    "ExecutionRecord",
    "PerformanceMetrics",
    "SkillPerformanceProfile",
    "FailurePattern",
    "VariationType",
    "EnvironmentVariation",
    "ImprovementProposal",
    "CandidateSkillVersion",
    "PromotionPolicy",
    "PromotionMode",
    "VersionChangeType",
    "LearningBudget",
    "LearningExperiment",
    "LearningAudit",
    "OutcomeAnalyzer",
    "PerformanceTracker",
    "FailurePatternDetector",
    "VariationDetector",
    "ImprovementGenerator",
    "CandidateBuilder",
    "ShadowEvaluator",
    "VersionComparator",
    "PromotionManager",
    "PromotionPolicyViolationError",
    "RollbackManager",
    "LearningStore",
    "LearningValidator",
    "LearningBenchmarkRunner",
    "Phase13BenchmarkResults",
]
