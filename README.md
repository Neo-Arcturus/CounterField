# creative-agent (QD-Ideator)

An offline-first, production-grade Quality-Diversity (QD) ideation harness and brainstorming engine for LLMs.

## Core Philosophy: Harness over Prompting

Standard prompting approaches (e.g. asking LLMs to use SCAMPER, 6 Thinking Hats, or "think out of the box") fail due to **Format Compliance without Cognitive Diversity**: the model respects the persona or labels while collapsing to the dataset mean (homogenization).

`creative-agent` treats LLM ideation as an evolutionary **Quality-Diversity (MAP-Elites)** search problem:
1. **Causal Mechanism Blacklisting**: Mines baseline clichés and extracts their structural causal mechanisms into a Negative Archive.
2. **Search-Space Partitioning**: Distributes divergent mutation operators across isolated generation contexts (no premature cross-talk).
3. **3-Layer Evaluator**:
   - Layer A (Lexical): n-gram / Jaccard token overlap
   - Layer B (Semantic): Embedding cosine distance
   - Layer C (Structural): Causal mechanism similarity against the Negative Archive
4. **Constrained Pareto Frontier**: Optimizes $(Novelty, Utility, Uniqueness)$ subject to $(Appropriateness \ge \tau, Coherence \ge \tau)$ to prevent meaningless absurdism ("Novelty Theater").
5. **Behavioral Niche Grid**: Preserves diverse elite solutions across behavioral dimensions (intervention level, resource intensity, feedback horizon).

---

## Architecture Overview

```
[Problem Input]
       │
       ▼
Problem Normalizer ➔ Baseline Cliché Miner ➔ Negative Archive (Causal Mechanisms)
       │
 ┌─────┴───────────────────────┐
 │ Independent Mutation Slots  │ (Inversion, Extreme Constraints, Removal,
 └─────┬───────────────────────┘  Cross-Domain Analogies, Role Shift, Multilingual Lens)
       ▼
3-Layer Evaluator (Lexical + Semantic + Structural)
       ▼
Quality-Diversity (MAP-Elites) Archive (36 behavioral niches)
       ▼
Pareto Frontier & Best-of-K Selection
```

---

## Quick Start

### Installation

Requires Python 3.10+ and Pydantic v2.

```bash
pip install -e .
```

### CLI Execution

```bash
# Text summary output
python3 -m creative_agent --problem "Design an innovative boss fight mechanism without quick-time events"

# Full JSON output including Pareto frontier and 3-layer diagnostic scores
python3 -m creative_agent --problem "Redesign code review to eliminate blocking wait times" --format json
```

### Running Tests

```bash
pytest -v
```
