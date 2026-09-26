from __future__ import annotations

from collections import defaultdict
from typing import Iterable

import networkx as nx

from .models import (
    AdmissionResult,
    AdmissionStage,
    AdmissionStatus,
    CanonicalMechanism,
    IdeaCandidate,
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
)


def _node_key(value: str) -> str:
    """Return the stable graph identity for a human-readable causal node."""
    return " ".join(value.casefold().split())


class StructuralValidationError(ValueError):
    """Raised when quality evaluation is attempted for an invalid mechanism."""

    def __init__(self, report: ValidationReport):
        self.report = report
        self.admission = AdmissionResult(
            status=AdmissionStatus.REJECTED,
            stage=AdmissionStage.STRUCTURAL_VALIDITY,
            reasons=tuple(
                issue.message for issue in report.issues
                if issue.severity == ValidationSeverity.FATAL
            ),
        )
        rules = ", ".join(issue.rule for issue in report.issues if issue.severity == ValidationSeverity.FATAL)
        super().__init__(f"causal mechanism failed structural validation: {rules}")


class CausalGraphValidator:
    """Deterministic structural validation for canonical causal mechanisms."""

    _CONTRADICTORY_RELATIONS = (
        frozenset(("increases", "decreases")),
        frozenset(("enables", "prevents")),
    )

    def build_graph(self, value: IdeaCandidate | CanonicalMechanism) -> nx.MultiDiGraph:
        mechanism = self._mechanism(value)
        graph = nx.MultiDiGraph()
        payoff = _node_key(mechanism.payoff)
        graph.add_node(payoff, label=mechanism.payoff, is_payoff=True)

        for index, link in enumerate(mechanism.causal_structure):
            cause, effect = _node_key(link.cause), _node_key(link.effect)
            graph.add_node(cause, label=link.cause, is_payoff=cause == payoff)
            graph.add_node(effect, label=link.effect, is_payoff=effect == payoff)
            graph.add_edge(cause, effect, key=index, relation=link.relation)

        graph.graph["payoff"] = payoff
        return graph

    # A convenient alternate name for callers that think in terms of conversion.
    to_graph = build_graph

    def validate(self, value: IdeaCandidate | CanonicalMechanism) -> ValidationReport:
        if isinstance(value, IdeaCandidate) and value.mechanism is None:
            return self._report([
                ValidationIssue(
                    severity=ValidationSeverity.FATAL,
                    rule="missing_mechanism",
                    message="The candidate has no canonical mechanism to validate.",
                )
            ])

        mechanism = self._mechanism(value)
        graph = self.build_graph(mechanism)
        payoff: str = graph.graph["payoff"]
        issues: list[ValidationIssue] = []

        if not mechanism.causal_structure:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.FATAL,
                rule="payoff_reachability",
                message="The causal graph is empty, so no intervention can reach the payoff.",
                involved_nodes=(self._label(graph, payoff),),
            ))
            return self._report(issues)

        issues.extend(self._contradiction_issues(graph))

        interventions = tuple(
            node for node in graph.nodes
            if node != payoff and graph.in_degree(node) == 0
        )
        successful_paths = self._paths_to_payoff(graph, interventions, payoff)
        if not successful_paths:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.FATAL,
                rule="payoff_reachability",
                message="No causal path connects an intervention to the declared payoff.",
                involved_nodes=tuple(self._label(graph, node) for node in (*interventions, payoff)),
                witness_path=self._failed_path_witness(graph, interventions, payoff),
            ))

        issues.extend(self._orphan_issues(graph, interventions, payoff))
        issues.extend(self._cycle_issues(graph, payoff))
        return self._report(issues)

    @staticmethod
    def _mechanism(value: IdeaCandidate | CanonicalMechanism) -> CanonicalMechanism:
        if isinstance(value, CanonicalMechanism):
            return value
        if isinstance(value, IdeaCandidate):
            if value.mechanism is None:
                raise ValueError("candidate has no mechanism")
            return value.mechanism
        raise TypeError("validator requires an IdeaCandidate or CanonicalMechanism")

    @staticmethod
    def _report(issues: list[ValidationIssue]) -> ValidationReport:
        return ValidationReport(
            is_valid=not any(issue.severity == ValidationSeverity.FATAL for issue in issues),
            issues=issues,
        )

    @staticmethod
    def _label(graph: nx.MultiDiGraph, node: str) -> str:
        return str(graph.nodes[node].get("label", node))

    def _labels(self, graph: nx.MultiDiGraph, nodes: Iterable[str]) -> tuple[str, ...]:
        return tuple(self._label(graph, node) for node in sorted(nodes))

    def _contradiction_issues(self, graph: nx.MultiDiGraph) -> list[ValidationIssue]:
        relations_by_pair: dict[tuple[str, str], set[str]] = defaultdict(set)
        for cause, effect, data in graph.edges(data=True):
            relations_by_pair[(cause, effect)].add(data["relation"])

        issues = []
        for (cause, effect), relations in sorted(relations_by_pair.items()):
            conflicts = [pair for pair in self._CONTRADICTORY_RELATIONS if pair <= relations]
            if conflicts:
                named = sorted({relation for pair in conflicts for relation in pair})
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.FATAL,
                    rule="contradictory_links",
                    message=(
                        f"The same causal pair has contradictory relations: "
                        f"{', '.join(named)}."
                    ),
                    involved_nodes=(self._label(graph, cause), self._label(graph, effect)),
                    witness_path=(self._label(graph, cause), self._label(graph, effect)),
                ))
        return issues

    @staticmethod
    def _paths_to_payoff(
        graph: nx.MultiDiGraph, interventions: Iterable[str], payoff: str
    ) -> list[list[str]]:
        paths = []
        for intervention in interventions:
            if nx.has_path(graph, intervention, payoff):
                paths.append(nx.shortest_path(graph, intervention, payoff))
        return paths

    def _failed_path_witness(
        self, graph: nx.MultiDiGraph, interventions: tuple[str, ...], payoff: str
    ) -> tuple[str, ...]:
        """Show a deterministic maximal causal prefix when payoff is unreachable."""
        best: list[str] = []
        for intervention in interventions:
            lengths = nx.single_source_shortest_path_length(graph, intervention)
            if not lengths:
                continue
            furthest = min(
                (node for node, distance in lengths.items() if distance == max(lengths.values())),
                default=intervention,
            )
            path = nx.shortest_path(graph, intervention, furthest)
            if len(path) > len(best):
                best = path
        if best:
            return tuple(self._label(graph, node) for node in best)
        return (self._label(graph, payoff),)

    def _orphan_issues(
        self, graph: nx.MultiDiGraph, interventions: tuple[str, ...], payoff: str
    ) -> list[ValidationIssue]:
        reachable_from_intervention: set[str] = set()
        for intervention in interventions:
            reachable_from_intervention.add(intervention)
            reachable_from_intervention.update(nx.descendants(graph, intervention))

        reaches_payoff = set(nx.ancestors(graph, payoff)) | {payoff}
        causal_nodes = set(graph.nodes) - {payoff}
        orphan_nodes = {
            node for node in causal_nodes
            if node not in reachable_from_intervention or node not in reaches_payoff
        }
        if not orphan_nodes:
            return []

        no_entry = orphan_nodes - reachable_from_intervention
        no_payoff = orphan_nodes - reaches_payoff
        details = []
        if no_entry:
            details.append("not reachable from an intervention")
        if no_payoff:
            details.append("unable to reach payoff")
        return [ValidationIssue(
            severity=ValidationSeverity.WARNING,
            rule="orphan_nodes",
            message=f"Orphan or dangling nodes are {' and '.join(details)}.",
            involved_nodes=self._labels(graph, orphan_nodes),
        )]

    def _cycle_issues(self, graph: nx.MultiDiGraph, payoff: str) -> list[ValidationIssue]:
        issues = []
        for component in nx.strongly_connected_components(graph):
            is_cycle = len(component) > 1 or any(graph.has_edge(node, node) for node in component)
            if not is_cycle or payoff in component:
                continue
            if any(nx.has_path(graph, node, payoff) for node in component):
                # The feedback loop has an exit to progress/payoff and is productive.
                continue
            subgraph = graph.subgraph(component)
            cycle_edges = nx.find_cycle(subgraph)
            cycle_nodes = [cycle_edges[0][0], *(edge[1] for edge in cycle_edges)]
            issues.append(ValidationIssue(
                severity=ValidationSeverity.FATAL,
                rule="terminal_free_cycle",
                message="A closed feedback cycle has no causal exit toward the payoff.",
                involved_nodes=self._labels(graph, component),
                witness_path=tuple(self._label(graph, node) for node in cycle_nodes),
            ))
        return issues


# Blueprint terminology uses both names; keep one implementation and two public APIs.
StaticStructuralValidator = CausalGraphValidator
