import random
from collections.abc import Sequence
from typing import Any, Protocol, TypeVar, runtime_checkable

T = TypeVar("T")


@runtime_checkable
class Rng(Protocol):
    """Structural interface for randomization. Any object with these
    three methods satisfies it — no inheritance required."""

    def choice(self, seq: Sequence[T]) -> T: ...
    def shuffle(self, x: list[Any]) -> None: ...
    def random(self) -> float: ...


class SeededRng:
    """Production RNG. Wraps random.Random for deterministic,
    seed-reproducible output."""

    def __init__(self, seed: int) -> None:
        self._rng = random.Random(seed)

    def choice(self, seq: Sequence[T]) -> T:
        return self._rng.choice(seq)

    def shuffle(self, x: list[Any]) -> None:
        self._rng.shuffle(x)

    def random(self) -> float:
        return self._rng.random()
