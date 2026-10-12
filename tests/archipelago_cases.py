"""Flag cases for the Archipelago Phase 2 tests (docs/archipelago.md): the coop test's finished
cases (tests/test_coop_reserved.py), plus the ZORA extras that move items into caves and the
mixed overworld quest."""
from dataclasses import replace

from tests.test_coop_reserved import BASELINE_FOR_OWNER_FLAGS, FINISHED_CASES, OWNER_FLAGS_ON, z1r_with
from zora.flags import zora_flags
from zora.flags.fields import DungeonLayoutSource, HintStyle, OverworldQuest, StartScreen, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.support import START_ITEM_TOGGLES

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
    # C01 = 2 (OW-MIX; Archipelago offers it, C06 stays at its default)
    "mixed overworld quest": (z1r_with(options={"C01": OverworldQuest.MIXED_FIRST_QUEST_VARIANT}), ""),
    # Held back from Archipelago until their logic scans pass (archipelago.HELD_BACK, owner ruling 2026-10-10)
    "second quest overworld": (z1r_with(options={"C01": OverworldQuest.SECOND_QUEST}), ""),
    "mixed overworld quest, second-quest variant": (
        z1r_with(options={"C01": OverworldQuest.MIXED_SECOND_QUEST_VARIANT}), ""),
    "random overworld quest": (z1r_with(options={"C01": OverworldQuest.RANDOM}), ""),
    "full start shuffle": (z1r_with(options={"C04": StartScreen.FULL_SHUFFLE}), ""),
    "wood sword screen start": (z1r_with(options={"C04": StartScreen.WOODEN_SWORD_SCREEN}), ""),
    "force overworld block": (z1r_with(toggles={"B81": ThreeState.ON}), ""),
    "wood sword cave behind blocks": (z1r_with(toggles={"B03": ThreeState.ON}), ""),
    # C03 = 1 (HT-HINT-04; logic scan passed 2026-10-11: 100 of 100 seeds)
    "helpful hints": (z1r_with(options={"C03": HintStyle.HELPFUL}), ""),
    # Logic scans passed 2026-10-11, 100 of 100 seeds at each value: C02 = 0 (PS-VAN), B25 on and
    # Random (VA-REJ-08), and each start item on and Random (FP-START-02 to -05). As in fc82ca6, a
    # toggle's case is On: Random is On or Off per seed, and Off is the baseline. The start items
    # run with Max Start Items All (C17 = 0), since the baseline's Max Start Items 0 keeps none.
    "first quest dungeons": (z1r_with(options={"C02": DungeonLayoutSource.FIRST_QUEST}), ""),
    # C02 = 1 (PS-VAN): passed 2026-10-11, 100 of 100 seeds, once the late gate walked item cellars
    "second quest dungeons": (z1r_with(options={"C02": DungeonLayoutSource.SECOND_QUEST}), ""),
    "important items in level 9": (z1r_with(toggles={"B25": ThreeState.ON}), ""),
    # B26 on (PS-START): passed 2026-10-11, 100 of 100 seeds at on and Random, with the baseline's
    # shapes dungeons and with 2nd Quest dungeons, whose paired levels can store exit room $7F
    # (PS-START-03)
    "start room swap": (z1r_with(toggles={"B26": ThreeState.ON}), ""),
    "start room swap, second quest dungeons": (
        z1r_with(options={"C02": DungeonLayoutSource.SECOND_QUEST}, toggles={"B26": ThreeState.ON}), ""),
    **{f"start item {field}": (z1r_with(options={"C17": 0}, toggles={field: ThreeState.ON}), "")
       for field in START_ITEM_TOGGLES},
}
