import math
from typing import Any, Protocol, Sequence, runtime_checkable

from ..models import QDArchiveEntry

_INTERVENTION = {"individual": 0.0, "team": 0.33, "organization": 0.66, "ecosystem": 1.0}
_RESOURCE = {"low": 0.0, "medium": 0.5, "high": 1.0}
_HORIZON = {"immediate": 0.0, "short": 0.5, "long": 1.0}


@runtime_checkable
class NicheSpace(Protocol):
    version: int

    def locate(self, entry: QDArchiveEntry) -> str: ...
    def maybe_expand(self, entries: Sequence[QDArchiveEntry], rng_seed: int) -> Any: ...
    @property
    def capacity(self) -> int | None: ...
    def snapshot(self) -> Any: ...
    def restore(self, state: Any) -> None: ...


class FixedGridSpace:
    """Legacy 36-cell grid (optionally refined by dynamics); the regression baseline."""

    version = 0

    @property
    def capacity(self) -> int | None:
        return 36

    def locate(self, entry: QDArchiveEntry) -> str:
        if entry.dynamics is None:
            return entry.niche.key
        return f"{entry.niche.key}|{entry.dynamics.key}"

    def maybe_expand(self, entries: Sequence[QDArchiveEntry], rng_seed: int) -> Any:
        return None

    def snapshot(self) -> Any:
        return None

    def restore(self, state: Any) -> None:
        return None


class CentroidNicheSpace:
    """Open-ended niche space whose centroids are only ever appended (G7: no re-clustering)."""

    def __init__(self, rho: float = 0.25, min_candidates: int = 1,
                 centroids: Sequence[Sequence[float]] = ()):
        if rho <= 0 or min_candidates < 1:
            raise ValueError("rho must be positive and min_candidates at least 1")
        self.rho = rho
        self.min_candidates = min_candidates
        self.version = 0
        self._centroids: list[tuple[float, ...]] = [tuple(c) for c in centroids]
        self._pending: list[tuple[float, ...]] = []

    @property
    def capacity(self) -> int | None:
        return None

    @property
    def centroids(self) -> tuple[tuple[float, ...], ...]:
        return tuple(self._centroids)

    @staticmethod
    def project(entry: QDArchiveEntry) -> tuple[float, ...]:
        n = entry.niche
        vec = [_INTERVENTION[n.intervention_level], _RESOURCE[n.resource_intensity], _HORIZON[n.feedback_horizon]]
        d = entry.dynamics
        if d is None:
            return tuple(vec + [0.0, 0.0, 0.0, 1.0])
        payoff = 1.0 if d.payoff_path_length is None else min(d.payoff_path_length / 10.0, 1.0)
        vec += [min(d.causal_depth / 10.0, 1.0), min(d.branching_factor / 5.0, 1.0),
                min(max(d.loop_density, 0.0), 1.0), payoff]
        return tuple(vec)

    def _nearest(self, vec: Sequence[float]) -> tuple[int, float]:
        best, best_d = -1, math.inf
        for i, c in enumerate(self._centroids):
            dist = math.dist(c, vec)
            if dist < best_d:
                best, best_d = i, dist
        return best, best_d

    def locate(self, entry: QDArchiveEntry) -> str:
        idx, _ = self._nearest(self.project(entry))
        return f"centroid_{idx}" if idx >= 0 else "centroid_unassigned"

    def maybe_expand(self, entries: Sequence[QDArchiveEntry], rng_seed: int) -> list[tuple[float, ...]]:
        """Append centroids for novel accepted entries; returns the centroids added by this call."""
        added: list[tuple[float, ...]] = []
        for entry in entries:
            vec = self.project(entry)
            if self._nearest(vec)[1] > self.rho:
                self._pending.append(vec)
        promoted = True
        while promoted:
            promoted = False
            for p in self._pending:
                if self._nearest(p)[1] <= self.rho:
                    continue
                group = [q for q in self._pending if math.dist(p, q) <= self.rho]
                if len(group) >= self.min_candidates:
                    self._centroids.append(p)
                    added.append(p)
                    self.version += 1
                    promoted = True
                    break
        self._pending = [q for q in self._pending if self._nearest(q)[1] > self.rho]
        return added

    def snapshot(self) -> Any:
        return (tuple(self._centroids), tuple(self._pending), self.version)

    def restore(self, state: Any) -> None:
        centroids, pending, self.version = state
        self._centroids, self._pending = list(centroids), list(pending)
