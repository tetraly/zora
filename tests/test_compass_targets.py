"""The compass marks each level's original Triforce room in per-level seeds (docs/design/archipelago-items.md piece 6):
with Add Triforces or Add Maps/Compasses to the Item Pool on, in Archipelago and single-player builds alike, each
level's Triforce room in its level info (byte $30, LevelInfo_TriforceRoomId) is the room BUILD left its piece in
(a cellar's: its stairs' room), and one of the level's rooms.

The serializer finds the room by the generic piece (derive_triforce_room_ptr). FINISH rewrites levels 1-7's pieces
as their own codes (write_level_codes), and the assignment may move them, so FINISH fixes each level's room first
(freeze_compass_targets). Before that, levels 1-7 got room $00 and the compass marker stood off the status bar's map
(a tester's report on 2.0.2's test build). tests/test_level_items_emulator.py checks the marker in the emulator."""
from functools import cache

import pytest

from tests.needs import needs_base_rom
from tests.test_solo_level_items import z1r
from zora import archipelago
from zora.flags.fields import ItemShuffleScope, ThreeState
from zora.flags.zora_flags import LevelItemShuffle, ZoraFlags, encode
from zora.generate import pipeline
from zora.model.levels import Level
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora.rom.serialize.levels import derive_triforce_room_ptr

SEED = 1
SWITCHES = {
    "triforces": {"triforce_shuffle": "anywhere"},
    "maps/compasses": {"map_compass_shuffle": "anywhere"},
    "both": {"triforce_shuffle": "anywhere", "map_compass_shuffle": "anywhere"},
}


def original_rooms(levels: list[Level]) -> dict[int, int]:
    """Each level's Triforce room as BUILD left it."""
    return {level.level_num: derive_triforce_room_ptr(level) for level in levels}


def written_rooms(rom: bytes, config=None) -> dict[int, tuple[int | None, frozenset[int]]]:  # type: ignore[no-untyped-def]
    """Each level's written Triforce room, with the level's rooms."""
    return {level.level_num: (level.triforce_room_ptr, frozenset(level.room_nums))
            for level in parse_rom(rom, config).levels}


@cache
def archipelago_case(switches: str) -> tuple[dict[int, int], dict[int, tuple[int | None, frozenset[int]]]]:
    """An Archipelago build with BUILD's own placement as the multiworld's (each place its own pool item)."""
    base = remember_repo_base_rom()
    result = archipelago.build_from_strings(*archipelago.flag_strings(SWITCHES[switches]), SEED, base)
    assignment = {place.name: item for place, item in zip(result.places, result.pool, strict=True)}
    return original_rooms(result.state.world.levels), written_rooms(archipelago.finish(result, assignment))


@cache
def single_player_case(switches: str) -> tuple[dict[int, int], dict[int, tuple[int | None, frozenset[int]]]]:
    """A single-player seed under Item Shuffle: Full, whose swaps move the level items."""
    base = remember_repo_base_rom()
    flags = z1r(ItemShuffleScope.FULL)
    on = SWITCHES[switches]
    zora = encode(ZoraFlags(
        triforce_shuffle=LevelItemShuffle.ANYWHERE if "triforce_shuffle" in on else LevelItemShuffle.OFF,
        map_compass_shuffle=LevelItemShuffle.ANYWHERE if "map_compass_shuffle" in on else LevelItemShuffle.OFF))
    chosen = pipeline.plan(flags, SEED, zora)
    built = pipeline.build(chosen, base)
    rom = pipeline.generate_rom(flags, SEED, base, zora_flag_string=zora).rom
    return original_rooms(built.world.levels), written_rooms(rom, chosen.config)


@needs_base_rom
@pytest.mark.parametrize("switches", SWITCHES)
@pytest.mark.parametrize("game", ["archipelago", "single player"])
def test_each_compass_marks_its_levels_original_triforce_room(game: str, switches: str) -> None:
    original, written = (archipelago_case if game == "archipelago" else single_player_case)(switches)
    for level_num, (room, rooms) in sorted(written.items()):
        assert room == original[level_num], (game, switches, level_num, room, original[level_num])
        assert room in rooms, (game, switches, level_num, f"${room:02X}")
