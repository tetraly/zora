"""Encode level data with second-quest dungeons (owner decision, 2026-10-12): the encoding takes the
second-quest blocks' space, so with it on, generation stores each second-quest set's room block in
that set's first-quest slot (GameWorld.store_second_quest_sets_in_first_quest_slots) and the
serializer writes it there and points the set's levels at it. No ROM byte is changed after
serialization (owner rule, 2026-10-13).

  - a world with no second-quest set is unchanged; for 2nd Quest (C02 = 1) both sets move, for
    Mixed + Shapes (C02 = 4) the second-quest set only; twice is once; a set split over two blocks
    is refused, and so is an encoded write of a second-quest set left in its own slot;
  - the bytes are those the ROM-byte fold of beta 4 (019f80c) gave: the stored world's ROM is the
    unstored world's ROM with that fold applied (`rom_byte_fold` below, kept here as the
    yardstick), but for the stored set's own second-quest slot, which keeps the base ROM's bytes
    (so a plain twin parses and writes back byte for byte); the encoding replaces that slot
    whatever it holds, so the encoded bytes are exactly the fold's;
  - a plain build is unchanged (the step runs only with Encode level data on);
  - with the private encoder: an encoded 2nd Quest or Mixed + Shapes ROM decodes to its plain
    twin's blocks and differs from that twin only where the encoding may write.
The 100-seed decode checks and the emulator runs are private tests (private/level_encoding/tests);
the compass on an encoded second-quest level is tests/test_compass_pointers.py's.
"""
import copy
from dataclasses import replace
from functools import cache

import pytest

from tests.test_coop_reserved import z1r_with
from zora.flags.codec import decode, encode
from zora.flags.fields import ENCODE_LEVEL_DATA, DungeonLayoutSource, ThreeState
from zora.generate.pipeline import build, plan
from zora.model.game_world import GameWorld
from zora.rom import level_encoding
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.code_patches import SEED_CODE_ADDRESS, SEED_CODE_LENGTH
from zora.rom.game_config import GameConfig
from zora.rom.layout import (
    LEVEL_1_6_DATA_ADDRESS,
    LEVEL_1_6_DATA_ADDRESS_Q2,
    LEVEL_7_9_DATA_ADDRESS,
    LEVEL_7_9_DATA_ADDRESS_Q2,
    ROOM_BLOCK_ADDRESSES_Q1,
    ROOM_BLOCK_HIGH_BYTES,
)
from zora.rom.parse.rom_file import parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom

SECOND_QUEST = z1r_with(options={"C02": DungeonLayoutSource.SECOND_QUEST})
MIXED_WITH_SHAPES = z1r_with(options={"C02": DungeonLayoutSource.MIXED_WITH_SHAPES})
# Mixed + Shapes seeds whose second-quest set is levels 1-6, levels 7-9, and neither (measured):
# plain, and with Encode level data on, whose flag string draws other sources
MIXED_SEEDS = {2: [0], 5: [1], 1: []}
ENCODED_MIXED_SEEDS = {7: [0], 1: [1], 2: []}

SET_LEVELS = (range(1, 7), range(7, 10))
ROOM_BLOCK_SIZE = 0x300
FIRST_QUEST_BLOCKS = (LEVEL_1_6_DATA_ADDRESS, LEVEL_7_9_DATA_ADDRESS)
SECOND_QUEST_BLOCKS = (LEVEL_1_6_DATA_ADDRESS_Q2, LEVEL_7_9_DATA_ADDRESS_Q2)
FIRST_QUEST_HIGH_BYTES = ROOM_BLOCK_HIGH_BYTES[:2]
SECOND_QUEST_HIGH_BYTES = ROOM_BLOCK_HIGH_BYTES[2:]


def encoded(flags: str) -> str:
    return encode(decode(flags).updated(toggles={ENCODE_LEVEL_DATA.id: ThreeState.ON}))


@cache
def built_world(flags: str, seed: int) -> GameWorld:
    return build(plan(flags, seed), remember_repo_base_rom()).world


@cache
def plain_config(flags: str) -> GameConfig:
    return replace(plan(flags, 1).config, level_encoding=None)


def stored(world: GameWorld) -> GameWorld:
    moved = copy.deepcopy(world)
    moved.store_second_quest_sets_in_first_quest_slots()
    return moved


def plain(world: GameWorld, flags: str) -> bytes:
    return serialize_to_rom(world, remember_repo_base_rom(), config=plain_config(flags))


def high_byte_addresses(set_index: int) -> list[int]:
    return [ROOM_BLOCK_ADDRESSES_Q1 + 2 * level + 1 for level in SET_LEVELS[set_index]]


def second_quest_sets(rom: bytes) -> list[int]:
    return [set_index for set_index in range(len(SET_LEVELS))
            if {rom[address] for address in high_byte_addresses(set_index)} == {SECOND_QUEST_HIGH_BYTES[set_index]}]


def rom_byte_fold(rom: bytes) -> bytes:
    """The yardstick: beta 4's level_encoding.fold_second_quest_blocks (019f80c), which changed
    the serialized ROM's bytes just before the encoder. Each set reading its second-quest block
    had that block copied over its first-quest block and its levels' high bytes pointed there."""
    folded = bytearray(rom)
    for set_index in second_quest_sets(rom):
        source, target = SECOND_QUEST_BLOCKS[set_index], FIRST_QUEST_BLOCKS[set_index]
        folded[target:target + ROOM_BLOCK_SIZE] = rom[source:source + ROOM_BLOCK_SIZE]
        for address in high_byte_addresses(set_index):
            folded[address] = FIRST_QUEST_HIGH_BYTES[set_index]
    return bytes(folded)


def changed_outside(before: bytes, after: bytes, allowed: list[tuple[int, int]]) -> list[int]:
    return [offset for offset, (old, new) in enumerate(zip(before, after, strict=True))
            if old != new and not any(start <= offset < end for start, end in allowed)]


def without_seed_code(rom: bytes) -> bytes:
    return rom[:SEED_CODE_ADDRESS] + rom[SEED_CODE_ADDRESS + SEED_CODE_LENGTH:]


def check_store(flags: str, seed: int, sets: list[int]) -> None:
    world = built_world(flags, seed)
    before = plain(world, flags)
    moved = stored(world)
    after = plain(moved, flags)
    assert second_quest_sets(before) == sets and second_quest_sets(after) == []
    for set_index in sets:
        assert moved.blocks[set_index] is moved.blocks_2q[set_index] is moved.level_blocks[set_index]
    # The ROM-byte fold left the block in its own second-quest slot too; now that slot keeps the
    # base ROM's bytes (the encoding replaces it, whatever it holds: test_the_encoder_receives...).
    # The seed's code hashes the finished ROM (FP-HASH-01); an encoded build hashes the encoded ROM.
    expected = bytearray(rom_byte_fold(before))
    base = remember_repo_base_rom()
    for set_index in sets:
        slot = SECOND_QUEST_BLOCKS[set_index]
        expected[slot:slot + ROOM_BLOCK_SIZE] = base[slot:slot + ROOM_BLOCK_SIZE]
    assert without_seed_code(after) == without_seed_code(bytes(expected))
    assert plain(stored(moved), flags) == after


@pytest.mark.skipif(not level_encoding.is_available(), reason="level encoding is not installed")
@pytest.mark.parametrize(("flags", "seed"), [(SECOND_QUEST, 1), (MIXED_WITH_SHAPES, 2), (MIXED_WITH_SHAPES, 5)])
def test_the_encoder_receives_what_the_rom_byte_fold_gave_it(flags: str, seed: int) -> None:
    """The encoded bytes are those of beta 4's path (the ROM-byte fold just before the encoder),
    for the same world: the second-quest slots the fold left holding the block make no difference."""
    key = plan(encoded(flags), seed).config.level_encoding
    assert key is not None
    world = built_world(flags, seed)
    old_path = level_encoding.encode_rom(rom_byte_fold(plain(world, flags)), key)
    new_path = level_encoding.encode_rom(plain(stored(world), flags), key)
    assert without_seed_code(new_path) == without_seed_code(old_path)


def test_no_second_quest_set_is_unchanged() -> None:
    world = built_world(z1r_with(), 1)
    moved = stored(world)
    assert plain(moved, z1r_with()) == plain(world, z1r_with())
    assert all(block is moved.level_blocks[index] for index, block in enumerate(moved.blocks))


@pytest.mark.parametrize("seed", [1, 2])
def test_second_quest_stores_both_sets(seed: int) -> None:
    check_store(SECOND_QUEST, seed, [0, 1])


@pytest.mark.parametrize("seed", sorted(MIXED_SEEDS))
def test_mixed_with_shapes_stores_its_second_quest_set(seed: int) -> None:
    check_store(MIXED_WITH_SHAPES, seed, MIXED_SEEDS[seed])


def test_a_set_over_two_blocks_is_refused() -> None:
    world = copy.deepcopy(built_world(SECOND_QUEST, 1))
    world.levels[1].block = world.blocks[0]
    with pytest.raises(ValueError, match="levels 1-6 read more than one room block"):
        world.store_second_quest_sets_in_first_quest_slots()


@pytest.mark.skipif(not level_encoding.is_available(), reason="level encoding is not installed")
def test_an_encoded_write_needs_the_sets_stored() -> None:
    chosen = plan(encoded(SECOND_QUEST), 1)
    base = remember_repo_base_rom()
    unstored = copy.deepcopy(build(chosen, base).world)
    unstored.blocks = [*built_world(z1r_with(), 1).blocks]
    with pytest.raises(ValueError, match="stored in its first-quest slot"):
        serialize_to_rom(unstored, base, config=chosen.config)


@pytest.mark.skipif(not level_encoding.is_available(), reason="level encoding is not installed")
@pytest.mark.parametrize(("flags", "seed"),
                         [(SECOND_QUEST, 1), *((MIXED_WITH_SHAPES, seed) for seed in ENCODED_MIXED_SEEDS)])
def test_an_encoded_second_quest_rom_decodes_to_its_plain_twin(flags: str, seed: int) -> None:
    """The encoded build differs from its plain twin (the same world, encoding off) only where the
    encoding may write and in the seed's code (FP-HASH-01 hashes the finished ROM), and its level
    data decodes to the twin's, where each second-quest set is in its first-quest slot."""
    chosen = plan(encoded(flags), seed)
    assert chosen.config.level_encoding is not None
    base = remember_repo_base_rom()
    world = build(chosen, base).world
    rom = serialize_to_rom(world, base, config=chosen.config)
    twin = serialize_to_rom(world, base, config=replace(chosen.config, level_encoding=None))
    sets = [0, 1] if flags == SECOND_QUEST else ENCODED_MIXED_SEEDS[seed]
    assert [index for index, block in enumerate(world.blocks_2q) if block is world.level_blocks[index]] == sets
    assert second_quest_sets(twin) == []
    assert level_encoding.decode_level_data(rom, chosen.config.level_encoding) == level_encoding.plain_level_data(twin)
    allowed = [*level_encoding.changed_ranges_allowed(), (SEED_CODE_ADDRESS, SEED_CODE_ADDRESS + SEED_CODE_LENGTH)]
    assert not changed_outside(twin, rom, allowed)


@pytest.mark.parametrize(("flags", "seed"), [(SECOND_QUEST, 1), (MIXED_WITH_SHAPES, 2), (MIXED_WITH_SHAPES, 5)])
def test_a_stored_plain_twin_round_trips(flags: str, seed: int) -> None:
    """The plain twin of an encoded build (scripts/qa_sweep.py's and make_playtest's round trip)
    parses and writes back byte for byte."""
    twin = plain(stored(built_world(flags, seed)), flags)
    reading = GameConfig(dungeon_nothing_code=plain_config(flags).dungeon_nothing_code,
                         hint_mode=plain_config(flags).hint_mode)
    assert serialize_to_rom(parse_rom(twin, reading), twin, reading) == twin
