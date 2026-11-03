import os
import pytest
from creative_agent.creativity.isomorphism import TemplateLibrary, CausalTemplate

def test_template_library_from_json():
    json_path = "/home/arcturus/hermesWorkspace/projects/CounterField/data/templates/geometric_mechanics.json"
    assert os.path.exists(json_path), "Curated template file must exist"
    
    lib = TemplateLibrary.from_json(json_path)
    assert len(lib.templates) == 10
    
    # Check specific templates
    wfc = lib.get("wave_function_collapse")
    assert wfc is not None
    assert wfc.domain == "constraint_satisfaction"
    assert "feedback_loop" in wfc.motifs
    assert len(wfc.roles) == 4
    assert len(wfc.links) == 4
    assert wfc.source_ref != ""
    assert len(wfc.domain_vocabulary) > 0

    tensor = lib.get("tensor_field_streamlines")
    assert tensor is not None
    assert tensor.domain == "computational_geometry"
    assert "singularity" in tensor.domain_vocabulary
