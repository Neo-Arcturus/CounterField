# Phase 1 TDD Implementation: Dialectical Red-Team Synthesis & Rule Library

## Objective
Implement **Phase 1 (Mechanism ③ Dialectical Red-Teaming)** of the CounterField Creativity Engine as specified in `docs/ADR_CREATIVITY_ENGINE.md` and `20_SPEC/ADR_CREATIVITY_ENGINE.md`.
All existing 55 tests MUST continue to pass untouched. 100% strict TDD.

---

## Detailed Specifications

### 1. `creative_agent/creativity/dialectic.py` (New Module)
- **`SynthesisProposal(StrictModel)`**:
  - `child: IdeaCandidate` (must have `parent_id == parent.id`, and `lineage` containing `DialecticEvidence`)
  - `counterexample: Counterexample`
  - `ops: tuple[str, ...]` (e.g. `("add_cost_node", "add_feedback_loop")`)

- **`RuleRecord(StrictModel)`**:
  - `violated_invariant: str`
  - `ops: tuple[str, ...]`
  - `candidate_ids: tuple[str, ...] = ()`
  - `promoted: bool = False`

- **`RuleLibrary`**:
  - Thread-safe / deterministic tracking of discovered repair-to-feature patterns.
  - `record_success(violated_invariant: str, ops: tuple[str, ...], candidate_id: str) -> bool`:
    * Adds `candidate_id` to the rule's record.
    * Only promotes to `promoted=True` if `len(set(candidate_ids)) >= 2` (prevents overfitting to a single candidate).
  - `promoted_rules() -> tuple[RuleRecord, ...]`: returns rules that reached promotion status.
  - `snapshot() -> Any` and `restore(state: Any)`: for transactional atomicity (Invariant G5).

- **`DialecticalSynthesizer(Protocol)`**:
  - `@runtime_checkable`
  - `def synthesize(self, entry: QDArchiveEntry, counterexamples: tuple[Counterexample, ...], rule_library: RuleLibrary) -> list[SynthesisProposal]: ...`

- **`SynthesisVerifier`**:
  Deterministic verification of the 4 dialectic invariant conditions:
  1. **Clean Replay**: `replay_counterexample(child_program, ce).reproduced is False`.
  2. **Exploit Preservation**: The witness actions from the counterexample execute without error in the child program (`replay.error is None`), proving the exploit was retained as a valid mechanic/gameplay path rather than trivially pruned.
  3. **Non-Cosmetic Modification**: Child's `causal_structure` must contain at least 1 new node and at least 2 new links compared to parent, or child's `DynamicalNicheDescriptor` shows increased `loop_density` or `causal_depth`.
  4. **Regression Prevention**: Any previous counterexamples associated with the parent (or in the corpus) do not reproduce on the child.

- **`CEGISGuidedSynthesizer`**:
  Default synthesizer implementing `DialecticalSynthesizer`. Uses `CEGISRepairEngine` as a baseline and offers hook/backend for mechanism expansion. Supports a scripted/deterministic backend for unit tests.

### 2. `creative_agent/creativity/lineage.py` (New Module)
- **`LineageVerdict(StrictModel)`**:
  - `verified: bool`
  - `reasons: tuple[str, ...] = ()`
  - `credit_awarded: bool = False`

- **`LineageVerifier(Protocol)`**:
  - `@runtime_checkable`
  - `def verify(self, candidate: IdeaCandidate, context: Any = None) -> LineageVerdict: ...`

- **`DialecticLineageVerifier`**:
  - Implements `LineageVerifier` for `DialecticEvidence` by delegating to `SynthesisVerifier`.
  - Invariant G2 (No evidence, no credit): if verification fails, `verified=False` and `credit_awarded=False`. The candidate may still be evaluated as a normal idea, but receives zero creative lineage credit.

### 3. `creative_agent/harness.py` & Integration
- Update `IdeationHarness.__init__`:
  - Accept optional keyword arguments:
    * `synthesizer: DialecticalSynthesizer | None = None`
    * `rule_library: RuleLibrary | None = None`
    * `evidence_verifiers: Sequence[LineageVerifier] = ()`
    * `max_synthesis_per_entry: int = 2`
- In `run()`:
  - When an evaluation returns fatal playtest issues or lands in `repair_incubator` (stage `AdmissionStage.RED_TEAM` or status `AdmissionStatus.REPAIRABLE`):
    * If `self.synthesizer` is active, call `self.synthesizer.synthesize(entry, counterexamples, self.rule_library)`.
    * Ensure depth cap: `lineage` depth chain <= 3 (Invariant G12).
    * Up to `max_synthesis_per_entry` proposals are synthesized per entry (Invariant G11).
    * Each synthesized child candidate is queued / evaluated through the full validation, evaluation, and archive insertion pipeline (Invariant G1: FATAL parents never enter production; only valid children can enter).
    * If child passes `LineageVerifier.verify`, award creative credit and record success in `rule_library`.
  - Invariant G5 (Archive Atomicity):
    * Include `rule_library.snapshot()` in archive snapshot/restore so that any exception during insertion cleanly rolls back rule library state.
  - In `HarnessResult.metrics`:
    * Add `synthesis_attempts`, `synthesis_successes`, `rules_promoted`.

### 4. Tests: `tests/test_creativity_phase1.py`
Implement the 9 Phase 1 tests specified in ADR-CF-C:
1. `test_fatal_parent_never_enters_production`: Invariant G1. A FATAL parent remains in `repair_incubator`, never in `elites` or `reservoir`.
2. `test_child_must_replay_clean_but_preserve_witness_prefix`: Child must stop exploit reproduction while witness actions still run without transition crash.
3. `test_cosmetic_synthesis_rejected`: A child with zero new nodes or <2 new links is rejected by `SynthesisVerifier`.
4. `test_regression_corpus_replayed`: If child fixes counterexample A but breaks on counterexample B, verification fails.
5. `test_rule_promotion_requires_two_independent_successes`: `RuleLibrary` requires 2 distinct candidate IDs before marking a rule as promoted.
6. `test_synthesis_budget_and_depth_cap`: Enforces `max_synthesis_per_entry` and max depth <= 3 (Invariants G11, G12).
7. `test_synthesis_atomic_rollback_on_insert_failure`: Exception during child insertion rolls back archive and `RuleLibrary` state (Invariant G5).
8. `test_repair_incubator_consumed_when_synthesizer_present_and_untouched_when_absent`: Confirms hook activation only when synthesizer is supplied.
9. `test_dialectic_end_to_end_in_harness`: Full harness run demonstrating FATAL parent -> dialectical synthesis -> verified child admitted to archive.

---

## Verification
- Run `.venv/bin/pytest -v`
- ALL 55 existing tests + ALL 9 new Phase 1 tests MUST pass 100% (64+ passed).
