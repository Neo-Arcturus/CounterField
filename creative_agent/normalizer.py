from .models import *
from .providers import IdeaProvider


class ProblemNormalizer:
    def __init__(self, provider: IdeaProvider):
        self.provider = provider

    def normalize(self, prompt: str) -> NormalizedProblem:
        return self.provider.normalize(prompt)


class BaselineClicheMiner:
    def __init__(self, provider: IdeaProvider):
        self.provider = provider

    def mine(self, problem: NormalizedProblem, count: int = 3) -> NegativeArchive:
        candidates = []
        seen = set()
        for candidate in self.provider.mine_baselines(problem, count):
            candidate = self.provider.canonicalize(problem, candidate)
            if candidate.mechanism and candidate.mechanism.fingerprint not in seen:
                seen.add(candidate.mechanism.fingerprint)
                candidates.append(candidate)
        if not candidates:
            raise RuntimeError("no valid baseline survived; provide a provider with canonical mechanisms")
        return NegativeArchive(
            baselines=tuple(candidates),
            mechanisms=tuple(x.mechanism for x in candidates if x.mechanism),
        )
