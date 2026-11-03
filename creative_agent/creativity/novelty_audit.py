"""Deterministic structural and label comparisons for reporting."""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from collections import Counter
from typing import Sequence

from ..models import CausalLink


def _digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _node_id(label: str) -> str:
    return " ".join(label.casefold().split())


def wl_feature_vector(links: Sequence[CausalLink], iterations: int = 3) -> Counter[str]:
    """Count anonymous node colours at every directed WL refinement step."""
    if iterations < 0:
        raise ValueError("iterations must be nonnegative")

    edges = {
        (_node_id(link.cause), link.relation, _node_id(link.effect))
        for link in links
    }
    nodes = sorted({node for source, _, target in edges for node in (source, target)})
    incoming: dict[str, list[tuple[str, str]]] = {node: [] for node in nodes}
    outgoing: dict[str, list[tuple[str, str]]] = {node: [] for node in nodes}
    for source, relation, target in edges:
        outgoing[source].append((relation, target))
        incoming[target].append((relation, source))

    colours = {
        node: _digest((
            "in", sorted(Counter(relation for relation, _ in incoming[node]).items()),
            "out", sorted(Counter(relation for relation, _ in outgoing[node]).items()),
        ))
        for node in nodes
    }
    features: Counter[str] = Counter()
    for step in range(iterations + 1):
        features.update(f"{step}:{colours[node]}" for node in nodes)
        if step == iterations:
            break
        colours = {
            node: _digest((
                colours[node],
                sorted(
                    [(relation, "out", colours[neighbor]) for relation, neighbor in outgoing[node]]
                    + [(relation, "in", colours[neighbor]) for relation, neighbor in incoming[node]]
                ),
            ))
            for node in nodes
        }
    return features


def wl_cosine(a: Counter[str], b: Counter[str]) -> float:
    """Cosine similarity of nonnegative WL feature counts."""
    if not a or not b:
        return 0.0
    dot = sum(count * b.get(feature, 0) for feature, count in a.items())
    norm_a = math.sqrt(sum(count * count for count in a.values()))
    norm_b = math.sqrt(sum(count * count for count in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


def label_tokens(links: Sequence[CausalLink]) -> frozenset[str]:
    """Extract Unicode alphanumeric words of at least three characters."""
    tokens: set[str] = set()
    for link in links:
        for label in (link.cause, link.effect):
            normalized = unicodedata.normalize("NFKC", label).casefold()
            current: list[str] = []
            for character in normalized:
                if character.isalnum():
                    current.append(character)
                else:
                    if len(current) >= 3:
                        tokens.add("".join(current))
                    current.clear()
            if len(current) >= 3:
                tokens.add("".join(current))
    return frozenset(tokens)


def token_jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """Jaccard overlap, with zero for two empty token sets."""
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def structural_novelty(
    links: Sequence[CausalLink],
    corpus: Sequence[Sequence[CausalLink]],
    iterations: int = 3,
) -> float:
    """Distance from the most structurally similar corpus member."""
    if not corpus:
        return 1.0
    vector = wl_feature_vector(links, iterations)
    similarity = max(wl_cosine(vector, wl_feature_vector(member, iterations)) for member in corpus)
    return max(0.0, min(1.0, 1.0 - similarity))


def label_overlap(links: Sequence[CausalLink], corpus: Sequence[Sequence[CausalLink]]) -> float:
    """Largest surface label overlap with a corpus member."""
    if not corpus:
        return 0.0
    tokens = label_tokens(links)
    return max(token_jaccard(tokens, label_tokens(member)) for member in corpus)
