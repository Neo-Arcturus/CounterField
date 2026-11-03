# TASK (Backend / TDD): structural novelty audit module (pure, deterministic, zero-LLM, zero-network)

Project root: /home/arcturus/hermesWorkspace/projects/CounterField  (test runner: `.venv/bin/pytest`, baseline 105 passed)

## Why
Yesterday's `novelty` score is a hash-embedding proxy that clusters ~0.68 regardless of structure, so "high novelty"
could not be evidenced. We need an INDEPENDENT, deterministic structural novelty measure used only for REPORTING
(it must never gate or alter archive admission).

## Files you may create (and nothing else; do NOT edit any existing file)
1. creative_agent/creativity/novelty_audit.py
2. tests/test_novelty_audit.py

## Contract (exact names / signatures)
```python
from __future__ import annotations
from collections import Counter
from typing import Sequence
from ..models import CausalLink          # fields: cause, relation, effect (relation in increases/decreases/enables/prevents/depends_on)

def wl_feature_vector(links: Sequence[CausalLink], iterations: int = 3) -> Counter[str]: ...
def wl_cosine(a: Counter[str], b: Counter[str]) -> float: ...                  # cosine in [0,1]; either empty -> 0.0
def label_tokens(links: Sequence[CausalLink]) -> frozenset[str]: ...           # NFKC + casefold, split on non-alphanumeric (unicode-aware, keep Hangul), drop tokens of len<3
def token_jaccard(a: frozenset[str], b: frozenset[str]) -> float: ...          # both empty -> 0.0
def structural_novelty(links: Sequence[CausalLink], corpus: Sequence[Sequence[CausalLink]], iterations: int = 3) -> float: ...
    # 1 - max_i wl_cosine(vec(links), vec(corpus[i])); empty corpus -> 1.0; result clamped to [0,1]
def label_overlap(links: Sequence[CausalLink], corpus: Sequence[Sequence[CausalLink]]) -> float: ...
    # max_i token_jaccard(...); empty corpus -> 0.0
```
### WL feature vector semantics
* Node labels are ANONYMOUS (text of cause/effect is ignored; nodes identified by casefolded+whitespace-normalised text only to build the graph).
* Duplicate (cause,relation,effect) links count once. Self-loops are allowed.
* Iteration 0 colour of a node = ("in", n_in_edges_by_relation..., "out", n_out_edges_by_relation...) as a canonical string
  (relation-aware, direction-aware). Iteration t+1 colour = hash/string of (own colour, sorted multiset of (relation, 'out', neighbour colour) for successors,
  sorted multiset of (relation, 'in', neighbour colour) for predecessors). Feature vector = Counter of every colour string (prefixed with its iteration index) over iterations 0..`iterations`.
* Use a stable digest (hashlib.sha256 -> hex[:16]) for colours; NEVER Python `hash()` (must be identical across processes).

## Required tests (tests/test_novelty_audit.py) -- all must be zero-network
1. identical link sets -> wl_cosine == 1.0 (approx).
2. node-relabelled isomorphic graph (same topology+relations, different text) -> cosine 1.0.
3. changing one relation (increases->prevents) lowers cosine below 1.0.
4. direction sensitivity: out-star {a->b, a->c, a->d} vs in-star {b->a, c->a, d->a} (same relation) -> cosine < 0.8 .
5. structural_novelty: empty corpus == 1.0; identical member in corpus == 0.0 (approx); strictly in [0,1].
6. label_overlap: identical labels -> 1.0; disjoint -> 0.0; empty corpus -> 0.0; Hangul labels tokenise (len>=3 rule applies to characters, so `가나다` kept).
7. determinism across processes: spawn `subprocess.run([sys.executable, "-c", ...])` computing a vector digest twice with different PYTHONHASHSEED values; results must be equal.
8. duplicate links count once; self-loop does not crash.

## Done criteria (Report-First)
* `.venv/bin/pytest -q` exits 0 for the WHOLE suite (105 existing + yours). Print the final pytest tail.
* `git diff --stat` must show NO modified tracked file besides what already was modified before you started (do not touch creative_agent/archive.py, evaluator.py, redteam.py, verifier.py, harness.py, models.py, providers.py, creativity/__init__.py).
* No network, no background loops, no hyper-parameter tuning. If a test fails twice, STOP and report the failure evidence.
