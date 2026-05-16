"""Deterministic stub RNG for parity testing.

choice() always returns seq[0], random() always returns 0.0, shuffle() is
identity. This makes both sides produce fully deterministic (non-random)
output, so any divergence is a logic bug rather than an RNG divergence.

The C# counterpart is the --stub-rng flag on the remap-rooms CLI subcommand,
which makes SodiumRand.Next() always return 0.
"""

from collections.abc import Sequence
from typing import Any, TypeVar

T = TypeVar("T")


class StubRng:
    """Always returns the first/zero option. Satisfies the zora Rng protocol."""

    def choice(self, seq: Sequence[T]) -> T:
        return seq[0]

    def shuffle(self, x: list[Any]) -> None:
        pass  # identity

    def random(self) -> float:
        return 0.0
