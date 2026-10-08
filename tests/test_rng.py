"""Tests for the deterministic BLAKE2b counter RNG."""
import hashlib

import pytest

from zora.generate.rng import Rng


def _reference_stream(seed: int, words: int) -> list[int]:
    out: list[int] = []
    n = 0
    while len(out) < words:
        digest = hashlib.blake2b(
            n.to_bytes(8, "little"), key=seed.to_bytes(8, "little"), digest_size=64
        ).digest()
        for i in range(8):
            out.append(int.from_bytes(digest[i * 8:(i + 1) * 8], "little"))
        n += 1
    return out[:words]


def test_stream_matches_spec() -> None:
    rng = Rng(42)
    expected = _reference_stream(42, 20)
    got = [rng._next_word() for _ in range(20)]
    assert got == expected


def test_word_consumption_order_across_blocks() -> None:
    # Drawing below(n) may reject words; ensure a fresh Rng replays identically.
    a = Rng(7)
    b = Rng(7)
    seq_a = [a.below(n) for n in (2, 3, 5, 7, 100, 1000, 12345)]
    seq_b = [b.below(n) for n in (2, 3, 5, 7, 100, 1000, 12345)]
    assert seq_a == seq_b


def test_below_bounds() -> None:
    rng = Rng(1)
    for _ in range(2000):
        for n in (1, 2, 3, 6, 10, 100, 10**6, (1 << 32) + 1, (1 << 63) + 12345):
            v = rng.below(n)
            assert 0 <= v < n


def test_below_rejects_bad_n() -> None:
    rng = Rng(1)
    with pytest.raises(ValueError):
        rng.below(0)
    with pytest.raises(ValueError):
        rng.below(-5)


def test_below_no_modulo_bias() -> None:
    # n=3: the naive-mask rejection path must make each residue reachable.
    rng = Rng(99)
    counts = [0, 0, 0]
    for _ in range(3000):
        counts[rng.below(3)] += 1
    # Uniform within tolerance: chi-square-free sanity bound.
    assert min(counts) > 700 and max(counts) < 1300


def test_choice_deterministic_and_member() -> None:
    a = Rng(5)
    b = Rng(5)
    seq = ["x", "y", "z"]
    picks_a = [a.choice(seq) for _ in range(50)]
    picks_b = [b.choice(seq) for _ in range(50)]
    assert picks_a == picks_b
    assert set(picks_a) == {"x", "y", "z"}
    with pytest.raises(ValueError):
        Rng(1).choice([])


def test_shuffle_is_deterministic_permutation() -> None:
    items = list(range(200))
    a, b = list(items), list(items)
    Rng(11).shuffle(a)
    Rng(11).shuffle(b)
    assert a == b
    assert sorted(a) == items
    c = list(items)
    Rng(12).shuffle(c)
    assert c != a  # overwhelmingly likely


def test_weighted_zero_weight_never_chosen() -> None:
    rng = Rng(3)
    for _ in range(2000):
        assert rng.weighted(["a", "b", "c"], [1, 0, 1]) in ("a", "c")


def test_weighted_frequency() -> None:
    rng = Rng(123)
    counts = {"a": 0, "b": 0}
    for _ in range(5000):
        counts[rng.weighted(["a", "b"], [3, 1])] += 1
    ratio = counts["a"] / counts["b"]
    assert 2.5 < ratio < 3.5


def test_weighted_errors() -> None:
    rng = Rng(1)
    with pytest.raises(ValueError):
        rng.weighted(["a"], [])
    with pytest.raises(ValueError):
        rng.weighted(["a", "b"], [0, 0])
    with pytest.raises(ValueError):
        rng.weighted(["a", "b"], [1, -1])


def test_chance_matches_draws() -> None:
    rng = Rng(77)
    hits = 0
    total = 4000
    for _ in range(total):
        if rng.chance(1, 5):
            hits += 1
    assert total // 5 - 300 < hits < total // 5 + 300


def test_seed_range() -> None:
    with pytest.raises(ValueError):
        Rng(-1)
    with pytest.raises(ValueError):
        Rng(1 << 64)


def test_different_seeds_differ() -> None:
    r1, r2 = Rng(1), Rng(2)
    assert [r1.below(1 << 62) for _ in range(8)] != [r2.below(1 << 62) for _ in range(8)]


def test_scripted_rng() -> None:
    from zora.generate.rng import IntRng, ScriptedRng

    r = ScriptedRng([1, 0, 2])
    assert r.choice(["a", "b", "c"]) == "b"
    assert r.choice(["a", "b", "c"]) == "a"
    assert r.below(9) == 2
    assert isinstance(r, IntRng)
    assert isinstance(Rng(1), IntRng)
    exhausted = ScriptedRng([0])
    assert exhausted.below(5) == 0
    with pytest.raises(IndexError):
        exhausted.below(5)
    with pytest.raises(ValueError):
        ScriptedRng([7]).below(5)
