import sys; sys.path.insert(0,".")
from creative_agent.creativity.template_lint import lint_template
from creative_agent.creativity.isomorphism import TemplateLibrary, default_templates
for name, lib in [("default12", TemplateLibrary(default_templates())), ("geometric10", TemplateLibrary.from_json("data/templates/geometric_mechanics.json")), ("defect10", TemplateLibrary.from_json("data/templates/defect_harvest_20261022.json"))]:
    ok=0
    for t in lib.templates:
        r = lint_template(t); r_fast = lint_template(t, run_playtest=False)
        ok += not r
        print(f"{name:12s} {t.id:34s} {'PASS' if not r else 'FAIL'}  fast={[x[:2] for x in r_fast]} full={[x[:2] for x in r]}")
    print(name, "pass", ok, "/", len(lib.templates))
