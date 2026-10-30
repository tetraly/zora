"""ZeroMeaning's nine Link sprites in the emulator (docs/z1m1/sprites.md; tests/test_z1m1_link_sprites.py):
walking each way, attacking each way, holding up an item and the title story each draw Link from the
set's art, the fromGame bytes filled in from the ROM; and in play Link's palette holds the set's own
colors (Playable character's colors: The set's own, the default).

Link's sprites are the OAM records at his place; each is an 8x16 half whose pattern-table bytes must be
the set's half of that tile number (link_sprite.LINK_HALVES names halves by the tile the game draws).
The poses draw: walking $00-$0E and the small shield's $58 and $5A, attacking $10-$1A, holding up an item
$78, and the title story's last scene Link holding up the triforce ($78, from its own pattern block).

Beside them, what Link's colors 2 and 3 also color (a set's own colors change them): the same scenes
on two ROMs differing only in those two colors, and every object whose pixels differ, Link aside."""
from functools import cache

import numpy as np
import pytest

from tests.emulator import OBJ_X, OBJ_Y, Button, Emulator
from tests.needs import needs_base_rom
from tests.test_assignment_emulator import Console
from tests.test_progressive_emulator import CAVE_INIT_FRAMES, CAVE_MODE, CAVE_WARE_XS, CAVE_WARE_Y, Game
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.model.enums import Destination, Enemy, Item
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.inventory import ITEMS, SWORD_SLOT
from zora.rom.link_art import sprite_set_tiles
from zora.rom.link_sprite import HALF_SIZE, LINK_HALVES, built_in_sprite_sets
from zora.rom.parse.rom_file import parse_rom
from zora.rom.player_settings import (
    CharacterColors,
    LinkSprite,
    PlayerSettings,
    apply_player_settings,
    shown_link_colors,
)

pytestmark = [needs_base_rom, pytest.mark.slow]

SEED = 1
SET_IDS = sorted(set_id for set_id in built_in_sprite_sets() if set_id.startswith("zeromeaning-"))
OAM_RECORD, HIDDEN_Y = 4, 0xEF
NEAR = 16                                 # Link's sprites lie within this many pixels of his place
TILE_BYTES = 16
SPRITE_TABLE = 0x1000                     # an 8x16 sprite's odd tile number picks the second pattern table
HALF_TILES = {int(name[1:], 16): index for index, name in enumerate(LINK_HALVES)}
WALKING = {Button.LEFT: {0x00, 0x02, 0x04, 0x06}, Button.RIGHT: {0x00, 0x02, 0x04, 0x06},
           Button.UP: {0x0C, 0x0E}, Button.DOWN: {0x08, 0x0A, 0x58, 0x5A}}
ATTACKING = {Button.RIGHT: {0x10, 0x12}, Button.DOWN: {0x14, 0x16}, Button.UP: {0x18, 0x1A}}
LIFTING = 0x78
WALK_FRAMES, ATTACK_FRAMES, LIFT_FRAMES = 16, 14, 240
STORY_FRAMES = 4600                       # the story's last scene (Link holding up the triforce) by then
LEVEL_INFO = 0x6B7E                       # WRAM: the loaded level information
SPRITE_PALETTE_0 = 20                     # its sprite palette 0, colors 1 to 3
# Colors 2 and 3 for the comparison: far from the game's ($27, $17)
VIVID_OTHER = (0x2A, 0x05)
PLAYFIELD_TOP = 64                        # screen rows above are the status bar
FRAMES_ON_SCREEN = 40


@cache
def finished() -> bytes:
    return generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, remember_repo_base_rom()).rom


@cache
def with_set(set_id: str) -> bytes:
    return apply_player_settings(finished(), PlayerSettings(link_sprite=LinkSprite.SET,
                                                            sprite_set=built_in_sprite_sets()[set_id]))


@cache
def drawn_halves(set_id: str) -> bytes:
    """The set's 640 bytes as the ROM holds them (fromGame from the base ROM)."""
    base = remember_repo_base_rom()
    return sprite_set_tiles(built_in_sprite_sets()[set_id], lambda offset, length: base[offset:offset + length])


def link_tiles_drawn(emu: Emulator, near: tuple[int, int] | None = None) -> set[int]:
    """The tile numbers of the OAM records at Link's place (or at `near`)."""
    x, y = near or (emu[OBJ_X], emu[OBJ_Y])
    oam = emu.sprites()
    return {oam[i + 1] for i in range(0, len(oam), OAM_RECORD)
            if oam[i] < HIDDEN_Y and abs(oam[i + 3] - x) <= NEAR and abs(oam[i] - y) <= NEAR}


def assert_drawn_from_the_set(emu: Emulator, tiles: set[int], set_id: str) -> None:
    """Each tile's 8x16 half in the pattern tables is the set's half of that tile number."""
    patterns, art = emu.pattern_tables(), drawn_halves(set_id)
    for tile in tiles:
        start = (tile & 1) * SPRITE_TABLE + (tile & ~1) * TILE_BYTES
        index = HALF_TILES[tile & ~1]
        assert patterns[start:start + HALF_SIZE] == art[index * HALF_SIZE:(index + 1) * HALF_SIZE], (set_id, hex(tile))


def in_play(rom: bytes) -> Game:
    game = Game(rom)
    game.emu[ITEMS + SWORD_SLOT] = 1
    return game


@pytest.mark.parametrize("set_id", SET_IDS)
def test_walking_and_attacking(set_id: str) -> None:
    game = in_play(with_set(set_id))
    for button, expected in WALKING.items():
        seen: set[int] = set()
        for _frame in range(WALK_FRAMES):
            game.emu.run(1, button)
            seen |= link_tiles_drawn(game.emu)
        assert expected <= seen and seen <= HALF_TILES.keys(), (button, sorted(map(hex, seen)))
        assert_drawn_from_the_set(game.emu, seen, set_id)
    for button, expected in ATTACKING.items():
        game.emu.run(4, button)
        game.emu.run(2, Button.A)
        seen = set()
        for _frame in range(ATTACK_FRAMES):
            game.emu.run(1)
            seen |= {tile for tile in link_tiles_drawn(game.emu) if tile & ~1 in HALF_TILES}
        assert expected <= seen, (button, sorted(map(hex, seen)))
        assert_drawn_from_the_set(game.emu, seen, set_id)


def cave_screen(rom: bytes, destination: Destination) -> int:
    return next(screen.screen_num for screen in parse_rom(rom).overworld.screens if screen.destination == destination)


def enter_cave(game: Game, rom: bytes, destination: Destination) -> None:
    game.go_to_screen(cave_screen(rom, destination))
    game.start_mode(CAVE_MODE)
    game.wait_for_play(CAVE_MODE)
    game.emu.run(CAVE_INIT_FRAMES)


@pytest.mark.parametrize("set_id", SET_IDS)
def test_holding_up_an_item(set_id: str) -> None:
    """The wooden sword cave's sword taken: Link holds it up, drawn with half $78."""
    rom = with_set(set_id)
    game = Game(rom)
    enter_cave(game, rom, Destination.WOOD_SWORD_CAVE)
    game.emu[OBJ_X], game.emu[OBJ_Y] = CAVE_WARE_XS[1], CAVE_WARE_Y
    seen: set[int] = set()
    for _frame in range(LIFT_FRAMES):
        game.emu.run(1)
        seen |= {tile for tile in link_tiles_drawn(game.emu) if tile & ~1 in HALF_TILES}
    assert LIFTING in seen, sorted(map(hex, seen))
    assert_drawn_from_the_set(game.emu, seen, set_id)


@pytest.mark.parametrize("set_id", SET_IDS)
def test_the_title_story(set_id: str) -> None:
    """The story's last scene: Link holding up the triforce, half $78 from the story's own patterns."""
    emu = Emulator(with_set(set_id))
    seen: set[int] = set()
    for _frame in range(STORY_FRAMES):
        emu.run(1)
        oam = emu.sprites()
        drawn = {oam[i + 1] for i in range(0, len(oam), OAM_RECORD) if oam[i] < HIDDEN_Y and oam[i + 1] == LIFTING}
        if drawn and not seen:
            assert_drawn_from_the_set(emu, drawn, set_id)
        seen |= drawn
    assert LIFTING in seen


@pytest.mark.parametrize("set_id", SET_IDS)
def test_links_palette_holds_the_sets_colors(set_id: str) -> None:
    rom = with_set(set_id)
    tunics, other = shown_link_colors(PlayerSettings(link_sprite=LinkSprite.SET,
                                                     sprite_set=built_in_sprite_sets()[set_id]))
    game = in_play(rom)
    palette = [game.emu[LEVEL_INFO + SPRITE_PALETTE_0 + entry] for entry in range(3)]
    assert palette == [tunics[0], *other], set_id
    mine = in_play(apply_player_settings(finished(), PlayerSettings(
        link_sprite=LinkSprite.SET, sprite_set=built_in_sprite_sets()[set_id], character_colors=CharacterColors.MINE)))
    assert [mine.emu[LEVEL_INFO + SPRITE_PALETTE_0 + entry] for entry in range(3)] == [0x29, 0x27, 0x17]


# --- What else colors 2 and 3 color --------------------------------------------------------------------

def vivid() -> bytes:
    return apply_player_settings(finished(), PlayerSettings(link_colors=VIVID_OTHER,
                                                            character_colors=CharacterColors.MINE))


def changed_away_from_link(first: Emulator, second: Emulator, below: int | None = None) -> bool:
    """Whether the two frames differ in the playfield anywhere but on Link (and, given `below`, above
    that screen row: a cave's wares are items, not its person)."""
    differs = np.any(first.last_frame != second.last_frame, axis=2)
    differs[:PLAYFIELD_TOP] = False
    if below is not None:
        differs[below:] = False
    x, y = first[OBJ_X], first[OBJ_Y] + 3          # OAM's Y is the screen row less one; Link's sprites sit 2 below
    differs[y:y + NEAR, x:x + NEAR] = False
    return bool(differs.any())


# The floor items that ItemSlotToPaletteOffsetsOrValues draws in palette 0 and that use colors 2 or 3
LINK_COLORED_ITEMS = {Item.WOOD_SWORD, Item.WOOD_ARROWS, Item.BOW, Item.RAFT, Item.LADDER, Item.MAGICAL_SHIELD,
                      Item.WOOD_BOOMERANG}
FLOOR_ITEMS = [item for item in Item if item.value < 0x24 and not item.name.startswith("ITEM_")]


def test_which_items_colors_2_and_3_also_color() -> None:
    """Every item put on a level 1 floor, in two ROMs differing only in Link's colors 2 and 3: the
    items whose pixels differ are LINK_COLORED_ITEMS, which the game also draws in the inventory and
    the status bar with the same palette (DrawItemBySlot)."""
    games = [Game(rom) for rom in (finished(), vivid())]
    for game in games:
        game.enter_level(1)
    colored = set()
    for item in FLOOR_ITEMS:
        for game in games:
            game.reload_room_with_item(item.value)
            game.emu.run(FRAMES_ON_SCREEN)
        if changed_away_from_link(games[0].emu, games[1].emu):
            colored.add(item)
    assert colored == LINK_COLORED_ITEMS, sorted(item.name for item in colored ^ LINK_COLORED_ITEMS)


# Scenes with people: the cave people (the sword caves' old man, a shop's merchant, the medicine shop's old
# woman once the letter is shown, a secret's Moblin), a level's old man and Zelda in level 9's last room
PEOPLE_CAVES = {"old man": Destination.WOOD_SWORD_CAVE, "merchant": Destination.SHOP_1,
                "old woman": Destination.POTION_SHOP, "Moblin": Destination.MEDIUM_SECRET}
LETTER_SLOT, LETTER_SHOWN = 0x0F, 2       # InvLetter: 2 once the old woman has seen it


WARES_ROW = CAVE_WARE_Y                  # a ware's OAM Y: the screen rows from here down hold the wares


def test_which_people_colors_2_and_3_also_color() -> None:
    """Zelda only (drawn in palette 0, tile $F6): the cave people are drawn in palette 1
    (SetUpCommonCaveObjects' attribute $81), and a level's old man as they are; a cave's wares change
    as LINK_COLORED_ITEMS do (the wooden sword under the old man, a shop's arrows and shield)."""
    roms = (finished(), vivid())
    colored = set()
    for name, destination in PEOPLE_CAVES.items():
        games = [Game(rom) for rom in roms]
        for rom, game in zip(roms, games, strict=True):
            game.emu[ITEMS + LETTER_SLOT] = LETTER_SHOWN
            enter_cave(game, rom, destination)
            game.emu.run(FRAMES_ON_SCREEN)
        if changed_away_from_link(games[0].emu, games[1].emu, below=WARES_ROW):
            colored.add(name)
    world = parse_rom(finished())
    level_9 = world.levels[8]
    zelda_room = next(room.room_num for room in level_9.rooms if room.enemy == Enemy.THE_KIDNAPPED)
    person_room = next((level.level_num, room.room_num) for level in world.levels for room in level.rooms
                       if room.is_person_room)
    for name, (level, room) in {"Zelda": (9, zelda_room), "a level's old man": person_room}.items():
        consoles = [Console(rom) for rom in roms]
        for console in consoles:
            console.enter_room(level, room)
            console.emu.run(FRAMES_ON_SCREEN)
        if changed_away_from_link(consoles[0].emu, consoles[1].emu):
            colored.add(name)
    assert colored == {"Zelda"}, sorted(colored)
