"""Domain-decoupling contracts for the QD search engine.

The harness only talks to these three protocols; the Default* classes bridge
the legacy IdeaProvider/ThreeLayerEvaluator components onto them.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from .evaluator import ThreeLayerEvaluator
from .models import (
    DynamicalNicheDescriptor,
    EvaluationBundle,
    IdeaCandidate,
    NegativeArchive,
    NicheDescriptor,
    NormalizedProblem,
    ValidationReport,
)
from .normalizer import BaselineClicheMiner, ProblemNormalizer
from .providers import EmbeddingProvider, HashEmbeddingProvider, IdeaProvider
from .qd import dynamical_niche_descriptor


@runtime_checkable
class DomainAdapter(Protocol):
    def normalize_problem(self, problem: str) -> NormalizedProblem: ...
    def generate_candidates(self, problem: NormalizedProblem, operator: str, context: tuple[IdeaCandidate, ...], count: int) -> list[IdeaCandidate]: ...
    def canonicalize_mechanism(self, problem: NormalizedProblem, candidate: IdeaCandidate) -> IdeaCandidate: ...
    def mine_baselines(self, problem: NormalizedProblem) -> NegativeArchive: ...


@runtime_checkable
class VerificationOracle(Protocol):
    def validate_structure(self, candidate: IdeaCandidate) -> ValidationReport: ...
    def evaluate(self, problem: NormalizedProblem, candidate: IdeaCandidate, baselines: NegativeArchive, thresholds: tuple[float, float]) -> EvaluationBundle: ...


@runtime_checkable
class BehaviorExtractor(Protocol):
    def extract_niche(self, problem: NormalizedProblem, candidate: IdeaCandidate) -> NicheDescriptor: ...
    def extract_dynamics(self, candidate: IdeaCandidate) -> DynamicalNicheDescriptor | None: ...


class DefaultDomainAdapter:
    def __init__(self, provider: IdeaProvider):
        self.provider = provider

    def normalize_problem(self, problem: str) -> NormalizedProblem:
        return ProblemNormalizer(self.provider).normalize(problem)

    def generate_candidates(self, problem, operator, context, count):
        return self.provider.generate(problem, operator, context, count)

    def canonicalize_mechanism(self, problem, candidate):
        return self.provider.canonicalize(problem, candidate)

    def mine_baselines(self, problem):
        return BaselineClicheMiner(self.provider).mine(problem)


class DefaultVerificationOracle:
    def __init__(self, evaluator: ThreeLayerEvaluator | IdeaProvider, embeddings: EmbeddingProvider | None = None):
        if not isinstance(evaluator, ThreeLayerEvaluator):
            evaluator = ThreeLayerEvaluator(evaluator, embeddings or HashEmbeddingProvider())
        self.evaluator = evaluator

    def validate_structure(self, candidate):
        return self.evaluator.validator.validate(candidate)

    def evaluate(self, problem, candidate, baselines, thresholds):
        return self.evaluator.evaluate(problem, candidate, baselines, thresholds)


class DefaultBehaviorExtractor:
    def __init__(self, provider: IdeaProvider):
        self.provider = provider

    def extract_niche(self, problem, candidate):
        return self.provider.describe_niche(problem, candidate)

    def extract_dynamics(self, candidate):
        if candidate.mechanism is None:
            return None
        return dynamical_niche_descriptor(candidate.mechanism)


__all__ = [
    "BehaviorExtractor",
    "DefaultBehaviorExtractor",
    "DefaultDomainAdapter",
    "DefaultVerificationOracle",
    "DomainAdapter",
    "VerificationOracle",
]
