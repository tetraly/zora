"""Item and location names and their Archipelago IDs.

Items use the seed format's item names (zora.model.item_names), the ones ZORA's receivable() allows
(owner ruling: rupees, regular hearts, fairies, maps, compasses, regular Triforce pieces, the
Triforce of Power and the clock are never Archipelago items). Locations use ZORA's superset of place
names (zora.generate.places.all_place_names), so every name any seed can produce has a fixed ID.

An ID is fixed by the name's place in ZORA's list, so a name left out leaves a gap and no other ID
moves. IDs are stable as long as those lists keep their order: test/test_ids.py pins them.

Some items take another name in Archipelago (owner decisions, 2026-10-18), with IDs of their own
after the item codes': with Progressive Items on, an upgrade-line item is named by its line, as
ZORA's hint text names it (Sword Upgrade, ...), and with Pegasus Boots on the boomerangs' line is
the Boots Upgrade; without Progressive Items, Pegasus Boots names the two boomerangs Pegasus Boots
and Magical Boots; with Swords at Wood Sword Only or Swordless, the White Sword's item is a Bomb
Upgrade. ItemNaming says which apply to a seed; zora_names turns
Archipelago's names back into the codes ZORA writes.
"""
from collections import defaultdict, deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from .zora import archipelago as zora_ap
from .zora.generate.places import all_place_names
from .zora.generate.steps.hint_text import UPGRADE_LINES
from .zora.model.item_names import ITEM_NAMES

ITEM_ID_BASE = 1
LOCATION_ID_BASE = 1
RENAMED_ID_BASE = 101

# Each upgrade line's Archipelago name, in ID order (UPGRADE_LINES' words).
LINE_ITEMS = {"SWORD": "Sword Upgrade", "CANDLE": "Candle Upgrade", "ARROW": "Arrow Upgrade",
              "RING": "Ring Upgrade", "BOOMERANG": "Boomerang Upgrade"}
assert set(LINE_ITEMS) == set(UPGRADE_LINES.values()), "an upgrade line without an Archipelago name"
BOMB_UPGRADE = "Bomb Upgrade"
WHITE_SWORD = "White Sword"
BOOTS_UPGRADE = "Boots Upgrade"         # the BOOMERANG line's name with Pegasus Boots on
# The boomerangs' items one by one with Pegasus Boots on and Progressive Items off (owner, 2026-10-18)
BOOTS = {"Boomerang": "Pegasus Boots", "Magical Boomerang": "Magical Boots"}
RENAMED_ITEMS = (*LINE_ITEMS.values(), BOMB_UPGRADE, BOOTS_UPGRADE, *BOOTS.values())

ITEM_NAME_TO_ID: dict[str, int] = {
    name: ITEM_ID_BASE + index for index, name in enumerate(ITEM_NAMES.values()) if zora_ap.receivable(name)
}
ITEM_NAME_TO_ID |= {name: RENAMED_ID_BASE + index for index, name in enumerate(RENAMED_ITEMS)}
LOCATION_NAME_TO_ID: dict[str, int] = {
    name: LOCATION_ID_BASE + index for index, name in enumerate(all_place_names())
}

# Each line item's line name and grade (1 for its lowest code), and the code each renamed item is
# given as: a line's lowest (the game gives the line's next level for any of its codes).
LINE_OF: dict[str, tuple[str, int]] = {}
GIVEN_AS: dict[str, str] = {BOMB_UPGRADE: WHITE_SWORD}
for _line, _upgrade in LINE_ITEMS.items():
    _codes = sorted(code for code, line in UPGRADE_LINES.items() if line == _line)
    LINE_OF |= {ITEM_NAMES[code]: (_upgrade, grade) for grade, code in enumerate(_codes, start=1)}
    GIVEN_AS[_upgrade] = ITEM_NAMES[_codes[0]]
GIVEN_AS[BOOTS_UPGRADE] = GIVEN_AS[LINE_ITEMS["BOOMERANG"]]
GIVEN_AS |= {boots: boomerang for boomerang, boots in BOOTS.items()}

# Owner decision (2026-10-08): the blue potion is filler; ZORA's logic never requires it.
FILLER_ITEMS = frozenset({"Blue Potion"})
HEART_CONTAINER = "Heart Container"


@dataclass(frozen=True)
class ItemNaming:
    """Which of Archipelago's own item names a seed uses (from zora.archipelago.give_rules)."""
    progressive: bool = False
    bomb_upgrade: bool = False
    pegasus_boots: bool = False

    @classmethod
    def of(cls, rules: object) -> "ItemNaming":
        # bomb_upgrade and pegasus_boots: GiveRules fields ZORA adds with those settings
        return cls(*(bool(getattr(rules, field, False)) for field in ("progressive_items", "bomb_upgrade",
                                                                       "pegasus_boots")))

    def archipelago_name(self, name: str) -> str:
        """A ZORA item name as this seed names it in Archipelago."""
        if self.bomb_upgrade and name == WHITE_SWORD:
            return BOMB_UPGRADE
        if self.progressive and name in LINE_OF:
            line = LINE_OF[name][0]
            return BOOTS_UPGRADE if self.pegasus_boots and line == LINE_ITEMS["BOOMERANG"] else line
        if self.pegasus_boots and name in BOOTS:
            return BOOTS[name]
        return name

    def line_of(self, name: str) -> tuple[str, int] | None:
        """The upgrade item and grade a ZORA item counts as, when this seed names it by its line."""
        line = LINE_OF.get(name)
        if not self.progressive or line is None or self.archipelago_name(name) in (name, BOMB_UPGRADE):
            return None
        return self.archipelago_name(name), line[1]

    def members(self, upgrade: str) -> set[str]:
        """The ZORA items this seed names `upgrade`."""
        return {name for name in LINE_OF if self.archipelago_name(name) == upgrade}


def zora_names(names: Iterable[str], pool: Sequence[str], naming: ItemNaming) -> list[str]:
    """Archipelago's item names as the ZORA names finish() takes: a renamed item becomes one of the
    pool's own codes it stands for, each used once in pool order, so finish() sees the pool it
    built; past them (an item added to the multiworld beyond the pool), the code it is given as."""
    left: defaultdict[str, deque[str]] = defaultdict(deque)
    for name in pool:
        left[naming.archipelago_name(name)].append(name)
    return [left[name].popleft() if left[name] else GIVEN_AS.get(name, name) for name in names]
