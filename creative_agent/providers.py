from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol, Any

from .models import *


class IdeaProvider(Protocol):
    def normalize(self, problem: str) -> NormalizedProblem: ...
    def mine_baselines(self, problem: NormalizedProblem, count: int) -> list[IdeaCandidate]: ...
    def canonicalize(self, problem: NormalizedProblem, candidate: IdeaCandidate) -> IdeaCandidate: ...
    def assess(self, problem: NormalizedProblem, candidate: IdeaCandidate) -> EvaluationScores: ...
    def describe_niche(self, problem: NormalizedProblem, candidate: IdeaCandidate) -> NicheDescriptor: ...


class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbeddingProvider:
    mode = "hash-lexical-proxy"

    def __init__(self, dimensions: int = 64):
        self.dimensions = dimensions
        self._cache: dict[str, list[float]] = {}

    def embed(self, texts: list[str]) -> list[list[float]]:
        result = []
        for text in texts:
            key = " ".join(text.casefold().split())
            if key not in self._cache:
                vector = [0.0] * self.dimensions
                features = re.findall(r"\w+", key, re.UNICODE)
                features += [key[i:i + 3] for i in range(max(0, len(key) - 2))]
                for feature in features:
                    digest = hashlib.sha256(feature.encode()).digest()
                    vector[int.from_bytes(digest[:4], "big") % self.dimensions] += 1
                norm = math.sqrt(sum(x * x for x in vector))
                self._cache[key] = [x / norm for x in vector] if norm else vector
            result.append(self._cache[key][:])
        return result


class MockIdeaProvider:
    mode = "mock"

    def normalize(self, problem: str) -> NormalizedProblem:
        text = " ".join(problem.split())
        if not text:
            raise ValueError("problem must not be empty")
        return NormalizedProblem(
            id=stable_id(text), original_prompt=text, objective=text,
            constraints=("avoid unnecessary complexity",), affected_system="people and their workflow",
        )

    def mine_baselines(self, problem: NormalizedProblem, count: int) -> list[IdeaCandidate]:
        templates = [
            ("Add a checklist", "Use a standard checklist to guide each participant."),
            ("Add a meeting", "Schedule a recurring meeting so information is shared."),
            ("Add a dashboard", "Display progress metrics so people can monitor work."),
        ]
        return [self._candidate(problem, title, desc, "baseline", i) for i, (title, desc) in enumerate(templates[:count])]

    def generate(self, problem, operator, private_history, count):
        ops = {
            "Inversion": ("Reverse the usual information flow", "The recipient initiates a signal that causes the provider to adapt."),
            "Extreme constraints": ("Design for one minute", "A tiny input triggers an automated default and removes coordination cost."),
            "Removal": ("Remove the meeting", "Asynchronous evidence replaces synchronized discussion and preserves accountability."),
            "Cross-domain analogy": ("Borrow from ecosystems", "Local signals cause neighboring participants to share resources when capacity changes."),
            "Role shift": ("Move ownership to the user", "The person experiencing friction decides the next action and receives immediate feedback."),
            "Multilingual/cultural conceptualization": ("Use reciprocity as a lens", "A reciprocal exchange makes each action create a visible benefit for another participant."),
        }
        title, desc = ops.get(operator, ("Adaptive experiment", "A small reversible experiment creates feedback before commitment."))
        return [self._candidate(problem, title, desc, operator, i) for i in range(count)]

    def canonicalize(self, problem, candidate):
        if candidate.mechanism:
            return candidate
        link = CausalLink(cause=candidate.title, relation="increases", effect="useful feedback")
        return candidate.model_copy(update={"mechanism": CanonicalMechanism(
            core_mechanism=candidate.description, causal_structure=(link,),
            affected_system=problem.affected_system, payoff="lower friction",
        )})

    def assess(self, problem, candidate):
        return EvaluationScores(novelty=.8, appropriateness=.75, utility=.7, surprise=.7, coherence=.85, mechanism_uniqueness=.8)

    def describe_niche(self, problem, candidate):
        choices: list[tuple[Any, Any, Any]] = [
            ("individual", "low", "immediate"),
            ("team", "medium", "short"),
            ("organization", "high", "long"),
        ]
        lvl, res, hor = choices[int(candidate.id[-2:], 16) % len(choices)]
        return NicheDescriptor(intervention_level=lvl, resource_intensity=res, feedback_horizon=hor)

    def _candidate(self, problem, title, description, operator, index):
        return IdeaCandidate(
            id=stable_id(problem.id, operator, str(index), title), problem_id=problem.id,
            title=title, description=description, operator=operator,
            provenance=Provenance(provider_mode="mock"),
        )
