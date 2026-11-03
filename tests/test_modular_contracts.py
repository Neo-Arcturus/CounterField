from creative_agent import (
    AdmissionResult,
    AdmissionStage,
    AdmissionStatus,
    BehaviorExtractor,
    DefaultBehaviorExtractor,
    DefaultDomainAdapter,
    DefaultVerificationOracle,
    DomainAdapter,
    MockIdeaProvider,
    NicheDescriptor,
    ThreeLayerEvaluator,
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
    VerificationOracle,
)
from creative_agent.harness import IdeationHarness
from creative_agent.models import HarnessConfig

CFG = HarnessConfig(generations=2, population_size=3, total_budget=6)
PROBLEM = "Reduce handoff errors between teams"


class CountingAdapter(DefaultDomainAdapter):
    def __init__(self, provider):
        super().__init__(provider)
        self.generated = 0

    def generate_candidates(self, problem, operator, context, count):
        self.generated += 1
        return super().generate_candidates(problem, operator, context, count)


def test_default_contracts_wire_cleanly():
    provider = MockIdeaProvider()
    harness = IdeationHarness(provider)
    assert isinstance(harness.adapter, DomainAdapter)
    assert isinstance(harness.oracle, VerificationOracle)
    assert isinstance(harness.extractor, BehaviorExtractor)
    result = harness.run(PROBLEM, CFG)
    assert result.status == "COMPLETED"
    assert result.metrics["attempts"] == 6
    assert len(result.selected) > 0


def test_custom_domain_adapter():
    provider = MockIdeaProvider()
    adapter = CountingAdapter(provider)
    harness = IdeationHarness(
        adapter,
        DefaultVerificationOracle(ThreeLayerEvaluator(provider)),
        DefaultBehaviorExtractor(provider),
    )
    result = harness.run(PROBLEM, CFG)
    assert harness.adapter is adapter
    assert adapter.generated == 6
    assert result.metrics["attempts"] == 6


def test_custom_verification_oracle():
    provider = MockIdeaProvider()
    base = DefaultVerificationOracle(ThreeLayerEvaluator(provider))

    class RejectingOracle:
        def __init__(self):
            self.calls = 0

        def validate_structure(self, candidate):
            self.calls += 1
            if self.calls % 2 == 0:
                return ValidationReport(
                    is_valid=False,
                    issues=(ValidationIssue(severity=ValidationSeverity.FATAL, rule="custom", message="custom rule violated"),),
                )
            return base.validate_structure(candidate)

        def evaluate(self, problem, candidate, baselines, thresholds):
            bundle = base.evaluate(problem, candidate, baselines, thresholds)
            return bundle.model_copy(update={
                "admission": AdmissionResult(
                    status=AdmissionStatus.REPAIRABLE,
                    stage=AdmissionStage.QUALITY_CONSTRAINTS,
                    reasons=("custom quality rule",),
                )
            })

    oracle = RejectingOracle()
    result = IdeationHarness(DefaultDomainAdapter(provider), oracle, DefaultBehaviorExtractor(provider)).run(PROBLEM, CFG)
    assert result.metrics["structural_failures"] == 3
    assert result.metrics["repair_incubator"] + result.metrics["failure_archive"] > 0
    assert result.metrics["occupied_niches"] == 0
    assert result.selected == ()


def test_custom_behavior_extractor():
    provider = MockIdeaProvider()
    fixed = NicheDescriptor(intervention_level="team", resource_intensity="low", feedback_horizon="immediate")

    class FixedExtractor(DefaultBehaviorExtractor):
        def extract_niche(self, problem, candidate):
            return fixed

    result = IdeationHarness(provider, extractor=FixedExtractor(provider)).run(PROBLEM, CFG)
    assert result.metrics["occupied_niches"] <= 1
    assert all(e.niche == fixed for e in result.selected)
