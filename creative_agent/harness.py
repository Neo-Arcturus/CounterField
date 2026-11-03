from .models import *
from .providers import IdeaProvider, HashEmbeddingProvider
from .evaluator import ThreeLayerEvaluator
from .contracts import (
    BehaviorExtractor, DefaultBehaviorExtractor, DefaultDomainAdapter,
    DefaultVerificationOracle, DomainAdapter, VerificationOracle,
)
from .archive import QDArchive
from .creativity.niche_space import NicheSpace
from .creativity.metrics import CreativeMetrics
from .creativity.operators import (
    ArchiveView, CreativeOperator, LegacyPromptOperator, OperatorContext, stable_hash,
)
from .creativity.dialectic import DialecticalSynthesizer, RuleLibrary, counterexample_hash
from .creativity.lineage import DialecticContext, DialecticLineageVerifier, LineageVerifier
from .creativity.inversion import InversionContext, InversionLineageVerifier, InversionOperator
from .creativity.isomorphism import BlendOperator, IsomorphismContext, TemplateLibrary
from .creativity.lineage import IsomorphismLineageVerifier
from typing import Any, Sequence

MAX_SYNTHESIS_DEPTH = 3

LEGACY_OPERATORS = ("Inversion", "Extreme constraints", "Removal", "Cross-domain analogy", "Role shift", "Multilingual/cultural conceptualization")


class IdeationHarness:
    def __init__(
        self,
        adapter: DomainAdapter | IdeaProvider,
        oracle: VerificationOracle | None = None,
        extractor: BehaviorExtractor | None = None,
        embeddings=None,
        *,
        operators: Sequence[CreativeOperator] | None = None,
        scheduler: Any = None,
        synthesizer: DialecticalSynthesizer | None = None,
        rule_library: RuleLibrary | None = None,
        evidence_verifiers: Sequence[LineageVerifier] = (),
        max_synthesis_per_entry: int = 2,
        niche_space: NicheSpace | None = None,
        **kwargs,
    ):
        if kwargs:
            raise TypeError(f"unexpected keyword arguments: {sorted(kwargs)}")
        # Legacy call: IdeationHarness(provider, embeddings) passes embeddings positionally.
        if oracle is not None and not isinstance(oracle, VerificationOracle):
            embeddings, oracle = oracle, None
        self.embeddings = embeddings or HashEmbeddingProvider()
        if isinstance(adapter, DomainAdapter):
            self.provider = getattr(adapter, "provider", None)
            self.adapter = adapter
        else:
            self.provider = adapter
            self.adapter = DefaultDomainAdapter(adapter)
        if oracle is None:
            if self.provider is None:
                raise TypeError("oracle is required when adapter is not provider-backed")
            oracle = DefaultVerificationOracle(ThreeLayerEvaluator(self.provider, self.embeddings))
        if extractor is None:
            if self.provider is None:
                raise TypeError("extractor is required when adapter is not provider-backed")
            extractor = DefaultBehaviorExtractor(self.provider)
        self.oracle = oracle
        self.extractor = extractor
        self.scheduler = scheduler
        self.niche_space = niche_space
        if max_synthesis_per_entry < 0:
            raise ValueError("max_synthesis_per_entry must not be negative")
        self.synthesizer = synthesizer
        self.rule_library = rule_library if rule_library is not None else (RuleLibrary() if synthesizer else None)
        self.evidence_verifiers = tuple(evidence_verifiers) or (
            (DialecticLineageVerifier(),) if synthesizer else ()
        )
        self.max_synthesis_per_entry = max_synthesis_per_entry
        self.operators = tuple(operators) if operators is not None else tuple(
            LegacyPromptOperator(self.adapter, name) for name in LEGACY_OPERATORS
        )
        if not self.operators:
            raise ValueError("operators must not be empty")
        self.inversion_operators = tuple(o for o in self.operators if isinstance(o, InversionOperator))
        self.inversion_verifier = next(
            (v for v in self.evidence_verifiers if isinstance(v, InversionLineageVerifier)),
            InversionLineageVerifier() if self.inversion_operators else None,
        )
        self.blend_operators = tuple(o for o in self.operators if isinstance(o, BlendOperator))
        self.isomorphism_verifier = next(
            (v for v in self.evidence_verifiers if isinstance(v, IsomorphismLineageVerifier)),
            IsomorphismLineageVerifier() if self.blend_operators else None,
        )

    @staticmethod
    def _select_parents(archive: QDArchive) -> tuple:
        pool = sorted(archive.elites.values(), key=lambda e: e.candidate.id) or sorted(
            archive.reservoir, key=lambda e: e.candidate.id
        )
        return tuple(e.candidate for e in pool[:2])

    def _synthesize(self, entry, archive, problem, negative, negative_fps, config, metrics, synth) -> None:
        """Dialectical hook: turn a repairable (FATAL red-team) parent into verified children.

        The parent stays in the repair incubator (G1); only children that pass the full pipeline enter.
        """
        evaluation = entry.evaluation
        counterexamples = evaluation.diagnostics.counterexamples if evaluation else entry.diagnostics.counterexamples
        parent = entry.candidate
        depth = synth["depth"].get(parent.id, 0)
        if not counterexamples or depth >= MAX_SYNTHESIS_DEPTH:
            return
        fresh = tuple(c for c in counterexamples if counterexample_hash(c) not in synth["seen"])  # G12
        if not fresh:
            return
        for ce in fresh:
            self.rule_library.add_counterexample(parent.mechanism.fingerprint, ce)
        fresh_hashes = {counterexample_hash(c) for c in fresh}
        synth["seen"] |= fresh_hashes
        proposals = self.synthesizer.synthesize(entry, fresh, self.rule_library)
        for proposal in proposals[: self.max_synthesis_per_entry]:  # G11
            child = proposal.child
            if child.parent_id != parent.id or counterexample_hash(proposal.counterexample) not in fresh_hashes:
                continue
            synth["attempts"] += 1
            synth["depth"][child.id] = depth + 1
            child = child.model_copy(update={"generation": entry.insertion_generation})
            try:
                canonical = self.adapter.canonicalize_mechanism(problem, child)
                if not self.oracle.validate_structure(canonical).is_valid:
                    continue
                result = self.oracle.evaluate(
                    problem, canonical, negative,
                    (config.appropriateness_threshold, config.coherence_threshold),
                )
                if result.scores is None:
                    continue
                child_entry = QDArchiveEntry(
                    candidate=canonical, niche=self.extractor.extract_niche(problem, canonical),
                    scores=result.scores, diagnostics=result.diagnostics,
                    insertion_generation=child.generation,
                    dynamics=result.dynamics or self.extractor.extract_dynamics(canonical),
                    evaluation=result,
                )
                context = DialecticContext(
                    parent=parent, counterexample=proposal.counterexample,
                    corpus=self.rule_library.corpus(parent.mechanism.fingerprint),
                )

                def credit(canonical=canonical, proposal=proposal, context=context):
                    verdicts = [v.verify(canonical, context) for v in self.evidence_verifiers]
                    if verdicts and all(v.verified and v.credit_awarded for v in verdicts):
                        self.rule_library.record_success(
                            proposal.counterexample.violated_invariant, proposal.ops, canonical.id)
                        synth["successes"] += 1

                if archive.insert(
                    child_entry, admission=result.admission,
                    blacklisted=canonical.mechanism.fingerprint in negative_fps, on_admit=credit,
                ):
                    metrics.record_admitted(canonical)
                elif archive.repair_incubator[-1:] == [child_entry]:
                    self._synthesize(child_entry, archive, problem, negative, negative_fps, config, metrics, synth)
            except Exception:
                metrics.count_error("evidence_errors")

    def run(self, problem: str, config: HarnessConfig | None = None) -> HarnessResult:
        config = config or HarnessConfig()
        normalized = self.adapter.normalize_problem(problem)
        negative = self.adapter.mine_baselines(normalized)
        archive = QDArchive(self.niche_space)
        archive.rule_library = self.rule_library
        inversion = {"attempts": 0, "successes": 0}
        isomorphism = {"attempts": 0, "successes": 0}
        synth = {"attempts": 0, "successes": 0, "seen": set(), "depth": {}}
        attempts = structural_failures = 0
        budget = min(config.total_budget, config.generations * config.population_size)
        metrics = CreativeMetrics()
        view = ArchiveView(archive)
        evaluation_errors = validation_errors = 0
        negative_fps = {x.fingerprint for x in negative.mechanisms}
        for slot in range(budget):
            operator = self.operators[slot % len(self.operators)]
            ctx = OperatorContext(
                problem=normalized, parents=self._select_parents(archive), baselines=negative,
                archive=view, slot=slot, rng_seed=stable_hash(config.seed, slot, operator.name),
            )
            try:
                candidates = operator.propose(ctx)
            except Exception:
                metrics.count_error("generation_errors")
                continue
            if not candidates:
                continue
            metrics.proposed += 1
            candidate = candidates[0].model_copy(update={"generation": slot // config.population_size})
            if (getattr(self.provider, "mode", None) == "llm"
                    and candidate.provenance.provider_mode == "mock"):
                candidate = candidate.model_copy(update={
                    "provenance": candidate.provenance.model_copy(update={"provider_mode": "mock-fallback"})
                })
                metrics.count_error("provider_fallbacks")
            try:
                canonical = self.adapter.canonicalize_mechanism(normalized, candidate)
            except Exception:
                metrics.count_error("canonicalize_errors")
                continue
            attempts += 1
            try:
                validation_report = self.oracle.validate_structure(canonical)
            except Exception:
                validation_errors += 1
                continue
            if not validation_report.is_valid:
                structural_failures += 1
                continue
            try:
                evaluation = self.oracle.evaluate(
                    normalized, canonical, negative,
                    (config.appropriateness_threshold, config.coherence_threshold),
                )
                scores = evaluation.scores
                if scores is None:
                    continue
                niche = self.extractor.extract_niche(normalized, canonical)
                entry = QDArchiveEntry(
                    candidate=canonical,
                    niche=niche,
                    scores=scores,
                    diagnostics=evaluation.diagnostics,
                    insertion_generation=candidate.generation,
                    dynamics=evaluation.dynamics or self.extractor.extract_dynamics(canonical),
                    evaluation=evaluation,
                )
                is_inversion = (self.inversion_verifier is not None and canonical.lineage is not None
                                and isinstance(canonical.lineage.evidence, InversionEvidence))

                def inversion_credit(canonical=canonical):
                    inversion["attempts"] += 1
                    claims = tuple(c for op in self.inversion_operators for c in op.claims.values())
                    verdict = self.inversion_verifier.verify(canonical, InversionContext(claims))
                    if verdict.verified and verdict.credit_awarded:
                        inversion["successes"] += 1
                        for op in self.inversion_operators:
                            op.record_credit(canonical)

                is_blend = (self.isomorphism_verifier is not None and canonical.lineage is not None
                            and isinstance(canonical.lineage.evidence, IsomorphismEvidence))

                def isomorphism_credit(canonical=canonical):
                    isomorphism["attempts"] += 1
                    verdict = self.isomorphism_verifier.verify(canonical, IsomorphismContext(
                        self.blend_operators[0].library if self.blend_operators else TemplateLibrary(), negative))
                    if verdict.verified and verdict.credit_awarded:
                        isomorphism["successes"] += 1
                        for op in self.blend_operators:
                            op.record_credit(canonical)

                if archive.insert(
                    entry,
                    admission=evaluation.admission,
                    blacklisted=canonical.mechanism.fingerprint in negative_fps,
                    rng_seed=ctx.rng_seed,
                    on_admit=(inversion_credit if is_inversion else isomorphism_credit if is_blend else None),
                ):
                    metrics.record_admitted(canonical)
                elif self.synthesizer is not None and archive.repair_incubator[-1:] == [entry]:
                    self._synthesize(entry, archive, normalized, negative, negative_fps, config, metrics, synth)
            except Exception:
                evaluation_errors += 1
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
                **metrics.errors,
                "validation_errors": validation_errors,
                "evaluation_errors": evaluation_errors,
                "inversion_attempts": inversion["attempts"],
                "inversion_successes": inversion["successes"],
                "isomorphism_attempts": isomorphism["attempts"],
                "isomorphism_successes": isomorphism["successes"],
                "synthesis_attempts": synth["attempts"],
                "synthesis_successes": synth["successes"],
                "rules_promoted": len(self.rule_library.promoted_rules()) if self.rule_library else 0,
                **({"niche_count": len(archive.elites), "qd_score": archive.qd_score}
                   if archive.coverage is None else {}),
            },
            selected=archive.best_of_k(min(5, len(archive.elites))) if archive.elites else (),
            frontier=archive.frontier(),
        )
