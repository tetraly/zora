"""Flag cases for the Archipelago Phase 2 tests (docs/archipelago.md): the coop test's finished
cases (tests/test_coop_reserved.py), plus the ZORA extras that move items into caves."""
from dataclasses import replace

from tests.test_coop_reserved import BASELINE_FOR_OWNER_FLAGS, FINISHED_CASES, OWNER_FLAGS_ON, z1r_with
from zora.flags import zora_flags
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF

# Randomize Magical Sword and Randomize Letter (version 1's "1.F")
SWORD_AND_LETTER = "1.F"
EVERY_ZORA_FLAG_ON = zora_flags.encode(replace(
    zora_flags.DEFAULT, randomize_magical_sword=True, randomize_letter=True, magical_sword_hearts_highest=12,
    progressive_items=True,
    shop_items_in_pool=True, **OWNER_FLAGS_ON))   # owner requirement B: at most 12 hearts with the sword randomized

FLAG_CASES: dict[str, tuple[str, str]] = {
    **FINISHED_CASES,
    "magical sword and letter": (MVP_BASELINE_LEVEL_ENCODING_OFF, SWORD_AND_LETTER),
    "every ZORA flag on": (z1r_with(toggles=BASELINE_FOR_OWNER_FLAGS), EVERY_ZORA_FLAG_ON),
}
