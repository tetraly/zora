"""Flag cases for the Archipelago Phase 2 tests (docs/archipelago.md): the coop test's finished
cases (tests/test_coop_reserved.py), plus the ZORA extras that move items into caves and the
mixed overworld quest."""
from dataclasses import replace

from tests.test_coop_reserved import BASELINE_FOR_OWNER_FLAGS, FINISHED_CASES, OWNER_FLAGS_ON, z1r_with
from zora.flags import zora_flags
from zora.flags.fields import (CaveShuffle, DungeonLayoutSource, DungeonRoomShuffle, HintStyle, HitPointChange,
                               Level9Requirement, OverworldQuest, PinnedItem, StartScreen, ThreeState,
                               WoodenSwordState)
from zora.flags.zora_flags import OopsAllBosses, OopsAllEnemies
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
    # B30 on (PS-OSTAIR): passed 2026-10-12, 100 of 100 seeds at on and Random
    "remove most open stairs": (z1r_with(toggles={"B30": ThreeState.ON}), ""),
    # B48 on (HT-BOOK): passed 2026-10-12, 100 of 100 seeds at on and Random
    "book to understand npcs": (z1r_with(toggles={"B48": ThreeState.ON}), ""),
    # C02 = 4 (SH-SRC): passed 2026-10-12, 100 of 100 seeds, alone and with B26 on
    "mixed and shapes dungeons": (z1r_with(options={"C02": DungeonLayoutSource.MIXED_WITH_SHAPES}), ""),
    **{f"start item {field}": (z1r_with(options={"C17": 0}, toggles={field: ThreeState.ON}), "")
       for field in START_ITEM_TOGGLES},
    # Passed 2026-10-13 (beta 5), 100 of 100 seeds at each value: B29 Off (FL-OFF-04; Off is the new
    # value, On the baseline's), and each Oops All value (ZORA extras, docs/design/oops-all.md)
    "bomb upgraders not shuffled": (z1r_with(toggles={"B29": ThreeState.OFF}), ""),
    **{f"oops all {family.name.lower()}": (MVP_BASELINE_LEVEL_ENCODING_OFF, zora_flags.encode(
        replace(zora_flags.DEFAULT, oops_all_enemies=family))) for family in OopsAllEnemies if family},
    "oops all dodongos": (MVP_BASELINE_LEVEL_ENCODING_OFF, zora_flags.encode(
        replace(zora_flags.DEFAULT, oops_all_bosses=OopsAllBosses.DODONGOS))),
    # Passed 2026-10-15 (beta 6), 100 of 100 seeds at each value, every event reached: B02 Off
    # (OW-CAVE-12; Off is the new value, On the baseline's) and Cave Shuffle Non-dungeons Only (C05 = 2,
    # OW-CAVE-09); C05 = 0, 1 and Random (OW-CAVE-09 to OW-CAVE-11) once the hint shops swap screens
    # with Randomize Dead Woods (3f35c57), with random settings for every other offered option
    "wood sword cave not shuffled": (z1r_with(toggles={"B02": ThreeState.OFF}), ""),
    "cave shuffle non-dungeon caves only": (z1r_with(options={"C05": CaveShuffle.NON_DUNGEON_CAVES_ONLY}), ""),
    "cave shuffle vanilla": (z1r_with(options={"C05": CaveShuffle.VANILLA}), ""),
    "cave shuffle dungeon doors only": (z1r_with(options={"C05": CaveShuffle.DUNGEON_DOORS_ONLY}), ""),
    "cave shuffle random": (z1r_with(options={"C05": CaveShuffle.RANDOM}), ""),
    # Passed 2026-10-16, 100 of 100 seeds at each value, every event reached, with random settings for
    # every other option: Dungeon Quest Mixed Quest, Random No Shapes and Random (C02 = 2, 5, 6;
    # SH-SRC-09, SH-SRC-10) and Allow Universal Drops In Shapes on (B91, SH-ROOM-16; Random is On
    # or Off per seed)
    "mixed quest dungeons": (z1r_with(options={"C02": DungeonLayoutSource.MIXED}), ""),
    "random dungeons without shapes": (z1r_with(options={"C02": DungeonLayoutSource.RANDOM_WITHOUT_SHAPES}), ""),
    "random dungeons": (z1r_with(options={"C02": DungeonLayoutSource.RANDOM}), ""),
    "universal drops in shapes": (z1r_with(toggles={"B91": ThreeState.ON}), ""),
    # Passed 2026-10-18, 100 of 100 seeds at each value, every event reached, with random settings for
    # every other offered option, then all of them together (archipelago.HELD_BACK's comment): one
    # case per group, each toggle On. The start items are above (START_ITEM_TOGGLES).
    "ganon hp zero": (z1r_with(toggles={"B41": ThreeState.ON}), ""),
    "ohko": (z1r_with(toggles={"B53": ThreeState.ON}), ""),
    "do not sort shapes": (z1r_with(toggles={"B86": ThreeState.ON}), ""),
    "pegasus boots": (MVP_BASELINE_LEVEL_ENCODING_OFF, zora_flags.encode(
        replace(zora_flags.DEFAULT, pegasus_boots=ThreeState.ON))),
    "highlight no-drop rooms": (MVP_BASELINE_LEVEL_ENCODING_OFF, zora_flags.encode(
        replace(zora_flags.DEFAULT, highlight_no_drop_rooms=ThreeState.ON))),
    "enemy and boss hp zero": (z1r_with(options={"C09": HitPointChange.ALL_ZERO, "C10": HitPointChange.ALL_ZERO}), ""),
    # the sword caves' redrawn hearts (B10) at the new range values: white 6 to 4, magical 12 to 13
    "sword heart ranges": (z1r_with(toggles={"B10": ThreeState.ON},
                                    options={"C20": 2, "C21": 2, "C22": 2, "C23": 1}), ""),
    "three start pieces": (z1r_with(options={"C18": 3}), ""),
    # Random start pieces between the range's ends: 2 to 6
    "random start pieces in a range": (z1r_with(options={"C18": 9, "C24": 2, "C25": 2}), ""),
    "one starting heart": (z1r_with(options={"C16": 0}), ""),
    "pinned items": (z1r_with(options={"C11": PinnedItem.WOODEN_BOOMERANG, "C13": PinnedItem.SILVER_ARROW,
                                       "C26": PinnedItem.HEART_CONTAINER, "C27": PinnedItem.MAGICAL_BOOMERANG}), ""),
    "wood sword only": (z1r_with(options={"C07": WoodenSwordState.WOODEN_SWORD_ONLY}), ""),
    # Passed 2026-10-18 once acceptance E10 kept Ganon's room out from behind level 9's last-boss
    # shutters (c155f9e), 100 of 100 seeds at each value, then with everything offered: B52 and B68
    # on and Random (B68 is a start item, above), Starting Hearts 7, 9 and 15, Armos Item: Recorder
    "permanent sword beam": (z1r_with(toggles={"B52": ThreeState.ON}), ""),
    "seven starting hearts": (z1r_with(options={"C16": 6}), ""),
    "recorder at the armos": (z1r_with(options={"C11": PinnedItem.RECORDER}), ""),
    # Passed 2026-10-18 at 79216a2 once a cap below the minimum and the looping level 9 pins were
    # refused, 100 of 100 seeds each: Magical Sword Hearts (min) 13 and 14 (C22 = 3, 4), Level 9 Item
    # 1 and 2 at Book and White Sword (C26, C27 = 1, 15)
    "magical sword hearts at least 14": (z1r_with(toggles={"B10": ThreeState.ON}, options={"C22": 4}), ""),
    "book and white sword in level 9": (z1r_with(options={"C26": PinnedItem.BOOK_OF_MAGIC,
                                                          "C27": PinnedItem.WHITE_SWORD}), ""),
    # Expanded Dungeon Locations on: passed 2026-10-18 at 7aa37c0, 100 of 100 seeds on and Random
    "expanded dungeon locations": (MVP_BASELINE_LEVEL_ENCODING_OFF, zora_flags.encode(
        replace(zora_flags.DEFAULT, expanded_dungeon_locations=ThreeState.ON))),
    # Allow Triforces in Stairways on, as redesigned (1e1e9f6, the world side ab24e8b): passed
    # 2026-10-18 at af98afa, 100 of 100 seeds on and Random, with Item Shuffle Full
    "triforces in stairways": (MVP_BASELINE_LEVEL_ENCODING_OFF, zora_flags.encode(
        replace(zora_flags.DEFAULT, allow_triforces_in_stairways=ThreeState.ON))),
    # Add Bridges to the River and Add Lost Woods Shortcut on, once the logic reached the river's west
    # side by them (6a3c660): passed 2026-10-19, 100 of 100 seeds on and Random each
    "bridges and lost woods shortcut": (z1r_with(toggles={"B87": ThreeState.ON, "B88": ThreeState.ON}), ""),
    # Beta 8's values, passed 2026-10-22, 100 of 100 seeds at each value, then 400 of 400 together
    # (archipelago.HELD_BACK's comment): Level 9 Entry (C08 = 1 to 12), the Uphill Battle set off (B18,
    # B20, B32, B33, B35), Dungeon Room Shuffle Vanilla (C14 = 0), and B07, B39, B21 and B37 on
    "open level 9": (z1r_with(options={"C08": Level9Requirement.OPEN}), ""),
    "specific triforces for level 9": (z1r_with(options={"C08": Level9Requirement.SPECIFIC_PIECES}), ""),
    "uphill battle set off": (z1r_with(toggles=dict.fromkeys(("B18", "B20", "B32", "B33", "B35"), ThreeState.OFF)), ""),
    "vanilla dungeon rooms": (z1r_with(options={"C14": DungeonRoomShuffle.VANILLA}), ""),
    "recorder to unbeaten dungeons and important drops": (
        z1r_with(toggles={"B07": ThreeState.ON, "B39": ThreeState.ON}), ""),
    "second quest doors and monsters": (z1r_with(toggles={"B21": ThreeState.ON, "B37": ThreeState.ON}), ""),
}
