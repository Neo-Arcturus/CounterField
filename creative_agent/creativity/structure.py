from __future__ import annotations

import networkx as nx

from ..models import CanonicalMechanism

MIN_STRUCTURAL_NODES = 4

def _graph(mechanism: CanonicalMechanism) -> nx.DiGraph:
    # Node labels are replaced by anonymous indices so the hash depends on topology + relations only.
    ids: dict[str, int] = {}
    g = nx.DiGraph()
    for link in mechanism.causal_structure:
        a = ids.setdefault(link.cause.casefold(), len(ids))
        b = ids.setdefault(link.effect.casefold(), len(ids))
        g.add_node(a, label="")
        g.add_node(b, label="")
        g.add_edge(a, b, relation=link.relation)
    return g

def is_small_graph(mechanism: CanonicalMechanism) -> bool:
    """Small graphs carry too little structure to be blacklisted by structural hash."""
    return _graph(mechanism).number_of_nodes() < MIN_STRUCTURAL_NODES

def structural_fingerprint(mechanism: CanonicalMechanism) -> str:
    g = _graph(mechanism)
    return nx.weisfeiler_lehman_graph_hash(g, edge_attr="relation", node_attr="label")
