import socket
import urllib.request

import pytest

import creative_agent.archive as archive_module
from creative_agent import (
    AdmissionResult,
    AdmissionStage,
    AdmissionStatus,
    AdversarialPlaytester,
    BaselineClicheMiner,
    CanonicalMechanism,
    CausalLink,
    EvaluationDiagnostics,
    MockIdeaProvider,
    NicheDescriptor,
    ProblemNormalizer,
    QDArchive,
    QDArchiveEntry,
    ThreeLayerEvaluator,
)
from creative_agent.cli import main
from creative_agent.models import clean
from tests.test_architecture_enhancements import _spam_program

NICHE = NicheDescriptor(
    intervention_level="individual", resource_intensity="low", feedback_horizon="immediate"
)
ACCEPTED = AdmissionResult(status=AdmissionStatus.ACCEPTED, stage=AdmissionStage.COMPLETE, reasons=())


def _candidate(operator="Removal"):
    provider = MockIdeaProvider()
    problem = ProblemNormalizer(provider).normalize("p0 invariants")
    candidate = provider.canonicalize(problem, provider.generate(problem, operator, (), 1)[0])
    return provider, problem, candidate


def _entry(candidate, provider, problem, **kwargs):
    return QDArchiveEntry(
        candidate=candidate,
        niche=NICHE,
        scores=provider.assess(problem, candidate),
        diagnostics=EvaluationDiagnostics(),
        **kwargs,
    )


def _snapshot(a):
    return (
        a.attempts, a.valid, a.duplicates, dict(a.niche_attempts), list(a.admission_log),
        set(a.seen_ids), set(a.seen_mechanisms), list(a.reservoir), dict(a.elites),
        list(a.repair_incubator), list(a.failure_archive),
    )


def test_missing_evidence_denied():
    provider, problem, cand = _candidate()
    archive = QDArchive()
    assert archive.insert(_entry(cand, provider, problem)) is False
    assert archive.elites == {} and archive.reservoir == []
    assert archive.valid == 0
    assert len(archive.failure_archive) == 1
    assert archive.admission_log[0][1].status == AdmissionStatus.REJECTED


def test_mismatched_candidate_evidence_denied():
    provider, problem, cand_a = _candidate("Removal")
    _, _, cand_b = _candidate("Role shift")
    assert cand_a.id != cand_b.id
    bundle = ThreeLayerEvaluator(provider).evaluate(problem, cand_a, BaselineClicheMiner(provider).mine(problem))
    bundle = bundle.model_copy(update={
        "candidate_id": cand_a.id,
        "candidate_fingerprint": cand_a.mechanism.fingerprint,
    })
    entry_b = _entry(cand_b, provider, problem)
    archive = QDArchive()
    assert archive.insert(entry_b, admission=bundle) is False
    assert archive.elites == {} and archive.reservoir == []
    assert archive.admission_log[0][1].status == AdmissionStatus.REJECTED

    with pytest.raises(ValueError):
        _entry(cand_b, provider, problem, evaluation=bundle)


def test_fatal_override_forged_accepted():
    provider, problem, cand = _candidate()
    report = AdversarialPlaytester(chaos_episodes=8).run_playtest(_spam_program())
    entry = QDArchiveEntry(
        candidate=cand, niche=NICHE, scores=provider.assess(problem, cand),
        diagnostics=EvaluationDiagnostics(playtest_report=report),
    )
    archive = QDArchive()
    assert archive.insert(entry, admission=ACCEPTED) is False
    assert archive.elites == {} and archive.reservoir == []
    assert archive.repair_incubator == [entry]
    assert archive.admission_log[0][1].stage == AdmissionStage.RED_TEAM


def test_atomic_insertion_rollback_on_exception(monkeypatch):
    provider, problem, cand_a = _candidate("Removal")
    _, _, cand_b = _candidate("Role shift")
    archive = QDArchive()
    assert archive.insert(_entry(cand_a, provider, problem), admission=ACCEPTED) is True
    before = _snapshot(archive)

    entry_b = _entry(cand_b, provider, problem)
    real = archive_module.dominates

    def boom(*a, **k):
        raise RuntimeError("fault")

    monkeypatch.setattr(archive_module, "dominates", boom)
    with pytest.raises(RuntimeError):
        archive.insert(entry_b, admission=ACCEPTED)
    assert _snapshot(archive) == before

    monkeypatch.setattr(archive_module, "dominates", real)
    assert archive.insert(entry_b, admission=ACCEPTED) is True
    assert archive.duplicates == 0 and archive.valid == 2


def test_unicode_normalization_and_pipe_escaping():
    assert clean("ＡＢＣ") == clean("ABC") == "ABC"
    assert clean("Café") == clean("Café")

    def fp(links):
        return CanonicalMechanism(
            core_mechanism="m", affected_system="s", payoff="p", causal_structure=links
        ).fingerprint

    one = (CausalLink(cause="a|enables|b", relation="enables", effect="c"),)
    two = (CausalLink(cause="a", relation="enables", effect="b|enables|c"),)
    assert fp(one) != fp(two)


def test_dry_run_zero_network_calls(monkeypatch, capsys):
    calls = []

    def deny(*a, **k):
        calls.append(a)
        raise AssertionError("network attempted")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)
    assert main(["--sample", "game-mechanics", "--provider", "llm", "--dry-run"]) == 0
    assert calls == []
