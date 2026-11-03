# Phase 2 TDD Implementation: Deliberate Invariant Inversion & Buffer Path Verification

## Objective
Implement **Phase 2 (Mechanism ① Deliberate Invariant Inversion)** of the CounterField Creativity Engine as specified in `docs/ADR_CREATIVITY_ENGINE.md` and `20_SPEC/ADR_CREATIVITY_ENGINE.md`.
All existing 64 tests MUST continue to pass untouched. 100% strict TDD.

---

## Detailed Specifications

### 1. `creative_agent/creativity/inversion.py` (New Module)
- **`InvariantClaim(StrictModel)`**:
  - `id: str` (e.g. `stable_id(statement, cause, relation, effect)`)
  - `statement: str`
  - `cause: str`
  - `relation: Literal["increases", "decreases", "enables", "prevents", "depends_on"]`
  - `effect: str`
  - `evidence_quote: str` (mandatory quote from problem prompt or baseline texts)

- **`InvariantMiner(Protocol)`**:
  - `@runtime_checkable`
  - `def mine(self, problem: NormalizedProblem, baselines: NegativeArchive) -> tuple[InvariantClaim, ...]: ...`

- **`DefaultInvariantMiner` (or `HeuristicInvariantMiner`)**:
  - Extracts common domain axioms or claims.
  - **Hallucination Guard**: A claim is ONLY valid if `evidence_quote` (after `clean()` / NFKC normalization and `casefold()`) is a genuine substring of `problem.original_prompt` or at least one baseline description/title. If not found, the claim MUST be silently dropped / rejected.

- **`InversionVerifier`**:
  Deterministic verification of the invariant inversion:
  1. **Link Existence**: `bound_link_indices` in `InversionEvidence` must be valid 0-based indices into `candidate.mechanism.causal_structure`.
  2. **Polarity Flip**: The relation of the bound link must be the exact polarity flip of the claim's relation:
     - `increases` <-> `decreases`
     - `enables` <-> `prevents`
     - `depends_on` <-> (inverted direction or invalid if no opposite defined)
  3. **Buffer Path (Non-catastrophic Inversion)**:
     - Using `CausalGraphValidator.build_graph(candidate.mechanism)`:
     - The flipped effect must have an active path to `payoff`.
     - Crucially, there must exist an alternate/buffer path or newly introduced node that bypasses the flipped link so that the inversion does not trivially destroy system payoff reachability.
  4. Returns `LineageVerdict(verified=True, credit_awarded=True)` if all checks pass, otherwise `verified=False`.

- **`InversionOperator` (`CreativeOperator`)**:
  - Implements `CreativeOperator` protocol.
  - Takes an `InvariantMiner`.
  - Curriculum: Starts with "single inversion" (1 claim). When a single inversion succeeds or archive has verified inversions, supports "double inversion" (2 simultaneous claims).
  - Proposes candidates carrying `CreativeLineage(operator="inversion", evidence=InversionEvidence(...))`.
  - Supports a scripted / deterministic backend for unit testing without external network calls.

### 2. `creative_agent/creativity/lineage.py`
- Add `InversionLineageVerifier`:
  - Implements `LineageVerifier` for `InversionEvidence` by calling `InversionVerifier`.
  - Invariant G2 (No evidence, no credit): if verification fails, `verified=False` and `credit_awarded=False`. The candidate may still be evaluated as a normal idea, but receives zero creative lineage credit.

### 3. `creative_agent/harness.py` & Integration
- Update `IdeationHarness`:
  - When `operators` includes an `InversionOperator` or `evidence_verifiers` includes `InversionLineageVerifier`, verify inversion evidence upon admission.
  - Track `inversion_attempts` and `inversion_successes` in `HarnessResult.metrics`.
  - Export new symbols in `creative_agent/creativity/__init__.py`.

### 4. Tests: `tests/test_creativity_phase2.py`
Implement the Phase 2 tests specified in ADR-CF-C:
1. `test_claim_without_prompt_evidence_quote_dropped`: Hallucinated claim without matching substring quote in prompt/baselines is dropped (test both English and Korean).
2. `test_polarity_flip_detected`: Verifies all polarity flip pairs (`increases` <-> `decreases`, `enables` <-> `prevents`).
3. `test_inversion_without_buffer_path_unverified_or_fatal`: Inversion without buffer path fails verification.
4. `test_unbound_link_indices_unverified`: Invalid or out-of-bounds indices in `bound_link_indices` fail verification.
5. `test_inversion_curriculum_single_then_double`: Demonstrates progression from single inversion to double inversion.
6. `test_unverified_inversion_gets_no_scheduler_reward`: Unverified inversion gets `credit_awarded=False` (Invariant G2).
7. `test_inversion_end_to_end_in_harness`: Full harness run with `InversionOperator` producing verified inverted candidate in archive.

---

## Verification
- Run `.venv/bin/pytest -v`
- ALL 64 existing tests + ALL 7 new Phase 2 tests MUST pass 100% (71+ passed).
