import pytest

from creative_agent import MockIdeaProvider
from creative_agent import archive as archive_module
from creative_agent.creativity import (
    CEGISGuidedSynthesizer, DialecticContext, DialecticalSynthesizer, DialecticLineageVerifier,
    LineageVerifier, RuleLibrary, SynthesisProposal, SynthesisVerifier,
)
from creative_agent.creativity.dialectic import counterexample_hash
from creative_agent.dsl import canonical_mechanism_to_dsl
from creative_agent.harness import MAX_SYNTHESIS_DEPTH, IdeationHarness
from creative_agent.models import (
    AdmissionStage, AdmissionStatus, CanonicalMechanism, CausalLink, CreativeLineage, DialecticEvidence,
    HarnessConfig, QDArchiveEntry, stable_id,
)
from creative_agent.dsl import simulate_program
from creative_agent.models import Counterexample
from creative_agent.redteam import AdversarialPlaytester, counterexamples_from_report, replay_counterexample

CFG = HarnessConfig(generations=1, population_size=1, total_budget=1)

def mech(links, payoff="reward"):
    return CanonicalMechanism(
        core_mechanism="c", affected_system="s", payoff=payoff,
        causal_structure=tuple(CausalLink(cause=a, relation=r, effect=b) for a, r, b in links),
    )

BASE = [
    ("effort", "enables", "skill"), ("skill", "enables", "reward"), ("cost", "enables", "paid"),
    ("paid", "enables", "reward"), ("reward", "increases", "effort"),
]
# FATAL: reachable_stuck_state via ('satisfy_paid',)
PARENT_M = mech(BASE)
# Fixes the stuck state while keeping the witness executable, adding a node, links and a loop.
GOOD_M = mech([("effort", "prevents", "skill"), *BASE[1:], ("paid", "enables", "ledger"), ("ledger", "enables", "reward")])
# Keeps the stuck state (witness still reproduces).
BAD_M = mech([*BASE, ("stipend", "enables", "effort"), ("stipend", "enables", "skill")])
# Fixes by pruning the guard: witness no longer executes.
PRUNED_M = mech([("effort", "enables", "skill"), ("skill", "enables", "reward"), ("cost", "enables", "paid"),
                 ("reward", "increases", "effort"), ("ledger", "enables", "paid"), ("paid", "increases", "ledger")])

def counterexample_for(mechanism):
    program = canonical_mechanism_to_dsl(mechanism)
    report = AdversarialPlaytester(chaos_episodes=8).run_playtest(program)
    return counterexamples_from_report(report, program)

class FixedProvider(MockIdeaProvider):
    """Every canonicalized candidate carries its own mechanism, or PARENT_M by default."""
    registry: dict = {}

    def canonicalize(self, problem, candidate):
        if candidate.mechanism:
            return candidate
        if candidate.operator == "baseline":  # keep baselines distinct from the parent (no blacklisting)
            return super().canonicalize(problem, candidate)
        return candidate.model_copy(update={"mechanism": PARENT_M})

class Scripted:
    def __init__(self, mechanisms, ops=("add_cost_node", "add_feedback_loop")):
        self.mechanisms, self.ops, self.calls = mechanisms, ops, 0

    def synthesize(self, entry, counterexamples, rule_library):
        self.calls += 1
        parent = entry.candidate
        out = []
        for ce in counterexamples:
            for i, m in enumerate(self.mechanisms):
                ev = DialecticEvidence(counterexample_hash=counterexample_hash(ce),
                                       parent_fingerprint=parent.mechanism.fingerprint, synthesis_ops=self.ops)
                child = parent.model_copy(update={
                    "id": stable_id(parent.id, "child", str(i), m.fingerprint), "mechanism": m,
                    "parent_id": parent.id, "operator": "dialectic",
                    "lineage": CreativeLineage(operator="dialectic", evidence=ev, parent_ids=(parent.id,)),
                })
                out.append(SynthesisProposal(child=child, counterexample=ce, ops=self.ops))
        return out

def parent_and_child(child_m):
    h = IdeationHarness(FixedProvider())
    problem = h.adapter.normalize_problem("p")
    cand = h.adapter.canonicalize_mechanism(problem, h.adapter.generate_candidates(problem, "Removal", (), 1)[0])
    ce = counterexample_for(PARENT_M)[0]
    syn = Scripted([child_m]).synthesize(
        QDArchiveEntry.model_construct(candidate=cand), (ce,), RuleLibrary())[0]
    return cand, syn.child, ce

def run_harness(**kw):
    h = IdeationHarness(FixedProvider(), **kw)
    return h, h.run("p", CFG)

def test_fatal_parent_never_enters_production():
    h, result = run_harness()
    assert result.metrics["repair_incubator"] == 1
    assert result.metrics["occupied_niches"] == 0 and result.frontier == ()
    h2, result2 = run_harness(synthesizer=Scripted([BAD_M]))
    assert all(e.candidate.parent_id is not None for e in result2.frontier)
    assert result2.metrics["occupied_niches"] == 0

def test_child_must_replay_clean_but_preserve_witness_prefix():
    verifier = SynthesisVerifier()
    parent, good, ce = parent_and_child(GOOD_M)
    assert verifier.check(parent, good, ce) == ()
    _, bad, _ = parent_and_child(BAD_M)
    assert any("still reproduces" in r for r in verifier.check(parent, bad, ce))
    _, pruned, _ = parent_and_child(PRUNED_M)
    assert any("not preserved" in r for r in verifier.check(parent, pruned, ce))

def test_cosmetic_synthesis_rejected():
    parent, _, ce = parent_and_child(GOOD_M)
    cosmetic = mech([("effort", "prevents", "skill"), *BASE[1:]])  # no new node, one changed link
    _, child, _ = parent_and_child(cosmetic)
    reasons = SynthesisVerifier().check(parent, child, ce)
    assert any("cosmetic" in r for r in reasons)
    verdict = DialecticLineageVerifier().verify(child, DialecticContext(parent, ce))
    assert verdict.verified is False and verdict.credit_awarded is False

def test_regression_corpus_replayed():
    parent, good, ce_a = parent_and_child(GOOD_M)
    verifier = SynthesisVerifier()
    assert verifier.check(parent, good, ce_a, corpus=[ce_a]) == ()
    # Counterexample B: a shortcut win that GOOD_M still permits (it fixes A but not B).
    program = canonical_mechanism_to_dsl(GOOD_M)
    trace = simulate_program(program, "payoff-seeking")
    assert trace.outcome == "win"
    ce_b = Counterexample(
        witness_actions=tuple(s.action for s in trace.trajectory), initial_state=ce_a.initial_state,
        violated_invariant="payoff_shortcut",
    )
    assert replay_counterexample(program, ce_b).reproduced
    reasons = verifier.check(parent, good, ce_a, corpus=[ce_a, ce_b])
    assert any("regression" in r for r in reasons)
    ctx = DialecticContext(parent, ce_a, corpus=[ce_b])
    assert DialecticLineageVerifier().verify(good, ctx).verified is False

def test_rule_promotion_requires_two_independent_successes():
    lib = RuleLibrary()
    assert lib.record_success("stuck", ("a",), "c1") is False
    assert lib.record_success("stuck", ("a",), "c1") is False
    assert lib.promoted_rules() == ()
    assert lib.record_success("stuck", ("a",), "c2") is True
    assert [r.candidate_ids for r in lib.promoted_rules()] == [("c1", "c2")]
    state = lib.snapshot()
    lib.record_success("other", ("b",), "c3")
    lib.restore(state)
    assert len(lib.promoted_rules()) == 1 and lib.snapshot() == state

def test_synthesis_budget_and_depth_cap():
    # Three proposals per counterexample, but only max_synthesis_per_entry=2 are attempted (G11).
    synth = Scripted([GOOD_M, BAD_M, PRUNED_M])
    _, result = run_harness(synthesizer=synth, max_synthesis_per_entry=2)
    assert 2 <= result.metrics["synthesis_attempts"] <= 2 * synth.calls
    one = Scripted([GOOD_M, BAD_M, PRUNED_M])
    _, capped = run_harness(synthesizer=one, max_synthesis_per_entry=1)
    assert 1 <= capped.metrics["synthesis_attempts"] <= one.calls
    _, none = run_harness(synthesizer=Scripted([GOOD_M]), max_synthesis_per_entry=0)
    assert none.metrics["synthesis_attempts"] == 0
    # A repairable child is re-synthesized at most MAX_SYNTHESIS_DEPTH levels deep, and a
    # counterexample hash is never synthesized twice (G12), so the chain terminates.
    _, chain = run_harness(synthesizer=Scripted([BAD_M]), max_synthesis_per_entry=2)
    assert chain.metrics["synthesis_attempts"] <= MAX_SYNTHESIS_DEPTH
    assert chain.metrics["synthesis_successes"] == 0
    assert chain.frontier == ()

def test_synthesis_atomic_rollback_on_insert_failure(monkeypatch):
    lib = RuleLibrary()
    h = IdeationHarness(FixedProvider(), synthesizer=Scripted([GOOD_M]), rule_library=lib)
    real = RuleLibrary.record_success

    def mutate_then_fail(self, *args):
        real(self, *args)
        raise RuntimeError("fault after rule mutation")

    monkeypatch.setattr(RuleLibrary, "record_success", mutate_then_fail)
    result = h.run("p", CFG)
    assert result.metrics["evidence_errors"] >= 1
    assert result.metrics["occupied_niches"] == 0 and result.frontier == ()
    assert result.metrics["synthesis_successes"] == 0
    assert lib._rules == {}  # child insert and rule update rolled back together

def test_repair_incubator_consumed_when_synthesizer_present_and_untouched_when_absent():
    synth = Scripted([GOOD_M])
    _, without = run_harness()
    assert without.metrics["synthesis_attempts"] == 0 and without.metrics["repair_incubator"] == 1
    assert without.frontier == ()
    h, with_ = run_harness(synthesizer=synth)
    assert synth.calls >= 1 and with_.metrics["synthesis_attempts"] >= 1

def test_dialectic_end_to_end_in_harness():
    lib = RuleLibrary()
    h, result = run_harness(synthesizer=Scripted([GOOD_M]), rule_library=lib)
    assert isinstance(h.synthesizer, DialecticalSynthesizer)
    assert all(isinstance(v, LineageVerifier) for v in h.evidence_verifiers)
    assert result.metrics["repair_incubator"] == 1  # the FATAL parent stays out
    assert result.metrics["synthesis_successes"] == 1
    assert len(result.frontier) == 1
    child = result.frontier[0].candidate
    assert child.parent_id and isinstance(child.lineage.evidence, DialecticEvidence)
    assert child.mechanism.fingerprint == GOOD_M.fingerprint
    assert lib.snapshot()[0]
    assert result.metrics["rules_promoted"] == 0
    # Default synthesizer satisfies the protocol too.
    assert isinstance(CEGISGuidedSynthesizer(), DialecticalSynthesizer)
