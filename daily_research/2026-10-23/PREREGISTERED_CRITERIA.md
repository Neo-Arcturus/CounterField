# Pre-registered acceptance criteria (frozen BEFORE results were read) -- 2026-10-23

Written at run time while the three LLM runs were in flight; results not yet inspected.

Admission (unchanged core gates): status=ACCEPTED, stage=COMPLETE, zero FATAL playtest issues.
Target: >= 10 distinct admitted candidates (unique mechanism fingerprint) across 3 contexts.

HIGH-NOVELTY (structural, deterministic, LLM-free; creative_agent/creativity/novelty_audit.py):
  corpus C = every admitted mechanism from 2026-10-22 archive_llm.json and archive_control.json
           + skeletons of the 22 pre-existing templates (default12 + geometric10)
           + skeletons of defect_harvest_v2 (10)
           + skeletons of the *other* v3 templates (a candidate is never compared with its own source template;
             its distance to its own source is reported separately as 'derivation distance')
  A candidate is HIGH-NOVELTY iff   structural_novelty(candidate, C) >= 0.25   AND   label_overlap(candidate, C) <= 0.10
  The old hash-proxy `novelty` score is reported but NOT used as evidence.

Negative-space claim (H-20261023): candidate is 'negative-space' iff it keeps >= 1 inhibitory link (prevents/decreases)
  whose cause is a non-source node AND the payoff stays reachable after deleting every inhibitory link (buffer path).
Niche coverage: report admitted count per intervention_level; success if >= 2 non-'individual' levels are occupied.
