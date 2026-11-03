from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Callable, Literal, Protocol, Sequence, runtime_checkable

import networkx as nx

from ..models import (
    CanonicalMechanism, CausalLink, CreativeLineage, IdeaCandidate, InversionEvidence, NegativeArchive,
    NormalizedProblem, Provenance, StrictModel, stable_id,
)
from ..verifier import CausalGraphValidator, _node_key
from .operators import OperatorContext

Relation = Literal["increases", "decreases", "enables", "prevents", "depends_on"]

POLARITY_FLIP: dict[str, str] = {
    "increases": "decreases", "decreases": "increases", "enables": "prevents", "prevents": "enables",
}

class InvariantClaim(StrictModel):
    id: str
    statement: str
    cause: str
    relation: Relation
    effect: str
    evidence_quote: str

    @classmethod
    def build(cls, statement: str, cause: str, relation: Relation, effect: str, evidence_quote: str):
        return cls(id=stable_id(statement, cause, relation, effect), statement=statement, cause=cause,
                   relation=relation, effect=effect, evidence_quote=evidence_quote)

@runtime_checkable
class InvariantMiner(Protocol):
    def mine(self, problem: NormalizedProblem, baselines: NegativeArchive) -> tuple[InvariantClaim, ...]: ...

def _norm(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split()).casefold()

def _corpus(problem: NormalizedProblem, baselines: NegativeArchive) -> tuple[str, ...]:
    texts = [problem.original_prompt]
    for b in baselines.baselines:
        texts += [b.title, b.description]
    return tuple(_norm(t) for t in texts)

def grounded_claims(
    claims: Sequence[InvariantClaim], problem: NormalizedProblem, baselines: NegativeArchive,
) -> tuple[InvariantClaim, ...]:
    """Hallucination guard: a claim survives only if its quote literally occurs in the prompt/baselines."""
    corpus = _corpus(problem, baselines)
    out, seen = [], set()
    for claim in claims:
        quote = _norm(claim.evidence_quote)
        if quote and claim.id not in seen and any(quote in text for text in corpus):
            seen.add(claim.id)
            out.append(claim)
    return tuple(out)

_EN = re.compile(
    r"\b([a-z][\w-]*(?: [\w-]+){0,2}?) (increases|decreases|enables|prevents|depends on) ([a-z][\w-]*(?: [\w-]+){0,2})\b",
    re.IGNORECASE)
_KO_RELATIONS = {
    "증가시킨다": "increases", "높인다": "increases", "감소시킨다": "decreases", "낮춘다": "decreases",
    "가능하게 한다": "enables", "막는다": "prevents", "방해한다": "prevents",
}
_KO = re.compile(r"(\S+?)(?:이|가|은|는)\s+(\S+?)(?:을|를)\s*(" + "|".join(_KO_RELATIONS) + ")")

class DefaultInvariantMiner:
    """Heuristic miner: lifts explicit 'X increases Y' style statements, plus optional seed claims.

    Every claim, seeded or extracted, passes the hallucination guard.
    """

    def __init__(self, seeds: Sequence[InvariantClaim] = ()):
        self.seeds = tuple(seeds)

    def mine(self, problem: NormalizedProblem, baselines: NegativeArchive) -> tuple[InvariantClaim, ...]:
        found: list[InvariantClaim] = list(self.seeds)
        texts = [problem.original_prompt, *(t for b in baselines.baselines for t in (b.title, b.description))]
        for text in texts:
            text = unicodedata.normalize("NFKC", text)
            for m in _EN.finditer(text):
                relation = m.group(2).lower().replace(" ", "_")
                found.append(InvariantClaim.build(m.group(0), m.group(1), relation, m.group(3), m.group(0)))
            for m in _KO.finditer(text):
                found.append(InvariantClaim.build(
                    m.group(0), m.group(1), _KO_RELATIONS[m.group(3)], m.group(2), m.group(0)))
        return grounded_claims(found, problem, baselines)

@dataclass(frozen=True)
class InversionContext:
    claims: tuple[InvariantClaim, ...]

CLAIM_ID_SEP = "+"

class InversionVerifier:
    """Deterministic check that an inversion binds real links, flips polarity, and keeps a buffer path."""

    def __init__(self, validator: CausalGraphValidator | None = None):
        self.validator = validator or CausalGraphValidator()

    @staticmethod
    def is_polarity_flip(claim: InvariantClaim, link: CausalLink) -> bool:
        if claim.relation == "depends_on":
            return (link.relation == "depends_on" and _norm(link.cause) == _norm(claim.effect)
                    and _norm(link.effect) == _norm(claim.cause))
        return (link.relation == POLARITY_FLIP[claim.relation]
                and _norm(link.cause) == _norm(claim.cause) and _norm(link.effect) == _norm(claim.effect))

    def verify(self, candidate: IdeaCandidate, evidence: InversionEvidence,
               claims: Sequence[InvariantClaim]) -> tuple[str, ...]:
        """Returns failure reasons; empty means verified."""
        mechanism = candidate.mechanism
        if mechanism is None:
            return ("candidate has no mechanism",)
        by_id = {c.id: c for c in claims}
        ids = evidence.claim_id.split(CLAIM_ID_SEP)
        if any(i not in by_id for i in ids):
            return ("unknown claim id",)
        indices = evidence.bound_link_indices
        if len(indices) != len(ids) or len(set(indices)) != len(indices):
            return ("bound_link_indices must bind exactly one distinct link per claim",)
        links = mechanism.causal_structure
        if any(isinstance(i, bool) or not 0 <= i < len(links) for i in indices):
            return ("bound link index out of range",)
        if not evidence.flipped_polarity:
            return ("evidence does not declare a polarity flip",)
        for cid, i in zip(ids, indices):
            if not self.is_polarity_flip(by_id[cid], links[i]):
                return (f"link {i} is not a polarity flip of claim {cid}",)
        return self._buffer_reasons(mechanism, indices)

    def _buffer_reasons(self, mechanism: CanonicalMechanism, indices: tuple[int, ...]) -> tuple[str, ...]:
        graph = self.validator.build_graph(mechanism)
        payoff = graph.graph["payoff"]
        links = mechanism.causal_structure
        bound = set(indices)
        pruned = nx.MultiDiGraph(
            (u, v, k, d) for u, v, k, d in graph.edges(keys=True, data=True) if k not in bound)
        pruned.add_nodes_from(graph.nodes)
        for i in indices:
            cause, effect = _node_key(links[i].cause), _node_key(links[i].effect)
            if not nx.has_path(graph, effect, payoff):
                return (f"flipped effect of link {i} cannot reach payoff",)
            if not nx.has_path(pruned, cause, payoff):
                return (f"no buffer path bypassing flipped link {i}",)
        return ()

class InversionLineageVerifier:
    """G2: no (valid) evidence, no credit; the candidate stays evaluable as an ordinary idea."""

    def __init__(self, verifier: InversionVerifier | None = None):
        self.verifier = verifier or InversionVerifier()

    def verify(self, candidate: IdeaCandidate, context=None):
        from .lineage import LineageVerdict
        evidence = candidate.lineage.evidence if candidate.lineage else None
        if not isinstance(evidence, InversionEvidence):
            return LineageVerdict(verified=False, reasons=("no inversion evidence",))
        if not isinstance(context, InversionContext):
            return LineageVerdict(verified=False, reasons=("missing inversion context",))
        reasons = self.verifier.verify(candidate, evidence, context.claims)
        return LineageVerdict(verified=not reasons, reasons=reasons, credit_awarded=not reasons)

Backend = Callable[[OperatorContext, tuple[InvariantClaim, ...]], "IdeaCandidate | None"]

def default_backend(ctx: OperatorContext, claims: tuple[InvariantClaim, ...]) -> IdeaCandidate:
    """Deterministic builder: flip each claimed link and route a buffer node around it to the payoff."""
    payoff = "resilient outcome"
    links: list[CausalLink] = []
    bound: list[int] = []
    for claim in claims:
        flipped = (claim.cause, claim.relation if claim.relation == "depends_on" else POLARITY_FLIP[claim.relation],
                   claim.effect)
        if claim.relation == "depends_on":
            flipped = (claim.effect, "depends_on", claim.cause)
        f_cause, f_relation, f_effect = flipped
        bound.append(len(links))
        buffer = f"buffer for {f_effect}"
        # The cause is gated behind the effect so the flipped guard cannot latch the run into a stuck state.
        links += [CausalLink(cause=f_cause, relation=f_relation, effect=f_effect),
                  CausalLink(cause=f_effect, relation="enables", effect=payoff),
                  CausalLink(cause=f_effect, relation="enables", effect=f_cause),
                  CausalLink(cause=f_cause, relation="enables", effect=buffer),
                  CausalLink(cause=buffer, relation="enables", effect=payoff),
                  CausalLink(cause=f"intervention on {f_effect}", relation="enables", effect=f_effect)]
    ids = CLAIM_ID_SEP.join(c.id for c in claims)
    title = "Inverted: " + "; ".join(c.statement for c in claims)
    return IdeaCandidate(
        id=stable_id(ctx.problem.id, "inversion", str(ctx.slot), ids), problem_id=ctx.problem.id,
        title=title, description=f"Deliberately invert the invariant(s) {title} with a buffer path.",
        mechanism=CanonicalMechanism(
            core_mechanism=f"Invert {title} while a buffer preserves the payoff",
            causal_structure=tuple(links), affected_system=ctx.problem.affected_system, payoff=payoff),
        operator="inversion", provenance=Provenance(provider_mode="scripted"),
        lineage=CreativeLineage(
            operator="inversion", parent_ids=(),
            evidence=InversionEvidence(claim_id=ids, bound_link_indices=tuple(bound), flipped_polarity=True)),
    )

class InversionOperator:
    name = "inversion"

    def __init__(self, miner: InvariantMiner | None = None, backend: Backend | None = None):
        self.miner = miner or DefaultInvariantMiner()
        self.backend = backend or default_backend
        self.claims: dict[str, InvariantClaim] = {}
        self.successes = 0

    def record_credit(self, candidate: IdeaCandidate) -> None:
        self.successes += 1

    def level(self, ctx: OperatorContext) -> int:
        """Curriculum: 1 (single) until an inversion has earned credit or sits in the archive, then 2."""
        in_archive = any(
            e.candidate.lineage and isinstance(e.candidate.lineage.evidence, InversionEvidence)
            for e in (*ctx.archive.elites.values(), *ctx.archive.reservoir))
        return 2 if self.successes or in_archive else 1

    def propose(self, ctx: OperatorContext) -> list[IdeaCandidate]:
        mined = grounded_claims(self.miner.mine(ctx.problem, ctx.baselines), ctx.problem, ctx.baselines)
        self.claims.update({c.id: c for c in mined})
        if not mined:
            return []
        want = min(self.level(ctx), len(mined))
        start = ctx.rng_seed % len(mined)
        chosen = tuple(mined[(start + k) % len(mined)] for k in range(want))
        candidate = self.backend(ctx, chosen)
        return [candidate] if candidate is not None else []
