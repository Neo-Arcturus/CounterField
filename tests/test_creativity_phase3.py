from creative_agent import MockIdeaProvider
from creative_agent.creativity import (
    BlendOperator, CausalTemplate, IsomorphismContext, IsomorphismLineageVerifier, IsomorphismVerifier,
    MotifExtractor, MotifProfile, TemplateLibrary,
)
from creative_agent.harness import IdeationHarness
from creative_agent.models import (
    CanonicalMechanism, CausalLink, CreativeLineage, HarnessConfig, IdeaCandidate, IsomorphismEvidence,
    NegativeArchive,
)

def links(*specs):
    return tuple(CausalLink(cause=a, relation=r, effect=b) for a, r, b in specs)

def mech(specs, payoff="z"):
    return CanonicalMechanism(core_mechanism="c", affected_system="s", payoff=payoff, causal_structure=links(*specs))

def cand(m, ev):
    return IdeaCandidate(id="c1", problem_id="p", title="t", description="d", mechanism=m,
                         lineage=CreativeLineage(operator="isomorphism", evidence=ev))

TEMPLATE = CausalTemplate(
    id="t", domain="ecology", roles=("pred", "prey", "bal"),
    links=links(("pred", "decreases", "prey"), ("prey", "increases", "pred"), ("pred", "enables", "bal")),
    motifs=("feedback_loop",), curated_by="x", source_ref="Lotka 1925", domain_vocabulary=("wolf",))
ROLE_MAP = {"pred": "audit team", "prey": "backlog", "bal": "release health"}
GOOD = mech([("audit team", "decreases", "backlog"), ("backlog", "increases", "audit team"),
             ("audit team", "enables", "release health")], payoff="release health")

def verify(m, role_map, baselines=None):
    return IsomorphismVerifier().verify(cand(m, IsomorphismEvidence(template_id="t", role_map=role_map)),
                                        IsomorphismEvidence(template_id="t", role_map=role_map), TEMPLATE, baselines)

def test_motif_extraction_feedback_bottleneck_asymmetry():
    ex = MotifExtractor()
    loop = links(("a", "increases", "b"), ("b", "increases", "a"))
    assert ex.extract_links(loop) == MotifProfile(has_feedback_loop=True)
    hub = links(("a", "enables", "h"), ("b", "enables", "h"), ("c", "enables", "h"), ("h", "enables", "d"))
    assert ex.extract_links(hub) == MotifProfile(has_bottleneck=True, has_asymmetry=True)
    chain = links(("a", "enables", "b"), ("c", "enables", "d"))
    assert ex.extract_links(chain) == MotifProfile()

def test_role_map_must_be_injective():
    assert verify(GOOD, ROLE_MAP) == ()
    reasons = verify(GOOD, {**ROLE_MAP, "bal": "backlog"})
    assert "role map is not injective" in reasons
    assert any("cover" in r for r in verify(GOOD, {"pred": "audit team"}))

def test_relation_preserving_monomorphism_required():
    bad = mech([("audit team", "increases", "backlog"), ("backlog", "increases", "audit team"),
                ("audit team", "enables", "release health")], payoff="release health")
    assert any("relation mismatch" in r for r in verify(bad, ROLE_MAP))
    assert any("missing edge" in r for r in verify(mech([("audit team", "enables", "release health")], "release health"), ROLE_MAP))

def test_template_vocabulary_copy_rejected():
    wolf = mech([("audit team", "decreases", "wolf pack"), ("wolf pack", "increases", "audit team"),
                 ("audit team", "enables", "release health")], payoff="release health")
    assert any("surface copy" in r for r in verify(wolf, {**ROLE_MAP, "prey": "wolf pack"}))
    copied = mech([("pred", "decreases", "backlog"), ("backlog", "increases", "pred"),
                   ("pred", "enables", "release health")], payoff="release health")
    assert any("surface copy" in r for r in verify(copied, {**ROLE_MAP, "pred": "pred"}))

def test_isomorphic_to_baseline_is_not_credited():
    big = mech([("a1", "decreases", "b1"), ("b1", "increases", "a1"), ("a1", "enables", "c1"),
                ("c1", "enables", "d1")], payoff="d1")
    twin = mech([("w", "decreases", "x"), ("x", "increases", "w"), ("w", "enables", "y"),
                 ("y", "enables", "q")], payoff="q")
    t = CausalTemplate(id="t", domain="ecology", roles=("r1", "r2"), links=links(("r1", "decreases", "r2")),
                       motifs=(), curated_by="x", source_ref="ref")
    ev = IsomorphismEvidence(template_id="t", role_map={"r1": "w", "r2": "x"})
    base = IdeaCandidate(id="b", problem_id="p", title="b", description="b", mechanism=big)
    archive = NegativeArchive(baselines=(base,), mechanisms=(big,))
    v = IsomorphismVerifier()
    assert v.verify(cand(twin, ev), ev, t, None) == ()
    assert "structurally isomorphic to a baseline" in v.verify(cand(twin, ev), ev, t, archive)
    verdict = IsomorphismLineageVerifier().verify(cand(twin, ev), IsomorphismContext(TemplateLibrary([t]), archive))
    assert not verdict.verified and not verdict.credit_awarded
    assert not IsomorphismLineageVerifier().verify(cand(twin, None), None).credit_awarded

def test_template_without_source_ref_excluded():
    lib = TemplateLibrary()
    assert len(lib.templates) == 12 and {t.domain for t in lib.templates} == {
        "ecology", "os_kernel", "thermodynamics", "auction"}
    profile = MotifProfile(has_feedback_loop=True, has_bottleneck=True, has_asymmetry=True)
    assert len(lib.match(profile, k=3)) == 3
    stripped = [t.model_copy(update={"source_ref": "  "}) for t in lib.templates[:11]]
    only = TemplateLibrary([*stripped, lib.templates[11]])
    assert only.match(profile, k=5) == (lib.templates[11],)

def test_blend_runs_zero_network_with_scripted_backend():
    op = BlendOperator()
    h = IdeationHarness(MockIdeaProvider(), operators=[op])
    result = h.run("Reduce churn in a subscription app", HarnessConfig(generations=1, population_size=3, total_budget=3))
    assert result.metrics["isomorphism_attempts"] >= 1
    assert result.metrics["isomorphism_successes"] == result.metrics["isomorphism_attempts"] >= 1
    assert op.successes == result.metrics["isomorphism_successes"]
