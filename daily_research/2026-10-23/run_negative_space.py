"""Daily QD run 2026-10-23 -- H-20261023 'Negative-Space Engine' (AR-2 earned inhibition), per-context runs.

Real pipeline only: IdeationHarness + QDArchive + CentroidNicheSpace + deterministic verifiers.
LLM (strict=True, no silent mock fallback) is confined to: normalize / baselines / role-mapping backend / assess / niche.
Everything downstream (structure validation, red-team playtest, WL fingerprint, isomorphism/inversion/dialectic
verification, archive admission) is deterministic and LLM-free.

Modes:
  control  : MockIdeaProvider + default scripted backends (zero network) -> baseline for comparison
  llm      : LLMIdeaProvider(strict) + RotatingBlend over the new template library
  audit    : re-verify a dumped archive from disk, independent of the run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter

ROOT = "/home/arcturus/hermesWorkspace/projects/CounterField"
OUT = f"{ROOT}/daily_research/2026-10-23"
sys.path.insert(0, ROOT)

import networkx as nx  # noqa: E402

import creative_agent.harness as harness_mod  # noqa: E402
from creative_agent.archive import QDArchive  # noqa: E402
from creative_agent.creativity import (  # noqa: E402
    BlendOperator, CEGISGuidedSynthesizer, CentroidNicheSpace, InversionOperator, IsomorphismContext,
    IsomorphismLineageVerifier, IsomorphismVerifier, MotifExtractor, MotifProfile, TemplateLibrary,
    InversionContext, InversionLineageVerifier, structural_fingerprint,
)
from creative_agent.creativity.isomorphism import _tokens, default_templates  # noqa: E402
from creative_agent.dsl import canonical_mechanism_to_dsl  # noqa: E402
from creative_agent.harness import IdeationHarness  # noqa: E402
from creative_agent.models import (  # noqa: E402
    CanonicalMechanism, CausalLink, CreativeLineage, HarnessConfig, IdeaCandidate, IsomorphismEvidence,
    InversionEvidence, Provenance, stable_id,
)
from creative_agent.providers import LLMIdeaProvider, MockIdeaProvider  # noqa: E402
from creative_agent.qd import dynamical_niche_descriptor  # noqa: E402
from creative_agent.redteam import AdversarialPlaytester  # noqa: E402
from creative_agent.verifier import CausalGraphValidator  # noqa: E402

PROBLEMS = {
    "team": ("Design a hypothesis-triage practice for a small research team of 4-8 people. "
             "Premature consensus increases wasted effort. Unfalsifiable claims decrease trust in results. "
             "Over-polished ideas prevent honest critique. Every added idea increases review load."),
    "organization": ("Design an organization-wide portfolio process that decides which of hundreds of competing research hypotheses get funded. "
                     "Sunk cost increases escalation. Reporting overhead decreases experimentation speed. "
                     "Prestige bias prevents unusual ideas from surviving review."),
    "ecosystem": ("Design a norm and incentive layer for an open ecosystem of independent labs sharing hypotheses publicly. "
                  "Herding increases monoculture. Duplicate effort decreases collective discovery rate. "
                  "Unretracted errors prevent reliable reuse."),
}
PROBLEM = PROBLEMS["team"]
TEMPLATE_JSON = f"{ROOT}/data/templates/negative_space_v3_20261023.json"
VALID_REL = ("increases", "decreases", "enables", "prevents", "depends_on")
HIGH_NOVELTY = 0.70  # fixed a priori


# ----------------------------------------------------------------------------- archive recorder (no core edits)
class RecArchive(QDArchive):
    LAST: "RecArchive | None" = None

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        RecArchive.LAST = self


harness_mod.QDArchive = RecArchive


# ----------------------------------------------------------------------------- LLM blend backend
class Stats:
    def __init__(self):
        self.c = Counter()


def make_llm_backend(provider: LLMIdeaProvider, stats: Stats):
    def backend(ctx, template, motifs):
        banned = sorted(_tokens(" ".join(template.roles)) | _tokens(" ".join(template.domain_vocabulary)))
        links_txt = "\n".join(f"  {l.cause} --{l.relation}--> {l.effect}" for l in template.links)
        feedback = ""
        for attempt in range(3):
            prompt = f"""You are the role-mapping stage of a Quality-Diversity ideation engine.
PROBLEM: {ctx.problem.original_prompt}
TARGET SYSTEM: {ctx.problem.affected_system}

SOURCE MECHANISM (domain: {template.domain}; ref: {template.source_ref}). Abstract causal skeleton:
roles = {list(template.roles)}
{links_txt}
In the source domain the benefit exists because an EARNED INHIBITION (a `prevents`/`decreases` edge) suppresses a side-branch inside a race window: the payoff is produced by something that is KEPT FROM HAPPENING (negative space). Preserve that inhibitory edge in the projection.

TASK: project this skeleton onto the PROBLEM by assigning each role a concrete, distinct concept of the problem
domain (hypothesis triage, review, funding, retraction, critique, incentives, reuse of results...).
Do NOT reuse the source-domain vocabulary. FORBIDDEN tokens inside any label (case-insensitive): {banned}
Then add 2-4 'extra_links' (problem-specific closure) between your labels or new nodes; use relations only from {list(VALID_REL)}.
Never add an extra link between the same (cause,effect) pair as a skeleton link. The last role is the payoff.
{feedback}
Return ONLY JSON:
{{"title": "...", "description": "concrete mechanism, 2-3 sentences, what the person actually experiences",
  "core_mechanism": "one sentence", "role_map": {{"<role>": "<label>", ...every role...}},
  "extra_links": [{{"cause":"..","relation":"..","effect":".."}}]}}"""
            res = provider._call(prompt)
            rm = {r: " ".join(str(res["role_map"][r]).split()) for r in template.roles}
            norm = {r: v.casefold() for r, v in rm.items()}
            if len(set(norm.values())) != len(norm):
                feedback = "PREVIOUS ATTEMPT INVALID: labels were not distinct."; stats.c["retry_not_injective"] += 1; continue
            bad = [(r, v) for r, v in rm.items() if v.casefold() == r.casefold() or (_tokens(v) & set(banned))]
            if bad:
                feedback = f"PREVIOUS ATTEMPT INVALID: forbidden vocabulary in {bad}."; stats.c["retry_surface_copy"] += 1; continue
            mapped = tuple(CausalLink(cause=rm[l.cause], relation=l.relation, effect=rm[l.effect]) for l in template.links)
            pairs = {(l.cause.casefold(), l.effect.casefold()) for l in mapped}
            extra = []
            for e in res.get("extra_links", [])[:4]:
                rel, c, f = str(e.get("relation", "")).strip().lower(), str(e.get("cause", "")).strip(), str(e.get("effect", "")).strip()
                if rel in VALID_REL and c and f and c.casefold() != f.casefold() and (c.casefold(), f.casefold()) not in pairs:
                    pairs.add((c.casefold(), f.casefold())); extra.append(CausalLink(cause=c, relation=rel, effect=f))
            payoff = rm[template.roles[-1]]
            mech = CanonicalMechanism(core_mechanism=str(res.get("core_mechanism", ""))[:400] or f"{template.id} projection",
                                      causal_structure=mapped + tuple(extra), affected_system=ctx.problem.affected_system, payoff=payoff)
            stats.c["backend_ok"] += 1
            return IdeaCandidate(
                id=stable_id(ctx.problem.id, "isomorphism", str(ctx.slot), template.id), problem_id=ctx.problem.id,
                title=str(res.get("title", template.id))[:160], description=str(res.get("description", ""))[:900],
                mechanism=mech, operator="isomorphism", provenance=Provenance(provider_mode="llm", source_domain=template.domain),
                lineage=CreativeLineage(operator="isomorphism", parent_ids=(), evidence=IsomorphismEvidence(template_id=template.id, role_map=rm)))
        stats.c["backend_gave_up"] += 1
        return None
    return backend


class RotatingBlend(BlendOperator):
    """Visits every template evenly (the stock matcher only ever uses the top-3 motif matches)."""

    def __init__(self, library, backend):
        super().__init__(library, backend=backend)
        self.n = 0

    def propose(self, ctx):
        ts = sorted(self.library.templates, key=lambda t: t.id)
        template = ts[self.n % len(ts)]
        self.n += 1
        c = self.backend(ctx, template, MotifProfile())
        return [c] if c is not None else []


# ----------------------------------------------------------------------------- dump
def dump_archive(arch: RecArchive, result, extra_meta: dict) -> dict:
    log = Counter((e.candidate.operator, a.status.value, a.stage.value) for e, a in arch.admission_log)
    def row(key, e):
        m = e.candidate.mechanism
        ev = e.candidate.lineage.evidence.model_dump(mode="json") if e.candidate.lineage and e.candidate.lineage.evidence else None
        return {
            "niche_key": key, "id": e.candidate.id, "title": e.candidate.title, "description": e.candidate.description,
            "operator": e.candidate.operator, "source_domain": e.candidate.provenance.source_domain,
            "provider_mode": e.candidate.provenance.provider_mode,
            "mechanism": m.model_dump(mode="json"), "mechanism_fingerprint": m.fingerprint,
            "wl_hash": structural_fingerprint(m), "lineage_evidence": ev,
            "scores": e.scores.model_dump(mode="json"),
            "niche": e.niche.model_dump(mode="json"), "dynamics": e.dynamics.model_dump(mode="json") if e.dynamics else None,
            "admission": e.evaluation.admission.model_dump(mode="json") if e.evaluation else None,
            "playtest_issues": [i.model_dump(mode="json") for i in (e.diagnostics.playtest_report.issues if e.diagnostics.playtest_report else [])],
        }
    rows = [row(k, e) for k, e in sorted(arch.elites.items())]
    elite_ids = {e.candidate.id for e in arch.elites.values()}
    admitted, seen = [], set()
    for e, a in arch.admission_log:
        if a.status.value == "ACCEPTED" and e.candidate.id in arch.seen_ids and e.candidate.id not in seen:
            seen.add(e.candidate.id)
            admitted.append({**row(arch._niche_key(e), e), "is_niche_elite": e.candidate.id in elite_ids})
    return {"meta": extra_meta, "metrics": result.metrics,
            "admission_log": [{"operator": k[0], "status": k[1], "stage": k[2], "n": n} for k, n in sorted(log.items())],
            "centroids": [list(c) for c in getattr(arch.niche_space, "centroids", ())],
            "elites": rows, "admitted": admitted}


# ----------------------------------------------------------------------------- run modes
def run(mode: str, budget: int, seed: int, ctx: str = "team"):
    global PROBLEM
    PROBLEM = PROBLEMS[ctx]
    t0 = time.time()
    stats = Stats()
    if mode == "control":
        provider = MockIdeaProvider()
        lib = TemplateLibrary(default_templates())
        ops = [BlendOperator(lib), BlendOperator(lib), InversionOperator(), BlendOperator(lib)]
        ops = [ops[0], InversionOperator()]
    else:
        import os
        provider = LLMIdeaProvider(model="cc/claude-sonnet-5-5", strict=True, timeout=120.0,
                                   api_key=os.environ["NINE_ROUTER_API_KEY"])
        lib = TemplateLibrary.from_json(TEMPLATE_JSON)
        blend = RotatingBlend(lib, make_llm_backend(provider, stats))
        ops = [blend, blend, InversionOperator(), blend]
    h = IdeationHarness(provider, operators=ops, synthesizer=CEGISGuidedSynthesizer(),
                        niche_space=CentroidNicheSpace(rho=0.2))
    cfg = HarnessConfig(generations=4, population_size=max(1, budget // 4), total_budget=budget, seed=seed)
    result = h.run(PROBLEM, cfg)
    arch = RecArchive.LAST
    meta = {"mode": mode, "context": ctx, "date": "2026-10-23", "seed": seed, "budget": budget, "problem": PROBLEM,
            "provider": type(provider).__name__, "model": getattr(provider, "model", None),
            "provider_fallbacks": getattr(provider, "fallbacks", 0), "backend_stats": dict(stats.c),
            "template_library": TEMPLATE_JSON if mode == "llm" else "default_templates()", "wall_seconds": round(time.time() - t0, 1)}
    data = dump_archive(arch, result, meta)
    path = f"{OUT}/archive_{mode}_{ctx}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(json.dumps({"mode": mode, "elites": len(arch.elites), "admitted": len(data["admitted"]), "metrics": result.metrics, "meta": meta}, ensure_ascii=False, indent=1))
    print("wrote", path)


# ----------------------------------------------------------------------------- independent audit (zero LLM)
def audit(mode: str, ctx: str = "team"):
    data = json.load(open(f"{OUT}/archive_{mode}_{ctx}.json", encoding="utf-8"))
    lib = TemplateLibrary.from_json(TEMPLATE_JSON) if mode == "llm" else TemplateLibrary(default_templates())
    validator, iso, tester = CausalGraphValidator(), IsomorphismVerifier(), AdversarialPlaytester()
    results, wl, fps = [], set(), set()
    for r in data["admitted"]:
        m = CanonicalMechanism.model_validate(r["mechanism"])
        rep = validator.validate(m)
        pt = tester.run_playtest(canonical_mechanism_to_dsl(m))
        fatal = [i.issue_type for i in pt.issues if i.severity == "FATAL"]
        dyn = dynamical_niche_descriptor(m)
        g = nx.DiGraph(); g.add_edges_from((l.cause.casefold(), l.effect.casefold()) for l in m.causal_structure)
        row = {"id": r["id"], "operator": r["operator"], "structural_valid": rep.is_valid, "fatal_playtest": fatal,
               "wl_hash_match": structural_fingerprint(m) == r["wl_hash"], "fp_match": m.fingerprint == r["mechanism_fingerprint"],
               "dynamics_match": dyn.model_dump(mode="json") == r["dynamics"], "payoff_in_graph": m.payoff.casefold() in g.nodes}
        ev = r["lineage_evidence"]
        if r["operator"] == "isomorphism" and ev:
            evd = IsomorphismEvidence.model_validate(ev)
            cand = IdeaCandidate(id=r["id"], problem_id="audit", title=r["title"], description=r["description"], mechanism=m,
                                 lineage=CreativeLineage(operator="isomorphism", evidence=evd))
            t = lib.get(evd.template_id)
            reasons = iso.verify(cand, evd, t, None) if t else ("unknown template",)
            row.update(iso_template=evd.template_id, iso_reasons=list(reasons), iso_verified=not reasons)
        row["pass"] = all([row["structural_valid"], not fatal, row["wl_hash_match"], row["fp_match"], row["dynamics_match"],
                           row.get("iso_verified", True)])
        results.append(row); wl.add(r["wl_hash"]); fps.add(r["mechanism_fingerprint"])
    summary = {"mode": mode, "context": ctx, "admitted": len(results), "elites": len(data["elites"]), "all_pass": all(x["pass"] for x in results),
               "failed": [x["id"] for x in results if not x["pass"]], "unique_wl_hashes": len(wl), "unique_fingerprints": len(fps)}
    json.dump({"summary": summary, "rows": results}, open(f"{OUT}/audit_{mode}_{ctx}.json", "w"), indent=2)
    print(json.dumps(summary, indent=1))
    sys.exit(0 if summary["all_pass"] else 2)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("control", "llm", "audit-control", "audit-llm"))
    ap.add_argument("--budget", type=int, default=48)
    ap.add_argument("--seed", type=int, default=20261023)
    ap.add_argument("--ctx", choices=tuple(PROBLEMS), default="team")
    a = ap.parse_args()
    if a.mode.startswith("audit-"):
        audit(a.mode.split("-", 1)[1], a.ctx)
    else:
        run(a.mode, a.budget, a.seed, a.ctx)
