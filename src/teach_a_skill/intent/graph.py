"""Structured Task Graph representation connecting goals, stages, actions, transitions, and entities."""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional

from teach_a_skill.intent.models import DemonstrationUnderstanding


class EdgeType(str, Enum):
    """Categorization of graph edges between task components."""

    TEMPORAL = "TEMPORAL"
    STATE_TRANSITION = "STATE_TRANSITION"
    SUBTASK = "SUBTASK"
    SUPPORTS = "SUPPORTS"
    PRECONDITION = "PRECONDITION"
    POSTCONDITION = "POSTCONDITION"

    def __str__(self) -> str:
        return self.value


@dataclass
class GraphNode:
    """A node in the task understanding graph."""

    node_id: str
    node_type: str  # goal, stage, action, state_transition, entity, precondition, postcondition
    label: str
    metadata: dict[str, Any] = field(default_factory=dict)
    provenance_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GraphNode":
        return cls(**data)


@dataclass
class GraphEdge:
    """A directed edge in the task understanding graph with explicit evidence provenance."""

    source_id: str
    target_id: str
    edge_type: EdgeType
    confidence: float = 1.0
    evidence_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["edge_type"] = str(self.edge_type)
        d["confidence"] = round(self.confidence, 4)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GraphEdge":
        d = dict(data)
        d["edge_type"] = EdgeType(d["edge_type"])
        return cls(**d)


@dataclass
class TaskGraph:
    """Directed graph representing semantic task structure and causal/temporal relations."""

    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)

    def add_node(self, node: GraphNode) -> None:
        self.nodes[node.node_id] = node

    def add_edge(self, edge: GraphEdge) -> None:
        self.edges.append(edge)

    def get_outgoing(self, node_id: str) -> list[GraphEdge]:
        return [e for e in self.edges if e.source_id == node_id]

    def get_incoming(self, node_id: str) -> list[GraphEdge]:
        return [e for e in self.edges if e.target_id == node_id]

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskGraph":
        nodes = {k: GraphNode.from_dict(v) for k, v in data.get("nodes", {}).items()}
        edges = [GraphEdge.from_dict(e) for e in data.get("edges", [])]
        return cls(nodes=nodes, edges=edges)

    @classmethod
    def build_from_understanding(cls, u: DemonstrationUnderstanding) -> "TaskGraph":
        """Constructs a grounded task graph from a DemonstrationUnderstanding object."""
        graph = cls()

        # 1. Goal / Task root node
        goal_id = f"goal_{u.task_id}"
        graph.add_node(
            GraphNode(
                node_id=goal_id,
                node_type="goal",
                label=u.goal or u.task_name,
                metadata={"task_id": u.task_id, "confidence": u.confidence},
                provenance_refs=[r.get("evidence_id", "") for r in u.evidence_refs if isinstance(r, dict)],
            )
        )

        # 2. Preconditions
        for idx, prec in enumerate(u.preconditions):
            prec_id = f"prec_{idx}"
            graph.add_node(
                GraphNode(
                    node_id=prec_id,
                    node_type="precondition",
                    label=prec.description,
                    metadata={"observed": prec.observed},
                    provenance_refs=prec.evidence_refs,
                )
            )
            graph.add_edge(
                GraphEdge(
                    source_id=prec_id,
                    target_id=goal_id,
                    edge_type=EdgeType.PRECONDITION,
                    evidence_refs=prec.evidence_refs,
                )
            )

        # 3. Stages
        prev_stage_id: Optional[str] = None
        for stage in u.stages:
            graph.add_node(
                GraphNode(
                    node_id=stage.stage_id,
                    node_type="stage",
                    label=stage.name,
                    metadata={
                        "description": stage.description,
                        "start_time_ms": stage.start_time_ms,
                        "end_time_ms": stage.end_time_ms,
                        "confidence": stage.confidence,
                    },
                    provenance_refs=stage.evidence_refs,
                )
            )
            # Goal subtask edge
            graph.add_edge(
                GraphEdge(
                    source_id=goal_id,
                    target_id=stage.stage_id,
                    edge_type=EdgeType.SUBTASK,
                    confidence=stage.confidence,
                    evidence_refs=stage.evidence_refs,
                )
            )

            # Temporal sequence between stages
            if prev_stage_id:
                graph.add_edge(
                    GraphEdge(
                        source_id=prev_stage_id,
                        target_id=stage.stage_id,
                        edge_type=EdgeType.TEMPORAL,
                        metadata={"relation": "BEFORE"},
                    )
                )
            prev_stage_id = stage.stage_id

        # 4. Actions
        action_map = {a.action_id: a for a in u.actions}
        for stage in u.stages:
            for act_id in stage.action_ids:
                act = action_map.get(act_id)
                if act:
                    if act.action_id not in graph.nodes:
                        graph.add_node(
                            GraphNode(
                                node_id=act.action_id,
                                node_type="action",
                                label=act.description,
                                metadata={
                                    "action_type": str(act.action_type),
                                    "timestamp_ms": act.timestamp_ms,
                                    "confidence": act.confidence,
                                },
                                provenance_refs=act.evidence_refs,
                            )
                        )
                    # Stage supports action
                    graph.add_edge(
                        GraphEdge(
                            source_id=stage.stage_id,
                            target_id=act.action_id,
                            edge_type=EdgeType.SUPPORTS,
                            confidence=act.confidence,
                            evidence_refs=act.evidence_refs,
                        )
                    )

        # 5. State transitions
        for trans in u.state_transitions:
            graph.add_node(
                GraphNode(
                    node_id=trans.transition_id,
                    node_type="state_transition",
                    label=trans.description,
                    metadata={
                        "before_state": trans.before_state,
                        "after_state": trans.after_state,
                        "transition_type": str(trans.transition_type),
                    },
                    provenance_refs=trans.evidence_refs,
                )
            )
            # Connect transition to goal or relevant stages/actions
            graph.add_edge(
                GraphEdge(
                    source_id=goal_id,
                    target_id=trans.transition_id,
                    edge_type=EdgeType.STATE_TRANSITION,
                    evidence_refs=trans.evidence_refs,
                )
            )

        # 6. Entities
        for ent in u.entities:
            graph.add_node(
                GraphNode(
                    node_id=ent.entity_id,
                    node_type="entity",
                    label=ent.label,
                    metadata={"entity_type": ent.entity_type},
                    provenance_refs=[r.get("evidence_id", "") for r in ent.evidence_refs if isinstance(r, dict)],
                )
            )

        # 7. Postconditions
        for idx, post in enumerate(u.postconditions):
            post_id = f"post_{idx}"
            graph.add_node(
                GraphNode(
                    node_id=post_id,
                    node_type="postcondition",
                    label=post.description,
                    metadata={"observed": post.observed},
                    provenance_refs=post.evidence_refs,
                )
            )
            graph.add_edge(
                GraphEdge(
                    source_id=goal_id,
                    target_id=post_id,
                    edge_type=EdgeType.POSTCONDITION,
                    evidence_refs=post.evidence_refs,
                )
            )

        return graph
