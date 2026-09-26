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


class AdmissionController:
    """Apply admission gates in a fixed order; later scores cannot mask failures."""

    def decide(
        self,
        *,
        scores: EvaluationScores | None,
        validation_report: ValidationReport | None,
        playtest_report: PlaytestReport | None,
        thresholds: tuple[float, float],
        evaluation_error: str | None = None,
    ) -> AdmissionResult:
        if evaluation_error or scores is None or validation_report is None or playtest_report is None:
            return AdmissionResult(
                status=AdmissionStatus.INVALID_EVALUATION,
                stage=AdmissionStage.EVALUATION_INTEGRITY,
                reasons=(evaluation_error or "evaluation evidence is incomplete",),
            )
        if not validation_report.is_valid:
            return AdmissionResult(
                status=AdmissionStatus.REJECTED,
                stage=AdmissionStage.STRUCTURAL_VALIDITY,
                reasons=tuple(
                    issue.message for issue in validation_report.issues
                    if issue.severity == ValidationSeverity.FATAL
                ) or ("structural validation failed",),
            )
        fatal_issues = [
            issue for issue in playtest_report.issues if issue.severity == "FATAL"
        ]
        if fatal_issues:
            return AdmissionResult(
                status=AdmissionStatus.REPAIRABLE,
                stage=AdmissionStage.RED_TEAM,
                reasons=tuple(
                    f"{issue.issue_type}: {issue.description}" for issue in fatal_issues
                ),
            )
        quality_failures = []
        if scores.appropriateness < thresholds[0]:
            quality_failures.append(
                f"appropriateness {scores.appropriateness:.3f} is below {thresholds[0]:.3f}"
            )
        if scores.coherence < thresholds[1]:
            quality_failures.append(
                f"coherence {scores.coherence:.3f} is below {thresholds[1]:.3f}"
            )
        if quality_failures:
            return AdmissionResult(
                status=AdmissionStatus.REPAIRABLE,
                stage=AdmissionStage.QUALITY_CONSTRAINTS,
                reasons=tuple(quality_failures),
            )
        return AdmissionResult(
            status=AdmissionStatus.ACCEPTED,
            stage=AdmissionStage.COMPLETE,
        )


class ThreeLayerEvaluator:
    def __init__(self, provider: IdeaProvider, embeddings: EmbeddingProvider | None = None,
                 structural_comparator: Callable | None = None,
                 validator: CausalGraphValidator | None = None):
        self.provider, self.embeddings = provider, embeddings
        self.structural_comparator = structural_comparator
        self.validator = validator or CausalGraphValidator()
        self.admission_controller = AdmissionController()

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
        try:
            text = candidate.description + " " + mechanism.core_mechanism
            lexical = max((jaccard(features(text), features(b.description)) for b in negative_archive.baselines), default=0)
            embedding = self._embedding(text, negative_archive)
            structural = max((self._structural(mechanism, b) for b in negative_archive.mechanisms), default=0)
            scores = self.provider.assess(problem, candidate).model_copy(update={
                "novelty": max(0, min(1, 1 - (.2 * lexical + .3 * embedding + .5 * structural))),
                "mechanism_uniqueness": max(0, 1 - structural),
            })
        except Exception as exc:
            error = f"quality evaluation failed: {type(exc).__name__}: {exc}"
            diagnostics = EvaluationDiagnostics(
                feasibility_reasons=(error,),
                provider_mode="mock" if getattr(self.provider, "mode", "") == "mock" else "external",
                embedding_mode=getattr(self.embeddings, "mode", "unavailable"),
                validation_report=validation_report,
            )
            admission = self.admission_controller.decide(
                scores=None,
                validation_report=validation_report,
                playtest_report=None,
                thresholds=thresholds,
                evaluation_error=error,
            )
            return EvaluationBundle(
                scores=None,
                diagnostics=diagnostics,
                admission=admission,
            )
        playtest_report = None
        counterexamples = ()
        try:
            from .redteam import AdversarialPlaytester
            from .dsl import StateMachineSimulator, canonical_mechanism_to_dsl

            program = canonical_mechanism_to_dsl(mechanism)
            playtest_report = AdversarialPlaytester().run_playtest(program)
            initial_state = StateMachineSimulator(program).initial_state()
            counterexamples = tuple(
                Counterexample(
                    witness_actions=issue.witness_actions,
                    initial_state=initial_state,
                    violated_invariant=issue.issue_type,
                )
                for issue in playtest_report.issues
                if issue.severity == "FATAL"
            )
            evaluation_error = None
        except Exception as exc:
            evaluation_error = f"red-team evaluation failed: {type(exc).__name__}: {exc}"

        admission = self.admission_controller.decide(
            scores=scores,
            validation_report=validation_report,
            playtest_report=playtest_report,
            thresholds=thresholds,
            evaluation_error=evaluation_error,
        )
        diagnostics = EvaluationDiagnostics(
            lexical_similarity=lexical, embedding_similarity=embedding,
            structural_similarity=structural,
            nearest_baseline_ids=tuple(x.id for x in negative_archive.baselines),
            feasibility_reasons=admission.reasons,
            provider_mode="mock" if getattr(self.provider, "mode", "") == "mock" else "external",
            embedding_mode=getattr(self.embeddings, "mode", "unavailable"),
            validation_report=validation_report,
            playtest_report=playtest_report,
            counterexamples=counterexamples,
        )
        from .qd import dynamical_niche_descriptor

        return EvaluationBundle(
            scores=scores,
            diagnostics=diagnostics,
            admission=admission,
            dynamics=dynamical_niche_descriptor(mechanism),
        )

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
