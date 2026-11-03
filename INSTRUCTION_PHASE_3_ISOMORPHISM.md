# Phase 3 TDD Implementation: Cross-Domain Isomorphism & Monomorphic Verifier

## Objective
Implement **Phase 3 (Mechanism ② Cross-Domain Isomorphism)** of the CounterField Creativity Engine as specified in `docs/ADR_CREATIVITY_ENGINE.md` and `20_SPEC/ADR_CREATIVITY_ENGINE.md`.
All existing 74 tests MUST continue to pass untouched. 100% strict TDD.

---

## Detailed Specifications

### 1. `creative_agent/creativity/isomorphism.py` (New Module)
- **`CausalTemplate(StrictModel)`**:
  - `id: str`
  - `domain: str` (e.g. `"ecology"`, `"os_kernel"`, `"thermodynamics"`, `"auction"`)
  - `roles: tuple[str, ...]` (abstract role nodes)
  - `links: tuple[CausalLink, ...]` (role-based causal structure preserving typed relations)
  - `motifs: tuple[str, ...]` (e.g. `("feedback_loop", "bottleneck", "asymmetry")`)
  - `curated_by: str`
  - `source_ref: str` (mandatory source reference; unreferenced LLM templates are disqualified)
  - `domain_vocabulary: tuple[str, ...] = ()` (blacklisted domain-specific terms to prevent surface copying)

- **`MotifProfile(StrictModel)`**:
  - `has_feedback_loop: bool = False` (SCC with size >= 2 or self loop)
  - `has_bottleneck: bool = False` (betweenness centrality >= 0.4 or articulation point)
  - `has_asymmetry: bool = False` (significant in-degree / out-degree asymmetry)

- **`MotifExtractor`**:
  - Deterministic extractor using `networkx`:
    * Analyzes graph of `CanonicalMechanism` or problem/baseline graphs.
    * Returns `MotifProfile`.

- **`TemplateLibrary`**:
  - Curated collection of 12 initial templates across 4 domains (3 per domain):
    * **Ecology**: `predator_prey_balance`, `trophic_cascade`, `niche_differentiation`
    * **OS Kernel**: `priority_inversion_mitigation`, `copy_on_write`, `work_stealing_queue`
    * **Thermodynamics**: `heat_sink_dissipation`, `phase_transition_hysteresis`, `entropy_barrier`
    * **Auction**: `vickrey_truthful_bidding`, `dutch_clock_escalation`, `clearinghouse_settlement`
  - `match(motifs: MotifProfile, k: int = 3) -> tuple[CausalTemplate, ...]`:
    * Filters out any template where `not template.source_ref.strip()` (Invariant: unreferenced templates disqualified).
    * Scores template motif overlap and returns top `k` candidates.

- **`IsomorphismVerifier`**:
  Deterministic verification of the mapped candidate against the causal template:
  1. **Injective Role Map**: `role_map` in `IsomorphismEvidence` must be injective (no two template roles map to the same candidate node).
  2. **Role Coverage**: All `template.roles` must be mapped in `role_map`.
  3. **Relation-Preserving Monomorphism**:
     * Candidate's causal structure must contain a subgraph that is isomorphic to the template graph under the given `role_map`, with identical `relation` on every mapped edge (`nx.algorithms.isomorphism.DiGraphMatcher` or direct edge mapping check).
  4. **Surface Copying Rejection (No Surface Theatre)**:
     * Candidate's mapped node labels must NOT verbatim copy template role names or words from `template.domain_vocabulary`. They must be genuine problem-domain concepts.
  5. **Baseline Isomorphism Rejection (Invariant G4)**:
     * If the candidate's `structural_fingerprint` matches the `structural_fingerprint` of any baseline in `NegativeArchive` (for graphs with >= 4 nodes), it is deemed a mere relabeling of an existing baseline, and verification fails.

- **`BlendOperator(CreativeOperator)`**:
  - Takes `TemplateLibrary` and `MotifExtractor`.
  - Analyzes problem/baseline motifs, picks matching templates, and projects them into domain concepts.
  - Proposes candidates with `CreativeLineage(operator="isomorphism", evidence=IsomorphismEvidence(...))`.
  - Supports scripted deterministic backend for zero-network testing (Invariant G9).

### 2. `creative_agent/creativity/lineage.py`
- Add `IsomorphismLineageVerifier`:
  - Implements `LineageVerifier` for `IsomorphismEvidence` by delegating to `IsomorphismVerifier`.
  - Invariant G2 (No evidence, no credit): returns `LineageVerdict(verified=False, credit_awarded=False)` if verification fails.

### 3. `creative_agent/harness.py` & Integration
- Update `IdeationHarness`:
  - Support `BlendOperator` and `IsomorphismLineageVerifier`.
  - Track `isomorphism_attempts` and `isomorphism_successes` in `HarnessResult.metrics`.
  - Export new symbols in `creative_agent/creativity/__init__.py`.

### 4. Tests: `tests/test_creativity_phase3.py`
Implement the 7 Phase 3 tests specified in ADR-CF-C:
1. `test_motif_extraction_feedback_bottleneck_asymmetry`: Fixed golden graphs produce exact expected `MotifProfile`.
2. `test_role_map_must_be_injective`: Non-injective role mapping (two template roles mapped to same node) fails verification.
3. `test_relation_preserving_monomorphism_required`: Subgraph with mismatched relation (e.g. `decreases` instead of `enables`) fails verification.
4. `test_template_vocabulary_copy_rejected`: Mapped node labels that copy template vocabulary/roles verbatim are rejected.
5. `test_isomorphic_to_baseline_is_not_credited`: If candidate has identical `structural_fingerprint` to a baseline, verification fails (Invariant G4).
6. `test_template_without_source_ref_excluded`: Templates lacking `source_ref` are filtered out from `TemplateLibrary.match()`.
7. `test_blend_runs_zero_network_with_scripted_backend`: BlendOperator executes with zero network and produces a verified candidate in the harness (Invariant G9).

---

## Verification
- Run `.venv/bin/pytest -v`
- ALL 74 existing tests + ALL 7 new Phase 3 tests MUST pass 100% (81+ passed).
