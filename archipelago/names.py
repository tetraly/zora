"""Item and location names and their Archipelago IDs.

Items use the seed format's item names (zora.model.item_names), the ones ZORA's receivable() allows
(owner ruling: rupees, regular hearts, fairies, maps, compasses, regular Triforce pieces, the
Triforce of Power and the clock are never Archipelago items). Locations use ZORA's superset of place
names (zora.generate.places.all_place_names), so every name any seed can produce has a fixed ID.

An ID is fixed by the name's place in ZORA's list, so a name left out leaves a gap and no other ID
moves. IDs are stable as long as those lists keep their order: test/test_ids.py pins them.
"""
from .zora import archipelago as zora_ap
from .zora.generate.places import all_place_names
from .zora.model.item_names import ITEM_NAMES

ITEM_ID_BASE = 1
LOCATION_ID_BASE = 1

ITEM_NAME_TO_ID: dict[str, int] = {
    name: ITEM_ID_BASE + index for index, name in enumerate(ITEM_NAMES.values()) if zora_ap.receivable(name)
}
LOCATION_NAME_TO_ID: dict[str, int] = {
    name: LOCATION_ID_BASE + index for index, name in enumerate(all_place_names())
}

# Owner decision (2026-10-08): the blue potion is filler; ZORA's logic never requires it.
FILLER_ITEMS = frozenset({"Blue Potion"})
HEART_CONTAINER = "Heart Container"
