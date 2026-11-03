# CounterField Modular Architecture: 3-Contract Abstraction

## Objective
Refactor `CounterField` (`creative-agent`) so that domain-specific logic is cleanly decoupled from the core QD search and archiving engine through 3 modular protocols/contracts:
1. `DomainAdapter`: Translates domain prompts/goals into normalized problems, generates candidates, canonicalizes mechanisms, and mines baseline cliches.
2. `VerificationOracle`: Validates candidate causal/structural invariants, runs domain simulations/adversarial playtests, and yields typed `EvaluationBundle`s.
3. `BehaviorExtractor`: Projects candidates into multi-dimensional niche/behavioral space (`NicheDescriptor` + `DynamicalNicheDescriptor`).

Backwards compatibility MUST be 100% preserved so existing CLI, harnesses, and all 40 existing tests continue to pass without modification.

---

## Detailed Specifications

### 1. `creative_agent/contracts.py` (New Module)
Define Python `typing.Protocol` (or ABC) interfaces and default bridge implementations:

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class DomainAdapter(Protocol):
    def normalize_problem(self, problem: str) -> NormalizedProblem: ...
    def generate_candidates(self, problem: NormalizedProblem, operator: str, context: tuple[IdeaCandidate, ...], count: int) -> list[IdeaCandidate]: ...
    def canonicalize_mechanism(self, problem: NormalizedProblem, candidate: IdeaCandidate) -> IdeaCandidate: ...
    def mine_baselines(self, problem: NormalizedProblem) -> NegativeArchive: ...

@runtime_checkable
class VerificationOracle(Protocol):
    def validate_structure(self, candidate: IdeaCandidate) -> ValidationReport: ...
    def evaluate(self, problem: NormalizedProblem, candidate: IdeaCandidate, baselines: NegativeArchive, thresholds: tuple[float, float]) -> EvaluationBundle: ...

@runtime_checkable
class BehaviorExtractor(Protocol):
    def extract_niche(self, problem: NormalizedProblem, candidate: IdeaCandidate) -> NicheDescriptor: ...
    def extract_dynamics(self, candidate: IdeaCandidate) -> DynamicalNicheDescriptor | None: ...
```

Provide standard default implementations that wrap existing components:
- `DefaultDomainAdapter(provider: IdeaProvider)`
- `DefaultVerificationOracle(evaluator: ThreeLayerEvaluator)` (or provider + embeddings)
- `DefaultBehaviorExtractor(provider: IdeaProvider)`

Export these classes from `creative_agent/__init__.py`.

### 2. `creative_agent/harness.py` Refactoring
Update `IdeationHarness.__init__`:
```python
def __init__(
    self,
    adapter: DomainAdapter | IdeaProvider,
    oracle: VerificationOracle | None = None,
    extractor: BehaviorExtractor | None = None,
    embeddings = None,
):
```
- If `adapter` is an `IdeaProvider` (or legacy constructor call `IdeationHarness(provider, embeddings)`):
  - Automatically wrap with `DefaultDomainAdapter(adapter)`
  - Automatically construct `DefaultVerificationOracle` using `ThreeLayerEvaluator(adapter, embeddings)`
  - Automatically construct `DefaultBehaviorExtractor(adapter)`
- If explicit `adapter: DomainAdapter`, `oracle: VerificationOracle`, `extractor: BehaviorExtractor` are provided, use them directly.
- In `run()`, orchestrate generation through `self.adapter`, validation and evaluation through `self.oracle`, and descriptor extraction through `self.extractor`.

### 3. Tests & Verification
Create `tests/test_modular_contracts.py` covering:
1. `test_default_contracts_wire_cleanly`: Proves `IdeationHarness(provider)` works with default contract wrappers.
2. `test_custom_domain_adapter`: A custom stub `DomainAdapter` plugging custom candidate generation into `IdeationHarness`.
3. `test_custom_verification_oracle`: A custom `VerificationOracle` that rejects candidates violating custom rules and verifies `repair_incubator` / `failure_archive` routing.
4. `test_custom_behavior_extractor`: A custom `BehaviorExtractor` overriding niche assignment.
5. Ensure all 40 existing tests pass untouched.

Run `.venv/bin/pytest` and verify that all 40 pre-existing tests + all new modular tests pass 100%.
