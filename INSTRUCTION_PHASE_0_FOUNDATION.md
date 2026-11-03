# Phase 0 TDD Implementation: Creative Operator Abstraction, Structural Fingerprint, and Metrics

## Objective
Implement **Phase 0 (Common Foundation)** of the CounterField Creativity Engine as specified in `docs/ADR_CREATIVITY_ENGINE.md` and `20_SPEC/ADR_CREATIVITY_ENGINE.md`.
All existing 44 tests MUST continue to pass untouched. 100% strict TDD.

---

## Detailed Specifications

### 1. `creative_agent/models.py`
- Define `CreativeLineage` models:
```python
class InversionEvidence(StrictModel):
    kind: Literal["inversion"] = "inversion"
    claim_id: str
    bound_link_indices: tuple[int, ...]
    flipped_polarity: bool

class IsomorphismEvidence(StrictModel):
    kind: Literal["isomorphism"] = "isomorphism"
    template_id: str
    role_map: dict[str, str]

class DialecticEvidence(StrictModel):
    kind: Literal["dialectic"] = "dialectic"
    counterexample_hash: str
    parent_fingerprint: str
    synthesis_ops: tuple[str, ...]

class CreativeLineage(StrictModel):
    operator: str
    evidence: InversionEvidence | IsomorphismEvidence | DialecticEvidence | None = None
    parent_ids: tuple[str, ...] = ()
```
- In `IdeaCandidate`, add:
  `lineage: CreativeLineage | None = None`
- Invariant G3: `CanonicalMechanism.fingerprint` implementation, NFKC normalization, and `|` escaping MUST NOT be modified in any way.

### 2. `creative_agent/creativity/` (New Package)
Create `creative_agent/creativity/`:
- `__init__.py`: Export key symbols.
- `operators.py`:
  - `class ArchiveView`: Read-only view over `QDArchive` (exposes `elites`, `reservoir`, `coverage`, `occupied_niches`, but prevents mutation).
  - `@dataclass(frozen=True) class OperatorContext`:
    * `problem: NormalizedProblem`
    * `parents: tuple[IdeaCandidate, ...]`
    * `baselines: NegativeArchive`
    * `archive: ArchiveView`
    * `slot: int`
    * `rng_seed: int` (deterministic seed per slot)
  - `@runtime_checkable class CreativeOperator(Protocol)`:
    * `name: str`
    * `def propose(self, ctx: OperatorContext) -> list[IdeaCandidate]: ...`
  - `class LegacyPromptOperator`:
    * Takes `adapter: DomainAdapter`, `operator: str`.
    * Implements `CreativeOperator` protocol.
    * Calls `adapter.generate_candidates(ctx.problem, self.operator, ctx.parents, 1)`.
- `structure.py`:
  - `def structural_fingerprint(mechanism: CanonicalMechanism) -> str`:
    * Builds a directed graph using `networkx.DiGraph`.
    * Nodes are anonymized (e.g. node labels erased or replaced with anonymous indices).
    * Edges carry the `relation` attribute.
    * Uses `networkx.weisfeiler_lehman_graph_hash(graph, edge_attr="relation")` to produce a structural fingerprint invariant to node relabeling.
    * If mechanism has no causal structure or nodes < 4, flag or handle appropriately (small graphs are not blacklisted).
- `metrics.py`:
  - Helper functions/structures to track creative yield, structural novelty, error classification counters (G10: `generation_errors`, `canonicalize_errors`, `evidence_errors`, `provider_fallbacks`).

### 3. `creative_agent/harness.py`
- Update `IdeationHarness.__init__` to accept optional keyword-only arguments:
  ```python
  def __init__(
      self,
      adapter: DomainAdapter | IdeaProvider,
      oracle: VerificationOracle | None = None,
      extractor: BehaviorExtractor | None = None,
      embeddings = None,
      *,
      operators: Sequence[CreativeOperator] | None = None,
      scheduler: Any = None,
      **kwargs,
  ):
  ```
- If `operators is None`:
  Use `LegacyPromptOperator` instances for the existing 6 operators in round-robin order (`["Inversion", "Extreme constraints", "Removal", "Cross-domain analogy", "Role shift", "Multilingual/cultural conceptualization"]`), ensuring byte-identical backward compatibility when default arguments are used.
- In `run()`:
  - Form `OperatorContext` per slot with:
    * `parents`: select non-empty parents from `archive.elites.values()` or `archive.reservoir` if available (e.g. top 1-2 parents or sample).
    * `rng_seed = stable_hash(config.seed, slot, operator.name)` (no global `random`!).
    * `archive`: read-only `ArchiveView(archive)`.
  - Propose candidates via `operator.propose(ctx)`.
  - Error classification (G10): Do NOT silently drop exceptions with bare `except Exception: continue`. Track error counters in `HarnessResult.metrics`:
    * `generation_errors`, `canonicalize_errors`, `validation_errors`, `evaluation_errors`.
  - If provider falls back to mock, mark `provenance.provider_mode = "mock-fallback"`.
  - Return all error counters in `HarnessResult.metrics`.

### 4. Tests: `tests/test_creativity_phase0.py`
Implement the 10 Phase 0 tests as specified in ADR-CF-C:
1. `test_default_harness_is_byte_identical`: When `operators=None`, `admission_log` and metrics match baseline behavior.
2. `test_fingerprint_golden_vectors_unchanged`: CanonicalMechanism.fingerprint matches fixed golden hashes (Invariant G3).
3. `test_lineage_excluded_from_fingerprint`: Adding `lineage` to `IdeaCandidate` does not alter its mechanism's fingerprint.
4. `test_structural_fingerprint_label_invariant`: Relabeling nodes produces identical `structural_fingerprint`, while flipping an edge relation produces a different fingerprint.
5. `test_structural_fingerprint_small_graph_not_blacklisted`: Graphs with < 4 nodes are handled cleanly.
6. `test_legacy_operator_matches_round_robin_order`: Verifies operators cycle through the 6 prompt operators when default.
7. `test_operator_rng_deterministic_by_seed`: Identical seeds produce identical slot rng_seeds (Invariant G8).
8. `test_generation_error_counters_not_silent`: Fault injection in `generate_candidates` increments `generation_errors` in metrics instead of being silently lost (Invariant G10).
9. `test_existing_protocols_unchanged`: `DomainAdapter`, `VerificationOracle`, `BehaviorExtractor` methods are strictly unchanged (Invariant F8).
10. `test_parent_selection_feeds_context`: When archive has entries, non-empty `parents` are supplied in `OperatorContext`.

---

## Verification
- Run `.venv/bin/pytest -v`
- ALL 44 existing tests + ALL 10 new Phase 0 tests MUST pass 100% (54 passed).
