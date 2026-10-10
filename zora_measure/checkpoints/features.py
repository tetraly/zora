"""The feature data's and code patches' figures (features-behavior.md)."""

import re
from collections import Counter
from functools import cache
from typing import Any

from zora.model.enums import Destination
from zora.model.game_world import GameWorld
from zora.model.overworld import ItemCave, MoneyMakingGameCave
from zora_measure.checkpoints.summaries import Summary

# --- B10 DATA checkpoints (docs/spec/features-behavior.md) -------------------

SPEC_B10 = "features-behavior.md @ 8d49fc3"


# FP-START-01's vector: 24 zero bytes, $22, $FF, eleven zero bytes, 8, two zero bytes
FP_START_ITEMS = bytes(24) + bytes([0x22, 0xFF]) + bytes(11) + bytes([0x08]) + bytes(2)
CONTINUE_HEARTS = 0x02


def b10_start_state(gw: GameWorld) -> dict[str, bool]:
    """FP-START-01: the Items block a new file and a second-quest switch
    start with (PRG0's immediate stores or a copied table, whichever the
    ROM holds) is the spec's vector; the Continue hearts operand is $02."""
    return {"new file": gw.starting_items_new_file == FP_START_ITEMS,
            "second-quest switch": gw.starting_items_second_quest == FP_START_ITEMS,
            "continue $02": gw.continue_hearts_operand == CONTINUE_HEARTS}


# FP-LOCK-02's Check as of the 2026-10-08 export (F10): line 15's entry addresses a record
# byte-identical to PRG0's line 15 record, and lines 12-14's entries are constant across the sample.
SPEC_B10_F10 = "features-behavior.md @ 66541d3"
LINE_15_PRG0 = "line 15 PRG0's record"
LINES_12_14_CONSTANT = "lines 12-14 constant"


@cache
def prg0_copyright_record() -> bytes:
    """PRG0's line 15 record (length, column, tiles), read from the repo's base ROM."""
    from zora.rom.base_rom import remember_repo_base_rom
    from zora.rom.parse.rom_file import parse_rom
    return parse_rom(remember_repo_base_rom()).credits_line_15_record


def b10_credits_locked(gw: GameWorld) -> tuple[bool, tuple[int, ...]]:
    """FP-LOCK-02 per ROM: whether line 15's record is PRG0's, and lines 12-14's entries (judged
    constant across the sample by the summary)."""
    return gw.credits_line_15_record == prg0_copyright_record(), tuple(gw.credits_pointers[:3])


def _credits_flags(records: list[tuple[bool, tuple[int, ...]]]) -> list[dict[str, bool]]:
    """Each ROM's two flags: its line 15 record, and its lines 12-14 entries equal to the sample's
    most common ones."""
    common = Counter(entries for _same, entries in records).most_common(1)[0][0] if records else ()
    return [{LINE_15_PRG0: same, LINES_12_14_CONSTANT: entries == common} for same, entries in records]


B10_CREDITS_SUMMARY = Summary(lambda values: " / ".join(str(sum(value[key] for value in values))
                                                        for key in (LINE_15_PRG0, LINES_12_14_CONSTANT)),
                              lambda flags: {key: float(hit) for key, hit in flags.items()},
                              resolve=_credits_flags)


def b10_mmg_amounts(gw: GameWorld) -> dict[str, int]:
    """FP-MMG-01: the five money-game amounts."""
    c = gw.overworld.get_cave(Destination.MONEY_MAKING_GAME, MoneyMakingGameCave)
    assert c is not None
    return {
        "p1": c.lose_small,
        "p2": c.lose_large,
        "p3": c.lose_small_2,
        "s": c.win_small,
        "l": c.win_large,
    }


def b10_sword_hearts(gw: GameWorld) -> dict[str, int]:
    """FP-SWORD-01: white and magical sword heart requirements."""
    ws = gw.overworld.get_cave(Destination.WHITE_SWORD_CAVE, ItemCave)
    ms = gw.overworld.get_cave(Destination.MAGICAL_SWORD_CAVE, ItemCave)
    assert ws is not None and ms is not None
    return {"white": ws.heart_requirement, "magical": ms.heart_requirement}


def b10_bomb_upgrade(gw: GameWorld) -> dict[str, int]:
    """FP-BOMB-01: bomb-upgrade price and capacity."""
    bu = gw.overworld.bomb_upgrade
    return {"cost": bu.cost, "count": bu.count}


# FP-TRIF-01's meaning: the count eight, as the digit or the word, standing
# alone (not part of a longer number or word)
EIGHT_COUNT = re.compile(r"(?<![0-9A-Z])(8|EIGHT)(?![0-9A-Z])")


def b10_level9_refusal(gw: GameWorld) -> bool:
    """FP-TRIF-01: the refusal text states the count eight, in any wording."""
    return EIGHT_COUNT.search(gw.level9_refusal_text) is not None


# The six constant B10 DATA items: the GameWorld field (read from the ROM by
# the parser) and the value each spec Check states
B10_CONSTANT_BYTES = (
    ("FP-RESET-01 operand $FA", "reset_controller1", 0xFA),
    ("FP-TEXT-01 text delay $02", "text_speed_value", 0x02),
    ("FP-BEEP-01 operand $00", "low_health_beep_value", 0x00),
    ("FP-FIX-01 DMC level $40", "dmc_level_value", 0x40),
    ("FP-Q2R-01 room $3E byte $01", "q2_room_trigger_value", 0x01),
    ("FP-LEVEL-01 dash tile $2F", "level_dash_tile", 0x2F),
)


def b10_constants(gw: GameWorld) -> dict[str, bool]:
    """FP-RESET-01, FP-TEXT-01, FP-BEEP-01, FP-FIX-01, FP-Q2R-01, FP-LEVEL-01:
    each byte of the finished ROM holds the spec's value."""
    return {label: getattr(gw, field) == value for label, field, value in B10_CONSTANT_BYTES}


def b10_title(gw: GameWorld) -> dict[str, Any]:
    """FP-TITLE-01: seed number shown and a constant version line (re-authored)."""
    return {"seed": gw.title_seed_number, "version": gw.title_version_line}



B10_MMG_SUMMARY = Summary(
    lambda vals: " ".join(f"{k} {min(v[k] for v in vals)}..{max(v[k] for v in vals)}"
                          for k in ("p1", "p2", "p3", "s", "l")),
    lambda v: {k: float(v[k]) for k in ("p1", "p2", "p3", "s", "l")},
)

B10_SWORD_SUMMARY = Summary(
    lambda vals: f"white {Counter(v['white'] for v in vals)} / magical {Counter(v['magical'] for v in vals)}",
    lambda v: {"white": float(v["white"]), "magical": float(v["magical"])},
)

B10_BOMB_SUMMARY = Summary(
    lambda vals: f"cost {min(v['cost'] for v in vals)}..{max(v['cost'] for v in vals)} "
                 f"count {Counter(v['count'] for v in vals)}",
    lambda v: {"cost": float(v["cost"]), "count": float(v["count"])},
)


B10_TITLE_SUMMARY = Summary(
    lambda vals: f"seeds {min(v['seed'] for v in vals)}..{max(v['seed'] for v in vals)}; "
                 f"version const {len({v['version'] for v in vals}) == 1}",
    lambda v: {"seed": float(v["seed"]), "version_const": float(len({v["version"]}) == 1)},
)


# --- B10 code-patch data (features-behavior.md) ------------------------------------


def exit_room_count_zero(gw: GameWorld) -> dict[str, bool]:
    """FP-ENTR-02: per dungeon 1-9, the level's exit-room count (level
    information +$23, low seven bits) is 0; and bit 7 is set in all nine."""
    from zora.rom.code_patches import EXIT_ROOM_COUNT_FLAG, LEVEL_INFO_EXIT_ROOM_COUNT
    stored = [level.palette_raw[LEVEL_INFO_EXIT_ROOM_COUNT] for level in gw.levels]
    flags = {str(level.level_num): value & ~EXIT_ROOM_COUNT_FLAG == 0
             for level, value in zip(gw.levels, stored, strict=True)}
    flags["bit 7"] = all(value & EXIT_ROOM_COUNT_FLAG for value in stored)
    return flags


def dungeon_arrival_codes(gw: GameWorld) -> bool:
    """FP-ENTR-01: every dungeon's arrival code (level information +$3D,
    the stairway list's last byte) is 2."""
    from zora.rom.code_patches import ARRIVAL_DUNGEON, LEVEL_INFO_ARRIVAL_CODE
    stairway_start = 0x34                       # level information +$34: the stairway list
    return all(level.stairway_data_raw[LEVEL_INFO_ARRIVAL_CODE - stairway_start] == ARRIVAL_DUNGEON
               for level in gw.levels)


def person_appearances(gw: GameWorld) -> dict[str, int]:
    """FP-PERSON-01: how many of the 17 cave person types take each of the
    four appearances $58-$5B."""
    from zora.generate.steps.person_appearances import (
        APPEARANCE_COUNT,
        CAVE_PERSON_TYPES,
        FIRST_APPEARANCE,
        person_appearance,
    )
    shown = Counter(person_appearance(gw, object_type) for object_type in CAVE_PERSON_TYPES)
    return {f"${code:02X}": shown[code]
            for code in range(FIRST_APPEARANCE, FIRST_APPEARANCE + APPEARANCE_COUNT)}


def _summed_counts(values: list[dict[str, int]]) -> str:
    return "/".join(str(sum(v[key] for v in values)) for key in values[0])


SUMMED_COUNTS = Summary(_summed_counts, lambda counts: {key: float(n) for key, n in counts.items()})
