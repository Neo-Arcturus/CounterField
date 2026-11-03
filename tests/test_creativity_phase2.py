import pytest

from creative_agent import MockIdeaProvider
from creative_agent.creativity import (
    DefaultInvariantMiner, InvariantClaim, InvariantMiner, InversionContext, InversionLineageVerifier,
    InversionOperator, InversionVerifier, POLARITY_FLIP, ArchiveView, OperatorContext, grounded_claims,
)
from creative_agent.archive import QDArchive
from creative_agent.harness import IdeationHarness
from creative_agent.models import (
    CanonicalMechanism, CausalLink, CreativeLineage, HarnessConfig, IdeaCandidate, InversionEvidence,
)

CFG = HarnessConfig(generations=1, population_size=1, total_budget=1)

def mech(links, payoff="reward"):
    return CanonicalMechanism(
        core_mechanism="c", affected_system="s", payoff=payoff,
        causal_structure=tuple(CausalLink(cause=a, relation=r, effect=b) for a, r, b in links))

def cand(m, ev):
    return IdeaCandidate(id="c1", problem_id="p", title="t", description="d", mechanism=m,
                         lineage=CreativeLineage(operator="inversion", evidence=ev))

def claim(rel="increases", cause="effort", effect="skill", quote="effort increases skill"):
    return InvariantClaim.build(f"{cause} {rel} {effect}", cause, rel, effect, quote)

def ev(claims, idx):
    return InversionEvidence(claim_id="+".join(c.id for c in claims), bound_link_indices=tuple(idx),
                             flipped_polarity=True)

def setup(prompt="p"):
    h = IdeationHarness(MockIdeaProvider())
    problem = h.adapter.normalize_problem(prompt)
    return problem, h.adapter.mine_baselines(problem)

GOOD = [("effort", "decreases", "skill"), ("skill", "enables", "reward"),
        ("effort", "enables", "coach"), ("coach", "enables", "reward")]

def test_claim_without_prompt_evidence_quote_dropped():
    for prompt, quote in (("Better teams: effort increases skill", "Effort  INCREASES skill"),
                          ("노력이 실력을 높인다 라는 통념", "노력이 실력을 높인다")):
        problem, base = setup(prompt)
        good, bad = claim(quote=quote), claim(quote="grit multiplies luck")
        kept = grounded_claims([good, bad], problem, base)
        assert kept == (good,)
        class Seeded:
            def mine(self, p, b):
                return grounded_claims([good, bad], p, b)
        assert isinstance(Seeded(), InvariantMiner)
        assert DefaultInvariantMiner(seeds=[good, bad]).mine(problem, base)[:1] == (good,)
        assert bad not in DefaultInvariantMiner(seeds=[bad]).mine(problem, base)

@pytest.mark.parametrize("rel", ["increases", "decreases", "enables", "prevents"])
def test_polarity_flip_detected(rel):
    c = claim(rel)
    flipped = CausalLink(cause="effort", relation=POLARITY_FLIP[rel], effect="skill")
    same = CausalLink(cause="effort", relation=rel, effect="skill")
    assert POLARITY_FLIP[POLARITY_FLIP[rel]] == rel
    assert InversionVerifier.is_polarity_flip(c, flipped)
    assert not InversionVerifier.is_polarity_flip(c, same)
    dep = claim("depends_on")
    assert InversionVerifier.is_polarity_flip(dep, CausalLink(cause="skill", relation="depends_on", effect="effort"))
    assert not InversionVerifier.is_polarity_flip(dep, CausalLink(cause="effort", relation="depends_on", effect="skill"))

def test_inversion_without_buffer_path_unverified_or_fatal():
    c = claim()
    v = InversionVerifier()
    assert v.verify(cand(mech(GOOD), ev([c], [0])), ev([c], [0]), [c]) == ()
    bare = mech(GOOD[:2])  # flipped link is the only route from effort
    reasons = v.verify(cand(bare, ev([c], [0])), ev([c], [0]), [c])
    assert any("buffer" in r for r in reasons)
    dead = mech([("effort", "decreases", "skill"), ("effort", "enables", "reward")])
    assert any("cannot reach payoff" in r for r in v.verify(cand(dead, ev([c], [0])), ev([c], [0]), [c]))

def test_unbound_link_indices_unverified():
    c = claim()
    v = InversionVerifier()
    for idx in ([9], [-1], [1], [], [0, 0]):
        e = ev([c], idx)
        assert v.verify(cand(mech(GOOD), e), e, [c]), idx

def _ctx(archive, slot=0):
    problem, base = setup("effort increases skill. coach enables reward.")
    return OperatorContext(problem=problem, parents=(), baselines=base, archive=ArchiveView(archive),
                           slot=slot, rng_seed=slot)

def test_inversion_curriculum_single_then_double():
    seeds = [claim(), claim("enables", "coach", "reward", "coach enables reward")]
    op = InversionOperator(DefaultInvariantMiner(seeds=seeds))
    ctx = _ctx(QDArchive())
    first = op.propose(ctx)[0]
    assert len(first.lineage.evidence.bound_link_indices) == 1
    op.record_credit(first)
    second = op.propose(ctx)[0]
    assert len(second.lineage.evidence.bound_link_indices) == 2
    assert InversionLineageVerifier().verify(second, InversionContext(tuple(op.claims.values()))).verified

def test_unverified_inversion_gets_no_scheduler_reward():
    c = claim()
    bad = cand(mech(GOOD[:2]), ev([c], [0]))
    verdict = InversionLineageVerifier().verify(bad, InversionContext((c,)))
    assert verdict.verified is False and verdict.credit_awarded is False
    none = InversionLineageVerifier().verify(bad.model_copy(update={"lineage": None}), InversionContext((c,)))
    assert none.credit_awarded is False

def test_inversion_end_to_end_in_harness():
    op = InversionOperator(DefaultInvariantMiner())
    h = IdeationHarness(MockIdeaProvider(), operators=[op])
    result = h.run("Why does it fail? effort increases skill", CFG)
    assert result.metrics["inversion_attempts"] >= 1
    assert result.metrics["inversion_successes"] >= 1
    assert any(isinstance(e.candidate.lineage.evidence, InversionEvidence) for e in result.frontier)
