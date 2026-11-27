"""Per-level mode's compass marker in the emulator (asm/flags2/level-compass; docs/design/archipelago-items.md piece
6), on PRG0 and PRG1. A level's compass marks its original Triforce room, and its marker blinks until the item at
the piece's original spot is taken, not until the level's piece is held: holding the piece, found elsewhere, leaves
it blinking; taking the room's item, whatever the assignment put there, makes it steady. Levels whose piece stood in
an item cellar follow that cellar (finish.compass_item_rooms). A ROM without the pool switches keeps the game's
marker: the patch is written only in per-level mode."""
import pytest

from tests.needs import needs_base_rom
from tests.test_assignment_emulator import Console
from tests.test_level_items_emulator import _finished, rom_with
from zora.generate.finish import compass_item_rooms
from zora.generate.places import Place, PlaceKind
from zora.model.enums import Item
from zora.rom import owner_patches
from zora.rom.flags2_patch_data import PATCHES

INV_COMPASS = 0x667                     # a bit per level 1-8
INV_TRIFORCE = 0x671
MARKER_ATTRIBUTES = 0x200 + 86 + 4      # Sprites+86, X = 4: the Triforce marker's palette
STEADY, BLINK = 0x03, 0x02
BLINK_CYCLE = 32                        # frames: 16 of each palette while it blinks
SAMPLES = 2 * BLINK_CYCLE


def spot_level(revision: str) -> tuple[int, int]:
    """The first level whose piece stood on a room's floor in BUILD, and that room (its compass's marked room)."""
    _, built = _finished(revision)
    rooms = compass_item_rooms(built.world)
    for level in sorted(built.world.levels, key=lambda level: level.level_num):
        if level.level_num <= len(rooms) and any(room.room_num == rooms[level.level_num - 1]
                                                 and room.item is Item.TRIFORCE for room in level.rooms):
            return level.level_num, rooms[level.level_num - 1]
    raise AssertionError("no level's piece on a room floor")


def console_in_spot(revision: str) -> tuple[Console, int]:
    """In the spot room of spot_level, which holds a heart container in place of the level's piece, with the
    level's compass."""
    level, room = spot_level(revision)
    place = Place(PlaceKind.ROOM, "the piece's spot", level=level, room_num=room)
    console = Console(rom_with(revision, ((place, Item.HEART_CONTAINER),)))
    console.enter_room(level, room)
    console.emu[INV_COMPASS] |= 1 << (level - 1)
    return console, level


def palettes(console: Console) -> set[int]:
    seen = set()
    for _ in range(SAMPLES):
        console.emu.run(1)
        seen.add(console.emu[MARKER_ATTRIBUTES])
    return seen


@needs_base_rom
@pytest.mark.parametrize("revision", ["prg0", "prg1"])
def test_the_piece_taken_elsewhere_leaves_the_marker_blinking(revision: str) -> None:
    """The level's piece held (found in another room or level), its spot's item still there: the marker blinks,
    where the game's would stand still."""
    console, level = console_in_spot(revision)
    console.emu[INV_TRIFORCE] |= 1 << (level - 1)
    assert palettes(console) == {STEADY, BLINK}


@needs_base_rom
@pytest.mark.parametrize("revision", ["prg0", "prg1"])
def test_taking_the_rooms_item_stops_the_blink(revision: str) -> None:
    """The spot's heart container taken, the level's piece never held: the marker stops blinking."""
    console, level = console_in_spot(revision)
    assert palettes(console) == {STEADY, BLINK}
    console.clear_monsters()
    console.take_room_item()
    assert not console.emu[INV_TRIFORCE] & 1 << (level - 1)
    assert palettes(console) == {STEADY}


def test_only_per_level_mode_writes_the_patch() -> None:
    """Every other ROM keeps the game's marker: the Archipelago and single-player patch sets leave it out."""
    patch = {offset for offset, _ in PATCHES["level-compass"]}
    for archipelago_rom, ap_items in ((False, False), (True, None), (False, True)):
        written = {offset for offset, _ in owner_patches.owner_patch_writes((), archipelago_rom=archipelago_rom,
                                                                              ap_items=ap_items)}
        assert not patch & written
    assert patch <= {offset for offset, _ in owner_patches.owner_patch_writes((), ap_items=True, per_level=True)}
