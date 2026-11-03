"""Schedulability lint for CausalTemplates (adapter rule R1-R4, added 2026-10-22).

Why: the Semantic-IR compiler turns every incoming link into an AND guard, inhibitory links
(`decreases`/`prevents`) into "cause must be absent" guards, and the state machine is monotone
(propositions are only ever set True). Consequences measured on 2026-10-22:
  * a cycle made only of positive links deadlocks (each node waits on the next)       -> R2
  * an inhibitory link whose cause is an exogenous source (initially True forever)
    can never be satisfied                                                              -> R3
  * a mechanism with no exogenous source has no intervention at all                     -> R1
while CausalGraphValidator happily accepts all three. This lint is deterministic and LLM-free;
R4 is the ground truth (real validator + real red-team), the others are cheap explanations.
It never relaxes any admission gate; it only filters *templates* before they are offered to generators.
"""
from __future__ import annotations

import networkx as nx

from ..models import CanonicalMechanism
from ..verifier import CausalGraphValidator, _node_key
from .isomorphism import CausalTemplate

INHIBITORY = frozenset({"decreases", "prevents"})


def lint_template(template: CausalTemplate, *, run_playtest: bool = True) -> tuple[str, ...]:
    """Return rule violations; an empty tuple means the template is schedulable."""
    g = nx.DiGraph()
    for link in template.links:
        g.add_edge(_node_key(link.cause), _node_key(link.effect), relation=link.relation)
    reasons: list[str] = []
    sources = {n for n in g if g.in_degree(n) == 0}
    payoff = _node_key(template.roles[-1])
    if not (sources - {payoff}):
        reasons.append("R1: no exogenous source role (no intervention can start the mechanism)")
    positive = nx.DiGraph((u, v) for u, v, d in g.edges(data=True) if d["relation"] not in INHIBITORY)
    positive.add_nodes_from(g)
    for comp in nx.strongly_connected_components(positive):
        if len(comp) > 1 or any(positive.has_edge(n, n) for n in comp):
            reasons.append(f"R2: positive-only feedback cycle deadlocks the compiled program: {sorted(comp)}")
    for u, v, d in g.edges(data=True):
        if d["relation"] in INHIBITORY and u in sources:
            reasons.append(f"R3: inhibitory link from exogenous source '{u}' -> '{v}' is unsatisfiable")
    if run_playtest:
        mech = CanonicalMechanism(core_mechanism=template.id, causal_structure=template.links,
                                  affected_system=template.domain, payoff=template.roles[-1])
        report = CausalGraphValidator().validate(mech)
        if not report.is_valid:
            reasons.append("R4: structural validation failed: " + ", ".join(
                i.rule for i in report.issues if i.severity.value == "FATAL"))
        else:
            from ..dsl import canonical_mechanism_to_dsl
            from ..redteam import AdversarialPlaytester
            fatal = [i.issue_type for i in AdversarialPlaytester().run_playtest(
                canonical_mechanism_to_dsl(mech)).issues if i.severity == "FATAL"]
            if fatal:
                reasons.append("R4: red-team FATAL on bare skeleton: " + ", ".join(fatal))
    return tuple(reasons)
