# P0 Integrity & Security Repair Task Contract

## Background & Objective
An independent R0 baseline audit identified critical integrity and reliability flaws in the `creative-agent` (CounterField) codebase:
1. `archive.py`: Incomplete/missing evidence is admitted into the production archive; evidence associated with a different candidate is accepted without validation; insertion exceptions leave dirty state (counters/logs/seen sets mutate before reservoir/elites commit), breaking atomicity and making retries fail as false duplicates.
2. `models.py`: `clean()` erroneously checks `hasattr(value, "normalize")` (which is always False for Python `str`), so NFKC and combining characters are never normalized. Furthermore, pipe delimiters `|` in causal links are unescaped, causing fingerprint collisions.
3. `cli.py`: `--dry-run` with `--provider llm` attempts 9 network requests before fallback, violating zero-network dry-run invariants.
4. `pyproject.toml`: Missing `requires-python` and `license` metadata.

You are tasked with fixing these P0 defects completely and proving correctness with unit tests.

---

## Detailed Specifications

### 1. `creative_agent/models.py` & Canonical Identity
- In `clean(value: str)`: Import `unicodedata`. Apply `unicodedata.normalize("NFKC", value)` and whitespace cleanup.
- In `CanonicalMechanism.fingerprint`:
  - When serializing causal links `f"{cause}|{relation}|{effect}"`, escape any `|` characters in `cause` and `effect` (e.g. `clean(x.cause).casefold().replace("|", r"\|")`) so distinct structures never collide.
- In `EvaluationBundle`:
  - Add an optional `candidate_id: str | None = None` and `candidate_fingerprint: str | None = None` to bind the evaluation bundle to its target candidate.
- In `QDArchiveEntry`:
  - Validate that if `self.evaluation` has `candidate_id`, it matches `self.candidate.id`. If `candidate_fingerprint` is provided, it must match `self.candidate.mechanism.fingerprint`.

### 2. `creative_agent/archive.py` & Invariant Enforcement
- **Evidence Requirement**:
  - `QDArchive.insert()` must NOT silently admit candidates without evidence.
  - If neither `admission` nor `entry.evaluation` is provided, the candidate cannot be admitted as ACCEPTED into elites or reservoir. It must be treated as missing evidence and rejected (`AdmissionStatus.REJECTED` or denied).
- **Candidate-Evidence Identity Match**:
  - If `admission` is an `EvaluationBundle` (or `entry.evaluation` exists), verify that its bound `candidate_id` or `candidate_fingerprint` (if present) matches `entry.candidate.id` and `entry.candidate.mechanism.fingerprint`. If mismatched, deny admission (`status: REJECTED`).
- **FATAL Override**:
  - Ensure any diagnostics or playtest reports containing `FATAL` issues cannot enter elites or reservoir, and are routed to `REPAIRABLE`/`RED_TEAM` in `repair_incubator`.
- **Atomic State Transitions**:
  - `QDArchive.insert()` must be transactional / atomic.
  - If any exception occurs during the insertion process (e.g. fault injection in `dominates()` or data structures), all mutated state must be safely rolled back (or computed in temporary staging and committed only upon success).
  - An exception during insert must leave `attempts`, `valid`, `duplicates`, `niche_attempts`, `admission_log`, `seen_ids`, `seen_mechanisms`, `reservoir`, `elites`, `repair_incubator`, and `failure_archive` exactly as they were before the call.
  - Subsequent retries of the same insertion must succeed cleanly without being falsely flagged as duplicates.

### 3. `creative_agent/cli.py` & Zero-Network Dry-Run
- When `--dry-run` is passed, the CLI must short-circuit before attempting any HTTP/socket calls to LLM providers (e.g., bypass provider network calls and use mock synthesis directly, or emit mock diagnostic output without initiating requests).
- Verify that `dry_run` under `--provider llm` attempts zero network connections.

### 4. `pyproject.toml`
- Add `requires-python = ">=3.10"` under `[project]`.
- Add `license = { text = "MIT" }` under `[project]`.

### 5. Verification & Tests
- Create `tests/test_p0_invariants.py` that explicitly tests:
  1. `test_missing_evidence_denied`: inserting an entry with no evaluation bundle or admission result is not admitted to elites/reservoir.
  2. `test_mismatched_candidate_evidence_denied`: evaluation bundle targeted for candidate A is rejected when inserted with candidate B.
  3. `test_fatal_override_forged_accepted`: fatal playtest issues override forged `ACCEPTED` status and route to repair incubator.
  4. `test_atomic_insertion_rollback_on_exception`: monkeypatching `dominates` to raise `RuntimeError` leaves archive snapshot completely unchanged, and immediate retry succeeds.
  5. `test_unicode_normalization_and_pipe_escaping`: fullwidth `ＡＢＣ` == `ABC`, combining `Cafe\u0301` == `Café`, and unescaped pipe strings don't collide.
  6. `test_dry_run_zero_network_calls`: `--dry-run` with `--provider llm` executes without attempting network sockets.
- Run `.venv/bin/pytest` to ensure all 34 existing tests + all new tests pass 100%.
