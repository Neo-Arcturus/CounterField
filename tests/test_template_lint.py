import json
import os

import pytest

from creative_agent.creativity.isomorphism import CausalTemplate, TemplateLibrary, default_templates
from creative_agent.creativity.template_lint import lint_template
from creative_agent.models import CausalLink

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V2 = os.path.join(ROOT, "data", "templates", "defect_harvest_v2_20261022.json")


def tpl(roles, specs, tid="t"):
    return CausalTemplate(
        id=tid, domain="d", roles=tuple(roles),
        links=tuple(CausalLink(cause=a, relation=r, effect=b) for a, r, b in specs),
        motifs=(), curated_by="x", source_ref="ref")


def rules(reasons):
    return {r.split(":")[0] for r in reasons}


def test_r1_no_exogenous_source():
    t = tpl(["a", "b", "z"], [("a", "enables", "b"), ("b", "enables", "a"), ("b", "enables", "z")])
    assert "R1" in rules(lint_template(t, run_playtest=False))


def test_r2_positive_cycle_deadlock():
    t = tpl(["s", "a", "b", "z"], [("s", "enables", "a"), ("a", "increases", "b"), ("b", "increases", "a"), ("b", "enables", "z")])
    assert "R2" in rules(lint_template(t, run_playtest=False))


def test_r3_inhibitory_from_exogenous_source():
    t = tpl(["s", "a", "z"], [("s", "prevents", "a"), ("a", "enables", "z"), ("s", "enables", "z")])
    assert "R3" in rules(lint_template(t, run_playtest=False))


def test_clean_template_passes_all_rules_including_playtest():
    t = tpl(["s", "a", "z"], [("s", "enables", "a"), ("a", "enables", "z")])
    assert lint_template(t) == ()


def test_r4_is_ground_truth_and_explained_by_cheap_rules_on_known_templates():
    # Every shipped template that the real red-team flags must also be flagged by a cheap rule (no unexplained R4-only
    # failures except the documented 'niche_differentiation' mutual-inhibition case).
    unexplained = []
    for t in default_templates():
        fast, full = lint_template(t, run_playtest=False), lint_template(t)
        if full and not fast:
            unexplained.append(t.id)
    assert unexplained == ["niche_differentiation"]


def test_defect_harvest_v2_library_is_schedulable_and_referenced():
    lib = TemplateLibrary.from_json(V2)
    assert len(lib.templates) == 10
    assert len({t.domain for t in lib.templates}) == 10
    for t in lib.templates:
        assert t.source_ref.strip() and t.domain_vocabulary
        assert lint_template(t) == (), t.id


def test_defect_harvest_v2_json_lint_marker_matches_reality():
    data = json.load(open(V2, encoding="utf-8"))
    assert all(t["meta"]["lint"] == "R1-R4 pass" for t in data["templates"])
