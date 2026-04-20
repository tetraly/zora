"""Mersenne Twister 19937-64 (MT19937-64) random number generator.

Matches the C++ std::mt19937_64 implementation used by the original
randomizer. Parameters: w=64, n=312, m=156, r=31.
"""

_W = 64
_N = 312
_M = 156
_R = 31
_LOWER_MASK = (1 << _R) - 1  # 0x7FFFFFFF
_UPPER_MASK = ((1 << _W) - 1) ^ _LOWER_MASK
_MASK64 = (1 << 64) - 1
_MAG01 = [0, 0xB5026F5AA96619E9]

_F = 6364136223846793005
_D = 0x5555555555555555
_U = 29
_S = 17
_B = 0x71D67FFFEDA60000
_T = 37
_C = 0xFFF7EEE000000000
_L = 43


class MersenneTwister64:
    """MT19937-64 PRNG matching C++ std::mt19937_64."""

    __slots__ = ('_mt', '_mti')

    def __init__(self, seed: int) -> None:
        seed &= _MASK64
        self._mt = [0] * _N
        self._mt[0] = seed
        for i in range(1, _N):
            self._mt[i] = (_F * (self._mt[i - 1] ^ (self._mt[i - 1] >> (_W - 2))) + i) & _MASK64
        self._mti = _N

    def next(self) -> int:
        """Generate the next uint64 value."""
        if self._mti >= _N:
            self._twist()

        y = self._mt[self._mti]
        self._mti += 1

        y ^= (y >> _U) & _D
        y ^= (y << _S) & _B
        y ^= (y << _T) & _C
        y ^= y >> _L

        return y & _MASK64

    def _twist(self) -> None:
        mt = self._mt
        for i in range(_N):
            x = (mt[i] & _UPPER_MASK) | (mt[(i + 1) % _N] & _LOWER_MASK)
            mt[i] = mt[(i + _M) % _N] ^ (x >> 1) ^ _MAG01[x & 1]
        self._mti = 0
