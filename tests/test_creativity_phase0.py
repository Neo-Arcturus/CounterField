import inspect

import pytest

from creative_agent import DefaultDomainAdapter, MockIdeaProvider
from creative_agent.contracts import BehaviorExtractor, DomainAdapter, VerificationOracle
from creative_agent.creativity import (
    ArchiveView, CreativeOperator, LegacyPromptOperator, OperatorContext,
    is_small_graph, stable_hash, structural_fingerprint,
)
from creative_agent.harness import LEGACY_OPERATORS, IdeationHarness
from creative_agent.models import (
    CanonicalMechanism, CausalLink, CreativeLineage, HarnessConfig, InversionEvidence,
)

CFG = HarnessConfig(generations=2, population_size=3, total_budget=6)
PROBLEM = "Reduce handoff errors between teams"

def mech(links, core="core"):
    return CanonicalMechanism(
        core_mechanism=core, affected_system="sys", payoff="pay",
        causal_structure=tuple(CausalLink(cause=c, relation=r, effect=e) for c, r, e in links),
    )

CHAIN = [("a", "increases", "b"), ("b", "enables", "c"), ("c", "prevents", "d"), ("a", "depends_on", "d")]

class Recorder(DefaultDomainAdapter):
    def __init__(self, provider):
        super().__init__(provider)
        self.calls = []

    def generate_candidates(self, problem, operator, context, count):
        self.calls.append((operator, context))
        return super().generate_candidates(problem, operator, context, count)

def _log(result_harness_args=()):
    h = IdeationHarness(MockIdeaProvider(), *result_harness_args)
    return h.run(PROBLEM, CFG)

def test_default_harness_is_byte_identical():
    r1, r2 = _log(), IdeationHarness(MockIdeaProvider(), operators=None).run(PROBLEM, CFG)
    assert r1.model_dump_json() == r2.model_dump_json()
    for key in ("generation_errors", "canonicalize_errors", "validation_errors", "evaluation_errors"):
        assert r1.metrics[key] == 0
    assert r1.metrics["attempts"] > 0

def test_fingerprint_golden_vectors_unchanged():
    m = mech([("x|y", "increases", "Z")])
    from creative_agent.models import stable_id
    assert m.fingerprint == stable_id("core", "sys", "pay", "x\\|y|increases|z")
    assert m.fingerprint == "2e118d40a98a94ab"
    assert m.fingerprint == mech([("X|Y", "increases", "z")]).fingerprint

def test_lineage_excluded_from_fingerprint():
    h = IdeationHarness(MockIdeaProvider())
    cand = h.adapter.generate_candidates(h.adapter.normalize_problem(PROBLEM), "Inversion", (), 1)[0]
    cand = h.adapter.canonicalize_mechanism(h.adapter.normalize_problem(PROBLEM), cand)
    ev = InversionEvidence(claim_id="c", bound_link_indices=(0,), flipped_polarity=True)
    tagged = cand.model_copy(update={"lineage": CreativeLineage(operator="x", evidence=ev)})
    assert tagged.mechanism.fingerprint == cand.mechanism.fingerprint
    assert cand.lineage is None

def test_structural_fingerprint_label_invariant():
    relabeled = [(c.upper() + "z", r, e.upper() + "z") for c, r, e in CHAIN]
    assert structural_fingerprint(mech(CHAIN)) == structural_fingerprint(mech(relabeled))
    flipped = [("a", "decreases", "b")] + CHAIN[1:]
    assert structural_fingerprint(mech(CHAIN)) != structural_fingerprint(mech(flipped))

def test_structural_fingerprint_small_graph_not_blacklisted():
    small = mech([("a", "increases", "b")])
    assert is_small_graph(small) and not is_small_graph(mech(CHAIN))
    assert isinstance(structural_fingerprint(small), str)
    assert isinstance(structural_fingerprint(mech([])), str)

def test_legacy_operator_matches_round_robin_order():
    adapter = Recorder(MockIdeaProvider())
    h = IdeationHarness(adapter)
    assert all(isinstance(o, CreativeOperator) for o in h.operators)
    h.run(PROBLEM, CFG)
    assert [c[0] for c in adapter.calls] == list(LEGACY_OPERATORS)

def test_operator_rng_deterministic_by_seed():
    seen = []

    class Spy:
        name = "spy"
        def propose(self, ctx):
            seen.append(ctx.rng_seed)
            return []

    for _ in range(2):
        IdeationHarness(MockIdeaProvider(), operators=[Spy()]).run(PROBLEM, CFG)
    assert seen[:6] == seen[6:]
    assert len(set(seen[:6])) == 6
    assert seen[0] == stable_hash(CFG.seed, 0, "spy")

def test_generation_error_counters_not_silent():
    class Boom(DefaultDomainAdapter):
        def generate_candidates(self, *a):
            raise RuntimeError("injected")

    r = IdeationHarness(Boom(MockIdeaProvider())).run(PROBLEM, CFG)
    assert r.metrics["generation_errors"] == 6

def test_existing_protocols_unchanged():
    def names(p):
        return {n: str(inspect.signature(getattr(p, n))) for n in p.__dict__ if not n.startswith("_")}
    assert set(names(DomainAdapter)) == {"normalize_problem", "generate_candidates", "canonicalize_mechanism", "mine_baselines"}
    assert set(names(VerificationOracle)) == {"validate_structure", "evaluate"}
    assert set(names(BehaviorExtractor)) == {"extract_niche", "extract_dynamics"}
    assert "(self, problem: 'NormalizedProblem', operator: 'str', context: 'tuple[IdeaCandidate, ...]', count: 'int') -> 'list[IdeaCandidate]'" == names(DomainAdapter)["generate_candidates"]

def test_parent_selection_feeds_context():
    adapter = Recorder(MockIdeaProvider())
    IdeationHarness(adapter).run(PROBLEM, CFG)
    assert adapter.calls[0][1] == ()
    assert any(len(ctx) > 0 for _, ctx in adapter.calls)

def test_archive_view_is_read_only():
    from creative_agent.archive import QDArchive
    v = ArchiveView(QDArchive())
    with pytest.raises(AttributeError):
        v.coverage = 1
    with pytest.raises(TypeError):
        v.elites["k"] = None
