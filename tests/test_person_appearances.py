"""FP-PERSON-01's cave person appearances keep their own tiles.

2.0.2's test build (and every release since FP-PERSON-01, 2026-10-02) drew the secret caves' Moblin
garbled: seed 123 with the flags below showed the elder's left half beside the tile after it. The draw
gave each of its 17 ObjAnimations slots ($6B-$7B) one of the four appearances ($58-$5B: the two elders,
the merchant, the Moblin) but left the slot's own frame list, the elder's [$98] for most, and
ObjAnimFrameHeap holds one list per pointer, written from the first slot that names it: a slot drawn
as the Moblin wrote $98 over the Moblin's $F8. The Moblin is drawn as two unmirrored tiles, so the
secret caves' Moblin (object type $7B, slot $7C, never drawn) showed $98 beside $9A.
"""
from functools import cache

import pytest

from tests.emulator import OBJ_TYPE, OBJ_X, OBJ_Y
from tests.needs import needs_base_rom
from tests.test_bait_in_pool import Console
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate import pipeline
from zora.generate.steps.person_appearances import APPEARANCE_COUNT, FIRST_APPEARANCE, FIRST_NPC_ENTRY
from zora.generate.steps.shuffle_enemy_groups import FIXED_FRAME_91
from zora.model.enums import Destination
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora.rom.player_settings import PlayerSettings

APPEARANCES = range(FIRST_APPEARANCE, FIRST_APPEARANCE + APPEARANCE_COUNT)
ELDER, SECOND_ELDER, MERCHANT, MOBLIN = APPEARANCES
GAME_TILES = {ELDER: 0x98, SECOND_ELDER: 0x9A, MERCHANT: 0x9C, MOBLIN: 0xF8}
# Shuffle Enemy Groups (B42) sets ObjAnimFrameHeap + 91, the Moblin's tile, to $B0 (PS-SPR).
SHUFFLED_GROUP_TILES = GAME_TILES | {FIXED_FRAME_91[0]: FIXED_FRAME_91[1]}
assert FIXED_FRAME_91[0] == MOBLIN

REPORTED = ("XYMGQYH7VTj2dNTXqGj4XU9p48AVhbD", "23.HamqMLlaU3pwF", 123)   # the 2.0.2 test report, B42 off
BASELINE = (MVP_BASELINE_LEVEL_ENCODING_OFF, "", 1)                         # B42 on
CASES = [(REPORTED, GAME_TILES), (BASELINE, SHUFFLED_GROUP_TILES)]

ANIMATION_SLOT_OFFSET = 1        # ObjAnimations slot 0 is Link: object type T is slot T + 1
PERSON_SLOT = 1                  # the cave person's object slot
SPRITE_RECORD = 4                # OAM: Y, tile, attributes, X
SPRITE_HEIGHT = 16
CAVE_SETTLE_FRAMES = 120


@cache
def _rom(case: tuple[str, str, int]) -> bytes:
    flags, zora, seed = case
    return pipeline.generate_rom(flags, seed, remember_repo_base_rom(), PlayerSettings(),
                                 zora_flag_string=zora).rom


@needs_base_rom
def test_the_game_tiles_are_the_original_games() -> None:
    enemies = parse_rom(remember_repo_base_rom()).enemies
    assert {appearance: enemies.frame_bytes(appearance, 1)[0] for appearance in APPEARANCES} == GAME_TILES


@needs_base_rom
@pytest.mark.parametrize(("case", "tiles"), CASES, ids=["reported", "baseline"])
def test_each_appearance_keeps_its_own_tile(case: tuple[str, str, int], tiles: dict[int, int]) -> None:
    enemies = parse_rom(_rom(case)).enemies
    assert {appearance: enemies.frame_bytes(appearance, 1)[0] for appearance in APPEARANCES} == tiles


@needs_base_rom
def test_the_reported_secret_cave_draws_the_moblin_with_its_own_tile() -> None:
    """In the emulator: the reported seed's secret cave draws its Moblin's left half with $F8, not the
    elder's $98."""
    rom = _rom(REPORTED)
    world = parse_rom(rom)
    screen = next(s.screen_num for s in world.overworld.screens if s.destination == Destination.MEDIUM_SECRET)
    console = Console(rom)
    console.enter_cave(screen)
    console.emu.run(CAVE_SETTLE_FRAMES)
    object_type = console.emu[OBJ_TYPE + PERSON_SLOT]
    appearance = world.enemies.overworld_npc_pointers[object_type + ANIMATION_SLOT_OFFSET - FIRST_NPC_ENTRY]
    assert appearance == MOBLIN
    x, y = console.emu[OBJ_X + PERSON_SLOT], console.emu[OBJ_Y + PERSON_SLOT]
    sprites = console.emu.sprites()
    records = [sprites[at:at + SPRITE_RECORD] for at in range(0, len(sprites), SPRITE_RECORD)]
    left = [tile for record_y, tile, _, record_x in records if record_x == x and abs(record_y - y) < SPRITE_HEIGHT]
    assert left == [GAME_TILES[MOBLIN]]
