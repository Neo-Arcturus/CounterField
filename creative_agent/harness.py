from .models import *
from .normalizer import ProblemNormalizer, BaselineClicheMiner
from .providers import IdeaProvider, HashEmbeddingProvider
from .evaluator import ThreeLayerEvaluator
from .archive import QDArchive


class IdeationHarness:
    def __init__(self, provider: IdeaProvider, embeddings=None):
        self.provider = provider
        self.embeddings = embeddings or HashEmbeddingProvider()

    def run(self, problem: str, config: HarnessConfig | None = None) -> HarnessResult:
        config = config or HarnessConfig()
        normalized = ProblemNormalizer(self.provider).normalize(problem)
        negative = BaselineClicheMiner(self.provider).mine(normalized)
        evaluator = ThreeLayerEvaluator(self.provider, self.embeddings)
        archive = QDArchive()
        budget = min(config.total_budget, config.generations * config.population_size)
        for slot in range(budget):
            operator = ["Inversion", "Extreme constraints", "Removal", "Cross-domain analogy", "Role shift", "Multilingual/cultural conceptualization"][slot % 6]
            candidate = self.provider.generate(normalized, operator, (), 1)[0]
            candidate = candidate.model_copy(update={"generation": slot // config.population_size})
            try:
                scores, diagnostics, feasible = evaluator.evaluate(normalized, candidate, negative, (config.appropriateness_threshold, config.coherence_threshold))
                canonical = self.provider.canonicalize(normalized, candidate)
                entry = QDArchiveEntry(candidate=canonical, niche=self.provider.describe_niche(normalized, canonical), scores=scores, diagnostics=diagnostics, insertion_generation=candidate.generation)
                archive.insert(entry, feasible=feasible, blacklisted=canonical.mechanism.fingerprint in {x.fingerprint for x in negative.mechanisms})
            except Exception:
                continue
        return HarnessResult(
            status="COMPLETED", termination_reason="budget exhausted",
            metrics={"coverage": archive.coverage, "duplicate_rate": archive.duplicate_rate, "attempts": archive.attempts, "occupied_niches": len(archive.elites)},
            selected=archive.best_of_k(min(5, len(archive.elites))) if archive.elites else (),
            frontier=archive.frontier(),
        )
