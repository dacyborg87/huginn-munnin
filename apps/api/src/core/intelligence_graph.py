from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


GraphContext = dict[str, Any]
ConditionFunction = Callable[[GraphContext], bool]
HandlerFunction = Callable[[GraphContext], GraphContext]


@dataclass
class Transition:
    condition_function: ConditionFunction
    target_node: str


@dataclass
class Node:
    id: str
    state_type: str
    handler_function: HandlerFunction
    possible_transitions: list[Transition] = field(default_factory=list)


class Graph:
    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}

    def add_node(self, node: Node) -> None:
        self.nodes[node.id] = node

    def add_transition(self, source_node: str, transition: Transition) -> None:
        self.nodes[source_node].possible_transitions.append(transition)

    def resolve_next_state(self, context: GraphContext) -> Node:
        current_state = context["current_state"]
        current_node = self.nodes[current_state]

        for transition in current_node.possible_transitions:
            if transition.condition_function(context):
                return self.nodes[transition.target_node]

        decision_scores = context.get("decision_scores", {})
        if decision_scores:
            selected_state = max(decision_scores, key=decision_scores.get)
            if selected_state in self.nodes:
                return self.nodes[selected_state]

        return current_node
