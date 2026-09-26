"""Quality-Diversity descriptors derived from mechanism dynamics.

These descriptors deliberately contain no quality, feasibility, or constraint
scores.  They describe where a mechanism behaves, while EvaluationBundle says
whether it is admissible and EvaluationScores say how well it performs.
"""

from __future__ import annotations

import networkx as nx

from .models import CanonicalMechanism, DynamicalNicheDescriptor


def _key(value: str) -> str:
    return " ".join(value.casefold().split())


def dynamical_niche_descriptor(
    mechanism: CanonicalMechanism,
) -> DynamicalNicheDescriptor:
    graph = nx.DiGraph()
    payoff = _key(mechanism.payoff)
    graph.add_node(payoff)
    for link in mechanism.causal_structure:
        graph.add_edge(_key(link.cause), _key(link.effect))

    if not graph.nodes:
        return DynamicalNicheDescriptor(
            causal_depth=0,
            branching_factor=0.0,
            loop_density=0.0,
            payoff_path_length=None,
        )

    components = list(nx.strongly_connected_components(graph))
    component_index = {
        node: index for index, component in enumerate(components) for node in component
    }
    condensation = nx.DiGraph()
    condensation.add_nodes_from(range(len(components)))
    for source, target in graph.edges:
        source_component = component_index[source]
        target_component = component_index[target]
        if source_component != target_component:
            condensation.add_edge(source_component, target_component)
    causal_depth = nx.dag_longest_path_length(condensation) if condensation.nodes else 0

    branching_factor = sum(dict(graph.out_degree()).values()) / max(1, graph.number_of_nodes())
    cyclic_components = {
        index
        for index, component in enumerate(components)
        if len(component) > 1 or any(graph.has_edge(node, node) for node in component)
    }
    loop_edges = sum(
        component_index[source] == component_index[target]
        and component_index[source] in cyclic_components
        for source, target in graph.edges
    )
    loop_density = loop_edges / max(1, graph.number_of_edges())

    sources = [node for node in graph.nodes if graph.in_degree(node) == 0]
    lengths = [
        nx.shortest_path_length(graph, source, payoff)
        for source in sources
        if nx.has_path(graph, source, payoff)
    ]
    payoff_path_length = min(lengths) if lengths else None
    return DynamicalNicheDescriptor(
        causal_depth=causal_depth,
        branching_factor=round(branching_factor, 6),
        loop_density=round(loop_density, 6),
        payoff_path_length=payoff_path_length,
    )


# Keep the historical archive import path available from the descriptor module.
from .archive import QDArchive, dominates  # noqa: E402  (intentional late import)


__all__ = ["QDArchive", "dominates", "dynamical_niche_descriptor"]
