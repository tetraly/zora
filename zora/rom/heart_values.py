"""HeartValues (aldonunez, RAM $066F): the heart containers less one in the high
nibble and the full hearts less one in the low nibble (PRG0's start: $22,
three containers, three full)."""

NIBBLE_BITS = 4
LOW_NIBBLE = 0x0F


def heart_values(containers: int, full_hearts: int) -> int:
    """The HeartValues byte for a heart-container count and a full-heart count."""
    return (containers - 1) << NIBBLE_BITS | (full_hearts - 1)


def heart_counts(value: int) -> tuple[int, int]:
    """(heart containers, full hearts) of a HeartValues byte."""
    return (value >> NIBBLE_BITS) + 1, (value & LOW_NIBBLE) + 1


PRG0_START_HEART_VALUES = heart_values(3, 3)
