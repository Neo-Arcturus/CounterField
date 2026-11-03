# Phase 4 TDD Implementation: Open-Ended Dynamic Niches & Append-Only Centroids

## Objective
Implement **Phase 4 (Mechanism ④ Open-Ended Dynamic Niches)** of the CounterField Creativity Engine as specified in `docs/ADR_CREATIVITY_ENGINE.md` and `20_SPEC/ADR_CREATIVITY_ENGINE.md`.
All existing 81 tests MUST continue to pass untouched. 100% strict TDD.

---

## Detailed Specifications

### 1. `creative_agent/creativity/niche_space.py` (New Module)
- **`NicheSpace(Protocol)`**:
  - `@runtime_checkable`
  - `version: int`
  - `def locate(self, entry: QDArchiveEntry) -> str: ...`  # returns niche_key
  - `def maybe_expand(self, entries: Sequence[QDArchiveEntry], rng_seed: int) -> Any: ...`
  - `@property def capacity(self) -> int | None: ...`  # None for open-ended space, integer for fixed grid
  - `def snapshot(self) -> Any: ...`
  - `def restore(self, state: Any) -> None: ...`

- **`FixedGridSpace` (Regression Baseline / Default)**:
  - Implements `NicheSpace`.
  - `capacity = 36`
  - `locate(entry)`:
    * If `entry.dynamics is None`: returns `entry.niche.key`
    * Else: returns `f"{entry.niche.key}|{entry.dynamics.key}"`
  - `maybe_expand`: no-op.
  - Exactly preserves legacy behavior and byte-identical outputs.

- **`CentroidNicheSpace` (Open-Ended Append-Only Centroids)**:
  - Behavior vector projection: maps `(entry.niche, entry.dynamics)` to a normalized numeric vector in $[0, 1]^D$:
    * `intervention_level`: `{"individual": 0.0, "team": 0.33, "organization": 0.66, "ecosystem": 1.0}`
    * `resource_intensity`: `{"low": 0.0, "medium": 0.5, "high": 1.0}`
    * `feedback_horizon`: `{"immediate": 0.0, "short": 0.5, "long": 1.0}`
    * `causal_depth`: normalized (e.g. `min(depth / 10.0, 1.0)`)
    * `branching_factor`: normalized (e.g. `min(branching / 5.0, 1.0)`)
    * `loop_density`: clamped `[0, 1]`
    * `payoff_path_length`: normalized (or `1.0` if unreachable)
  - `capacity`: returns `None` (open-ended unbounded niche space).
  - Starts with an initial set of centroids (or seeds from initial entries).
  - `locate(entry)`: finds nearest centroid by Euclidean distance; returns `f"centroid_{idx}"` (or centroid id).
  - **Append-Only Expansion (`maybe_expand`)**:
    * If an accepted entry's distance to nearest existing centroid exceeds novelty threshold `rho` (e.g. `rho = 0.25`), and `min_candidates` (e.g. 1 or 2) accumulate:
    * Add new centroid at the candidate's vector.
    * **Invariant G7 (Monotone Elites)**: Existing centroids and prior allocations are NEVER modified or recomputed. No retroactive re-clustering!
  - `snapshot()` & `restore()`: snapshot/restore list of centroids and counter for transactional rollback.

### 2. `creative_agent/archive.py` Integration
- Update `QDArchive.__init__`:
  - `def __init__(self, niche_space: NicheSpace | None = None):`
  - Defaults to `FixedGridSpace()`.
- Update `_niche_key(self, entry)`:
  - Calls `self.niche_space.locate(entry)`.
- Update `_snapshot()` & `_restore()`:
  - Invariant G5 (Archive Atomicity): includes `self.niche_space.snapshot()` and `self.niche_space.restore()` in the transaction snapshot. Any exception during `insert()` cleanly rolls back niche space state!
- Update `coverage` property:
  - Invariant F5: `coverage` returns `len(self.elites) / self.niche_space.capacity` if `self.niche_space.capacity` is not None, else `None`.
  - Add `qd_score` helper / metric: sum of scalar quality scores of all elites.

### 3. `creative_agent/harness.py` Integration
- Accept `niche_space: NicheSpace | None = None` in `IdeationHarness.__init__` and pass to `QDArchive`.
- In `run()`:
  - After admitting entries or before insert, invoke `archive.niche_space.maybe_expand(...)` using slot's deterministic seed.
  - In `HarnessResult.metrics`:
    * If `archive.coverage is None`: report `"coverage": None`, `"niche_count": len(archive.elites)`, `"qd_score": sum(e.scores.novelty + e.scores.utility for e in archive.elites.values())`.
- Export new classes from `creative_agent/creativity/__init__.py`.

### 4. Tests: `tests/test_creativity_phase4.py`
Implement the 7 Phase 4 tests specified in ADR-CF-C:
1. `test_fixed_grid_space_equals_legacy_keys`: Verifies `FixedGridSpace` produces exact same niche keys as previous legacy logic.
2. `test_centroid_expansion_is_append_only_and_elites_monotone`: Confirm existing elites are NEVER evicted when space expands (Invariant G7).
3. `test_expansion_rolled_back_with_failed_insert`: Exception during insert rolls back niche expansion (Invariant G5).
4. `test_expansion_deterministic_by_seed`: Expansion gives identical centroids for identical rng_seed (Invariant G8).
5. `test_coverage_none_for_open_space_and_metrics_present`: `archive.coverage` returns `None` for open space, but `niche_count` and `qd_score` are present in metrics.
6. `test_reservoir_independent_of_niche_space`: Pareto reservoir / frontier composition is identical regardless of whether `FixedGridSpace` or `CentroidNicheSpace` is used (Invariant G6).
7. `test_below_rho_does_not_expand`: Entries with distance < rho do NOT trigger centroid expansion.

---

## Verification
- Run `.venv/bin/pytest -v`
- ALL 81 existing tests + ALL 7 new Phase 4 tests MUST pass 100% (88+ passed).
