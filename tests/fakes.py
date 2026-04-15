from collections.abc import Iterator, Sequence
from typing import TypeVar

T = TypeVar("T")


class ScriptedRng:
    """Test fake for Rng. Feed it exact return values; it yields them in order.

    Pass integer indices to choice() and float values to random().
    shuffle() is a no-op — arrange input in the expected post-shuffle order.

    Example:
        rng = ScriptedRng([1, 0, 2])
        rng.choice(['a', 'b', 'c'])  # returns 'b' (index 1)
        rng.choice(['a', 'b', 'c'])  # returns 'a' (index 0)
        rng.choice(['a', 'b', 'c'])  # returns 'c' (index 2)
    """

    def __init__(self, values: list) -> None:
        self._values: Iterator[float] = iter(values)

    def random(self) -> float:
        return next(self._values)

    def choice(self, seq: Sequence[T]) -> T:
        return seq[int(next(self._values))]

    def shuffle(self, x: list) -> None:
        pass  # no-op; control order by arranging input before calling shuffle
