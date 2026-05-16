"""Deterministic hash-based RNG for parity testing.

Uses SHA-256(seed_bytes_LE || counter_bytes_LE) to produce a stream of values.
Each call hashes the seed concatenated with an incrementing counter, interprets
the first 8 bytes as a signed int64, takes abs(), then uses modulo for integer
draws (matching C#'s NextRng() % N pattern).

Reproducible in any language with SHA-256. The matching C# implementation is
the --hash-rng flag in parity/csharp/ParityRunner/Program.cs.
"""

import hashlib
import struct
from collections.abc import Sequence
from typing import Any, TypeVar

T = TypeVar("T")


class HashRng:
    """Deterministic RNG using abs(SHA-256-derived int64) % N. Satisfies the zora Rng protocol."""

    def __init__(self, seed: int = 12345) -> None:
        self._seed_bytes = seed.to_bytes(8, "little", signed=False)
        self._counter = 0

    def _next_abs_i64(self) -> int:
        """Return abs(first 8 bytes of SHA-256(seed||counter) as signed int64).
        Matches C# SodiumRand.Next() which does Math.Abs on a signed long."""
        counter_bytes = self._counter.to_bytes(8, "little")
        digest = hashlib.sha256(self._seed_bytes + counter_bytes).digest()
        self._counter += 1
        return abs(struct.unpack_from("<q", digest, 0)[0])

    def randbelow(self, n: int) -> int:
        """Return a random int in [0, n) using modulo — matches C#'s NextRng() % n."""
        return self._next_abs_i64() % n

    def random(self) -> float:
        """Return a float in [0, 1). Used by callers that don't call randbelow directly."""
        return self._next_abs_i64() / (2**63)

    def choice(self, seq: Sequence[T]) -> T:
        return seq[self.randbelow(len(seq))]

    def shuffle(self, x: list[Any]) -> None:
        n = len(x)
        for i in range(n - 1, 0, -1):
            j = self.randbelow(i + 1)
            x[i], x[j] = x[j], x[i]
