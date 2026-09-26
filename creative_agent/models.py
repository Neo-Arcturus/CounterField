from __future__ import annotations

import hashlib
import math
import re
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def clean(value: str) -> str:
    value = " ".join(value.normalize("NFKC").split()) if hasattr(value, "normalize") else " ".join(value.split())
    if not value:
        raise ValueError("value must not be blank")
    return value


def stable_id(*values: str) -> str:
    return hashlib.sha256("\x1f".join(" ".join(v.casefold().split()) for v in values).encode()).hexdigest()[:16]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CausalLink(StrictModel):
    cause: str
    relation: Literal["increases", "decreases", "enables", "prevents", "depends_on"]
    effect: str

    _cause = field_validator("cause", "effect")(clean)


class CanonicalMechanism(StrictModel):
    core_mechanism: str
    causal_structure: tuple[CausalLink, ...]
    affected_system: str
    payoff: str

    _text = field_validator("core_mechanism", "affected_system", "payoff")(clean)

    @property
    def fingerprint(self) -> str:
        links = sorted(
            f"{clean(x.cause).casefold()}|{x.relation}|{clean(x.effect).casefold()}"
            for x in self.causal_structure
        )
        return stable_id(self.core_mechanism, self.affected_system, self.payoff, *links)


class Provenance(StrictModel):
    source_domain: str = "generic"
    culture_language_lens: str = "none"
    provider_mode: str = "mock"

    _text = field_validator("source_domain", "culture_language_lens", "provider_mode")(clean)


class IdeaCandidate(StrictModel):
    id: str
    problem_id: str
    title: str
    description: str
    mechanism: CanonicalMechanism | None = None
    operator: str = "baseline"
    worker_id: str = "worker-0"
    generation: int = 0
    parent_id: str | None = None
    assumptions: tuple[str, ...] = ()
    provenance: Provenance = Provenance()

    _text = field_validator("id", "problem_id", "title", "description")(clean)


class NicheDescriptor(StrictModel):
    intervention_level: Literal["individual", "team", "organization", "ecosystem"]
    resource_intensity: Literal["low", "medium", "high"]
    feedback_horizon: Literal["immediate", "short", "long"]

    @property
    def key(self) -> str:
        return f"{self.intervention_level}:{self.resource_intensity}:{self.feedback_horizon}"


class EvaluationScores(StrictModel):
    novelty: float = Field(ge=0, le=1)
    appropriateness: float = Field(ge=0, le=1)
    utility: float = Field(ge=0, le=1)
    surprise: float = Field(ge=0, le=1)
    coherence: float = Field(ge=0, le=1)
    mechanism_uniqueness: float = Field(ge=0, le=1)

    @field_validator("*")
    @classmethod
    def finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("scores must be finite")
        return value


class ValidationSeverity(str, Enum):
    FATAL = "FATAL"
    WARNING = "WARNING"


class ValidationIssue(StrictModel):
    severity: ValidationSeverity
    rule: str
    message: str
    involved_nodes: tuple[str, ...] = ()
    witness_path: tuple[str, ...] = ()


class ValidationReport(StrictModel):
    is_valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)


class PlaytestIssue(StrictModel):
    """A reproducible problem found by an adversarial simulation bot."""

    severity: Literal["FATAL", "WARNING"]
    bot_name: str
    issue_type: str
    description: str
    witness_actions: tuple[str, ...] = ()

    _text = field_validator("bot_name", "issue_type", "description")(clean)


class PlaytestReport(StrictModel):
    """Aggregate result of exploit, fatigue, and chaos playtesting."""

    is_passed: bool
    exploit_detected: bool
    fatigue_score: float = Field(ge=0, le=1)
    robustness_score: float = Field(ge=0, le=1)
    issues: list[PlaytestIssue] = Field(default_factory=list)
    bot_results: dict[str, Any] = Field(default_factory=dict)

    @field_validator("fatigue_score", "robustness_score")
    @classmethod
    def finite_playtest_score(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("playtest scores must be finite")
        return value


class EvaluationDiagnostics(StrictModel):
    lexical_similarity: float = 0
    embedding_similarity: float = 0
    structural_similarity: float = 0
    nearest_baseline_ids: tuple[str, ...] = ()
    feasibility_reasons: tuple[str, ...] = ()
    provider_mode: str = "mock"
    embedding_mode: str = "hash-lexical-proxy"
    validation_report: ValidationReport | None = None
    playtest_report: PlaytestReport | None = None


class QDArchiveEntry(StrictModel):
    candidate: IdeaCandidate
    niche: NicheDescriptor
    scores: EvaluationScores
    diagnostics: EvaluationDiagnostics
    insertion_generation: int = 0

    @model_validator(mode="after")
    def mechanism_required(self):
        if self.candidate.mechanism is None:
            raise ValueError("archive entries require a mechanism")
        return self


class NormalizedProblem(StrictModel):
    id: str
    original_prompt: str
    objective: str
    constraints: tuple[str, ...] = ()
    affected_system: str

    _text = field_validator("id", "original_prompt", "objective", "affected_system")(clean)


class NegativeArchive(StrictModel):
    baselines: tuple[IdeaCandidate, ...]
    mechanisms: tuple[CanonicalMechanism, ...]

    @model_validator(mode="after")
    def nonempty(self):
        if not self.baselines:
            raise ValueError("negative archive must contain at least one baseline")
        return self


class HarnessConfig(StrictModel):
    workers: int = Field(default=1, gt=0)
    generations: int = Field(default=3, gt=0)
    population_size: int = Field(default=6, gt=0)
    total_budget: int = Field(default=18, gt=0)
    seed: int = 42
    appropriateness_threshold: float = Field(default=.5, ge=0, le=1)
    coherence_threshold: float = Field(default=.5, ge=0, le=1)
    patience: int = Field(default=3, gt=0)
    epsilon: float = Field(default=.001, ge=0)


class GenerationStats(StrictModel):
    attempts: int = 0
    valid: int = 0
    feasible: int = 0
    failures: int = 0


class HarnessResult(StrictModel):
    status: str
    termination_reason: str
    metrics: dict[str, float | int]
    selected: tuple[QDArchiveEntry, ...] = ()
    frontier: tuple[QDArchiveEntry, ...] = ()
