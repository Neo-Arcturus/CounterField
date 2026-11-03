import sys, json, collections
sys.path.insert(0,"/home/arcturus/hermesWorkspace/projects/CounterField")
from creative_agent.creativity import TemplateLibrary
from creative_agent.models import CanonicalMechanism, CausalLink
from creative_agent.dsl import canonical_mechanism_to_dsl
from creative_agent.redteam import AdversarialPlaytester
from creative_agent.verifier import CausalGraphValidator
lib = TemplateLibrary.from_json("data/templates/defect_harvest_20261022.json")
for t in lib.templates:
    m = CanonicalMechanism(core_mechanism="x", causal_structure=t.links, affected_system="s", payoff=t.roles[-1])
    v = CausalGraphValidator().validate(m)
    rep = AdversarialPlaytester().run_playtest(canonical_mechanism_to_dsl(m))
    print(f"{t.id:36s} valid={v.is_valid} struct_issues={[i.rule for i in v.issues]} playtest={[(i.issue_type,i.severity) for i in rep.issues]}")
a = json.load(open("daily_research/2026-10-22/archive_llm.json"))
for e in a["elites"]: print("ELITE", e["title"], e["source_domain"], e["playtest_issues"], e["scores"]["novelty"])
