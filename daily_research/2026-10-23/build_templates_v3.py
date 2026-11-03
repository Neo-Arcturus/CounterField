"""Adapter rule AR-2 'Earned Inhibition / Race-Window Gate' -- template library v3 (H-20261023 'Negative-Space Engine').

Axiom inverted (Invariant Inversion):  mainstream QD/ideation engines treat *absence / pruning / prevention* as a cost
(a rejected candidate is a lost candidate) and optimise by ADDING mechanisms.  Here the load-bearing causal edge of
every source mechanism is a `prevents`/`decreases` edge: the benefit is produced by something that is *kept from
happening*.  Each template is a published mechanism from a distant field whose payoff exists only because an
inhibitor fires inside a race window.

AR-2 (new adapter rule, extends AR-1):
  * An inhibitory edge is legal iff its CAUSE is a derived (non-source) node, i.e. the inhibitor has to be *earned*
    by an upstream positive chain (R3 stays: never inhibit from an exogenous source).
  * The inhibited node is a side-branch that is enabled by its own exogenous source (the thing to be suppressed
    exists first, then the earned inhibitor erases its effect before the payoff gate) -- the race window.
  * The payoff must remain reachable through positive edges only (buffer path), so removing the inhibitory edge
    never severs solvability (compatible with the Axiomatic-Inversion buffer-path invariant).
Every template must pass creative_agent.creativity.template_lint.lint_template (R1-R4).
"""
import json
import sys

ROOT = "/home/arcturus/hermesWorkspace/projects/CounterField"
sys.path.insert(0, ROOT)

from creative_agent.creativity.isomorphism import CausalTemplate, MotifExtractor  # noqa: E402
from creative_agent.creativity.template_lint import lint_template  # noqa: E402
from creative_agent.models import CausalLink  # noqa: E402

CURATOR = "Minerva Lead 2026-10-23 (Negative-Space Engine H-20261023, AR-2 earned-inhibition)"
E, I, P, D = "enables", "increases", "prevents", "decreases"

T = [
    dict(id="serotiny_fire_gated_release", domain="fire_ecology",
         roles=["canopy_seed_store", "heat_pulse", "understory_fuel", "ground_combustion", "resin_seal_melt",
                "shade_competitor_growth", "open_seedbed", "regeneration_flush"],
         links=[("heat_pulse", E, "ground_combustion"), ("understory_fuel", E, "ground_combustion"),
                ("ground_combustion", E, "resin_seal_melt"), ("canopy_seed_store", E, "resin_seal_melt"),
                ("ground_combustion", P, "shade_competitor_growth"),
                ("ground_combustion", E, "open_seedbed"), ("resin_seal_melt", E, "regeneration_flush"),
                ("open_seedbed", E, "regeneration_flush")],
         ref="Lamont, Enright & He 1991, Canopy seed storage in woody plants, Botanical Review 57(4):277-317; Keeley & Zedler 1998, Evolution of life histories in Pinus, in Ecology and Biogeography of Pinus",
         vocab=["serotiny", "serotinous", "cone", "fire", "wildfire", "pine", "resin", "canopy", "seedbed"]),
    dict(id="p53_damage_checkpoint_arrest", domain="cell_biology",
         roles=["genotoxic_lesion", "growth_mitogen", "sensor_kinase", "checkpoint_effector", "division_drive",
                "repair_window", "apoptotic_commitment", "tissue_integrity"],
         links=[("genotoxic_lesion", E, "sensor_kinase"), ("sensor_kinase", E, "checkpoint_effector"),
                ("growth_mitogen", E, "division_drive"), ("checkpoint_effector", P, "division_drive"),
                ("checkpoint_effector", E, "repair_window"), ("repair_window", E, "apoptotic_commitment"),
                ("apoptotic_commitment", E, "tissue_integrity"), ("repair_window", E, "tissue_integrity")],
         ref="Vogelstein, Lane & Levine 2000, Surfing the p53 network, Nature 408:307-310; Hartwell & Weinert 1989, Checkpoints, Science 246:629-634",
         vocab=["p53", "apoptosis", "caspase", "cell", "dna", "checkpoint", "mitosis", "tumor", "cancer"]),
    dict(id="aimd_loss_backoff_fairness", domain="network_congestion_control",
         roles=["ack_clock", "send_rate_growth", "loss_event", "window_halving", "queue_overflow_risk",
                "flow_share_equalisation", "fair_equilibrium"],
         links=[("ack_clock", I, "send_rate_growth"), ("send_rate_growth", E, "queue_overflow_risk"),
                ("loss_event", E, "window_halving"), ("send_rate_growth", E, "window_halving"),
                ("window_halving", P, "queue_overflow_risk"),
                ("window_halving", E, "flow_share_equalisation"), ("send_rate_growth", E, "flow_share_equalisation"),
                ("flow_share_equalisation", E, "fair_equilibrium")],
         ref="Chiu & Jain 1989, Analysis of the increase and decrease algorithms for congestion avoidance, Computer Networks and ISDN Systems 17(1):1-14; Jacobson 1988, Congestion avoidance and control, SIGCOMM '88",
         vocab=["tcp", "packet", "congestion", "router", "window", "aimd", "bandwidth", "ack", "queue"]),
    dict(id="notch_lateral_inhibition_pattern", domain="developmental_biology",
         roles=["proneural_bias_a", "proneural_bias_b", "delta_ligand_a", "notch_signal_b", "delta_ligand_b",
                "fate_divergence", "fine_grained_pattern"],
         links=[("proneural_bias_a", I, "delta_ligand_a"), ("delta_ligand_a", E, "notch_signal_b"),
                ("proneural_bias_b", E, "delta_ligand_b"), ("notch_signal_b", P, "delta_ligand_b"),
                ("delta_ligand_a", E, "fate_divergence"), ("notch_signal_b", E, "fate_divergence"),
                ("fate_divergence", E, "fine_grained_pattern")],
         ref="Collier, Monk, Maini & Lewis 1996, Pattern formation by lateral inhibition with feedback, J. Theor. Biol. 183(4):429-446; Heitzler & Simpson 1991, Cell 64(6):1083-1092",
         vocab=["notch", "delta", "neuroblast", "lateral", "proneural", "cell", "fate", "drosophila", "ligand"]),
    dict(id="persister_bet_hedge_survival", domain="microbiology",
         roles=["stochastic_switch", "antibiotic_exposure", "dormant_subpopulation", "growth_dependent_killing",
                "active_division", "post_exposure_regrowth", "lineage_survival"],
         links=[("stochastic_switch", E, "dormant_subpopulation"), ("antibiotic_exposure", E, "growth_dependent_killing"),
                ("active_division", E, "growth_dependent_killing"), ("dormant_subpopulation", P, "growth_dependent_killing"),
                ("dormant_subpopulation", E, "post_exposure_regrowth"), ("antibiotic_exposure", E, "post_exposure_regrowth"),
                ("post_exposure_regrowth", E, "lineage_survival")],
         ref="Balaban, Merrin, Chait, Kowalik & Leibler 2004, Bacterial persistence as a phenotypic switch, Science 305(5690):1622-1625",
         vocab=["persister", "antibiotic", "bacteria", "bacterial", "dormant", "dormancy", "microbe", "phenotypic", "kill"]),
    dict(id="vickrey_second_price_truth", domain="auction_mechanism_design",
         roles=["private_valuation", "second_price_rule", "bid_submission", "winner_selection",
                "bid_shading_incentive", "price_determination", "truthful_revelation"],
         links=[("private_valuation", E, "bid_submission"), ("bid_submission", E, "bid_shading_incentive"),
                ("bid_submission", E, "winner_selection"), ("second_price_rule", E, "price_determination"),
                ("winner_selection", E, "price_determination"), ("price_determination", P, "bid_shading_incentive"),
                ("price_determination", E, "truthful_revelation"), ("private_valuation", E, "truthful_revelation")],
         ref="Vickrey 1961, Counterspeculation, auctions, and competitive sealed tenders, J. Finance 16(1):8-37; Clarke 1971, Public Choice 11:17-33",
         vocab=["auction", "bidder", "vickrey", "bid", "valuation", "reserve", "seller", "winner", "payment"]),
    dict(id="generational_gc_reclaim_gate", domain="runtime_memory_management",
         roles=["allocation_stream", "weak_generational_hypothesis", "young_space_fill", "minor_collection",
                "heap_exhaustion_risk", "survivor_promotion", "stable_throughput"],
         links=[("allocation_stream", E, "young_space_fill"), ("young_space_fill", E, "heap_exhaustion_risk"),
                ("weak_generational_hypothesis", E, "minor_collection"), ("young_space_fill", E, "minor_collection"),
                ("minor_collection", P, "heap_exhaustion_risk"),
                ("minor_collection", E, "survivor_promotion"), ("survivor_promotion", E, "stable_throughput"),
                ("allocation_stream", E, "stable_throughput")],
         ref="Ungar 1984, Generation scavenging, ACM SIGPLAN Notices 19(5):157-167; Lieberman & Hewitt 1983, A real-time garbage collector based on the lifetimes of objects, CACM 26(6):419-429",
         vocab=["garbage", "heap", "allocation", "gc", "pointer", "malloc", "jvm", "collector", "memory"]),
    dict(id="sandpile_toppling_criticality", domain="statistical_physics",
         roles=["grain_drop", "slope_buildup", "threshold_exceedance", "toppling_cascade", "runaway_slope",
                "dissipation_at_boundary", "critical_steady_state"],
         links=[("grain_drop", I, "slope_buildup"), ("slope_buildup", E, "runaway_slope"),
                ("slope_buildup", E, "threshold_exceedance"), ("threshold_exceedance", E, "toppling_cascade"),
                ("toppling_cascade", P, "runaway_slope"),
                ("toppling_cascade", E, "dissipation_at_boundary"), ("dissipation_at_boundary", E, "critical_steady_state"),
                ("grain_drop", E, "critical_steady_state")],
         ref="Bak, Tang & Wiesenfeld 1987, Self-organized criticality: an explanation of 1/f noise, Phys. Rev. Lett. 59(4):381-384",
         vocab=["sandpile", "avalanche", "grain", "critical", "criticality", "toppling", "slope", "power", "noise"]),
    dict(id="ostrom_graduated_sanction_commons", domain="institutional_economics",
         roles=["harvest_pressure", "monitoring_by_users", "graduated_sanction_rule", "sanction_application",
                "defection_temptation", "compliance_norm", "commons_persistence"],
         links=[("harvest_pressure", E, "monitoring_by_users"), ("harvest_pressure", E, "defection_temptation"),
                ("graduated_sanction_rule", E, "sanction_application"), ("monitoring_by_users", E, "sanction_application"),
                ("sanction_application", P, "defection_temptation"),
                ("sanction_application", E, "compliance_norm"), ("compliance_norm", E, "commons_persistence"),
                ("monitoring_by_users", E, "commons_persistence")],
         ref="Ostrom 1990, Governing the Commons: The Evolution of Institutions for Collective Action, Cambridge University Press (design principles 4-5)",
         vocab=["commons", "sanction", "irrigation", "fishery", "herder", "tragedy", "ostrom", "harvest", "appropriator"]),
    dict(id="trophic_cascade_predator_gate", domain="community_ecology",
         roles=["herbivore_growth", "predator_return", "browsing_pressure", "fear_avoidance_behaviour",
                "riparian_overbrowse", "seedling_escape", "riparian_recovery"],
         links=[("herbivore_growth", E, "browsing_pressure"), ("browsing_pressure", E, "riparian_overbrowse"),
                ("predator_return", E, "fear_avoidance_behaviour"), ("browsing_pressure", E, "fear_avoidance_behaviour"),
                ("fear_avoidance_behaviour", P, "riparian_overbrowse"),
                ("fear_avoidance_behaviour", E, "seedling_escape"), ("seedling_escape", E, "riparian_recovery"),
                ("predator_return", E, "riparian_recovery")],
         ref="Ripple & Beschta 2004, Wolves and the ecology of fear, BioScience 54(8):755-766; Paine 1966, Food web complexity and species diversity, American Naturalist 100:65-75",
         vocab=["wolf", "elk", "yellowstone", "predator", "prey", "willow", "trophic", "cascade", "herbivore"]),
]


def main(out):
    ex, templates, failed = MotifExtractor(), [], []
    for t in T:
        links = tuple(CausalLink(cause=a, relation=r, effect=b) for a, r, b in t["links"])
        assert {a for a, _, _ in t["links"]} | {b for _, _, b in t["links"]} == set(t["roles"]), t["id"]
        motifs = tuple(sorted(ex.extract_links(links).names))
        ct = CausalTemplate(id=t["id"], domain=t["domain"], roles=tuple(t["roles"]), links=links, motifs=motifs,
                            curated_by=CURATOR, source_ref=t["ref"], domain_vocabulary=tuple(t["vocab"]))
        reasons = lint_template(ct)
        n_inh = sum(1 for _, r, _ in t["links"] if r in (P, D))
        print(f"{t['id']:36s} {'PASS' if not reasons else 'FAIL'} inhibitory_edges={n_inh} {reasons}")
        if reasons:
            failed.append(t["id"])
        templates.append({"id": t["id"], "domain": t["domain"], "roles": t["roles"],
                          "links": [{"cause": a, "relation": r, "effect": b} for a, r, b in t["links"]],
                          "motifs": list(motifs), "curated_by": CURATOR, "source_ref": t["ref"],
                          "domain_vocabulary": t["vocab"],
                          "meta": {"hypothesis": "H-20261023 Negative-Space Engine", "adapter_rule": "AR-2 earned-inhibition",
                                   "lint": "R1-R4 pass" if not reasons else "FAIL"}})
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"templates": templates}, f, ensure_ascii=False, indent=2)
    print("failed:", failed)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main(f"{ROOT}/data/templates/negative_space_v3_20261023.json")
