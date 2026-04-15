"""
Determinism tests: verify that generate_game produces identical output regardless
of what random state exists outside of it before each call.
"""
import random

from flags.flags_generated import Flags
from zora.generate_game import generate_game

_SEED = 42
_FLAGS = Flags()


def test_generate_game_is_deterministic() -> None:
    """Five generate_game calls with the same seed must produce the same hash,
    even when interleaved with arbitrary random operations that pollute the
    global random state between calls."""

    ips1, hash1, *_ = generate_game(_FLAGS, seed=_SEED)

    # Pollute global random state
    random.seed(99999)
    for _ in range(500):
        random.random()

    ips2, hash2, *_ = generate_game(_FLAGS, seed=_SEED)

    # More random pollution
    random.seed(0)
    random.shuffle(list(range(1000)))

    ips3, hash3, *_ = generate_game(_FLAGS, seed=_SEED)

    # Generate a fourth and fifth time back-to-back with no pollution
    ips4, hash4, *_ = generate_game(_FLAGS, seed=_SEED)
    ips5, hash5, *_ = generate_game(_FLAGS, seed=_SEED)

    hashes = [hash1, hash2, hash3, hash4, hash5]
    assert all(h == hash1 for h in hashes), (
        f"Hash mismatch across generations: {hashes}"
    )

    patches = [ips1, ips2, ips3, ips4, ips5]
    assert all(p == ips1 for p in patches), (
        "IPS patch bytes differ across generations with the same seed"
    )
