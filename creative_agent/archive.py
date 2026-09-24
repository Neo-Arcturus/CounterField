from .models import *


def dominates(a, b, tolerance=1e-9):
    x = (a.novelty, a.utility, a.mechanism_uniqueness)
    y = (b.novelty, b.utility, b.mechanism_uniqueness)
    return all(i >= j - tolerance for i, j in zip(x, y)) and any(i > j + tolerance for i, j in zip(x, y))


class QDArchive:
    def __init__(self):
        self.elites = {}
        self.reservoir = []
        self.seen_ids, self.seen_mechanisms = set(), set()
        self.attempts = self.valid = self.duplicates = 0
        self.niche_attempts = {}

    def insert(self, entry: QDArchiveEntry, feasible=True, blacklisted=False):
        self.attempts += 1
        self.niche_attempts[entry.niche.key] = self.niche_attempts.get(entry.niche.key, 0) + 1
        if not feasible or blacklisted:
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
        old = self.elites.get(entry.niche.key)
        if old is None or dominates(entry.scores, old.scores) or (not dominates(old.scores, entry.scores) and entry.candidate.id < old.candidate.id):
            self.elites[entry.niche.key] = entry
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
