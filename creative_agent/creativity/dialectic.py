from __future__ import annotations

import hashlib
import threading
from typing import Any, Callable, Protocol, Sequence, runtime_checkable

from ..dsl import canonical_mechanism_to_dsl
from ..models import (
    CanonicalMechanism, Counterexample, CreativeLineage, DialecticEvidence, IdeaCandidate,
    QDArchiveEntry, StrictModel, stable_id,
)
from ..qd import dynamical_niche_descriptor
from ..redteam import CEGISRepairEngine, replay_counterexample

def counterexample_hash(counterexample: Counterexample) -> str:
    payload = "\x1f".join((
        counterexample.violated_invariant, *counterexample.witness_actions,
        repr(sorted(counterexample.initial_state.items())),
    ))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]

class SynthesisProposal(StrictModel):
    child: IdeaCandidate
    counterexample: Counterexample
    ops: tuple[str, ...]

class RuleRecord(StrictModel):
    violated_invariant: str
    ops: tuple[str, ...]
    candidate_ids: tuple[str, ...] = ()
    promoted: bool = False

class RuleLibrary:
    """Repair-to-feature patterns; a rule is promoted only after two independent candidates succeed."""

    PROMOTION_THRESHOLD = 2

    def __init__(self):
        self._lock = threading.RLock()
        self._rules: dict[tuple[str, tuple[str, ...]], RuleRecord] = {}
        self._corpus: dict[str, tuple[Counterexample, ...]] = {}

    def record_success(self, violated_invariant: str, ops: tuple[str, ...], candidate_id: str) -> bool:
        key = (violated_invariant, tuple(ops))
        with self._lock:
            rule = self._rules.get(key) or RuleRecord(violated_invariant=violated_invariant, ops=key[1])
            ids = rule.candidate_ids if candidate_id in rule.candidate_ids else (*rule.candidate_ids, candidate_id)
            promoted = rule.promoted or len(set(ids)) >= self.PROMOTION_THRESHOLD
            self._rules[key] = rule.model_copy(update={"candidate_ids": ids, "promoted": promoted})
            return promoted

    def promoted_rules(self) -> tuple[RuleRecord, ...]:
        with self._lock:
            return tuple(r for _, r in sorted(self._rules.items()) if r.promoted)

    def add_counterexample(self, parent_fingerprint: str, counterexample: Counterexample) -> None:
        with self._lock:
            known = self._corpus.get(parent_fingerprint, ())
            if counterexample not in known:
                self._corpus[parent_fingerprint] = (*known, counterexample)

    def corpus(self, parent_fingerprint: str) -> tuple[Counterexample, ...]:
        with self._lock:
            return self._corpus.get(parent_fingerprint, ())

    def snapshot(self) -> Any:
        with self._lock:
            return (dict(self._rules), dict(self._corpus))

    def restore(self, state: Any) -> None:
        with self._lock:
            rules, corpus = state
            self._rules, self._corpus = dict(rules), dict(corpus)

@runtime_checkable
class DialecticalSynthesizer(Protocol):
    def synthesize(
        self, entry: QDArchiveEntry, counterexamples: tuple[Counterexample, ...], rule_library: RuleLibrary,
    ) -> list[SynthesisProposal]: ...

def _nodes(mechanism: CanonicalMechanism) -> set[str]:
    return {
        " ".join(label.casefold().split())
        for link in mechanism.causal_structure for label in (link.cause, link.effect)
    }

def _links(mechanism: CanonicalMechanism) -> set[tuple[str, str, str]]:
    return {
        (" ".join(x.cause.casefold().split()), x.relation, " ".join(x.effect.casefold().split()))
        for x in mechanism.causal_structure
    }

class SynthesisVerifier:
    """Deterministic four-condition check; every condition must hold for a child to be verified."""

    def check(
        self,
        parent: IdeaCandidate,
        child: IdeaCandidate,
        counterexample: Counterexample,
        corpus: Sequence[Counterexample] = (),
    ) -> tuple[str, ...]:
        """Return failure reasons; an empty tuple means verified."""
        if child.parent_id != parent.id:
            return ("child.parent_id does not reference the parent",)
        if child.lineage is None or not isinstance(child.lineage.evidence, DialecticEvidence):
            return ("child carries no dialectic evidence",)
        if parent.mechanism is None or child.mechanism is None:
            return ("parent and child require mechanisms",)
        try:
            program = canonical_mechanism_to_dsl(child.mechanism)
        except Exception as exc:
            return (f"child does not compile: {type(exc).__name__}: {exc}",)

        reasons: list[str] = []
        replay = replay_counterexample(program, counterexample)
        if replay.reproduced:
            reasons.append("counterexample still reproduces on child")
        if replay.error is not None:
            reasons.append(f"exploit not preserved, witness fails to execute: {replay.error}")

        new_nodes = _nodes(child.mechanism) - _nodes(parent.mechanism)
        new_links = _links(child.mechanism) - _links(parent.mechanism)
        before = dynamical_niche_descriptor(parent.mechanism)
        after = dynamical_niche_descriptor(child.mechanism)
        structural = len(new_nodes) >= 1 and len(new_links) >= 2
        dynamical = after.loop_density > before.loop_density or after.causal_depth > before.causal_depth
        if not (structural or dynamical):
            reasons.append("cosmetic modification: insufficient new nodes/links and no dynamical change")

        for old in corpus:
            if old != counterexample and replay_counterexample(program, old).reproduced:
                reasons.append(f"regression: earlier counterexample '{old.violated_invariant}' reproduces")
        return tuple(reasons)

    def verify(self, parent, child, counterexample, corpus=()) -> bool:
        return not self.check(parent, child, counterexample, corpus)

# Backend: (entry, counterexample, rule_library) -> [(mechanism, ops), ...]
ExpansionBackend = Callable[[QDArchiveEntry, Counterexample, RuleLibrary], Sequence[tuple[CanonicalMechanism, tuple[str, ...]]]]

class CEGISGuidedSynthesizer:
    """Turns an exploit into a mechanic: CEGIS repair is the baseline, the backend proposes expansions."""

    def __init__(self, backend: ExpansionBackend | None = None, *, engine: CEGISRepairEngine | None = None):
        self.backend = backend or self._default_backend
        self.engine = engine or CEGISRepairEngine(chaos_episodes=8)

    @staticmethod
    def _default_backend(entry, counterexample, rule_library):
        mechanism = entry.candidate.mechanism
        links = mechanism.causal_structure
        # Gate the payoff behind a new bookkeeping node fed by the first mid-chain effect: an exploit
        # becomes a priced step in the causal chain instead of a free shortcut.
        anchor = links[0].effect
        node = f"{counterexample.violated_invariant} ledger"
        extra = (
            type(links[0])(cause=anchor, relation="enables", effect=node),
            type(links[0])(cause=node, relation="enables", effect=mechanism.payoff),
        )
        child = mechanism.model_copy(update={"causal_structure": (*links, *extra)})
        return [(child, ("add_cost_node", "add_feedback_loop"))]

    def synthesize(self, entry, counterexamples, rule_library):
        parent = entry.candidate
        if parent.mechanism is None:
            return []
        proposals = []
        for counterexample in counterexamples:
            baseline = ()
            try:
                healed = self.engine.heal(canonical_mechanism_to_dsl(parent.mechanism), (counterexample,)).healed
                baseline = ("cegis_baseline_healed",) if healed else ()
            except Exception:
                pass
            for mechanism, ops in self.backend(entry, counterexample, rule_library):
                ops = (*baseline, *ops)
                evidence = DialecticEvidence(
                    counterexample_hash=counterexample_hash(counterexample),
                    parent_fingerprint=parent.mechanism.fingerprint,
                    synthesis_ops=ops,
                )
                child = parent.model_copy(update={
                    "id": stable_id(parent.id, evidence.counterexample_hash, mechanism.fingerprint, *ops),
                    "title": f"{parent.title} (dialectic)",
                    "mechanism": mechanism,
                    "operator": "dialectic",
                    "parent_id": parent.id,
                    "lineage": CreativeLineage(operator="dialectic", evidence=evidence, parent_ids=(parent.id,)),
                })
                proposals.append(SynthesisProposal(child=child, counterexample=counterexample, ops=ops))
        return proposals
