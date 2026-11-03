from .models import *
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .creativity.niche_space import NicheSpace


def dominates(a, b, tolerance=1e-9):
    x = (a.novelty, a.utility, a.mechanism_uniqueness)
    y = (b.novelty, b.utility, b.mechanism_uniqueness)
    return all(i >= j - tolerance for i, j in zip(x, y)) and any(i > j + tolerance for i, j in zip(x, y))


class QDArchive:
    def __init__(self, niche_space: "NicheSpace | None" = None):
        if niche_space is None:
            # deferred: creativity/__init__ imports modules that import this one
            from .creativity.niche_space import FixedGridSpace
            niche_space = FixedGridSpace()
        self.niche_space = niche_space
        self.elites = {}
        self.reservoir = []
        self.repair_incubator = []
        self.failure_archive = []
        self.admission_log = []
        self.seen_ids, self.seen_mechanisms = set(), set()
        self.attempts = self.valid = self.duplicates = 0
        self.niche_attempts = {}
        self.rule_library = None

    def _niche_key(self, entry: QDArchiveEntry):
        return self.niche_space.locate(entry)

    def _snapshot(self):
        return (
            list(self.reservoir), dict(self.elites), list(self.repair_incubator),
            list(self.failure_archive), list(self.admission_log),
            set(self.seen_ids), set(self.seen_mechanisms),
            self.attempts, self.valid, self.duplicates, dict(self.niche_attempts),
            self.rule_library.snapshot() if self.rule_library is not None else None,
            self.niche_space.snapshot(),
        )

    def _restore(self, snap):
        (self.reservoir, self.elites, self.repair_incubator, self.failure_archive,
         self.admission_log, self.seen_ids, self.seen_mechanisms, self.attempts,
         self.valid, self.duplicates, self.niche_attempts, rules, niche_state) = snap
        self.niche_space.restore(niche_state)
        if self.rule_library is not None:
            self.rule_library.restore(rules)

    def insert(
        self,
        entry: QDArchiveEntry,
        admission: AdmissionResult | EvaluationBundle | None = None,
        *,
        feasible: bool | None = None,
        blacklisted: bool = False,
        on_admit=None,
        rng_seed: int = 0,
    ):
        snap = self._snapshot()
        try:
            admitted = self._insert(entry, admission, feasible, blacklisted, rng_seed)
            if admitted and on_admit is not None:
                on_admit()  # runs inside the transaction so side effects roll back with the insert
            return admitted
        except BaseException:
            self._restore(snap)
            raise

    def _insert(self, entry, admission, feasible, blacklisted, rng_seed=0):
        self.attempts += 1
        niche_key = self._niche_key(entry)
        self.niche_attempts[niche_key] = self.niche_attempts.get(niche_key, 0) + 1

        bundle = admission if isinstance(admission, EvaluationBundle) else entry.evaluation
        mismatch = bundle is not None and (
            (bundle.candidate_id is not None and bundle.candidate_id != entry.candidate.id)
            or (bundle.candidate_fingerprint is not None
                and bundle.candidate_fingerprint != entry.candidate.mechanism.fingerprint)
        )
        if isinstance(admission, EvaluationBundle):
            admission = admission.admission
        elif admission is None and entry.evaluation is not None:
            admission = entry.evaluation.admission
        if mismatch:
            admission = AdmissionResult(
                status=AdmissionStatus.REJECTED,
                stage=AdmissionStage.EVALUATION_INTEGRITY,
                reasons=("evaluation evidence belongs to a different candidate",),
            )
        elif admission is None:
            if feasible is None:
                admission = AdmissionResult(
                    status=AdmissionStatus.REJECTED,
                    stage=AdmissionStage.COMPLETE,
                    reasons=("missing evaluation evidence",),
                )
            else:
                # explicit legacy feasibility flag from callers predating EvaluationBundle
                admission = AdmissionResult(
                    status=AdmissionStatus.ACCEPTED if feasible else AdmissionStatus.REPAIRABLE,
                    stage=AdmissionStage.COMPLETE if feasible else AdmissionStage.QUALITY_CONSTRAINTS,
                    reasons=() if feasible else ("legacy feasibility gate failed",),
                )

        fatal_playtest = (
            entry.diagnostics.playtest_report is not None
            and any(
                issue.severity == "FATAL"
                for issue in entry.diagnostics.playtest_report.issues
            )
        )
        if fatal_playtest and admission.status == AdmissionStatus.ACCEPTED:
            admission = AdmissionResult(
                status=AdmissionStatus.REPAIRABLE,
                stage=AdmissionStage.RED_TEAM,
                reasons=("fatal red-team issue cannot enter the production archive",),
            )
        if blacklisted:
            admission = AdmissionResult(
                status=AdmissionStatus.REJECTED,
                stage=AdmissionStage.NOVELTY_POLICY,
                reasons=("mechanism fingerprint is in the negative archive",),
            )

        self.admission_log.append((entry, admission))
        if admission.status == AdmissionStatus.REPAIRABLE:
            self.repair_incubator.append(entry)
            return False
        if admission.status != AdmissionStatus.ACCEPTED:
            self.failure_archive.append(entry)
            return False
        self.valid += 1
        fp = entry.candidate.mechanism.fingerprint
        if entry.candidate.id in self.seen_ids or fp in self.seen_mechanisms:
            self.duplicates += 1
            return False
        self.seen_ids.add(entry.candidate.id); self.seen_mechanisms.add(fp)
        self.niche_space.maybe_expand((entry,), rng_seed)
        niche_key = self._niche_key(entry)
        self.reservoir = [x for x in self.reservoir if not dominates(entry.scores, x.scores)]
        if not any(dominates(x.scores, entry.scores) for x in self.reservoir):
            self.reservoir.append(entry)
        old = self.elites.get(niche_key)
        if old is None or dominates(entry.scores, old.scores) or (not dominates(old.scores, entry.scores) and entry.candidate.id < old.candidate.id):
            self.elites[niche_key] = entry
        return True

    @property
    def coverage(self):
        capacity = self.niche_space.capacity
        return None if capacity is None else len(self.elites) / capacity

    @property
    def qd_score(self): return sum(e.scores.novelty + e.scores.utility for e in self.elites.values())

    @property
    def duplicate_rate(self): return self.duplicates / self.valid if self.valid else 0

    def frontier(self): return tuple(sorted(self.reservoir, key=lambda x: x.candidate.id))
    def best_of_k(self, k):
        if k <= 0: raise ValueError("k must be positive")
        values = list(self.frontier())
        values += [x for x in sorted(self.elites.values(), key=lambda x: x.candidate.id) if x not in values]
        return tuple(values[:k])
