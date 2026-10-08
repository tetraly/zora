"""Deterministic RNG for ZORA generation.

Stream: block n = blake2b(n as 8 LE bytes, key=seed as 8 LE bytes, 64 bytes),
consumed as little-endian unsigned 64-bit words, 8 per block, in order.
Never use Python's random; never use floats; never depend on set iteration order.

SPEC reference: project brief (reproducibility rules).
"""
import hashlib
from collections.abc import Sequence
from typing import Any, Protocol, TypeVar, runtime_checkable

T = TypeVar("T")


@runtime_checkable
class IntRng(Protocol):
    """Structural interface for integer randomness (shapes of the old
    project's Rng protocol, but integer-first: `below` replaces `random()`)."""

    def below(self, n: int) -> int: ...

    def choice(self, seq: Sequence[T]) -> T: ...

    def shuffle(self, items: list[Any]) -> None: ...


class _DerivedHelpers:
    """choice/shuffle/weighted/chance implemented on top of below().

    Subclasses provide below(n) with uniform ints in [0, n)."""

    def below(self, n: int) -> int:
        raise NotImplementedError

    def choice(self, seq: Sequence[T]) -> T:
        if not seq:
            raise ValueError("choice from empty sequence")
        return seq[self.below(len(seq))]

    def shuffle(self, items: list[Any]) -> None:
        """In-place Fisher-Yates."""
        for i in range(len(items) - 1, 0, -1):
            j = self.below(i + 1)
            items[i], items[j] = items[j], items[i]

    def weighted(self, options: list[T], weights: list[int]) -> T:
        """Pick option by integer weight. Total weight must be > 0."""
        if len(options) != len(weights):
            raise ValueError("options/weights length mismatch")
        total = 0
        for w in weights:
            if w < 0:
                raise ValueError(f"negative weight {w}")
            total += w
        if total <= 0:
            raise ValueError("total weight must be positive")
        target = self.below(total)
        acc = 0
        for option, w in zip(options, weights, strict=True):
            acc += w
            if target < acc:
                return option
        raise AssertionError("unreachable: weight walk exhausted")

    def chance(self, numerator: int, denominator: int) -> bool:
        """True exactly numerator/denominator of the time (integers only)."""
        if not 0 <= numerator <= denominator:
            raise ValueError(f"bad chance {numerator}/{denominator}")
        return self.below(denominator) < numerator


BYTE_RANGE = 256       # most passes' discarded draws are numbers below 256


def discard(rng: IntRng, count: int = 1, number_range: int = BYTE_RANGE) -> None:
    """Draw `count` numbers below number_range and throw them away: a pass's
    leading discards, where the stream position matters and the values do
    not."""
    for _ in range(count):
        rng.below(number_range)


class Rng(_DerivedHelpers):
    """Counter-mode BLAKE2b RNG yielding uniform integers."""

    _WORDS_PER_BLOCK = 8  # 64-byte block / 8-byte word

    def __init__(self, seed: int) -> None:
        if not 0 <= seed < (1 << 64):
            raise ValueError(f"seed must fit in unsigned 64-bit, got {seed}")
        self._seed_bytes = seed.to_bytes(8, "little")
        self._block_index = 0
        self._words: list[int] = []
        self._word_pos = self._WORDS_PER_BLOCK  # force first refill

    # --- low-level stream ---

    def _next_word(self) -> int:
        if self._word_pos >= self._WORDS_PER_BLOCK:
            digest = hashlib.blake2b(
                self._block_index.to_bytes(8, "little"),
                key=self._seed_bytes,
                digest_size=64,
            ).digest()
            self._words = [
                int.from_bytes(digest[i * 8:(i + 1) * 8], "little")
                for i in range(self._WORDS_PER_BLOCK)
            ]
            self._block_index += 1
            self._word_pos = 0
        word = self._words[self._word_pos]
        self._word_pos += 1
        return word


    # --- distributions ---

    def below(self, n: int) -> int:
        """Uniform int in [0, n) by rejection sampling (no modulo bias)."""
        if n <= 0:
            raise ValueError(f"n must be positive, got {n}")
        if n == 1:
            return 0
        bit_count = n.bit_length()
        mask = (1 << bit_count) - 1
        while True:
            value = self._next_word() & mask
            if value < n:
                return value


class ScriptedRng(_DerivedHelpers):
    """Test double: feed exact below() return values, consumed in order.

    choice()/weighted()/chance()/shuffle() all route through below(), so
    scripted values are draws in [0, n) for the call site's current n.
    """

    def __init__(self, values: list[int]) -> None:
        self._values = list(values)
        self._pos = 0

    def below(self, n: int) -> int:
        if self._pos >= len(self._values):
            raise IndexError(f"ScriptedRng exhausted at below({n})")
        v = self._values[self._pos]
        self._pos += 1
        if not 0 <= v < n:
            raise ValueError(f"scripted value {v} outside [0, {n})")
        return v
