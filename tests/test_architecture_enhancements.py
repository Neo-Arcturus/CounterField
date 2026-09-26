import pytest
from pydantic import ValidationError

from creative_agent import (
    AdmissionStage,
    AdmissionStatus,
    AdversarialPlaytester,
    CanonicalMechanism,
    CausalLink,
    CEGISRepairEngine,
    DSLAction,
    DSLProgram,
    EvaluationBundle,
    EvaluationDiagnostics,
    EvaluationScores,
    GuardCondition,
    IdeaCandidate,
    NicheDescriptor,
    QDArchive,
    QDArchiveEntry,
    StateEffect,
    StateVariable,
    TerminalCondition,
    canonical_mechanism_to_dsl,
    compile_semantic_ir,
    counterexamples_from_report,
    dynamical_niche_descriptor,
    mechanism_to_semantic_ir,
    replay_counterexample,
    verify_compilation_invariants,
)
from creative_agent.evaluator import ThreeLayerEvaluator
from creative_agent.normalizer import BaselineClicheMiner, ProblemNormalizer
from creative_agent.providers import HashEmbeddingProvider, MockIdeaProvider


def _mechanism(*links, payoff="reward"):
    return CanonicalMechanism(
        core_mechanism="Typed causal mechanism",
        causal_structure=tuple(
            CausalLink(cause=cause, relation=relation, effect=effect)
            for cause, relation, effect in links
        ),
        affected_system="test system",
        payoff=payoff,
    )


def _spam_program():
    return DSLProgram(
        states={
            "score": StateVariable(
                name="score", var_type="int", initial_value=0, min_val=0, max_val=4
            )
        },
        actions=(DSLAction(
            name="tap",
            actor="player",
            guards=(GuardCondition(var_name="score", op="lt", value=4),),
            effects=(StateEffect(var_name="score", op="add", value=1),),
        ),),
        terminal_conditions=(TerminalCondition(
            outcome="win",
            guards=(GuardCondition(var_name="score", op="gte", value=4),),
        ),),
        max_steps=8,
    )


def test_semantic_ir_groups_edges_and_compiles_dependencies_as_guards():
    mechanism = _mechanism(
        ("key", "enables", "reward"),
        ("hazard", "prevents", "reward"),
    )

    ir = mechanism_to_semantic_ir(mechanism)
    program = compile_semantic_ir(ir)

    assert len(ir.actions) == 1
    assert len(program.actions) == 1
    guards = {
        (guard.var_name, guard.op, guard.value) for guard in program.actions[0].guards
    }
    assert ("key", "eq", True) in guards
    assert ("hazard", "eq", False) in guards
    assert verify_compilation_invariants(ir, program).is_valid

    bypass = program.actions[0].model_copy(update={"guards": ()})
    tampered = program.model_copy(update={"actions": (bypass,)})
    report = verify_compilation_invariants(ir, tampered)
    assert not report.is_valid
    assert any("dependency" in violation for violation in report.violations)


def test_case_variants_share_one_semantic_proposition():
    mechanism = _mechanism(
        ("input", "enables", "System Response"),
        ("system response", "depends_on", "reward"),
    )

    ir = mechanism_to_semantic_ir(mechanism)
    program = canonical_mechanism_to_dsl(mechanism)

    assert len(ir.propositions) == 3
    assert len(program.actions) == 2


def test_evaluator_returns_immutable_typed_bundle_with_legacy_unpacking():
    provider = MockIdeaProvider()
    problem = ProblemNormalizer(provider).normalize("typed evaluation")
    negative = BaselineClicheMiner(provider).mine(problem)
    candidate = provider.generate(problem, "Inversion", (), 1)[0]

    bundle = ThreeLayerEvaluator(provider, HashEmbeddingProvider()).evaluate(
        problem, candidate, negative
    )
    scores, diagnostics, feasible = bundle

    assert isinstance(bundle, EvaluationBundle)
    assert scores == bundle.scores
    assert diagnostics == bundle.diagnostics
    assert feasible is True
    assert bundle.admission.status == AdmissionStatus.ACCEPTED
    with pytest.raises(ValidationError):
        bundle.admission = bundle.admission


def test_evaluation_failure_is_typed_invalid_evaluation(monkeypatch):
    provider = MockIdeaProvider()
    problem = ProblemNormalizer(provider).normalize("invalid evaluation")
    negative = BaselineClicheMiner(provider).mine(problem)
    candidate = provider.generate(problem, "Removal", (), 1)[0]

    monkeypatch.setattr(provider, "assess", lambda *_: (_ for _ in ()).throw(RuntimeError("offline")))
    bundle = ThreeLayerEvaluator(provider).evaluate(problem, candidate, negative)

    assert bundle.scores is None
    assert bundle.admission.status == AdmissionStatus.INVALID_EVALUATION
    assert bundle.admission.stage == AdmissionStage.EVALUATION_INTEGRITY


def test_evaluator_promotes_fatal_playtest_to_hard_admission_decision():
    provider = MockIdeaProvider()
    problem = ProblemNormalizer(provider).normalize("red-team gate")
    negative = BaselineClicheMiner(provider).mine(problem)
    generated = provider.generate(problem, "Removal", (), 1)[0]
    candidate = generated.model_copy(update={
        "mechanism": _mechanism(("active hazard", "prevents", "reward")),
    })

    bundle = ThreeLayerEvaluator(provider).evaluate(problem, candidate, negative)

    assert bundle.diagnostics.playtest_report is not None
    assert any(
        issue.severity == "FATAL"
        for issue in bundle.diagnostics.playtest_report.issues
    )
    assert bundle.admission.status == AdmissionStatus.REPAIRABLE
    assert bundle.admission.stage == AdmissionStage.RED_TEAM
    assert bundle.admission.route == "repair_incubator"


def test_fatal_playtest_cannot_enter_production_even_with_forged_feasible_flag():
    provider = MockIdeaProvider()
    problem = ProblemNormalizer(provider).normalize("hard gate")
    candidate = provider.canonicalize(
        problem, provider.generate(problem, "Role shift", (), 1)[0]
    )
    report = AdversarialPlaytester(chaos_episodes=8).run_playtest(_spam_program())
    scores = provider.assess(problem, candidate)
    entry = QDArchiveEntry(
        candidate=candidate,
        niche=NicheDescriptor(
            intervention_level="individual",
            resource_intensity="low",
            feedback_horizon="immediate",
        ),
        scores=scores,
        diagnostics=EvaluationDiagnostics(playtest_report=report),
    )

    archive = QDArchive()
    assert archive.insert(entry, feasible=True) is False
    assert archive.elites == {}
    assert archive.repair_incubator == [entry]


def test_cegis_repair_eliminates_and_replays_spam_counterexample():
    program = _spam_program()
    report = AdversarialPlaytester(chaos_episodes=8).run_playtest(program)
    counterexample = counterexamples_from_report(report, program)[0]
    assert replay_counterexample(program, counterexample).reproduced

    result = CEGISRepairEngine(chaos_episodes=8).heal(
        program, (counterexample,)
    )

    assert result.healed
    assert result.steps[0].operator.value == "split_transition"
    assert not replay_counterexample(result.program, counterexample).reproduced
    assert result.playtest_report.is_passed


def test_dynamical_descriptor_is_separate_from_quality_dimensions():
    mechanism = _mechanism(
        ("a", "enables", "b"),
        ("b", "enables", "c"),
        ("b", "enables", "d"),
        ("d", "enables", "b"),
        ("c", "enables", "reward"),
    )

    descriptor = dynamical_niche_descriptor(mechanism)

    assert descriptor.causal_depth == 3
    assert descriptor.branching_factor == 1.0
    assert descriptor.loop_density == 0.4
    assert descriptor.payoff_path_length == 3
    assert not hasattr(descriptor, "novelty")
