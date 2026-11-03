"""Adapter rule AR-1 'Epoch Unrolling' applied to the Defect-Harvesting library (v2, schedulable).

AR-1: a published feedback mechanism (A -> B -> A) is expressed for the monotone Semantic-IR as an
epoch chain (A_early -> B_early -> A_late -> B_late), every defect/noise/decay is an explicit *exogenous* source
that is consumed positively (defect = fuel, an `enables`/`increases` edge, never an inhibitory edge from a source).
Each template must pass creative_agent.creativity.template_lint.lint_template (R1-R4) before it is shipped.
"""
import json
import sys

ROOT = "/home/arcturus/hermesWorkspace/projects/CounterField"
sys.path.insert(0, ROOT)

from creative_agent.creativity.isomorphism import CausalTemplate, MotifExtractor  # noqa: E402
from creative_agent.creativity.template_lint import lint_template  # noqa: E402
from creative_agent.models import CausalLink  # noqa: E402

CURATOR = "Minerva Lead 2026-10-22 (Defect-Harvesting H-20261022, AR-1 epoch-unrolled)"
E, I = "enables", "increases"

T = [
    dict(id="parrondo_losing_pair_ratchet", domain="nonlinear_stat_physics",
         roles=["alternation_clock", "losing_game_a", "state_remap", "losing_game_b", "ratchet_gain"],
         links=[("alternation_clock", E, "losing_game_a"), ("losing_game_a", E, "state_remap"),
                ("state_remap", E, "losing_game_b"), ("alternation_clock", E, "losing_game_b"),
                ("losing_game_b", I, "ratchet_gain"), ("state_remap", I, "ratchet_gain")],
         ref="Harmer & Abbott 1999, Parrondo's paradox, Statistical Science 14(2):206-213",
         vocab=["parrondo", "ratchet", "paradox", "gambling", "capital", "coin", "flashing", "losing"]),
    dict(id="hormetic_dose_overcompensation", domain="toxicology",
         roles=["sublethal_stressor", "damage_signal", "repair_response", "adaptive_capacity", "second_exposure", "overcompensated_resilience"],
         links=[("sublethal_stressor", I, "damage_signal"), ("damage_signal", E, "repair_response"),
                ("repair_response", I, "adaptive_capacity"), ("second_exposure", E, "overcompensated_resilience"),
                ("adaptive_capacity", E, "overcompensated_resilience")],
         ref="Calabrese & Baldwin 2003, Hormesis: the dose-response revolution, Annu Rev Pharmacol Toxicol 43:175-197",
         vocab=["hormesis", "dose", "toxin", "toxic", "poison", "xenobiotic", "stressor", "damage"]),
    dict(id="clonal_two_round_affinity_maturation", domain="immunology",
         roles=["antigen_encounter", "clonal_expansion_one", "mutation_burst_one", "affinity_selection_one", "antigen_persistence",
                "clonal_expansion_two", "mutation_burst_two", "affinity_selection_two", "memory_repertoire"],
         links=[("antigen_encounter", E, "clonal_expansion_one"), ("clonal_expansion_one", I, "mutation_burst_one"),
                ("mutation_burst_one", I, "affinity_selection_one"), ("affinity_selection_one", E, "clonal_expansion_two"),
                ("antigen_persistence", E, "clonal_expansion_two"), ("clonal_expansion_two", I, "mutation_burst_two"),
                ("mutation_burst_two", I, "affinity_selection_two"), ("affinity_selection_two", E, "memory_repertoire")],
         ref="Burnet 1959, The Clonal Selection Theory of Acquired Immunity (Vanderbilt Univ. Press); Eisen & Siskind 1964, Biochemistry 3(7):996-1008",
         vocab=["antibody", "antigen", "lymphocyte", "germinal", "bcell", "immune", "clonal", "mutation", "affinity"]),
    dict(id="physarum_flux_pruning_network", domain="biological_network_design",
         roles=["food_source_pair", "flux_early", "conductivity_early", "decay_pressure", "branch_pruning", "conductivity_late", "network_efficiency"],
         links=[("food_source_pair", I, "flux_early"), ("flux_early", I, "conductivity_early"),
                ("decay_pressure", E, "branch_pruning"), ("conductivity_early", E, "branch_pruning"),
                ("conductivity_early", I, "conductivity_late"), ("branch_pruning", E, "network_efficiency"),
                ("conductivity_late", E, "network_efficiency")],
         ref="Tero et al. 2010, Rules for biologically inspired adaptive network design, Science 327(5964):439-442",
         vocab=["physarum", "slime", "mold", "polycephalum", "tube", "plasmodium", "flux", "conductivity", "pruning"]),
    dict(id="kuramoto_heterogeneity_cluster_lock", domain="nonlinear_dynamics",
         roles=["frequency_heterogeneity", "coupling_strength", "drift_dispersion", "cluster_lock", "mean_field_amplitude", "collective_rhythm"],
         links=[("frequency_heterogeneity", I, "drift_dispersion"), ("drift_dispersion", E, "cluster_lock"),
                ("coupling_strength", E, "cluster_lock"), ("cluster_lock", I, "mean_field_amplitude"),
                ("mean_field_amplitude", E, "collective_rhythm"), ("coupling_strength", E, "collective_rhythm")],
         ref="Strogatz 2000, From Kuramoto to Crawford: exploring the onset of synchronization, Physica D 143(1-4):1-20",
         vocab=["kuramoto", "oscillator", "synchronization", "phase", "firefly", "pendulum", "coupling", "frequency"]),
    dict(id="stochastic_resonance_chain", domain="signal_processing",
         roles=["weak_signal", "noise_amplitude", "threshold_crossing", "spike_coherence", "signal_detectability"],
         links=[("weak_signal", E, "threshold_crossing"), ("noise_amplitude", I, "threshold_crossing"),
                ("threshold_crossing", I, "spike_coherence"), ("spike_coherence", I, "signal_detectability"),
                ("weak_signal", E, "signal_detectability")],
         ref="Benzi, Sutera & Vulpiani 1981, The mechanism of stochastic resonance, J. Phys. A 14(11):L453-L457",
         vocab=["resonance", "stochastic", "noise", "snr", "bistable", "threshold", "spike", "detectability"]),
    dict(id="negative_selection_censoring", domain="artificial_immune_systems",
         roles=["random_detector_pool", "self_profile", "candidate_detector", "censoring_step", "mature_repertoire", "nonself_detection"],
         links=[("random_detector_pool", E, "candidate_detector"), ("candidate_detector", E, "censoring_step"),
                ("self_profile", E, "censoring_step"), ("censoring_step", E, "mature_repertoire"),
                ("mature_repertoire", E, "nonself_detection")],
         ref="Forrest, Perelson, Allen & Cherukuri 1994, Self-nonself discrimination in a computer, IEEE Symp. Security and Privacy, pp.202-212",
         vocab=["detector", "censor", "tolerance", "thymus", "anomaly", "intrusion", "repertoire", "nonself"]),
    dict(id="red_queen_two_round_arms_race", domain="coevolution",
         roles=["parasite_adaptation_one", "selection_pressure_one", "host_variant_one", "arms_clock", "parasite_adaptation_two",
                "selection_pressure_two", "host_variant_two", "lineage_persistence"],
         links=[("parasite_adaptation_one", I, "selection_pressure_one"), ("selection_pressure_one", I, "host_variant_one"),
                ("host_variant_one", E, "parasite_adaptation_two"), ("arms_clock", E, "parasite_adaptation_two"),
                ("parasite_adaptation_two", I, "selection_pressure_two"), ("selection_pressure_two", I, "host_variant_two"),
                ("host_variant_two", E, "lineage_persistence"), ("host_variant_one", E, "lineage_persistence")],
         ref="Van Valen 1973, A new evolutionary law, Evolutionary Theory 1:1-30",
         vocab=["parasite", "host", "red", "queen", "coevolution", "pathogen", "lineage", "arms", "race"]),
    dict(id="stigmergic_evaporation_route_lock", domain="collective_insect_behaviour",
         roles=["agent_walk_early", "pheromone_trace", "trail_choice", "agent_walk_late", "evaporation_clock", "stale_trace_erasure",
                "shortest_route_lock", "colony_throughput"],
         links=[("agent_walk_early", I, "pheromone_trace"), ("pheromone_trace", I, "trail_choice"),
                ("trail_choice", I, "agent_walk_late"), ("evaporation_clock", E, "stale_trace_erasure"),
                ("trail_choice", E, "stale_trace_erasure"), ("stale_trace_erasure", E, "shortest_route_lock"),
                ("agent_walk_late", E, "shortest_route_lock"), ("shortest_route_lock", E, "colony_throughput")],
         ref="Grasse 1959, La reconstruction du nid et les coordinations interindividuelles chez Bellicositermes natalensis, Insectes Sociaux 6(1):41-80",
         vocab=["stigmergy", "pheromone", "ant", "termite", "evaporation", "colony", "trail", "walk", "route"]),
    dict(id="crdt_divergence_join_convergence", domain="distributed_systems",
         roles=["concurrent_updates", "replica_divergence", "gossip_round", "anti_entropy_exchange", "semilattice_rule", "join_merge", "converged_state"],
         links=[("concurrent_updates", I, "replica_divergence"), ("replica_divergence", E, "anti_entropy_exchange"),
                ("gossip_round", E, "anti_entropy_exchange"), ("anti_entropy_exchange", E, "join_merge"),
                ("semilattice_rule", E, "join_merge"), ("join_merge", E, "converged_state")],
         ref="Shapiro, Preguica, Baquero & Zawirski 2011, Conflict-free replicated data types, SSS 2011, LNCS 6976:386-400",
         vocab=["crdt", "replica", "semilattice", "merge", "consistency", "gossip", "divergence", "convergence"]),
]


def main(out):
    ex, templates, failed = MotifExtractor(), [], []
    for t in T:
        links = tuple(CausalLink(cause=a, relation=r, effect=b) for a, r, b in t["links"])
        motifs = tuple(sorted(ex.extract_links(links).names))
        ct = CausalTemplate(id=t["id"], domain=t["domain"], roles=tuple(t["roles"]), links=links, motifs=motifs,
                            curated_by=CURATOR, source_ref=t["ref"], domain_vocabulary=tuple(t["vocab"]))
        reasons = lint_template(ct)
        print(f"{t['id']:42s} {'PASS' if not reasons else 'FAIL'} {reasons}")
        if reasons:
            failed.append(t["id"])
        templates.append({"id": t["id"], "domain": t["domain"], "roles": t["roles"],
                          "links": [{"cause": a, "relation": r, "effect": b} for a, r, b in t["links"]],
                          "motifs": list(motifs), "curated_by": CURATOR, "source_ref": t["ref"],
                          "domain_vocabulary": t["vocab"],
                          "meta": {"hypothesis": "H-20261022 Defect-Harvesting", "adapter_rule": "AR-1 epoch-unrolling",
                                   "lint": "R1-R4 pass" if not reasons else "FAIL"}})
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"templates": templates}, f, ensure_ascii=False, indent=2)
    print("failed:", failed)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main(f"{ROOT}/data/templates/defect_harvest_v2_20261022.json")
