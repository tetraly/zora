"""Boss placement (SH-BOSS-01..07)."""
from zora.generate.errors import GenerationFailure
from zora.generate.rng import Rng
from zora.generate.shapes.options import ShapeOptions
from zora.generate.shapes.tables import (
    BOSS_COUNTS,
    DODONGO_BAD_LAYOUTS,
    GLEEOK4_EXTRA_BAD,
    GLEEOK_BAD_LAYOUTS,
    GOHMA_BAD_LAYOUTS,
    LEVEL_BOSS_POOL,
)
from zora.generate.shapes.world import SetWorld
from zora.model.enums import Item, RoomType
from zora.model.rooms import NO_ITEM_CODE


# SH-BOSS-05 (PS-BOSS-04 states the same bars): is this boss barred here?
def boss_barred(level_layout: int, movable: bool, boss: int) -> bool:
    if boss in (0x43, 0x44, 0x45):  # gleeok 2/3/4 heads
        if level_layout in GLEEOK_BAD_LAYOUTS or movable:
            return True
        if boss == 0x45 and level_layout in GLEEOK4_EXTRA_BAD:
            return True
        return False
    if boss in (0x33, 0x34):  # gohma
        return level_layout in GOHMA_BAD_LAYOUTS
    if boss in (0x31, 0x32):  # dodongo
        return level_layout in DODONGO_BAD_LAYOUTS
    # aqua, digdogger, manhandla, patra: no layout restrictions in the spec
    return False


def place_bosses(world: SetWorld, rng: Rng, opts: ShapeOptions) -> None:
    for blob in range(world.blob_count):
        level = world.levels[blob]
        pool = LEVEL_BOSS_POOL[level]
        count = BOSS_COUNTS[level]
        entrance = world.entrance.get(level)
        candidates = [c for c in sorted(world.cells_by_blob[blob])
                      if world.plans[c].enemy is None
                      and c != entrance
                      and world.plans[c].layout not in (RoomType.TRIFORCE_ROOM,)
                      and not (world.plans[c].layout == RoomType.TURNSTILE_ROOM)]
        # SH-BOSS-04: exclude layout $20 "with or without a push block"
        candidates = [c for c in candidates
                      if not (world.plans[c].layout == RoomType.TURNSTILE_ROOM)]
        placed = 0
        for i in range(count):
            # SH-BOSS-06: the first boss in levels 1-8 must sit on an item
            # (which becomes the heart container).
            need_item = (i == 0 and level <= 8)
            options = [c for c in candidates
                       if not need_item
                       or (world.plans[c].item not in (None, NO_ITEM_CODE))]
            if not options:
                raise GenerationFailure(
                    f"level {level}: no room for boss #{i} (need item={need_item})"
                )
            for _ in range(200):
                cell = options[rng.below(len(options))]
                boss = pool[rng.below(len(pool))]
                plan = world.plans[cell]
                if not boss_barred(plan.layout or 0, plan.movable, boss):
                    break
            else:
                raise GenerationFailure(f"level {level}: boss placement failed")
            plan.enemy = boss
            candidates.remove(cell)
            if need_item:
                plan.item = Item.HEART_CONTAINER
                world.boss_room[level] = cell
            placed += 1
        if placed != count:
            raise GenerationFailure(f"level {level}: placed {placed}/{count} bosses")
