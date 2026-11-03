from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Sequence

import networkx as nx

from ..models import (
    CanonicalMechanism, CausalLink, CreativeLineage, IdeaCandidate, IsomorphismEvidence, NegativeArchive,
    Provenance, StrictModel, stable_id,
)
from .operators import OperatorContext
from .structure import is_small_graph, structural_fingerprint

BOTTLENECK_BETWEENNESS = 0.4
ASYMMETRY_DEGREE_GAP = 2

class CausalTemplate(StrictModel):
    id: str
    domain: str
    roles: tuple[str, ...]
    links: tuple[CausalLink, ...]
    motifs: tuple[str, ...]
    curated_by: str
    source_ref: str
    domain_vocabulary: tuple[str, ...] = ()

class MotifProfile(StrictModel):
    has_feedback_loop: bool = False
    has_bottleneck: bool = False
    has_asymmetry: bool = False

    @property
    def names(self) -> frozenset[str]:
        return frozenset(n for n, on in (("feedback_loop", self.has_feedback_loop),
                                         ("bottleneck", self.has_bottleneck),
                                         ("asymmetry", self.has_asymmetry)) if on)

def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()

def _digraph(links: Sequence[CausalLink]) -> nx.DiGraph:
    g = nx.DiGraph()
    for link in links:
        g.add_edge(_norm(link.cause), _norm(link.effect), relation=link.relation)
    return g

class MotifExtractor:
    """Deterministic structural motif detection (no LLM)."""

    def extract_links(self, links: Sequence[CausalLink]) -> MotifProfile:
        g = _digraph(links)
        if g.number_of_nodes() == 0:
            return MotifProfile()
        feedback = any(len(c) >= 2 for c in nx.strongly_connected_components(g)) or nx.number_of_selfloops(g) > 0
        und = nx.Graph(g)
        und.remove_edges_from(list(nx.selfloop_edges(und)))
        betweenness = nx.betweenness_centrality(g) if g.number_of_nodes() > 2 else {}
        bottleneck = (any(v >= BOTTLENECK_BETWEENNESS for v in betweenness.values())
                      or (und.number_of_nodes() > 2 and any(True for _ in nx.articulation_points(und))))
        asymmetry = any(abs(g.in_degree(n) - g.out_degree(n)) >= ASYMMETRY_DEGREE_GAP for n in g)
        return MotifProfile(has_feedback_loop=feedback, has_bottleneck=bottleneck, has_asymmetry=asymmetry)

    def extract(self, mechanism: CanonicalMechanism) -> MotifProfile:
        return self.extract_links(mechanism.causal_structure)

    def extract_all(self, mechanisms: Sequence[CanonicalMechanism]) -> MotifProfile:
        links = [l for m in mechanisms for l in m.causal_structure]
        return self.extract_links(links)

def _t(id, domain, roles, links, motifs, ref, vocab):
    parsed = tuple(CausalLink(cause=a, relation=r, effect=b) for a, r, b in links)
    return CausalTemplate(id=id, domain=domain, roles=tuple(roles), links=parsed, motifs=tuple(motifs),
                          curated_by="CounterField curators", source_ref=ref, domain_vocabulary=tuple(vocab))

def default_templates() -> tuple[CausalTemplate, ...]:
    return (
        _t("predator_prey_balance", "ecology", ("resource", "prey", "predator", "equilibrium"),
           [("resource", "enables", "prey"), ("prey", "increases", "predator"), ("predator", "decreases", "prey"),
            ("predator", "enables", "equilibrium"), ("prey", "enables", "equilibrium")],
           ("feedback_loop",), "Lotka 1925, Elements of Physical Biology",
           ("predator", "prey", "lotka", "volterra", "population")),
        _t("trophic_cascade", "ecology", ("apex", "mesoconsumer", "producer", "ecosystem_health"),
           [("apex", "decreases", "mesoconsumer"), ("mesoconsumer", "decreases", "producer"),
            ("producer", "enables", "ecosystem_health"), ("apex", "enables", "ecosystem_health")],
           ("asymmetry", "bottleneck"), "Paine 1966, Food web complexity and species diversity",
           ("apex", "predator", "herbivore", "trophic", "producer")),
        _t("niche_differentiation", "ecology", ("shared_resource", "species_a", "species_b", "coexistence"),
           [("shared_resource", "enables", "species_a"), ("shared_resource", "enables", "species_b"),
            ("species_a", "prevents", "species_b"), ("species_b", "prevents", "species_a"),
            ("species_a", "enables", "coexistence"), ("species_b", "enables", "coexistence")],
           ("feedback_loop", "asymmetry"), "Hutchinson 1957, Concluding remarks (Cold Spring Harbor Symp.)",
           ("species", "niche", "habitat", "competition")),
        _t("priority_inversion_mitigation", "os_kernel", ("high_task", "low_task", "lock", "throughput"),
           [("low_task", "enables", "lock"), ("lock", "prevents", "high_task"), ("high_task", "increases", "low_task"),
            ("low_task", "enables", "throughput"), ("high_task", "enables", "throughput")],
           ("feedback_loop", "bottleneck"), "Sha, Rajkumar, Lehoczky 1990, Priority Inheritance Protocols (IEEE ToC)",
           ("mutex", "scheduler", "priority", "thread", "semaphore")),
        _t("copy_on_write", "os_kernel", ("shared_page", "writer", "private_copy", "isolation"),
           [("writer", "enables", "private_copy"), ("shared_page", "enables", "private_copy"),
            ("private_copy", "enables", "isolation"), ("shared_page", "enables", "isolation")],
           ("bottleneck", "asymmetry"), "Bach 1986, The Design of the UNIX Operating System",
           ("page", "fork", "kernel", "mmu", "cow")),
        _t("work_stealing_queue", "os_kernel", ("busy_worker", "idle_worker", "task_queue", "balanced_load"),
           [("busy_worker", "enables", "task_queue"), ("task_queue", "enables", "idle_worker"),
            ("idle_worker", "decreases", "busy_worker"), ("idle_worker", "enables", "balanced_load"),
            ("busy_worker", "enables", "balanced_load")],
           ("feedback_loop", "bottleneck"), "Blumofe & Leiserson 1999, Scheduling Multithreaded Computations (JACM)",
           ("worker", "deque", "steal", "cpu", "core")),
        _t("heat_sink_dissipation", "thermodynamics", ("heat_source", "sink", "gradient", "steady_temperature"),
           [("heat_source", "increases", "gradient"), ("gradient", "increases", "sink"),
            ("sink", "decreases", "gradient"), ("sink", "enables", "steady_temperature"),
            ("gradient", "enables", "steady_temperature")],
           ("feedback_loop",), "Incropera & DeWitt, Fundamentals of Heat and Mass Transfer, ch.1",
           ("heat", "thermal", "temperature", "conduction", "sink")),
        _t("phase_transition_hysteresis", "thermodynamics", ("control_field", "order_state", "memory", "regime"),
           [("control_field", "increases", "order_state"), ("order_state", "increases", "memory"),
            ("memory", "increases", "order_state"), ("order_state", "enables", "regime"),
            ("control_field", "enables", "regime")],
           ("feedback_loop", "asymmetry"), "Landau & Lifshitz, Statistical Physics Part 1, ch.14",
           ("phase", "hysteresis", "magnet", "transition", "order")),
        _t("entropy_barrier", "thermodynamics", ("disorder_source", "barrier", "protected_order", "persistence"),
           [("disorder_source", "increases", "barrier"), ("barrier", "prevents", "protected_order"),
            ("barrier", "enables", "persistence"), ("protected_order", "enables", "persistence")],
           ("bottleneck", "asymmetry"), "Prigogine 1977, Self-Organization in Nonequilibrium Systems",
           ("entropy", "dissipative", "boltzmann", "equilibrium")),
        _t("vickrey_truthful_bidding", "auction", ("bidder", "second_price", "true_value", "efficient_allocation"),
           [("true_value", "enables", "bidder"), ("bidder", "increases", "second_price"),
            ("second_price", "enables", "efficient_allocation"), ("bidder", "enables", "efficient_allocation")],
           ("bottleneck", "asymmetry"), "Vickrey 1961, Counterspeculation, Auctions and Competitive Sealed Tenders",
           ("bid", "auction", "bidder", "price", "vickrey")),
        _t("dutch_clock_escalation", "auction", ("clock", "price_drop", "buyer", "sale"),
           [("clock", "enables", "price_drop"), ("price_drop", "increases", "buyer"),
            ("buyer", "prevents", "clock"), ("buyer", "enables", "sale"), ("price_drop", "enables", "sale")],
           ("feedback_loop", "bottleneck"), "Milgrom 2004, Putting Auction Theory to Work, ch.1",
           ("dutch", "clock", "descending", "auction", "price")),
        _t("clearinghouse_settlement", "auction", ("order_flow", "clearinghouse", "counterparty", "settled_state"),
           [("order_flow", "enables", "clearinghouse"), ("counterparty", "enables", "clearinghouse"),
            ("clearinghouse", "enables", "settled_state")],
           ("bottleneck", "asymmetry"), "Kroszner 1999, Can the Financial Markets Privately Regulate Risk? (JMCB)",
           ("clearing", "margin", "settlement", "exchange", "trade")),
    )

class TemplateLibrary:
    def __init__(self, templates: Sequence[CausalTemplate] | None = None):
        self.templates = tuple(default_templates() if templates is None else templates)

    @classmethod
    def from_json(cls, json_path: str) -> "TemplateLibrary":
        import json
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        raw_list = data.get("templates", []) if isinstance(data, dict) else data
        parsed = []
        for t in raw_list:
            links = tuple(CausalLink(cause=l["cause"], relation=l["relation"], effect=l["effect"]) for l in t["links"])
            parsed.append(CausalTemplate(
                id=t["id"],
                domain=t["domain"],
                roles=tuple(t["roles"]),
                links=links,
                motifs=tuple(t["motifs"]),
                curated_by=t["curated_by"],
                source_ref=t["source_ref"],
                domain_vocabulary=tuple(t.get("domain_vocabulary", ()))
            ))
        return cls(templates=parsed)

    def get(self, template_id: str) -> CausalTemplate | None:
        return next((t for t in self.templates if t.id == template_id), None)

    def match(self, motifs: MotifProfile, k: int = 3) -> tuple[CausalTemplate, ...]:
        wanted = motifs.names
        scored = []
        for t in self.templates:
            if not t.source_ref.strip():  # unreferenced templates are disqualified
                continue
            have = set(t.motifs)
            overlap = len(wanted & have)
            scored.append((-overlap, len(have - wanted), t.id, t))
        scored.sort(key=lambda s: s[:3])
        return tuple(s[3] for s in scored[:max(k, 0)])

def _tokens(text: str) -> set[str]:
    return {tok for tok in re.split(r"[\W_]+", text.casefold()) if len(tok) > 1}

class IsomorphismVerifier:
    """Injective, role-covering, relation-preserving monomorphism with no surface copying (G4 included)."""

    def verify(self, candidate: IdeaCandidate, evidence: IsomorphismEvidence, template: CausalTemplate,
               baselines: NegativeArchive | None = None) -> tuple[str, ...]:
        """Returns failure reasons; empty means verified."""
        mechanism = candidate.mechanism
        if mechanism is None:
            return ("candidate has no mechanism",)
        if evidence.template_id != template.id:
            return ("evidence template id mismatch",)
        if not template.source_ref.strip():
            return ("template has no source_ref",)
        role_map = {k: _norm(v) for k, v in evidence.role_map.items()}
        missing = [r for r in template.roles if r not in role_map]
        if missing:
            return (f"role map does not cover roles: {', '.join(missing)}",)
        if len(set(role_map[r] for r in template.roles)) != len(template.roles):
            return ("role map is not injective",)
        reasons = self._monomorphism(mechanism, template, role_map)
        if reasons:
            return reasons
        banned = _tokens(" ".join(template.roles)) | _tokens(" ".join(template.domain_vocabulary))
        for role in template.roles:
            label = role_map[role]
            if label == _norm(role) or _tokens(label) & banned:
                return (f"surface copy of template vocabulary in label '{label}'",)
        if baselines is not None and not is_small_graph(mechanism):
            fp = structural_fingerprint(mechanism)
            if any(not is_small_graph(m) and structural_fingerprint(m) == fp for m in baselines.mechanisms):
                return ("structurally isomorphic to a baseline",)
        return ()

    @staticmethod
    def _monomorphism(mechanism: CanonicalMechanism, template: CausalTemplate,
                      role_map: dict[str, str]) -> tuple[str, ...]:
        cand = _digraph(mechanism.causal_structure)
        for link in template.links:
            u, v = role_map[link.cause], role_map[link.effect]
            if not cand.has_edge(u, v):
                return (f"missing edge {link.cause}->{link.effect} in candidate",)
            if cand.edges[u, v]["relation"] != link.relation:
                return (f"relation mismatch on {link.cause}->{link.effect}",)
        return ()

@dataclass(frozen=True)
class IsomorphismContext:
    library: TemplateLibrary
    baselines: NegativeArchive | None = None

Backend = Callable[[OperatorContext, CausalTemplate, MotifProfile], "IdeaCandidate | None"]

def default_backend(ctx: OperatorContext, template: CausalTemplate, motifs: MotifProfile) -> IdeaCandidate:
    """Deterministic projection: each role becomes a neutral component of the problem's own system."""
    labels = {role: f"{ctx.problem.affected_system} component {chr(65 + i)}" for i, role in enumerate(template.roles)}
    links = tuple(CausalLink(cause=labels[l.cause], relation=l.relation, effect=labels[l.effect])
                  for l in template.links)
    payoff = labels[template.roles[-1]]
    title = f"Blend: {template.id} structure for {ctx.problem.objective}"
    return IdeaCandidate(
        id=stable_id(ctx.problem.id, "isomorphism", str(ctx.slot), template.id), problem_id=ctx.problem.id,
        title=title, description=f"Project the {template.domain} mechanism {template.id} onto the problem.",
        mechanism=CanonicalMechanism(
            core_mechanism=f"Reuse the causal structure of {template.id} within {ctx.problem.affected_system}",
            causal_structure=links, affected_system=ctx.problem.affected_system, payoff=payoff),
        operator="isomorphism", provenance=Provenance(provider_mode="scripted"),
        lineage=CreativeLineage(
            operator="isomorphism", parent_ids=(),
            evidence=IsomorphismEvidence(template_id=template.id, role_map=labels)),
    )

class BlendOperator:
    name = "isomorphism"

    def __init__(self, library: TemplateLibrary | None = None, extractor: MotifExtractor | None = None,
                 backend: Backend | None = None):
        self.library = library or TemplateLibrary()
        self.extractor = extractor or MotifExtractor()
        self.backend = backend or default_backend
        self.successes = 0

    def record_credit(self, candidate: IdeaCandidate) -> None:
        self.successes += 1

    def propose(self, ctx: OperatorContext) -> list[IdeaCandidate]:
        motifs = self.extractor.extract_all(
            [*ctx.baselines.mechanisms, *(p.mechanism for p in ctx.parents if p.mechanism)])
        matches = self.library.match(motifs, k=3)
        if not matches:
            return []
        template = matches[ctx.rng_seed % len(matches)]
        candidate = self.backend(ctx, template, motifs)
        return [candidate] if candidate is not None else []
