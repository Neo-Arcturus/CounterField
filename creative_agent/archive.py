from .models import *


def dominates(a, b, tolerance=1e-9):
    x = (a.novelty, a.utility, a.mechanism_uniqueness)
    y = (b.novelty, b.utility, b.mechanism_uniqueness)
    return all(i >= j - tolerance for i, j in zip(x, y)) and any(i > j + tolerance for i, j in zip(x, y))


class QDArchive:
    def __init__(self):
        self.elites = {}
        self.reservoir = []
        self.repair_incubator = []
        self.failure_archive = []
        self.admission_log = []
        self.seen_ids, self.seen_mechanisms = set(), set()
        self.attempts = self.valid = self.duplicates = 0
        self.niche_attempts = {}

    @staticmethod
    def _niche_key(entry: QDArchiveEntry):
        if entry.dynamics is None:
            return entry.niche.key
        return f"{entry.niche.key}|{entry.dynamics.key}"

    def insert(
        self,
        entry: QDArchiveEntry,
        admission: AdmissionResult | EvaluationBundle | None = None,
        *,
        feasible: bool | None = None,
        blacklisted: bool = False,
    ):
        self.attempts += 1
        niche_key = self._niche_key(entry)
        self.niche_attempts[niche_key] = self.niche_attempts.get(niche_key, 0) + 1

        if isinstance(admission, EvaluationBundle):
            admission = admission.admission
        elif admission is None and entry.evaluation is not None:
            admission = entry.evaluation.admission
        if admission is None:
            admitted = True if feasible is None else feasible
            admission = AdmissionResult(
                status=AdmissionStatus.ACCEPTED if admitted else AdmissionStatus.REPAIRABLE,
                stage=AdmissionStage.COMPLETE if admitted else AdmissionStage.QUALITY_CONSTRAINTS,
                reasons=() if admitted else ("legacy feasibility gate failed",),
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
        self.reservoir = [x for x in self.reservoir if not dominates(entry.scores, x.scores)]
        if not any(dominates(x.scores, entry.scores) for x in self.reservoir):
            self.reservoir.append(entry)
        old = self.elites.get(niche_key)
        if old is None or dominates(entry.scores, old.scores) or (not dominates(old.scores, entry.scores) and entry.candidate.id < old.candidate.id):
            self.elites[niche_key] = entry
        return True

    @property
    def coverage(self): return len(self.elites) / 36

    @property
    def duplicate_rate(self): return self.duplicates / self.valid if self.valid else 0

    def frontier(self): return tuple(sorted(self.reservoir, key=lambda x: x.candidate.id))
    def best_of_k(self, k):
        if k <= 0: raise ValueError("k must be positive")
        values = list(self.frontier())
        values += [x for x in sorted(self.elites.values(), key=lambda x: x.candidate.id) if x not in values]
        return tuple(values[:k])
