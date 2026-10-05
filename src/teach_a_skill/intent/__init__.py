"""Phase 7: Intent & Demonstration Understanding Layer.

Transforms multimodal observations, canonical events, perception, and speech evidence
into structured task representations, goals, semantic actions, and grounded intent models.
"""

from teach_a_skill.intent.benchmark import IntentBenchmarkRunner
from teach_a_skill.intent.cache import IntentCache
from teach_a_skill.intent.graph import EdgeType, GraphEdge, GraphNode, TaskGraph
from teach_a_skill.intent.models import (
    ActionType,
    DemonstratedIntent,
    DemonstrationUnderstanding,
    IntentManifest,
    IntentType,
    Postcondition,
    Precondition,
    SemanticAction,
    StateTransition,
    StateTransitionType,
    TaskAmbiguity,
    TaskEntity,
    TaskStage,
)
from teach_a_skill.intent.pipeline import IntentPipeline
from teach_a_skill.intent.providers.base import (
    SemanticCapabilities,
    SemanticProvider,
    SemanticProviderCategory,
)
from teach_a_skill.intent.providers.deterministic import DeterministicSemanticProvider
from teach_a_skill.intent.providers.local_llm import LocalLLMProvider
from teach_a_skill.intent.providers.mock import MockSemanticProvider
from teach_a_skill.intent.providers.registry import SemanticProviderRegistry
from teach_a_skill.intent.query import IntentQueryEngine
from teach_a_skill.intent.storage import IntentStorage
from teach_a_skill.intent.validator import IntentValidator

__all__ = [
    "ActionType",
    "DemonstratedIntent",
    "DemonstrationUnderstanding",
    "DeterministicSemanticProvider",
    "EdgeType",
    "GraphEdge",
    "GraphNode",
    "IntentBenchmarkRunner",
    "IntentCache",
    "IntentManifest",
    "IntentPipeline",
    "IntentQueryEngine",
    "IntentStorage",
    "IntentType",
    "IntentValidator",
    "LocalLLMProvider",
    "MockSemanticProvider",
    "Postcondition",
    "Precondition",
    "SemanticAction",
    "SemanticCapabilities",
    "SemanticProvider",
    "SemanticProviderCategory",
    "SemanticProviderRegistry",
    "StateTransition",
    "StateTransitionType",
    "TaskAmbiguity",
    "TaskEntity",
    "TaskGraph",
    "TaskStage",
]
