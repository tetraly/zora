"""Compass, map, boomerangs (SH-ITEM-01..03; shapes-answers.md update 10)."""
from ...model.enums import Item
from ...model.rooms import NO_ITEM_CODE
from ..errors import GenerationFailure
from ..rng import Rng
from .options import ShapeOptions
from .world import SetWorld

# update 10: a room counts unless the low seven bits of its item byte (item
# plus the two boss-sound bits) are one of these reserved items.
RESERVED_ITEMS = frozenset({NO_ITEM_CODE, Item.TRIFORCE_OF_POWER, Item.HEART_CONTAINER, Item.TRIFORCE,
                            Item.COMPASS, Item.MAP, Item.WOOD_BOOMERANG, Item.MAGICAL_BOOMERANG})
ITEM_DRAW_BUDGET = 10_000


def _counts(world: SetWorld, blob: int, cell: int) -> bool:
    if world.blob_of[cell] != blob:
        return False
    p = world.plans[cell]
    item = p.item if p.item is not None else 0x03
    return ((item | (p.boss_sound << 5)) & 0x7F) not in RESERVED_ITEMS


def counting_rooms(world: SetWorld, blob: int) -> int:
    """Rooms of the level that the item draws can hit."""
    return sum(_counts(world, blob, c) for c in world.cells_by_blob[blob])


def place_progression_items(world: SetWorld, rng: Rng,
                            opts: ShapeOptions) -> None:
    for blob in range(world.blob_count):
        level = world.levels[blob]
        # SH-ITEM-01: compass then map; SH-ITEM-02: boomerangs in levels 1
        # and 2. Each keeps the hit room's item position and trigger.
        codes = [Item.COMPASS, Item.MAP]
        if level == 1:
            codes.append(Item.WOOD_BOOMERANG)
        elif level == 2:
            codes.append(Item.MAGICAL_BOOMERANG)
        # Draws are uniform over all 128 cells; a miss is redrawn. One
        # budget of 10,000 draws per level covers its two or three items.
        budget = ITEM_DRAW_BUDGET
        for code in codes:
            while True:
                if budget <= 0:
                    raise GenerationFailure(
                        f"level {level}: no room for item {code:02X}"
                    )
                budget -= 1
                cell = rng.below(len(world.blob_of))
                if _counts(world, blob, cell):
                    world.plans[cell].item = code
                    break
