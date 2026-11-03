from __future__ import annotations

from dataclasses import dataclass, field

from ..models import IdeaCandidate
from .structure import structural_fingerprint

ERROR_KEYS = (
    "generation_errors", "canonicalize_errors", "validation_errors",
    "evaluation_errors", "evidence_errors", "provider_fallbacks",
)

@dataclass
class CreativeMetrics:
    errors: dict[str, int] = field(default_factory=lambda: {k: 0 for k in ERROR_KEYS})
    proposed: int = 0
    admitted: int = 0
    structures: set[str] = field(default_factory=set)

    def count_error(self, key: str) -> None:
        self.errors[key] = self.errors.get(key, 0) + 1

    def record_admitted(self, candidate: IdeaCandidate) -> None:
        self.admitted += 1
        if candidate.mechanism is not None and candidate.mechanism.causal_structure:
            self.structures.add(structural_fingerprint(candidate.mechanism))

    @property
    def creative_yield(self) -> float:
        return self.admitted / self.proposed if self.proposed else 0.0

    @property
    def structural_novelty(self) -> int:
        return len(self.structures)
