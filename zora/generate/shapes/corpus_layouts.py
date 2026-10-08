"""Random-room layout weights (SH-ROOM-09), fitted from the
1000-ROM Consternation corpus by scripts/fit_layout_weights.py.

SPEC-GAP 1: the spec does not transcribe the per-level tables; these are
set-level (1-6 / 7-9) aggregates of observed layout frequencies after
subtracting planned cells (person rooms, T2 stair rooms) and forcing
reserved layouts (SH-ROOM-08) to zero. Sum ~= 1000 per set. Codes are
full 7-bit room-data layout values ($40+ = that layout + push block).
"""

RANDOM_LAYOUT_WEIGHTS: dict[str, list[int]] = {
    "1-6": [
          82,    7,   29,   38,   16,   21,    7,    5,
          11,    1,   28,    2,   10,   29,    5,    5,
           1,   28,    9,   29,   20,   47,   20,   30,
          40,    9,    0,    0,    0,   44,   20,   27,
           0,    0,    6,   86,   76,   38,   77,    0,
           0,    0,    0,    0,    0,    0,    0,    0,
           0,    0,    0,    0,    0,    0,    0,    0,
           0,    0,    0,    0,    0,    0,    0,    0,
           0,    6,    0,    0,    0,    0,    6,    5,
           4,    0,   13,    0,    2,    5,    0,    0,
           0,   11,    0,    0,    0,    0,    0,    0,
           0,    0,    0,    0,    0,    0,    0,   15,
           2,    0,    8,    0,    0,    0,    1,    0,
           0,    0,    0,    0,    0,    0,    0,    0,
           0,    0,    0,    0,    0,    0,    0,    0,
           0,    0,    0,    0,    0,    0,    0,    0,
    ],
    "7-9": [
          82,    8,   12,   24,   12,   21,    8,    5,
          14,    2,   33,    2,   11,   21,    5,    8,
           1,   29,    5,   25,   21,   18,   31,   14,
          33,   14,    0,    0,    0,   27,   24,   23,
           0,    0,    9,  109,   91,   40,   69,    0,
           0,    0,    0,    0,    0,    0,    0,    0,
           0,    0,    0,    0,    0,    0,    0,    0,
           0,    0,    0,    0,    0,    0,    0,    0,
           0,    8,    0,    0,    0,    0,    9,    9,
           5,    0,   13,    0,    4,    8,    0,    0,
           0,   16,    0,    0,    0,    0,    0,    0,
           0,    0,    0,    0,    0,    0,    0,   23,
          24,    0,   11,    0,    0,    0,    1,    0,
           0,    0,    0,    0,    0,    0,    0,    0,
           0,    0,    0,    0,    0,    0,    0,    0,
           0,    0,    0,    0,    0,    0,    0,    0,
    ],
}
