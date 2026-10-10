"""The four published presets (FL-PRE-01 to FL-PRE-04), CP-5's baseline with level encoding off, and
ZORA's own presets, which set the ZORA flag string too (ZORA_PRESETS)."""
from __future__ import annotations

# ---------------------------------------------------------------------------
# FL-PRE-01 to FL-PRE-04: the four presets
# ---------------------------------------------------------------------------

MVP_BASELINE = "oIbnPfPb01Hll3D29Bc2!etrojQOSjJQZUJ3A"
PUBLISHED_VARIANT_A = "oIbnPfPb01Hll3D295IGDxxjR4UwfEok8P4MD"
PUBLISHED_VARIANT_B = "24hJoDaoq92qaumIfio4Qq8LtfU0Xt8tpG3Iafo"
PUBLISHED_VARIANT_C = "oIbnRjuMUKqwdnOXzOMO7PuDtwAvU3boJnaXW"
# CP-5: the MVP baseline with level encoding (B82) off, the string the 1,000-ROM corpus was built from.
MVP_BASELINE_LEVEL_ENCODING_OFF = "8hq4BeR1JXo89BJ2!TFpTP02u8UJ3A"

PRESETS: dict[str, str] = {
    "MVP baseline": MVP_BASELINE,
    "Published variant A": PUBLISHED_VARIANT_A,
    "Published variant B": PUBLISHED_VARIANT_B,
    "Published variant C": PUBLISHED_VARIANT_C,
}


# ---------------------------------------------------------------------------
# ZORA's presets: a Z1R string and a ZORA string
# ---------------------------------------------------------------------------

# All Swords No Boards (docs/design/asnb.md section 1): Progressive Items on, Add L4 Sword = Level 2,
# Level 9 Entrance = Level 4 sword, on CP-5 (C02 = 3, generated shapes; C07 = 0, normal) with B09
# Extra Candles off, which Progressive Items refuses (PI-FLAG-03).
ASNB_FLAGS = "8hq4BeR1JXo7yjOOHjbxryVQW!UJ3A"
ASNB_ZORA_FLAGS = "4.T9Jvg"
ZORA_PRESETS: dict[str, tuple[str, str]] = {
    "All Swords No Boards": (ASNB_FLAGS, ASNB_ZORA_FLAGS),
}
