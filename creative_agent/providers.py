from __future__ import annotations

import hashlib
import json
import math
import os
import re
import urllib.request
from typing import Protocol, Any

from .models import *


class IdeaProvider(Protocol):
    def normalize(self, problem: str) -> NormalizedProblem: ...
    def mine_baselines(self, problem: NormalizedProblem, count: int) -> list[IdeaCandidate]: ...
    def generate(self, problem: NormalizedProblem, operator: str, private_history: tuple[IdeaCandidate, ...] | list[IdeaCandidate], count: int) -> list[IdeaCandidate]: ...
    def canonicalize(self, problem: NormalizedProblem, candidate: IdeaCandidate) -> IdeaCandidate: ...
    def assess(self, problem: NormalizedProblem, candidate: IdeaCandidate) -> EvaluationScores: ...
    def describe_niche(self, problem: NormalizedProblem, candidate: IdeaCandidate) -> NicheDescriptor: ...


class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbeddingProvider:
    mode = "hash-lexical-proxy"

    def __init__(self, dimensions: int = 64):
        self.dimensions = dimensions
        self._cache: dict[str, list[float]] = {}

    def embed(self, texts: list[str]) -> list[list[float]]:
        result = []
        for text in texts:
            key = " ".join(text.casefold().split())
            if key not in self._cache:
                vector = [0.0] * self.dimensions
                features = re.findall(r"\w+", key, re.UNICODE)
                features += [key[i:i + 3] for i in range(max(0, len(key) - 2))]
                for feature in features:
                    digest = hashlib.sha256(feature.encode()).digest()
                    vector[int.from_bytes(digest[:4], "big") % self.dimensions] += 1
                norm = math.sqrt(sum(x * x for x in vector))
                self._cache[key] = [x / norm for x in vector] if norm else vector
            result.append(self._cache[key][:])
        return result


class MockIdeaProvider:
    mode = "mock"

    def normalize(self, problem: str) -> NormalizedProblem:
        text = " ".join(problem.split())
        if not text:
            raise ValueError("problem must not be empty")
        return NormalizedProblem(
            id=stable_id(text), original_prompt=text, objective=text,
            constraints=("avoid unnecessary complexity",), affected_system="people and their workflow",
        )

    def mine_baselines(self, problem: NormalizedProblem, count: int) -> list[IdeaCandidate]:
        templates = [
            ("Add a checklist", "Use a standard checklist to guide each participant."),
            ("Add a meeting", "Schedule a recurring meeting so information is shared."),
            ("Add a dashboard", "Display progress metrics so people can monitor work."),
        ]
        return [self._candidate(problem, title, desc, "baseline", i) for i, (title, desc) in enumerate(templates[:count])]

    def generate(self, problem, operator, private_history, count):
        ops = {
            "Inversion": ("Reverse the usual information flow", "The recipient initiates a signal that causes the provider to adapt."),
            "Extreme constraints": ("Design for one minute", "A tiny input triggers an automated default and removes coordination cost."),
            "Removal": ("Remove the meeting", "Asynchronous evidence replaces synchronized discussion and preserves accountability."),
            "Cross-domain analogy": ("Borrow from ecosystems", "Local signals cause neighboring participants to share resources when capacity changes."),
            "Role shift": ("Move ownership to the user", "The person experiencing friction decides the next action and receives immediate feedback."),
            "Multilingual/cultural conceptualization": ("Use reciprocity as a lens", "A reciprocal exchange makes each action create a visible benefit for another participant."),
        }
        title, desc = ops.get(operator, ("Adaptive experiment", "A small reversible experiment creates feedback before commitment."))
        return [self._candidate(problem, title, desc, operator, i) for i in range(count)]

    def canonicalize(self, problem, candidate):
        if candidate.mechanism:
            return candidate
        link = CausalLink(cause=candidate.title, relation="increases", effect="lower friction")
        return candidate.model_copy(update={"mechanism": CanonicalMechanism(
            core_mechanism=candidate.description, causal_structure=(link,),
            affected_system=problem.affected_system, payoff="lower friction",
        )})

    def assess(self, problem, candidate):
        return EvaluationScores(novelty=.8, appropriateness=.75, utility=.7, surprise=.7, coherence=.85, mechanism_uniqueness=.8)

    def describe_niche(self, problem, candidate):
        choices: list[tuple[Any, Any, Any]] = [
            ("individual", "low", "immediate"),
            ("team", "medium", "short"),
            ("organization", "high", "long"),
        ]
        lvl, res, hor = choices[int(candidate.id[-2:], 16) % len(choices)]
        return NicheDescriptor(intervention_level=lvl, resource_intensity=res, feedback_horizon=hor)

    def _candidate(self, problem, title, description, operator, index):
        return IdeaCandidate(
            id=stable_id(problem.id, operator, str(index), title), problem_id=problem.id,
            title=title, description=description, operator=operator,
            provenance=Provenance(provider_mode="mock"),
        )


class LLMIdeaProvider:
    mode = "llm"

    def __init__(self, base_url: str | None = None, model: str = "Hermes-delegate", api_key: str | None = None):
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL", "http://127.0.0.1:20128/v1")).rstrip("/")
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")

    def _call(self, prompt: str, system: str = "You are a specialized game design and ideation engine. Output strictly valid JSON without preamble.") -> Any:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a creative systems architect and game designer. Always output strict, valid JSON without extra chat or conversational filler."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.85,
            "stream": False,
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"].strip()
        # Strip markdown fences if present
        if content.startswith("```"):
            lines = content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines).strip()
        return json.loads(content)

    def normalize(self, problem: str) -> NormalizedProblem:
        prompt = (
            f"Analyze this problem/design goal: '{problem}'\n"
            "Return JSON with:\n"
            "- objective: clear primary objective\n"
            "- constraints: list of constraints or negative conditions\n"
            "- affected_system: target system name (e.g. 'boss combat encounter', 'inventory system')\n"
        )
        try:
            res = self._call(prompt)
            return NormalizedProblem(
                id=stable_id(problem),
                original_prompt=problem,
                objective=res.get("objective", problem),
                constraints=tuple(res.get("constraints", ())),
                affected_system=res.get("affected_system", "core gameplay system"),
            )
        except Exception:
            return MockIdeaProvider().normalize(problem)

    def mine_baselines(self, problem: NormalizedProblem, count: int) -> list[IdeaCandidate]:
        prompt = (
            f"Problem: {problem.objective}\n"
            f"Affected system: {problem.affected_system}\n"
            f"Generate exactly {count} most CLICHÉ, PREDICTABLE, OBVIOUS baseline ideas/solutions that typical designers default to.\n"
            "Return JSON array of objects with keys: 'title', 'description'."
        )
        try:
            items = self._call(prompt)
            candidates = []
            for i, it in enumerate(items[:count]):
                candidates.append(IdeaCandidate(
                    id=stable_id(problem.id, "baseline", str(i), it["title"]),
                    problem_id=problem.id,
                    title=it["title"],
                    description=it["description"],
                    operator="baseline",
                    provenance=Provenance(provider_mode="llm", source_domain="baseline-miner"),
                ))
            return candidates
        except Exception:
            return MockIdeaProvider().mine_baselines(problem, count)

    def generate(self, problem: NormalizedProblem, operator: str, private_history: Any, count: int) -> list[IdeaCandidate]:
        operator_guides = {
            "Inversion": "Invert standard cause-and-effect or flip the direction of power/agency.",
            "Extreme constraints": "Eliminate 90% of resources, buttons, or time; make the severe constraint the core mechanic.",
            "Removal": "Identify a foundational assumption everyone takes for granted in this genre and completely delete it.",
            "Cross-domain analogy": "Extract an abstract causal mechanism from an external field (biology, fluid dynamics, logistics, economics) and map it structurally onto the mechanic.",
            "Role shift": "Shift ownership/control dynamically between player, enemy, and environment.",
            "Multilingual/cultural conceptualization": "Anchor the mechanic around a non-Western cultural or philosophical concept (e.g. Jeong, Ma, Wabi-sabi, Han, Ubuntu).",
        }
        guide = operator_guides.get(operator, "Divergent mutation")
        prompt = (
            f"Design Goal: {problem.objective}\n"
            f"Target System: {problem.affected_system}\n"
            f"Constraints: {list(problem.constraints)}\n"
            f"Assigned Mutation Operator: [{operator}]\n"
            f"Operator Directive: {guide}\n\n"
            f"Generate {count} highly creative, mechanically concrete, playable game mechanic concept(s).\n"
            "Return JSON array of objects with keys:\n"
            "- 'title': concise name\n"
            "- 'description': concrete gameplay mechanics\n"
            "- 'core_mechanism': 1-sentence underlying mechanical causal logic\n"
            "- 'causal_structure': list of {'cause': string, 'relation': 'increases'|'decreases'|'enables'|'prevents'|'depends_on', 'effect': string}\n"
            "- 'payoff': tactical tension or gameplay payoff\n"
            "- 'niche': {'intervention_level': 'individual'|'team'|'organization'|'ecosystem', 'resource_intensity': 'low'|'medium'|'high', 'feedback_horizon': 'immediate'|'short'|'long'}\n"
        )
        try:
            items = self._call(prompt)
            candidates = []
            valid_relations = {"increases", "decreases", "enables", "prevents", "depends_on"}
            for i, it in enumerate(items[:count]):
                links = []
                for c in it.get("causal_structure", []):
                    rel = c.get("relation", "enables").lower()
                    if rel not in valid_relations:
                        rel = "enables"
                    links.append(CausalLink(cause=c.get("cause", ""), relation=rel, effect=c.get("effect", "")))
                mech = CanonicalMechanism(
                    core_mechanism=it.get("core_mechanism", it.get("description", "")),
                    causal_structure=tuple(links) if links else (CausalLink(cause=it["title"], relation="enables", effect="payoff"),),
                    affected_system=problem.affected_system,
                    payoff=it.get("payoff", "tactical dynamic"),
                )
                niche_data = it.get("niche", {})
                lvl = niche_data.get("intervention_level", "individual")
                if lvl not in ("individual", "team", "organization", "ecosystem"):
                    lvl = "individual"
                res_int = niche_data.get("resource_intensity", "medium")
                if res_int not in ("low", "medium", "high"):
                    res_int = "medium"
                hor = niche_data.get("feedback_horizon", "short")
                if hor not in ("immediate", "short", "long"):
                    hor = "short"
                
                cand = IdeaCandidate(
                    id=stable_id(problem.id, operator, str(i), it["title"]),
                    problem_id=problem.id,
                    title=it["title"],
                    description=it["description"],
                    operator=operator,
                    mechanism=mech,
                    provenance=Provenance(provider_mode="llm", source_domain=operator),
                )
                # Cache niche descriptor on object to avoid extra roundtrips
                setattr(cand, "_cached_niche", NicheDescriptor(intervention_level=lvl, resource_intensity=res_int, feedback_horizon=hor))
                candidates.append(cand)
            return candidates
        except Exception:
            return MockIdeaProvider().generate(problem, operator, private_history, count)

    def canonicalize(self, problem: NormalizedProblem, candidate: IdeaCandidate) -> IdeaCandidate:
        if candidate.mechanism:
            return candidate
        prompt = (
            f"Deconstruct this mechanic into its core causal mechanism structure.\n"
            f"Title: {candidate.title}\n"
            f"Description: {candidate.description}\n"
            f"System: {problem.affected_system}\n"
            "Return JSON object with keys:\n"
            "- core_mechanism: concise 1-sentence summary of the underlying mechanical logic\n"
            "- causal_structure: list of objects with {'cause': string, 'relation': string ('increases'|'decreases'|'triggers'|'inverts'), 'effect': string}\n"
            "- affected_system: specific subsystem affected\n"
            "- payoff: what tactical tension or emotional dynamic this creates"
        )
        try:
            res = self._call(prompt)
            valid_relations = {"increases", "decreases", "enables", "prevents", "depends_on"}
            def clean_rel(r: str) -> Any:
                r = r.lower().strip()
                if r in valid_relations:
                    return r
                if "inc" in r or "amp" in r:
                    return "increases"
                if "dec" in r or "reduc" in r:
                    return "decreases"
                if "prev" in r or "block" in r or "stop" in r:
                    return "prevents"
                if "dep" in r or "need" in r or "req" in r:
                    return "depends_on"
                return "enables"

            links = tuple(
                CausalLink(cause=x.get("cause", ""), relation=clean_rel(x.get("relation", "enables")), effect=x.get("effect", ""))
                for x in res.get("causal_structure", [])
            )
            mech = CanonicalMechanism(
                core_mechanism=res.get("core_mechanism", candidate.description),
                causal_structure=links if links else (CausalLink(cause=candidate.title, relation="enables", effect="tactical feedback"),),
                affected_system=res.get("affected_system", problem.affected_system),
                payoff=res.get("payoff", "tactical dynamic"),
            )
            return candidate.model_copy(update={"mechanism": mech})
        except Exception:
            return MockIdeaProvider().canonicalize(problem, candidate)

    def assess(self, problem: NormalizedProblem, candidate: IdeaCandidate) -> EvaluationScores:
        prompt = (
            f"Evaluate this candidate mechanic on 6 independent dimensions (0.0 to 1.0):\n"
            f"Objective: {problem.objective}\n"
            f"Title: {candidate.title}\n"
            f"Description: {candidate.description}\n"
            "Dimensions:\n"
            "- novelty: how surprising and unprecedented is this mechanic? (0=cliché, 1=groundbreaking)\n"
            "- appropriateness: does it fit the genre and actually solve the objective? (0=irrelevant/broken, 1=ideal)\n"
            "- utility: how deep is the gameplay and player decision-making? (0=shallow gimmick, 1=rich mastery)\n"
            "- surprise: does it create a delightful 'aha' moment? (0=predictable, 1=mind-bending)\n"
            "- coherence: is the mechanical logic intuitive and non-contradictory? (0=confusing, 1=crystal clear)\n"
            "- mechanism_uniqueness: how distinct is the causal chain from standard gaming tropes? (0=standard, 1=unique)\n"
            "Return JSON with float values for: novelty, appropriateness, utility, surprise, coherence, mechanism_uniqueness"
        )
        try:
            res = self._call(prompt)
            return EvaluationScores(
                novelty=float(res.get("novelty", 0.7)),
                appropriateness=float(res.get("appropriateness", 0.8)),
                utility=float(res.get("utility", 0.75)),
                surprise=float(res.get("surprise", 0.7)),
                coherence=float(res.get("coherence", 0.8)),
                mechanism_uniqueness=float(res.get("mechanism_uniqueness", 0.75)),
            )
        except Exception:
            return MockIdeaProvider().assess(problem, candidate)

    def describe_niche(self, problem: NormalizedProblem, candidate: IdeaCandidate) -> NicheDescriptor:
        cached = getattr(candidate, "_cached_niche", None)
        if cached is not None:
            return cached
        prompt = (
            f"Classify this mechanic into the MAP-Elites behavioral niche dimensions:\n"
            f"Title: {candidate.title}\n"
            f"Description: {candidate.description}\n"
            "Options:\n"
            "- intervention_level: 'individual' (single player only) | 'team' (cooperative/allies) | 'organization' (boss+minions/squad) | 'ecosystem' (whole environment/ambient world)\n"
            "- resource_intensity: 'low' | 'medium' | 'high'\n"
            "- feedback_horizon: 'immediate' | 'short' | 'long'\n"
            "Return JSON with keys: intervention_level, resource_intensity, feedback_horizon"
        )
        try:
            res = self._call(prompt)
            lvl = res.get("intervention_level", "individual")
            if lvl not in ("individual", "team", "organization", "ecosystem"):
                lvl = "individual"
            res_int = res.get("resource_intensity", "medium")
            if res_int not in ("low", "medium", "high"):
                res_int = "medium"
            hor = res.get("feedback_horizon", "short")
            if hor not in ("immediate", "short", "long"):
                hor = "short"
            return NicheDescriptor(intervention_level=lvl, resource_intensity=res_int, feedback_horizon=hor)
        except Exception:
            return MockIdeaProvider().describe_niche(problem, candidate)
