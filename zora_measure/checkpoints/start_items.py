"""Starting items (features-behavior.md FP-START-02, FP-START-03, FP-START-05): the Checks measured
on finished ROMs. The spec's figures are the original randomizer's corpora: start-items-all (the MVP baseline
with Max Start Items All and Start Raft, Start Recorder and Start Power Bracelet on), start-items-rp6
(Random%'s six fields on) and hopla (zora_measure.corpora.corpus(name))."""
from collections.abc import Callable

from zora.generate.steps.cave_entries import RAFT_SCREENS
from zora.generate.steps.wood_sword_behind_blocks import BRACELET_SCREENS_WITH_32_33
from zora.model.enums import Item
from zora.model.game_world import GameWorld
from zora.rom.code_patches import PRG0_START_ITEMS
from zora.rom.start_items import HEART_VALUES_INDEX, ITEM_SLOTS, START_ITEM_SLOTS
from zora_measure.checkpoints.mixed_overworld import wood_sword_screen
from zora_measure.checkpoints.summaries import Summary

SPEC_START_ITEMS = "features-behavior.md @ F12"
# The corpora's flag strings (FP-START-02, FP-START-05), as ZORA encodes them.
START_ITEMS_ALL_FLAGS = "24UvCdw5OK1UIbAoBysjIZZEmvvXVazJV"
START_ITEMS_RP6_FLAGS = "qK68IC2aGKODuTQv7tFuo65c161UuVGnazJV"
HOPLA_FLAGS = "24UvB8dMXACpM!tUJ43MYSZ!QLLGtnaXW"
# Hopla with the five values ZORA does not build yet at the MVP baseline's (Dungeon Quest: Mixed +
# Shapes, C02 = 4; B25, B26, B30, B48 on): every start-item field, the start hearts, the overworld
# quest and B03 as Hopla has them, so its start-items rows compare with the hopla corpus.
HOPLA_BUILT_FLAGS = "24UvAOT!bXsqTCZFJHyLlAYLtbVYtnaXO"
HOPLA_ITEMS = (Item.RAFT, Item.RECORDER, Item.POWER_BRACELET)
RP6_ITEMS = (Item.BOMBS, Item.BAIT, Item.LETTER, Item.BLUE_CANDLE, Item.WOOD_BOOMERANG, Item.MAGICAL_BOOMERANG)
NAMES = {Item.RAFT: "Raft", Item.RECORDER: "Recorder", Item.POWER_BRACELET: "Power Bracelet", Item.BOMBS: "bombs",
         Item.BAIT: "Bait", Item.LETTER: "Letter", Item.BLUE_CANDLE: "blue candle",
         Item.WOOD_BOOMERANG: "wooden Boomerang", Item.MAGICAL_BOOMERANG: "Magical Boomerang"}


def _table(gw: GameWorld) -> bytes:
    return gw.starting_items_new_file or PRG0_START_ITEMS


def held(items: tuple[Item, ...]) -> Callable[[GameWorld], dict[str, bool]]:
    """FP-START-02: which of `items` the starting table holds, and how many."""
    def measure(gw: GameWorld) -> dict[str, bool]:
        table = _table(gw)
        present = [table[START_ITEM_SLOTS[item][0]] == START_ITEM_SLOTS[item][1] for item in items]
        figures = {NAMES[item]: flag for item, flag in zip(items, present, strict=True)}
        figures.update({f"exactly {count}": sum(present) == count for count in range(len(items) + 1)})
        return figures
    return measure


def table_bytes(gw: GameWorld) -> dict[str, bool]:
    """FP-START-03: each item slot raised, every other byte (but the hearts byte) FP-START-01's, the
    hearts byte $22 or $32 (C16 = 2 or 3), and the second-quest switch's table the same."""
    table = _table(gw)
    figures = {f"slot {slot} raised": table[slot] != PRG0_START_ITEMS[slot] for slot in ITEM_SLOTS}
    figures["other bytes FP-START-01's"] = all(
        table[index] == PRG0_START_ITEMS[index] for index in range(len(table))
        if index not in ITEM_SLOTS and index != HEART_VALUES_INDEX)
    figures.update({f"hearts ${value:02X}": table[HEART_VALUES_INDEX] == value for value in (0x22, 0x32)})
    figures["second quest the same"] = (gw.starting_items_second_quest or PRG0_START_ITEMS) == table
    return figures


def cave_by_start_item(gw: GameWorld) -> dict[str, bool]:
    """FP-START-04's Check: the wooden-sword cave on a Power Bracelet screen of OW-CAVE-07 (the
    Bracelet set with $20 and $21) or on a Raft screen ($2F, $45), by Hopla's start item."""
    screen = wood_sword_screen(gw)
    table = _table(gw)
    figures = {}
    for item in HOPLA_ITEMS:
        held_item = table[START_ITEM_SLOTS[item][0]] == START_ITEM_SLOTS[item][1]
        figures[f"{NAMES[item]}: Bracelet screen"] = held_item and screen in BRACELET_SCREENS_WITH_32_33
        figures[f"{NAMES[item]}: Raft screen"] = held_item and screen in RAFT_SCREENS
    return figures


def _counts(values: list[dict[str, bool]]) -> str:
    keys = [key for key in values[0] if any(value[key] for value in values)] if values else []
    return "; ".join(f"{key} {sum(value[key] for value in values)}" for key in keys)


# Each figure's count; the text lists the figures some ROM shows.
START_COUNTS = Summary(_counts, lambda value: {key: float(flag) for key, flag in value.items()})
