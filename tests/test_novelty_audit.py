"""Contract tests for deterministic, reporting-only novelty measures."""

from __future__ import annotations

import os
import subprocess
import sys
from collections import Counter

import pytest

from creative_agent.creativity.novelty_audit import (
    label_overlap,
    label_tokens,
    structural_novelty,
    token_jaccard,
    wl_cosine,
    wl_feature_vector,
)
from creative_agent.models import CausalLink


def links(*triples: tuple[str, str, str]) -> tuple[CausalLink, ...]:
    return tuple(CausalLink(cause=cause, relation=relation, effect=effect)
                 for cause, relation, effect in triples)


STAR = links(
    ("a", "increases", "b"),
    ("a", "increases", "c"),
    ("a", "increases", "d"),
)


def test_identical_link_sets_have_unit_cosine() -> None:
    vector = wl_feature_vector(STAR)
    assert wl_cosine(vector, wl_feature_vector(tuple(reversed(STAR)))) == pytest.approx(1.0)


def test_node_relabeling_preserves_features() -> None:
    renamed = links(
        ("engine", "increases", "wheel"),
        ("engine", "increases", "road"),
        ("engine", "increases", "speed"),
    )
    assert wl_feature_vector(STAR) == wl_feature_vector(renamed)
    assert wl_cosine(wl_feature_vector(STAR), wl_feature_vector(renamed)) == pytest.approx(1.0)


def test_relation_change_lowers_cosine() -> None:
    changed = links(
        ("a", "prevents", "b"),
        ("a", "increases", "c"),
        ("a", "increases", "d"),
    )
    assert wl_cosine(wl_feature_vector(STAR), wl_feature_vector(changed)) < 1.0


def test_edge_direction_changes_star_features() -> None:
    incoming = links(
        ("b", "increases", "a"),
        ("c", "increases", "a"),
        ("d", "increases", "a"),
    )
    assert wl_cosine(wl_feature_vector(STAR), wl_feature_vector(incoming)) < 0.8


def test_structural_novelty_contract() -> None:
    changed = links(
        ("a", "prevents", "b"),
        ("a", "increases", "c"),
        ("a", "increases", "d"),
    )
    assert structural_novelty(STAR, ()) == 1.0
    assert structural_novelty(STAR, (changed, STAR)) == pytest.approx(0.0)
    assert 0.0 < structural_novelty(STAR, (changed,)) < 1.0
    assert 0.0 <= structural_novelty((), (STAR,)) <= 1.0


def test_label_overlap_and_unicode_tokens() -> None:
    base = links(("Alpha engine", "enables", "Beta wheel"))
    same_labels = links(("alpha  ENGINE", "prevents", "beta WHEEL"))
    disjoint = links(("Gamma cloud", "enables", "Delta river"))
    assert label_overlap(base, (same_labels,)) == 1.0
    assert label_overlap(base, (disjoint,)) == 0.0
    assert label_overlap(base, ()) == 0.0
    assert label_tokens(links(("가나다", "enables", "가나"))) == frozenset({"가나다"})
    assert label_tokens(links(("Ｆｏｏ_bar", "enables", "BAZ"))) == frozenset({"foo", "bar", "baz"})


def test_token_jaccard_empty_and_partial() -> None:
    assert token_jaccard(frozenset(), frozenset()) == 0.0
    assert token_jaccard(frozenset({"one", "two"}), frozenset({"two", "three"})) == pytest.approx(1 / 3)


def test_wl_cosine_empty_vector() -> None:
    assert wl_cosine(Counter(), wl_feature_vector(STAR)) == 0.0
    assert wl_cosine(Counter(), Counter()) == 0.0


def test_duplicate_links_count_once_and_self_loop_is_supported() -> None:
    original = links(("Node", "enables", "Node"))
    duplicates = links(("Node", "enables", "Node"), (" node ", "enables", "NODE"))
    assert wl_feature_vector(original) == wl_feature_vector(duplicates)
    assert sum(wl_feature_vector(original).values()) == 4


def test_feature_digest_is_independent_of_python_hash_seed() -> None:
    code = (
        "import hashlib, json; "
        "from creative_agent.models import CausalLink; "
        "from creative_agent.creativity.novelty_audit import wl_feature_vector; "
        "links = [CausalLink(cause=a, relation=r, effect=b) for a,r,b in "
        "[('a','increases','b'),('b','prevents','c'),('c','enables','a')]]; "
        "payload = json.dumps(sorted(wl_feature_vector(links).items())); "
        "print(hashlib.sha256(payload.encode()).hexdigest())"
    )
    digests = []
    for seed in ("1", "977"):
        env = os.environ.copy()
        env["PYTHONHASHSEED"] = seed
        result = subprocess.run(
            [sys.executable, "-c", code], env=env, capture_output=True,
            text=True, check=True,
        )
        digests.append(result.stdout.strip())
    assert digests[0] == digests[1]
