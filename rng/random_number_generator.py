# rng/random_number_generator.py

import random
from typing import List, TypeVar, Sequence, Tuple, Optional

T = TypeVar('T')


class RandomNumberGenerator:
    """Deterministic RNG manager for ZORA randomizer.

    This class wraps Python's random.Random to provide deterministic
    randomization across all randomizer operations. All randomization
    should use this class instead of the global random module to ensure
    reproducibility with the same seed.

    The API mirrors Python's random.Random class for consistency and
    ease of substitution.

    Usage:
        rng = RandomNumberGenerator(12345)
        value = rng.randint(1, 100)
        rng.shuffle(my_list)
    """

    def __init__(self, seed: int):
        """Initialize RNG with a seed.

        Args:
            seed: Integer seed for deterministic random generation
        """
        self._seed = seed
        self._rng = random.Random(seed)
        self._initial_state = self._rng.getstate()

    @property
    def seed(self) -> int:
        """Get the seed used to initialize this RNG."""
        return self._seed

    def reset(self) -> None:
        """Reset RNG to initial seeded state."""
        self._rng.setstate(self._initial_state)

    def getstate(self) -> Tuple:
        """Return internal state; can be passed to setstate() later.

        Mirrors random.Random.getstate() API.
        """
        return self._rng.getstate()

    def setstate(self, state: Tuple) -> None:
        """Restore internal state from object returned by getstate().

        Mirrors random.Random.setstate() API.

        Args:
            state: State object from previous getstate() call
        """
        self._rng.setstate(state)

    # ========================================================================
    # Random operation methods (mirror random.Random API)
    # ========================================================================

    def randint(self, a: int, b: int) -> int:
        """Return random integer in range [a, b], including both end points.

        Mirrors random.Random.randint() API.
        """
        return self._rng.randint(a, b)

    def choice(self, seq: Sequence[T]) -> T:
        """Choose a random element from a non-empty sequence.

        Mirrors random.Random.choice() API.
        """
        return self._rng.choice(seq)

    def choices(
        self,
        population: Sequence[T],
        weights: Optional[Sequence[float]] = None,
        k: int = 1
    ) -> List[T]:
        """Return a k-sized list of elements chosen from population with replacement.

        Mirrors random.Random.choices() API.

        Args:
            population: Sequence to sample from
            weights: Optional weights for weighted sampling
            k: Number of elements to choose
        """
        return self._rng.choices(population, weights=weights, k=k)

    def shuffle(self, x: List) -> None:
        """Shuffle list x in-place, and return None.

        Mirrors random.Random.shuffle() API.

        Args:
            x: List to shuffle in-place
        """
        self._rng.shuffle(x)

    def random(self) -> float:
        """Return random float in the range [0.0, 1.0).

        Mirrors random.Random.random() API.
        """
        return self._rng.random()

    # ========================================================================
    # ZORA-specific methods
    # ========================================================================

    def GetCode(self) -> List[int]:
        """Generate a 4-character code for the output ROM.

        Returns 4 integers in the range [0x00, 0x23] (0-35 decimal),
        corresponding to the character set 0-9 and A-Z.

        This code is deterministic based on the RNG seed and can be used
        for verification or display in the ROM.

        Returns:
            List of 4 integers, each in range [0x00, 0x23]
        """
        return [self.randint(0x00, 0x23) for _ in range(4)]
