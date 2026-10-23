"""The four published presets (FL-PRE-01 to FL-PRE-04), CP-5's baseline and published variant A with
level encoding off, and ZORA's own presets, which set the ZORA flag string too, with three community
flagsets (ZORA_PRESETS)."""
from __future__ import annotations

# ---------------------------------------------------------------------------
# FL-PRE-01 to FL-PRE-04: the four presets
# ---------------------------------------------------------------------------

MVP_BASELINE = "oIbnPfPb01Hll3D29Bc2!etrojQOSjJQZUJ3A"
PUBLISHED_VARIANT_A = "oIbnPfPb01Hll3D295IGDxxjR4UwfEok8P4MD"
PUBLISHED_VARIANT_B = "24hJoDaoq92qaumIfio4Qq8LtfU0Xt8tpG3Iafo"
PUBLISHED_VARIANT_C = "oIbnRjuMUKqwdnOXzOMO7PuDtwAvU3boJnaXW"
# Hopla, the community's name for published variant C (features-behavior.md FP-START-02), with Encode
# level data on as published; the page shows variant C by this name (form.PRESET_LABELS; owner, beta 5).
HOPLA = PUBLISHED_VARIANT_C
# Consternation Remastered, the community's name for published variant A, also with Encode level data on
# as published (form.PRESET_LABELS; owner, beta 5). Random% (published variant B) stays off the menu.
CONSTERNATION_REMASTERED = PUBLISHED_VARIANT_A
# CP-5: the MVP baseline with level encoding (B82) off, the string the 1,000-ROM corpus was built from.
MVP_BASELINE_LEVEL_ENCODING_OFF = "8hq4BeR1JXo89BJ2!TFpTP02u8UJ3A"
# Published variant A with level encoding (B82) off: the spec's string for it (PS-ITW-07's second
# Check), which decodes as variant A in every other field. Not on the page's menu (owner, beta 5),
# which offers variant A, as Consternation Remastered, with level encoding on.
PUBLISHED_VARIANT_A_LEVEL_ENCODING_OFF = "8hq4BeR1JXhpMPc6s5bu0bWYCiP4MD"

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
# Extra Candles off (Progressive Items refused it until beta 8).
ASNB_FLAGS = "8hq4BeR1JXo7yjOOHjbxryVQW!UJ3A"
ASNB_ZORA_FLAGS = "4.T9Jvg"
# Vanilla (owner, 2026-10-17): every flag Off, the closest to the original game ZORA produces. Every
# Z1R field off or at its first value (Settings.zero), and every ZORA flag off, except where ZORA does
# not produce that value: Hint Type Community (C03 = 2; Normal is not produced), Dungeon Room Shuffle
# Within each dungeon (C14; Vanilla is not produced), Starting Hearts 3 (C16 = 2, the original's;
# index 0 is 1 heart), and B18, B20, B32, B33, B35 and B43 on (their off is not produced).
# tests/test_presets.py builds it from those values.
VANILLA_FLAGS = "CEERPCkLslB6BApr1Him1SiR28Y"
# Three community flagsets (owner, 2026-10-18), each a Z1R string alone, on the menu under these
# names, each as published. TTP5: Muffle Rug has Add Money or Life Rooms (B22) off and Change Leave
# Your Rooms (B23) on, kept as given (FL-DEP-06).
OHK0HPLA_REMASTERED_FLAGS = "oIbnRjuQKp1DXiYCys9LwvSpzqZbXk1pRmZzr"
TTP5_MUFFLE_RUG_FLAGS = "2487lt0moGMFLRug1ofQdxPuUBWnJVSsi7d202I"
TTP5_PICK_5_FLAGS = "p8GIOeYEAonHy5131VdG6b94Ts3EMMvBaQoWR"
# The 2026 tournament presets as v3.6.6 builds them in (owner, beta 8): TTP5 Muffle Rug and Pick 5 above
# are those strings already; TTP5 Uphill Battle (replacing a damaged copy from an out-of-date
# document) and SGLive Onsite join them. The beta 8 export (flags-behavior.md FL-SUP-01) produces every
# field of all four.
TTP5_UPHILL_BATTLE_FLAGS = "143oNtDD4Pw3Yw6SRryTCXlqTsRz2fxg4s4pJW"
SGLIVE_ONSITE_FLAGS = "12TDBKH6mxLfnSz4T7ME4bcIaaUe9sE7UVmj7RA"
ZORA_PRESETS: dict[str, tuple[str, str]] = {
    "All Swords No Boards": (ASNB_FLAGS, ASNB_ZORA_FLAGS),
    "Vanilla": (VANILLA_FLAGS, ""),
    "OHK0HPla Remastered": (OHK0HPLA_REMASTERED_FLAGS, ""),
    "TTP5: Muffle Rug": (TTP5_MUFFLE_RUG_FLAGS, ""),
    "TTP5: Pick 5": (TTP5_PICK_5_FLAGS, ""),
    "TTP5: Uphill Battle": (TTP5_UPHILL_BATTLE_FLAGS, ""),
    "SGLive Onsite 2026": (SGLIVE_ONSITE_FLAGS, ""),
}
