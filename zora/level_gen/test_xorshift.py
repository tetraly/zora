"""Xorshift32 RNG for cross-platform byte-comparison testing.

Identical algorithm in Python and C# (TestXorshift.cs) ensures both
sides consume the same RNG stream when given the same seed.
"""


class Xorshift32:
    def __init__(self, seed: int):
        self._state = seed & 0xFFFFFFFF
        if self._state == 0:
            self._state = 1

    def next(self) -> int:
        x = self._state
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        self._state = x
        return x

    def random(self) -> float:
        return self.next() / 0x100000000

    def choice(self, seq):
        idx = self.next() % len(seq)
        return seq[idx]

    def shuffle(self, x):
        for i in range(len(x) - 1, 0, -1):
            j = self.next() % (i + 1)
            x[i], x[j] = x[j], x[i]


if __name__ == "__main__":
    rng = Xorshift32(12345)
    print("Xorshift32 first 20 values for seed=12345:")
    for i in range(20):
        print(f"  {i:2d}: {rng.next()}")
