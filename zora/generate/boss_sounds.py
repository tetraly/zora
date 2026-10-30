"""PS-MONRD-07, the boss-sound end pass: only Ganon's level-9 neighbours keep a boss sound.

A dungeon room's boss sound (LevelBlockAttrsE bits 6-5, BossSound) loops in that room while the
level's boss is undefeated (CheckBossSoundEffectUW). Earlier steps leave sounds that name no boss:
PRG0's own (29 rooms, beside several bosses), the monster re-deal's marks (PS-MONRD-03) when the late
gate does not run (VA-REJ-02), and the one the map move carries away from Ganon (SH-MAP-06), a
phantom roar (player report, beta 8). Once per seed, after the accepted pass, the end pass resets
every boss sound of the four room blocks. The sounds before it are read (the acceptance check's and
the hints' whole-item-byte lookups, PS-MONRD-03), so the pass runs after the hint text.

The same pass forces level 9's Triforce gate room's north, east and west sides to shutters unless
walls (PS-MONRD-07's informative bullet, VA-REJ-19, A77). The late gate already forces them right
after its repair wherever the walks count the room's shutters open; this catches the room it must
leave alone until after the beatability checks (A80: a second-quest level 9 whose start room moved,
trigger 0).

Every boss of levels 1-8 is silent, so a roar is heard only beside Ganon. (Gatekeeper Bosses, retired
2026-10-29, first gave its gatekeepers' neighbours their boss's own sound; players took those roars for
bugs: docs/reports/bugs-2809934285.md, docs/reports/gatekeeper-lessons.md.)"""
from __future__ import annotations

from ..model import room_grid
from ..model.enums import BossSound, Enemy, Item, Side
from ..model.game_world import GameWorld
from ..model.levels import L9_ENTRY_PERSON_LIST, LEVEL_9, LevelBlock
from ..model.rooms import PERSON_LAYOUT_BYTE, ItemInfo, Room
from .late_gate.blocks import LAST_BOSS_SECRET
from .late_gate.fixes import force_gate_room_sides

GANON_MONSTER_BYTE = Enemy.THE_BEAST.value                               # whole monster byte $3E
GANON_ITEM = ItemInfo(Item.TRIFORCE_OF_POWER, BossSound.NONE, True)      # item byte $8E
GANON_NEIGHBOR_SOUND = BossSound.ROAR_AQUAMENTUS_GLEEOK_GANON            # boss sound 1 (bit 5, $20)
LEVELS_7_TO_9_BLOCK = 1                                                  # index in each quest's pair


def _level_9_rooms(gw: GameWorld, block: LevelBlock) -> set[int]:
    """The rooms of the block's level 9: the seed's own when it lives there, else the block's
    PRG0 level 9 (a quest's unused block keeps its own, and its Ganon is marked too)."""
    if gw.levels[LEVEL_9 - 1].block is block:
        return set(gw.levels[LEVEL_9 - 1].room_nums)
    return {number for level in block.levels if level.level_num == LEVEL_9 for number in level.room_nums}


def _ganon_rooms(block: LevelBlock) -> list[Room]:
    return [room for room in block.rooms if room.monster_byte == GANON_MONSTER_BYTE]


def ganon_neighbors(gw: GameWorld, block: LevelBlock) -> set[int]:
    """PS-MONRD-07 step 3's rooms: each up, down, left and right neighbour of a Ganon room that
    belongs to level 9; no test crosses a row end or the block's top or bottom."""
    level_9 = _level_9_rooms(gw, block)
    return {number for room in _ganon_rooms(block) for side in Side
            if (number := room_grid.neighbor(room.room_num, side)) is not None and number in level_9}


def _all_blocks(gw: GameWorld) -> list[LevelBlock]:
    """The four room blocks, each once (an encoded seed's first-quest slot may hold a quest-2 block)."""
    blocks: list[LevelBlock] = []
    for block in (*gw.blocks, *gw.blocks_2q):
        if all(block is not seen for seen in blocks):
            blocks.append(block)
    return blocks


def _levels_7_to_9_blocks(gw: GameWorld) -> list[LevelBlock]:
    blocks = [gw.blocks[LEVELS_7_TO_9_BLOCK], gw.blocks_2q[LEVELS_7_TO_9_BLOCK]]
    return blocks if blocks[0] is not blocks[1] else blocks[:1]


def _gate_room(gw: GameWorld, block: LevelBlock) -> Room | None:
    """The block's first level-9 room, in room order, with the whole monster byte $0B and the
    whole layout byte $A6: the Triforce gate room (VA-REJ-19)."""
    level_9 = _level_9_rooms(gw, block)
    return next((room for room in block.rooms if room.room_num in level_9
                 and room.monster_byte == L9_ENTRY_PERSON_LIST and room.layout_byte == PERSON_LAYOUT_BYTE), None)


def boss_sound_end_pass(gw: GameWorld) -> None:
    """PS-MONRD-07: clear every room's boss sound in all four blocks; in the two levels 7-9 blocks
    give each Ganon room item byte $8E and trigger byte $03, then set boss sound 1 on its level-9
    neighbours, and force the Triforce gate room's north, east and west sides (VA-REJ-19)."""
    for block in _all_blocks(gw):
        for room in block.rooms:
            room.boss_sound = BossSound.NONE
    for block in _levels_7_to_9_blocks(gw):
        for room in _ganon_rooms(block):
            room.item_info = GANON_ITEM
            room.secret_info = LAST_BOSS_SECRET
        for number in ganon_neighbors(gw, block):
            block.room(number).boss_sound = GANON_NEIGHBOR_SOUND
        if (gate_room := _gate_room(gw, block)) is not None:
            force_gate_room_sides(gate_room)


def boss_sound_problems(gw: GameWorld) -> list[str]:
    """Every room whose boss sound is not PS-MONRD-07's result: sound 1 on Ganon's level-9
    neighbours in the levels 7-9 blocks, none anywhere else."""
    problems = []
    marked = {id(block): ganon_neighbors(gw, block) for block in _levels_7_to_9_blocks(gw)}
    for block_name, block in zip(("1-6", "7-9", "2Q 1-6", "2Q 7-9"), (*gw.blocks, *gw.blocks_2q), strict=True):
        expected_rooms = marked.get(id(block), set())
        for room in block.rooms:
            expected = GANON_NEIGHBOR_SOUND if room.room_num in expected_rooms else BossSound.NONE
            if room.boss_sound != expected:
                problems.append(f"block {block_name}: room ${room.room_num:02X} has boss sound "
                                f"{room.boss_sound.name}, PS-MONRD-07 gives {expected.name}")
    return problems


def check_boss_sounds(gw: GameWorld) -> None:
    """The world ships PS-MONRD-07's boss sounds exactly; a later step that wrote one is a bug."""
    problems = boss_sound_problems(gw)
    if problems:
        raise AssertionError("; ".join(problems))
