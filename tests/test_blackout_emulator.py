"""Blackout (B50; post-shapes-b5.md PS-COLOR-04) in the emulator, on CP-5 with Blackout on: every room's
dark flag is cleared but Ganon's, so a room shows lit without the candle, in its level's darkened
colours (inner palette 3); the same ROM with that one room's dark flag set back, as PRG0 has its dark
rooms, shows the room dark instead. Ganon's room stays dark (its item byte $8E, PS-MONRD-03).

A room is dark when nearly all of its inner area is drawn black (the dark palette: only Link shows),
and lit when at most half is; the status bar and the walls are not looked at. A screenshot of each room is saved
to temp/emulator/blackout/ for a look."""
from functools import cache
from pathlib import Path

import numpy as np
import pytest

from tests.needs import needs_base_rom
from tests.test_assignment_emulator import Console
from tests.test_highlight_no_drop_rooms_emulator import (
    INNER_BOTTOM,
    INNER_LEFT,
    INNER_RIGHT,
    INNER_TOP,
    OPPOSITE,
    STEPS,
    Walker,
)
from zora.flags.codec import decode, encode
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.model.enums import Enemy, RoomType, WallType
from zora.model.levels import Level
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom

pytestmark = [needs_base_rom, pytest.mark.slow]

SEED = 1
LEVEL_1, LEVEL_9 = 1, 9
BLACK = (0, 0, 0)
BLACK_FLOOR_AT_LEAST = 0.9          # Link, the room's item and its blocks' edges aside
PLAY_AREA = slice(64, 240)           # the screen rows below the status bar
SHOTS = Path(__file__).resolve().parent.parent / "temp" / "emulator" / "blackout"


@cache
def blackout_rom() -> bytes:
    flags = encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(toggles={"B50": ThreeState.ON}))
    return generate_rom(flags, SEED, remember_repo_base_rom()).rom


def level(rom: bytes, number: int) -> Level:
    return next(level for level in parse_rom(rom).levels if level.level_num == number)


def doorway(rom: bytes) -> tuple[int, str, int]:
    """A room of level 1 (not a person's) entered from a neighbour of the level through an open door:
    the neighbour, the side it is left by and the room. The game darkens a dark room as Link walks
    in (entering it directly, as Console.enter_room does, does not)."""
    first = level(rom, LEVEL_1)
    rooms = {room.room_num: room for room in first.rooms}
    for room in first.rooms:
        if room.room_type == RoomType.BLACK_ROOM or room.has_monster_bit:
            continue
        for side, step in STEPS.items():
            neighbour = rooms.get(room.room_num - step)
            if neighbour is not None and getattr(neighbour.walls, side) == WallType.OPEN_DOOR \
                    and getattr(room.walls, OPPOSITE[side]) == WallType.OPEN_DOOR:
                return neighbour.room_num, side, room.room_num
    raise AssertionError("no room of level 1 has an open door from a neighbour")


def with_dark_room(rom: bytes, room_num: int) -> bytes:
    """The ROM with one room of level 1's dark flag set, as PRG0 has its dark rooms."""
    world = parse_rom(rom)
    block = next(level.block for level in world.levels if level.level_num == LEVEL_1)
    block.room(room_num).is_dark = True
    return serialize_to_rom(world, rom)


def walked_in(rom: bytes, shot: str) -> np.ndarray:
    """The play area once Link has walked into doorway()'s room (monsters cleared), saved as `shot`."""
    neighbour, side, _room = doorway(blackout_rom())
    console = Console(rom)
    walker = Walker(console)
    walker.enter(LEVEL_1, neighbour)
    walker.walk(side)
    frame = console.emu.last_frame
    SHOTS.mkdir(parents=True, exist_ok=True)
    np.save(SHOTS / f"{shot}.npy", frame)
    return frame[PLAY_AREA]


def colours(area: np.ndarray) -> set[tuple[int, ...]]:
    return {tuple(int(channel) for channel in pixel) for pixel in np.unique(area.reshape(-1, 3), axis=0)}


def test_the_rooms_show_blackouts_colours_without_the_candle() -> None:
    """Blackout's look: the floor black ($0E), the walls drawn in the level's accent; no room of the
    level is dark, so the same room with its dark flag set back draws its walls dimmer."""
    rom = blackout_rom()
    assert not any(room.is_dark for room in level(rom, LEVEL_1).rooms)
    lit = walked_in(rom, "lit")
    inner = lit[INNER_TOP - PLAY_AREA.start:INNER_BOTTOM - PLAY_AREA.start, INNER_LEFT:INNER_RIGHT]
    assert np.mean(np.all(inner == BLACK, axis=2)) > BLACK_FLOOR_AT_LEAST
    dark = walked_in(with_dark_room(rom, doorway(rom)[2]), "dark")
    assert np.any(lit != dark)
    assert colours(lit) - colours(dark), "the dark room should lose the lit room's wall colour"


def test_ganons_room_stays_dark() -> None:
    rom = blackout_rom()
    ganon = next(room for room in level(rom, LEVEL_9).rooms if room.enemy == Enemy.THE_BEAST)
    assert ganon.is_dark
