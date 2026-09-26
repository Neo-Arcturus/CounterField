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
        attempts = structural_failures = 0
        budget = min(config.total_budget, config.generations * config.population_size)
        operators = ["Inversion", "Extreme constraints", "Removal", "Cross-domain analogy", "Role shift", "Multilingual/cultural conceptualization"]
        for slot in range(budget):
            operator = operators[slot % len(operators)]
            try:
                candidates = self.provider.generate(normalized, operator, (), 1)
                if not candidates:
                    continue
                candidate = candidates[0].model_copy(update={"generation": slot // config.population_size})
                canonical = self.provider.canonicalize(normalized, candidate)
                attempts += 1
                validation_report = evaluator.validator.validate(canonical)
                if not validation_report.is_valid:
                    structural_failures += 1
                    continue
                evaluation = evaluator.evaluate(
                    normalized,
                    canonical,
                    negative,
                    (config.appropriateness_threshold, config.coherence_threshold),
                )
                scores = evaluation.scores
                if scores is None:
                    continue
                diagnostics = evaluation.diagnostics
                niche = self.provider.describe_niche(normalized, canonical)
                entry = QDArchiveEntry(
                    candidate=canonical,
                    niche=niche,
                    scores=scores,
                    diagnostics=diagnostics,
                    insertion_generation=candidate.generation,
                    dynamics=evaluation.dynamics,
                    evaluation=evaluation,
                )
                archive.insert(
                    entry,
                    admission=evaluation.admission,
                    blacklisted=canonical.mechanism.fingerprint in {
                        x.fingerprint for x in negative.mechanisms
                    },
                )
            except Exception as exc:
                continue
        return HarnessResult(
            status="COMPLETED", termination_reason="budget exhausted",
            metrics={
                "coverage": archive.coverage,
                "duplicate_rate": archive.duplicate_rate,
                "attempts": attempts,
                "structural_failures": structural_failures,
                "occupied_niches": len(archive.elites),
                "repair_incubator": len(archive.repair_incubator),
                "failure_archive": len(archive.failure_archive),
            },
            selected=archive.best_of_k(min(5, len(archive.elites))) if archive.elites else (),
            frontier=archive.frontier(),
        )
