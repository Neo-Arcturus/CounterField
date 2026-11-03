from __future__ import annotations

import hashlib
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Protocol, runtime_checkable

from ..archive import QDArchive
from ..contracts import DomainAdapter
from ..models import IdeaCandidate, NegativeArchive, NormalizedProblem, QDArchiveEntry

def stable_hash(*values) -> int:
    """Process-independent 63-bit seed; replaces global `random` for per-slot determinism."""
    digest = hashlib.sha256("\x1f".join(str(v) for v in values).encode()).digest()
    return int.from_bytes(digest[:8], "big") >> 1

class ArchiveView:
    """Read-only window over a QDArchive; operators must not mutate search state."""
    __slots__ = ("_archive",)

    def __init__(self, archive: QDArchive):
        object.__setattr__(self, "_archive", archive)

    def __setattr__(self, name, value):
        raise AttributeError("ArchiveView is read-only")

    @property
    def elites(self) -> Mapping[str, QDArchiveEntry]:
        return MappingProxyType(dict(self._archive.elites))

    @property
    def reservoir(self) -> tuple[QDArchiveEntry, ...]:
        return tuple(self._archive.reservoir)

    @property
    def coverage(self) -> float | None:
        return self._archive.coverage

    @property
    def occupied_niches(self) -> int:
        return len(self._archive.elites)

@dataclass(frozen=True)
class OperatorContext:
    problem: NormalizedProblem
    parents: tuple[IdeaCandidate, ...]
    baselines: NegativeArchive
    archive: ArchiveView
    slot: int
    rng_seed: int

@runtime_checkable
class CreativeOperator(Protocol):
    name: str
    def propose(self, ctx: OperatorContext) -> list[IdeaCandidate]: ...

class LegacyPromptOperator:
    def __init__(self, adapter: DomainAdapter, operator: str):
        self.adapter = adapter
        self.name = operator

    def propose(self, ctx: OperatorContext) -> list[IdeaCandidate]:
        return self.adapter.generate_candidates(ctx.problem, self.name, ctx.parents, 1)
