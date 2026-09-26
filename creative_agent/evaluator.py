from __future__ import annotations

import math
import re
from typing import Callable
from .models import *
from .providers import EmbeddingProvider, IdeaProvider
from .verifier import CausalGraphValidator, StructuralValidationError


def tokens(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.casefold(), re.UNICODE))


def features(text: str) -> set[str]:
    words = re.findall(r"\w+", text.casefold(), re.UNICODE)
    return set(words) | {f"{a} {b}" for a, b in zip(words, words[1:])}


def jaccard(a, b):
    return len(a & b) / len(a | b) if a | b else 0.0


class ThreeLayerEvaluator:
    def __init__(self, provider: IdeaProvider, embeddings: EmbeddingProvider | None = None,
                 structural_comparator: Callable | None = None,
                 validator: CausalGraphValidator | None = None):
        self.provider, self.embeddings = provider, embeddings
        self.structural_comparator = structural_comparator
        self.validator = validator or CausalGraphValidator()

    def validate(self, problem, candidate):
        """Canonicalize a candidate and run the structural validity gate."""
        canonical = self.provider.canonicalize(problem, candidate)
        return canonical, self.validator.validate(canonical)

    def evaluate(self, problem, candidate, negative_archive, thresholds=(.5, .5)):
        candidate, validation_report = self.validate(problem, candidate)
        if not validation_report.is_valid:
            # Quality scores are intentionally never requested for invalid structures.
            raise StructuralValidationError(validation_report)
        mechanism = candidate.mechanism
        if mechanism is None:
            raise ValueError("candidate has no mechanism")
        text = candidate.description + " " + mechanism.core_mechanism
        lexical = max((jaccard(features(text), features(b.description)) for b in negative_archive.baselines), default=0)
        embedding = self._embedding(text, negative_archive)
        structural = max((self._structural(mechanism, b) for b in negative_archive.mechanisms), default=0)
        scores = self.provider.assess(problem, candidate).model_copy(update={
            "novelty": max(0, min(1, 1 - (.2 * lexical + .3 * embedding + .5 * structural))),
            "mechanism_uniqueness": max(0, 1 - structural),
        })
        feasible = scores.appropriateness >= thresholds[0] and scores.coherence >= thresholds[1]
        diagnostics = EvaluationDiagnostics(
            lexical_similarity=lexical, embedding_similarity=embedding,
            structural_similarity=structural,
            nearest_baseline_ids=tuple(x.id for x in negative_archive.baselines),
            feasibility_reasons=() if feasible else ("appropriateness or coherence below threshold",),
            provider_mode="mock" if getattr(self.provider, "mode", "") == "mock" else "external",
            embedding_mode=getattr(self.embeddings, "mode", "unavailable"),
            validation_report=validation_report,
        )
        return scores, diagnostics, feasible

    def _embedding(self, text, archive):
        if not self.embeddings:
            return 0.0
        vectors = self.embeddings.embed([text] + [x.description for x in archive.baselines])
        if any(len(v) != len(vectors[0]) or any(not math.isfinite(x) for x in v) for v in vectors):
            raise ValueError("invalid embedding response")
        norm = lambda v: math.sqrt(sum(x*x for x in v))
        if not norm(vectors[0]):
            return 0.0
        return max((max(0, min(1, sum(a*b for a,b in zip(vectors[0], v)) / (norm(vectors[0])*norm(v)))) for v in vectors[1:] if norm(v)), default=0)

    def _structural(self, a, b):
        if self.structural_comparator:
            return self.structural_comparator(a, b)
        links = lambda x: {(z.cause.casefold(), z.relation, z.effect.casefold()) for z in x.causal_structure}
        return .5*jaccard(links(a), links(b)) + .25*jaccard(tokens(a.core_mechanism), tokens(b.core_mechanism)) + .125*jaccard(tokens(a.affected_system), tokens(b.affected_system)) + .125*jaccard(tokens(a.payoff), tokens(b.payoff))
