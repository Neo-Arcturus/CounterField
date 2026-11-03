"""Independent post-hoc analysis for 2026-10-23 (zero LLM, zero network).

Implements PREREGISTERED_CRITERIA.md exactly. Reads dumped archives, re-derives everything from the stored mechanisms.
"""
import glob
import json
import sys
from collections import Counter

ROOT = "/home/arcturus/hermesWorkspace/projects/CounterField"
OUT = f"{ROOT}/daily_research/2026-10-23"
sys.path.insert(0, ROOT)

import networkx as nx  # noqa: E402

from creative_agent.creativity import TemplateLibrary  # noqa: E402
from creative_agent.creativity.isomorphism import default_templates  # noqa: E402
from creative_agent.creativity.novelty_audit import label_overlap, structural_novelty  # noqa: E402
from creative_agent.models import CanonicalMechanism  # noqa: E402

NOV_MIN, OVL_MAX = 0.25, 0.10
INH = {"prevents", "decreases"}


def links_of(m):
    return tuple(m.causal_structure)


def negative_space(m):
    g = nx.DiGraph(); inh = []
    for l in m.causal_structure:
        g.add_edge(l.cause.casefold(), l.effect.casefold(), relation=l.relation)
    sources = {n for n in g if g.in_degree(n) == 0}
    for u, v, d in g.edges(data=True):
        if d["relation"] in INH and u not in sources:
            inh.append((u, v))
    pruned = nx.DiGraph((u, v) for u, v, d in g.edges(data=True) if d["relation"] not in INH)
    pay = m.payoff.casefold()
    buffer_ok = any(pay in pruned and pruned.has_node(s) and nx.has_path(pruned, s, pay) for s in sources if s != pay)
    return bool(inh) and buffer_ok, len(inh)


def main():
    prior_corpus, prior_names = [], []
    for f in ("2026-10-22/archive_llm.json", "2026-10-22/archive_control.json"):
        d = json.load(open(f"{ROOT}/daily_research/{f}", encoding="utf-8"))
        for r in d["admitted"]:
            prior_corpus.append(links_of(CanonicalMechanism.model_validate(r["mechanism"]))); prior_names.append(f"{f}:{r['id']}")
    tmpl = {}
    for name, lib in (("default12", TemplateLibrary(default_templates())),
                      ("geometric10", TemplateLibrary.from_json(f"{ROOT}/data/templates/geometric_mechanics.json")),
                      ("defect10", TemplateLibrary.from_json(f"{ROOT}/data/templates/defect_harvest_v2_20261022.json")),
                      ("negspace10", TemplateLibrary.from_json(f"{ROOT}/data/templates/negative_space_v3_20261023.json"))):
        for t in lib.templates:
            tmpl[t.id] = tuple(t.links)
    rows, seen = [], set()
    for path in sorted(glob.glob(f"{OUT}/archive_*_*.json")):
        d = json.load(open(path, encoding="utf-8"))
        ctx, mode = d["meta"].get("context", "?"), d["meta"]["mode"]
        for r in d["admitted"]:
            m = CanonicalMechanism.model_validate(r["mechanism"])
            if m.fingerprint in seen:
                continue
            seen.add(m.fingerprint)
            ev = r.get("lineage_evidence") or {}
            own = ev.get("template_id")
            corpus = list(prior_corpus) + [v for k, v in tmpl.items() if k != own]
            ls = links_of(m)
            nov, ovl = structural_novelty(ls, corpus), label_overlap(ls, corpus)
            deriv = structural_novelty(ls, [tmpl[own]]) if own in tmpl else None
            # within-batch (peer) structural distance: nearest other admitted candidate of today
            ns, nin = negative_space(m)
            fatal = [i for i in r["playtest_issues"] if i.get("severity") == "FATAL"]
            rows.append({"ctx": ctx, "mode": mode, "id": r["id"], "title": r["title"], "operator": r["operator"],
                         "template": own, "source_domain": r["source_domain"], "wl_hash": r["wl_hash"],
                         "fingerprint": m.fingerprint, "intervention_level": r["niche"]["intervention_level"],
                         "structural_novelty": round(nov, 4), "label_overlap": round(ovl, 4),
                         "derivation_distance": None if deriv is None else round(deriv, 4),
                         "negative_space": ns, "n_inhibitory_nonsource": nin, "n_links": len(ls), "fatal": len(fatal),
                         "proxy_novelty": round(r["scores"]["novelty"], 4),
                         "high_novelty": bool(nov >= NOV_MIN and ovl <= OVL_MAX and not fatal)})
    # peer distance
    for i, r in enumerate(rows):
        me = links_of(CanonicalMechanism.model_validate(next(x for x in
             (y for p in glob.glob(f"{OUT}/archive_*_*.json") for y in json.load(open(p))["admitted"]) if x["id"] == r["id"])["mechanism"]))
        others = [links_of(CanonicalMechanism.model_validate(x["mechanism"])) for p in glob.glob(f"{OUT}/archive_*_*.json")
                  for x in json.load(open(p))["admitted"] if x["id"] != r["id"]]
        r["peer_structural_novelty"] = round(structural_novelty(me, others), 4) if others else None
    for mode in ("llm", "control"):
        sub = [r for r in rows if r["mode"] == mode]
        if not sub:
            continue
        print(f"[{mode}] unique admitted={len(sub)} unique WL={len({r['wl_hash'] for r in sub})} "
              f"high_novelty={sum(r['high_novelty'] for r in sub)} negative_space={sum(r['negative_space'] for r in sub)} "
              f"levels={dict(Counter(r['intervention_level'] for r in sub))} by_ctx={dict(Counter(r['ctx'] for r in sub))}")
    summ = {"criteria": {"structural_novelty_min": NOV_MIN, "label_overlap_max": OVL_MAX},
            "corpus_size_prior_admitted": len(prior_corpus), "corpus_size_templates": len(tmpl), "rows": rows}
    json.dump(summ, open(f"{OUT}/novelty_audit_report.json", "w"), ensure_ascii=False, indent=2)
    for r in rows:
        print(f"{r['mode'][:3]} {r['ctx'][:4]} {r['operator'][:4]} nov={r['structural_novelty']:.3f} ovl={r['label_overlap']:.3f} "
              f"deriv={r['derivation_distance']} peer={r['peer_structural_novelty']} neg={int(r['negative_space'])} "
              f"HN={int(r['high_novelty'])} lvl={r['intervention_level'][:4]} {r['template']} | {r['title'][:50]}")


if __name__ == "__main__":
    main()
