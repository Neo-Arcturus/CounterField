import pytest
from creative_agent.models import (
    CausalLink,
    CanonicalMechanism,
    IdeaCandidate,
    NicheDescriptor,
    EvaluationScores,
    NormalizedProblem,
    NegativeArchive,
    HarnessConfig,
)
from creative_agent.providers import MockIdeaProvider, HashEmbeddingProvider
from creative_agent.normalizer import ProblemNormalizer, BaselineClicheMiner
from creative_agent.evaluator import ThreeLayerEvaluator
from creative_agent.archive import QDArchive, dominates
from creative_agent.harness import IdeationHarness


def test_models_and_fingerprint():
    link1 = CausalLink(cause="Player action", relation="increases", effect="boss resistance")
    link2 = CausalLink(cause="Environment pulse", relation="enables", effect="vulnerability window")
    mech = CanonicalMechanism(
        core_mechanism="Adaptive environmental shift",
        causal_structure=(link1, link2),
        affected_system="boss combat loop",
        payoff="dynamic tactical diversity",
    )
    assert len(mech.fingerprint) == 16
    assert mech.core_mechanism == "Adaptive environmental shift"


def test_niche_descriptor():
    nd = NicheDescriptor(
        intervention_level="team",
        resource_intensity="medium",
        feedback_horizon="short",
    )
    assert nd.key == "team:medium:short"


def test_dominance_logic():
    a = EvaluationScores(
        novelty=0.8, appropriateness=0.8, utility=0.8,
        surprise=0.7, coherence=0.9, mechanism_uniqueness=0.9
    )
    b = EvaluationScores(
        novelty=0.6, appropriateness=0.8, utility=0.7,
        surprise=0.5, coherence=0.8, mechanism_uniqueness=0.7
    )
    assert dominates(a, b)
    assert not dominates(b, a)


def test_normalizer_and_negative_archive():
    provider = MockIdeaProvider()
    normalizer = ProblemNormalizer(provider)
    prob = normalizer.normalize("Design a stealth puzzle without vision cones")
    assert prob.id
    assert prob.objective

    miner = BaselineClicheMiner(provider)
    neg_archive = miner.mine(prob)
    assert len(neg_archive.baselines) > 0
    assert len(neg_archive.mechanisms) > 0


def test_three_layer_evaluator():
    provider = MockIdeaProvider()
    embeddings = HashEmbeddingProvider()
    normalizer = ProblemNormalizer(provider)
    miner = BaselineClicheMiner(provider)

    prob = normalizer.normalize("Create a dialogue system without branching trees")
    neg = miner.mine(prob)

    evaluator = ThreeLayerEvaluator(provider, embeddings)
    candidate = provider.generate(prob, "Inversion", (), 1)[0]
    scores, diag, feasible = evaluator.evaluate(prob, candidate, neg)

    assert 0.0 <= scores.novelty <= 1.0
    assert 0.0 <= diag.lexical_similarity <= 1.0
    assert 0.0 <= diag.embedding_similarity <= 1.0
    assert 0.0 <= diag.structural_similarity <= 1.0
    assert feasible is True


def test_qd_archive():
    archive = QDArchive()
    provider = MockIdeaProvider()
    prob = ProblemNormalizer(provider).normalize("A new game puzzle")
    cand = provider.canonicalize(prob, provider.generate(prob, "Removal", (), 1)[0])
    niche = provider.describe_niche(prob, cand)
    scores = provider.assess(prob, cand)
    from creative_agent.models import EvaluationDiagnostics, QDArchiveEntry

    entry = QDArchiveEntry(
        candidate=cand,
        niche=niche,
        scores=scores,
        diagnostics=EvaluationDiagnostics(),
        insertion_generation=0,
    )
    inserted = archive.insert(entry, feasible=True, blacklisted=False)
    assert inserted is True
    assert archive.attempts == 1
    assert archive.valid == 1
    assert len(archive.elites) == 1


def test_harness_end_to_end():
    provider = MockIdeaProvider()
    embeddings = HashEmbeddingProvider()
    harness = IdeationHarness(provider, embeddings)

    cfg = HarnessConfig(generations=2, population_size=4, total_budget=8)
    res = harness.run("Redesign file transfer without centralized storage", cfg)

    assert res.status == "COMPLETED"
    assert res.termination_reason == "budget exhausted"
    assert res.metrics["attempts"] == 8
    assert len(res.selected) > 0
