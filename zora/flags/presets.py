"""The four published presets (FL-PRE-01 to FL-PRE-04), CP-5's baseline and published variant A with
level encoding off, and ZORA's own presets, which set the ZORA flag string too, with the community
flagsets (ZORA_PRESETS).

PRESET_LIST is the one canonical, ordered list of every preset: each entry's shortcut, name and two flag
strings. The page's preset menu (form.presets) and https://zora.gg/presets.json, the presets a race bot
can roll (scripts/flags_api.py --presets; docs/flags-api.md "Presets"), are both made from it."""
from __future__ import annotations

from dataclasses import dataclass

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
# field of all four. Rookie Rumble, v3.6.6's fifth built-in preset, is not on the menu (owner ruling,
# 2026-10-27).
TTP5_UPHILL_BATTLE_FLAGS = "143oNtDD4Pw3Yw6SRryTCXlqTsRz2fxg4s4pJW"
SGLIVE_ONSITE_FLAGS = "12TDBKH6mxLfnSz4T7ME4bcIaaUe9sE7UVmj7RA"
# Zora The Explorer, weeks 1 to 5, and Consternation Plus (2026-11-17), each as published. Weeks 4 and 5
# share a Z1R string and differ in the ZORA string.
ZTE_WEEK_1_2_FLAGS = "143oNtDD4PAvB!U8nSk4yS8L09lgT10vRVe7sx"
ZTE_WEEK_3_FLAGS = "143oNtDD4PAvB!U8nSk4m!DgIQ6oraWI4Me7sx"
ZTE_WEEK_4_5_FLAGS = "143oNtDD4PAvB!U8nSk4mxFW0br2w5YUspe7sx"
CONSTERNATION_PLUS_FLAGS = "oIbnPfPb01Hll3D29Bc2!etrojQOSjJQZUULH"


# ---------------------------------------------------------------------------
# The canonical list
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Preset:
    """One preset: `key`, its shortcut (lowercase letters and digits; a race bot's command for it); `name`, the
    name the page's menu shows; `flags` and `zora`, its Z1R and ZORA flag strings (`zora` empty for none).
    `menu_id` is the page's own id for it (form.presets' "name"), when that differs from `name`; `hidden` keeps
    it off the page's menu."""
    key: str
    name: str
    flags: str
    zora: str = ""
    menu_id: str = ""
    hidden: bool = False

    @property
    def id(self) -> str:
        """The page's id for this preset (form.presets' "name"; the menu shows `name`)."""
        return self.menu_id or self.name


# The published presets, by their community names (owner rulings, beta 5), and CP-5: each a Z1R string alone.
# Random% (published variant B) stays off the menu (owner, beta 5).
Z1R_MENU: tuple[Preset, ...] = (
    Preset("consternation", "Consternation", MVP_BASELINE, menu_id="MVP baseline"),
    Preset("consternationremastered", "Consternation Remastered", PUBLISHED_VARIANT_A,
           menu_id="Published variant A"),
    Preset("randompercent", "Random%", PUBLISHED_VARIANT_B, menu_id="Published variant B", hidden=True),
    Preset("hopla", "Hopla", PUBLISHED_VARIANT_C, menu_id="Published variant C"),
    Preset("consternationnoencoding", "Consternation without level encoding", MVP_BASELINE_LEVEL_ENCODING_OFF,
           menu_id="MVP baseline, level encoding off"),
)
# ZORA's own presets and the community flagsets, after the published ones on the menu.
ZORA_MENU: tuple[Preset, ...] = (
    Preset("asnb", "All Swords No Boards", ASNB_FLAGS, ASNB_ZORA_FLAGS),
    Preset("vanilla", "Vanilla", VANILLA_FLAGS),
    Preset("ohk0hplaremastered", "OHK0HPla Remastered", OHK0HPLA_REMASTERED_FLAGS),
    Preset("ttp5mufflerug", "TTP5: Muffle Rug", TTP5_MUFFLE_RUG_FLAGS),
    Preset("ttp5pick5", "TTP5: Pick 5", TTP5_PICK_5_FLAGS),
    Preset("ttp5uphillbattle", "TTP5: Uphill Battle", TTP5_UPHILL_BATTLE_FLAGS),
    Preset("sglive2026", "SGLive Onsite 2026", SGLIVE_ONSITE_FLAGS),
    Preset("zte1", "Zora The Explorer Week 1", ZTE_WEEK_1_2_FLAGS, "10.J2EGOED"),
    Preset("zte2", "Zora The Explorer Week 2", ZTE_WEEK_1_2_FLAGS, "10.J2EkcYg"),
    Preset("zte3", "Zora The Explorer Week 3", ZTE_WEEK_3_FLAGS, "10.JpkCdvd"),
    Preset("zte4", "Zora The Explorer Week 4", ZTE_WEEK_4_5_FLAGS, "10.JpaUYAv"),
    Preset("zte5", "Zora The Explorer Week 5", ZTE_WEEK_4_5_FLAGS, "13.7Zg4ZxiL"),
    Preset("consternationplus", "Consternation Plus", CONSTERNATION_PLUS_FLAGS, "18.1DzN7gO9LZ4p"),
)
PRESET_LIST: tuple[Preset, ...] = Z1R_MENU + ZORA_MENU

# ZORA's presets by name: each one's Z1R and ZORA strings (the output matrix, the frozen strings and the tests).
ZORA_PRESETS: dict[str, tuple[str, str]] = {preset.name: (preset.flags, preset.zora) for preset in ZORA_MENU}
