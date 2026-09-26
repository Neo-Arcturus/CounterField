import pytest

from creative_agent.models import CanonicalMechanism, CausalLink, ValidationSeverity
from creative_agent.evaluator import ThreeLayerEvaluator
from creative_agent.normalizer import BaselineClicheMiner, ProblemNormalizer
from creative_agent.providers import MockIdeaProvider
from creative_agent.verifier import CausalGraphValidator, StructuralValidationError


def mechanism(*links, payoff="player mastery"):
    return CanonicalMechanism(
        core_mechanism="A testable causal mechanism",
        causal_structure=tuple(CausalLink(cause=a, relation=r, effect=b) for a, r, b in links),
        affected_system="test system",
        payoff=payoff,
    )


def rules(report, severity=None):
    return {
        issue.rule for issue in report.issues
        if severity is None or issue.severity == severity
    }


def test_valid_graph_with_productive_feedback_loop_passes():
    candidate = mechanism(
        ("player action", "enables", "system response"),
        ("system response", "increases", "feedback strength"),
        ("feedback strength", "increases", "system response"),
        ("feedback strength", "enables", "player mastery"),
    )

    report = CausalGraphValidator().validate(candidate)

    assert report.is_valid
    assert not report.issues


def test_unreachable_payoff_is_fatal():
    candidate = mechanism(
        ("player action", "enables", "system response"),
        payoff="unconnected payoff",
    )

    report = CausalGraphValidator().validate(candidate)

    assert not report.is_valid
    assert "payoff_reachability" in rules(report, ValidationSeverity.FATAL)
    issue = next(i for i in report.issues if i.rule == "payoff_reachability")
    assert issue.witness_path == ("player action", "system response")


def test_orphan_disconnected_intervention_warns():
    candidate = mechanism(
        ("player action", "enables", "player mastery"),
        ("unused lever", "enables", "decorative response"),
    )

    report = CausalGraphValidator().validate(candidate)

    assert report.is_valid
    assert "orphan_nodes" in rules(report, ValidationSeverity.WARNING)
    issue = next(i for i in report.issues if i.rule == "orphan_nodes")
    assert set(issue.involved_nodes) == {"unused lever", "decorative response"}


@pytest.mark.parametrize(
    "first, second",
    [("increases", "decreases"), ("enables", "prevents")],
)
def test_contradictory_links_are_fatal(first, second):
    candidate = mechanism(
        ("player action", first, "player mastery"),
        ("player action", second, "player mastery"),
    )

    report = CausalGraphValidator().validate(candidate)

    assert not report.is_valid
    assert "contradictory_links" in rules(report, ValidationSeverity.FATAL)


def test_terminal_free_cycle_trap_is_fatal():
    candidate = mechanism(
        ("player action", "enables", "locked state"),
        ("locked state", "enables", "waiting state"),
        ("waiting state", "enables", "locked state"),
    )

    report = CausalGraphValidator().validate(candidate)

    assert not report.is_valid
    assert "terminal_free_cycle" in rules(report, ValidationSeverity.FATAL)
    cycle = next(i for i in report.issues if i.rule == "terminal_free_cycle")
    assert cycle.witness_path[0] == cycle.witness_path[-1]


def test_evaluator_rejects_invalid_structure_before_quality_scoring(monkeypatch):
    provider = MockIdeaProvider()
    problem = ProblemNormalizer(provider).normalize("Test the validity gate")
    negative = BaselineClicheMiner(provider).mine(problem)
    candidate = provider.generate(problem, "Inversion", (), 1)[0].model_copy(update={
        "mechanism": mechanism(
            ("player action", "enables", "dead end"),
            payoff="unreachable payoff",
        )
    })

    def unexpected_assessment(*args, **kwargs):
        pytest.fail("quality scoring must not run for a structurally invalid candidate")

    monkeypatch.setattr(provider, "assess", unexpected_assessment)

    with pytest.raises(StructuralValidationError) as raised:
        ThreeLayerEvaluator(provider).evaluate(problem, candidate, negative)

    assert "payoff_reachability" in rules(raised.value.report, ValidationSeverity.FATAL)
