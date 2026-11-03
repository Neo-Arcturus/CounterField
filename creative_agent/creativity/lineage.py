from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence, runtime_checkable

from ..models import Counterexample, DialecticEvidence, IdeaCandidate, StrictModel
from .dialectic import SynthesisVerifier, counterexample_hash

class LineageVerdict(StrictModel):
    verified: bool
    reasons: tuple[str, ...] = ()
    credit_awarded: bool = False

@runtime_checkable
class LineageVerifier(Protocol):
    def verify(self, candidate: IdeaCandidate, context: Any = None) -> LineageVerdict: ...

@dataclass(frozen=True)
class DialecticContext:
    parent: IdeaCandidate
    counterexample: Counterexample
    corpus: Sequence[Counterexample] = ()

class DialecticLineageVerifier:
    """G2: no (valid) evidence, no credit; the candidate stays evaluable as an ordinary idea."""

    def __init__(self, verifier: SynthesisVerifier | None = None):
        self.verifier = verifier or SynthesisVerifier()

    def verify(self, candidate: IdeaCandidate, context: Any = None) -> LineageVerdict:
        evidence = candidate.lineage.evidence if candidate.lineage else None
        if not isinstance(evidence, DialecticEvidence):
            return LineageVerdict(verified=False, reasons=("no dialectic evidence",))
        if not isinstance(context, DialecticContext):
            return LineageVerdict(verified=False, reasons=("missing dialectic context",))
        mismatches = []
        if evidence.counterexample_hash != counterexample_hash(context.counterexample):
            mismatches.append("evidence counterexample hash mismatch")
        if context.parent.mechanism is None or evidence.parent_fingerprint != context.parent.mechanism.fingerprint:
            mismatches.append("evidence parent fingerprint mismatch")
        reasons = (*mismatches, *self.verifier.check(
            context.parent, candidate, context.counterexample, context.corpus))
        verified = not reasons
        return LineageVerdict(verified=verified, reasons=tuple(reasons), credit_awarded=verified)

# Re-exported here so all lineage verifiers live behind one import path.
from .inversion import InversionContext, InversionLineageVerifier  # noqa: E402,F401

from ..models import IsomorphismEvidence  # noqa: E402
from .isomorphism import IsomorphismContext, IsomorphismVerifier  # noqa: E402

class IsomorphismLineageVerifier:
    """G2: no (valid) evidence, no credit; the candidate stays evaluable as an ordinary idea."""

    def __init__(self, verifier: IsomorphismVerifier | None = None):
        self.verifier = verifier or IsomorphismVerifier()

    def verify(self, candidate: IdeaCandidate, context: Any = None) -> LineageVerdict:
        evidence = candidate.lineage.evidence if candidate.lineage else None
        if not isinstance(evidence, IsomorphismEvidence):
            return LineageVerdict(verified=False, reasons=("no isomorphism evidence",))
        if not isinstance(context, IsomorphismContext):
            return LineageVerdict(verified=False, reasons=("missing isomorphism context",))
        template = context.library.get(evidence.template_id)
        if template is None:
            return LineageVerdict(verified=False, reasons=("unknown template",))
        reasons = self.verifier.verify(candidate, evidence, template, context.baselines)
        return LineageVerdict(verified=not reasons, reasons=reasons, credit_awarded=not reasons)
