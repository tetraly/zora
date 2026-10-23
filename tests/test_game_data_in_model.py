"""Game data ZORA used to write after serialization lives in the GameWorld model (owner ruling,
2026-10-13): each level's exit room and arrival code and the overworld's arrival code (level
information +$23 and +$3D, FP-ENTR-01/02), fp-start-02's start table (FP-START-03) and the
engine's "no item" byte (Randomize Magical Sword's $0E). Generation sets them, the serializer
writes them, the parser reads them back, so parsing a finished ROM and writing it again over the
PRG0 base reproduces every byte.
"""
from dataclasses import replace
from functools import cache

import pytest

from tests.needs import needs_base_rom
from zora.flags.codec import decode, encode
from zora.flags.fields import ENCODE_LEVEL_DATA, DungeonLayoutSource, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import Built, build, finish, plan
from zora.model.enums import DungeonNothingCode
from zora.model.levels import ARRIVAL_DUNGEON, ARRIVAL_OVERWORLD
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.code_patches import (
    EXIT_ROOM_COUNT_FLAG,
    LEVEL_INFO_ARRIVAL_CODE,
    LEVEL_INFO_EXIT_ROOM_COUNT,
    SEED_CODE_ADDRESS,
    SEED_CODE_LENGTH,
    START_ITEMS_SIZE,
    START_ITEMS_TABLE,
)
from zora.rom.final_steps import FINAL_STEPS
from zora.rom.game_config import GameConfig
from zora.rom.layout import ASM_NOTHING_CODE_PATCH_OFFSET, LEVEL_INFO_ADDRESS, LEVEL_INFO_SIZE
from zora.rom.parse.rom_file import original_bins_from_rom, parse_rom
from zora.rom.player_settings import DEFAULT_PLAYER_SETTINGS
from zora.rom.serialize.game_world import serialize_game_world
from zora.rom.serialize.rom_file import serialize_to_rom
from zora_measure.checkpoints.start_items import START_ITEMS_ALL_FLAGS
from zora_measure.checkpoints.start_rooms import START_ROOM_SWAP_FLAGS

SWORD = "1.D"                     # ZORA flags: Randomize Magical Sword, the hearts capped at 12
# (name, flag string, ZORA flag string): each case writes one of the moved values its own way
CASES = [
    ("baseline", MVP_BASELINE_LEVEL_ENCODING_OFF, ""),
    ("Randomize Magical Sword", MVP_BASELINE_LEVEL_ENCODING_OFF, SWORD),
    ("start items", START_ITEMS_ALL_FLAGS, ""),
    ("start-room swap", START_ROOM_SWAP_FLAGS, ""),
    ("2nd Quest", encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(
        options={"C02": DungeonLayoutSource.SECOND_QUEST})), ""),
]
CASE_NAMES = [name for name, _, _ in CASES]
SEED = 1


def plain(flags: str) -> str:
    """The flags with Encode level data off: the parser reads plain room data."""
    return encode(decode(flags).updated(toggles={ENCODE_LEVEL_DATA.id: ThreeState.OFF}))


@cache
def finished(name: str) -> tuple[Built, bytes]:
    _, flags, zora = CASES[CASE_NAMES.index(name)]
    base = remember_repo_base_rom()
    built = build(plan(plain(flags), SEED, zora), base)
    return built, finish(built, base)


@needs_base_rom
@pytest.mark.parametrize("name", CASE_NAMES)
def test_generation_sets_the_values(name: str) -> None:
    built, _ = finished(name)
    world = built.world
    assert all(level.exit_room is not None and level.arrival_code is not None for level in world.levels)
    assert world.overworld_arrival_code == ARRIVAL_OVERWORLD
    assert world.dungeon_nothing_code is built.plan.config.dungeon_nothing_code
    moved = name == "start-room swap"
    assert any(level.arrival_code != ARRIVAL_DUNGEON for level in world.levels) == moved
    assert (world.dungeon_nothing_code is DungeonNothingCode.ZORA_REMAP) == (name == "Randomize Magical Sword")
    assert bool(world.start_items) == (name == "start items")


@needs_base_rom
@pytest.mark.parametrize("name", CASE_NAMES)
def test_the_serializer_writes_them_and_the_parser_reads_them_back(name: str) -> None:
    """The model's serialization alone (no final step) holds the finished ROM's bytes."""
    built, rom = finished(name)
    world, config = built.world, built.plan.config
    base = remember_repo_base_rom()
    serialized = bytearray(base)
    patch = serialize_game_world(world, original_bins_from_rom(base), hint_mode=config.hint_mode, config=config)
    patch.apply(serialized)
    for level in world.levels:
        info = LEVEL_INFO_ADDRESS + level.level_num * LEVEL_INFO_SIZE
        for offset in (LEVEL_INFO_EXIT_ROOM_COUNT, LEVEL_INFO_ARRIVAL_CODE):
            assert serialized[info + offset] == rom[info + offset]
        assert level.exit_room is not None
        assert rom[info + LEVEL_INFO_EXIT_ROOM_COUNT] == level.exit_room | EXIT_ROOM_COUNT_FLAG
    assert serialized[LEVEL_INFO_ADDRESS + LEVEL_INFO_ARRIVAL_CODE] == rom[LEVEL_INFO_ADDRESS + LEVEL_INFO_ARRIVAL_CODE]
    assert serialized[ASM_NOTHING_CODE_PATCH_OFFSET] == rom[ASM_NOTHING_CODE_PATCH_OFFSET]
    if world.start_items:
        table = slice(START_ITEMS_TABLE, START_ITEMS_TABLE + START_ITEMS_SIZE)
        assert serialized[table] == rom[table]
    parsed = parse_rom(rom, replace(config, level_encoding=None))
    assert [(level.exit_room, level.arrival_code) for level in parsed.levels] == \
        [(level.exit_room, level.arrival_code) for level in world.levels]
    assert parsed.overworld_arrival_code == world.overworld_arrival_code
    assert parsed.dungeon_nothing_code is world.dungeon_nothing_code
    assert set(parsed.start_items) == set(world.start_items)


@needs_base_rom
@pytest.mark.parametrize("name", CASE_NAMES)
def test_a_finished_rom_round_trips_over_prg0(name: str) -> None:
    """Parse the finished ROM, write the world over the PRG0 base with the build's config: every
    byte comes back, the moved ones included (and over the finished ROM itself)."""
    built, rom = finished(name)
    config = built.plan.config
    world = parse_rom(rom, config)
    # with the default player settings, as finish() writes them: they write the statistics screen,
    # which every ROM has (2026-10-17) and the world does not hold
    again = serialize_to_rom(world, remember_repo_base_rom(), config=config, player_settings=DEFAULT_PLAYER_SETTINGS)
    # The seed's code is the generated world's (owner ruling, beta 5: code_patches.seed_code_items);
    # a world parsed back is not the generated one, so over the base it gets its own code. Written
    # over the finished ROM itself (below), the code the ROM shows is kept.
    seed_code = range(SEED_CODE_ADDRESS, SEED_CODE_ADDRESS + SEED_CODE_LENGTH)
    assert [hex(offset) for offset in range(len(rom))
            if again[offset] != rom[offset] and offset not in seed_code] == []
    assert serialize_to_rom(world, rom, config=config) == rom


def test_no_final_step_writes_game_data() -> None:
    """Hidden Health (B55, FP-HIDE-01) writes code after the player settings, which it overrides."""
    assert [step.name for step in FINAL_STEPS] == ["code_patches", "encode_level_data", "slot_identity",
                                                   "stamp_seed_code", "stamp_seed_number", "player_settings",
                                                   "hidden_health"]


@needs_base_rom
def test_the_code_patches_need_the_entry_codes() -> None:
    """A world no generation finished (PRG0's, parsed) has no entry codes: writing ZORA's code
    patches, which read them, is refused until they are recorded."""
    base = remember_repo_base_rom()
    world = parse_rom(base)
    with pytest.raises(ValueError, match="record_level_entry_codes"):
        serialize_to_rom(world, base, config=GameConfig(features_b10=True))
    world.record_level_entry_codes()
    serialize_to_rom(world, base, config=GameConfig(features_b10=True))
