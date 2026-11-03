import pytest

from creative_agent import (
    AdmissionResult, AdmissionStage, AdmissionStatus, EvaluationDiagnostics, MockIdeaProvider,
    NicheDescriptor, ProblemNormalizer, QDArchive, QDArchiveEntry,
)
from creative_agent.creativity import CentroidNicheSpace, FixedGridSpace, NicheSpace
from creative_agent.harness import IdeationHarness
from creative_agent.models import DynamicalNicheDescriptor, HarnessConfig

ACCEPTED = AdmissionResult(status=AdmissionStatus.ACCEPTED, stage=AdmissionStage.COMPLETE, reasons=())
OPERATORS = ("Inversion", "Extreme constraints", "Removal", "Cross-domain analogy", "Role shift")
NEAR = NicheDescriptor(intervention_level="individual", resource_intensity="low", feedback_horizon="immediate")
FAR = NicheDescriptor(intervention_level="ecosystem", resource_intensity="high", feedback_horizon="long")
DYN = DynamicalNicheDescriptor(causal_depth=2, branching_factor=1.0, loop_density=0.2, payoff_path_length=3)


def _entries(niches, dynamics=None):
    provider = MockIdeaProvider()
    problem = ProblemNormalizer(provider).normalize("phase 4 niches")
    out = []
    for i, niche in enumerate(niches):
        cand = provider.canonicalize(problem, provider.generate(problem, OPERATORS[i % len(OPERATORS)], (), i + 1)[0])
        out.append(QDArchiveEntry(candidate=cand, niche=niche, scores=provider.assess(problem, cand),
                                  diagnostics=EvaluationDiagnostics(), dynamics=dynamics))
    return out


def test_fixed_grid_space_equals_legacy_keys():
    space = FixedGridSpace()
    assert isinstance(space, NicheSpace) and space.capacity == 36
    plain, dyn = _entries([NEAR], None)[0], _entries([FAR], DYN)[0]
    assert space.locate(plain) == plain.niche.key
    assert space.locate(dyn) == f"{dyn.niche.key}|{dyn.dynamics.key}"
    assert QDArchive()._niche_key(dyn) == space.locate(dyn)


def test_centroid_expansion_is_append_only_and_elites_monotone():
    space = CentroidNicheSpace(centroids=[CentroidNicheSpace.project(_entries([NEAR], DYN)[0])])
    archive = QDArchive(space)
    near, far = _entries([NEAR, FAR], DYN)
    assert archive.insert(near, ACCEPTED)
    before_centroids, before_elites = space.centroids, dict(archive.elites)
    assert archive.insert(far, ACCEPTED)
    assert space.centroids[:len(before_centroids)] == before_centroids and len(space.centroids) == 2
    assert all(archive.elites[k] is v for k, v in before_elites.items())
    assert len(archive.elites) == 2


def test_expansion_rolled_back_with_failed_insert():
    space = CentroidNicheSpace()
    archive = QDArchive(space)
    entry = _entries([FAR], DYN)[0]

    def boom():
        raise RuntimeError("fail")

    with pytest.raises(RuntimeError):
        archive.insert(entry, ACCEPTED, on_admit=boom)
    assert space.centroids == () and space.version == 0
    assert archive.elites == {} and archive.reservoir == []


def test_expansion_deterministic_by_seed():
    def run():
        space = CentroidNicheSpace(min_candidates=1)
        space.maybe_expand(_entries([NEAR, FAR], DYN), rng_seed=7)
        return space.centroids, space.version
    assert run() == run()


def test_coverage_none_for_open_space_and_metrics_present():
    assert QDArchive().coverage is not None
    archive = QDArchive(CentroidNicheSpace())
    archive.insert(_entries([FAR], DYN)[0], ACCEPTED)
    assert archive.coverage is None and archive.qd_score > 0
    result = IdeationHarness(MockIdeaProvider(), niche_space=CentroidNicheSpace()).run(
        "phase 4 metrics", HarnessConfig(generations=2, population_size=3, total_budget=6))
    assert result.metrics["coverage"] is None
    assert result.metrics["niche_count"] >= 1 and result.metrics["qd_score"] > 0


def test_reservoir_independent_of_niche_space():
    entries = _entries([NEAR, FAR, NEAR, FAR], DYN)
    ids = []
    for space in (FixedGridSpace(), CentroidNicheSpace()):
        archive = QDArchive(space)
        for e in entries:
            archive.insert(e, ACCEPTED)
        ids.append([e.candidate.id for e in archive.frontier()])
    assert ids[0] == ids[1]


def test_below_rho_does_not_expand():
    base = CentroidNicheSpace.project(_entries([NEAR], DYN)[0])
    space = CentroidNicheSpace(rho=0.25, centroids=[base])
    assert space.maybe_expand(_entries([NEAR], DYN), rng_seed=1) == []
    assert space.centroids == (base,) and space.version == 0
