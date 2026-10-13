"""Encode level data with second-quest dungeons (owner decision, 2026-10-12): just before the
encoding, level_encoding.fold_second_quest_blocks copies each second-quest set's room block into
that set's first-quest block and points the set's levels there.

  - the fold leaves a ROM with no second-quest set unchanged (PRG0, the encoded baseline's sets);
  - for 2nd Quest (C02 = 1) it folds both sets, for Mixed + Shapes (C02 = 4) the second-quest set
    only, changing nothing else; folding twice is folding once; a set split over two blocks is
    refused;
  - a plain build is unchanged by it (it runs only with Encode level data on);
  - with the private encoder: an encoded 2nd Quest or Mixed + Shapes ROM decodes to its plain
    twin's folded blocks and differs from that twin only where the encoding may write.
The 100-seed decode checks and the emulator runs are private tests (private/level_encoding/tests).
"""
from dataclasses import replace
from functools import cache

import pytest

from tests.test_coop_reserved import z1r_with
from zora.flags.codec import decode, encode
from zora.flags.fields import ENCODE_LEVEL_DATA, DungeonLayoutSource, ThreeState
from zora.generate.pipeline import build, generate_rom, plan
from zora.rom import level_encoding
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.code_patches import SEED_CODE_ADDRESS, SEED_CODE_LENGTH
from zora.rom.layout import ROOM_BLOCK_ADDRESSES_Q1
from zora.rom.level_encoding import (
    FIRST_QUEST_BLOCKS,
    FIRST_QUEST_HIGH_BYTES,
    ROOM_BLOCK_SIZE,
    SECOND_QUEST_BLOCKS,
    SECOND_QUEST_HIGH_BYTES,
    SET_LEVELS,
    fold_second_quest_blocks,
)
from zora.rom.serialize.rom_file import serialize_to_rom

SECOND_QUEST = z1r_with(options={"C02": DungeonLayoutSource.SECOND_QUEST})
MIXED_WITH_SHAPES = z1r_with(options={"C02": DungeonLayoutSource.MIXED_WITH_SHAPES})
# Mixed + Shapes seeds whose second-quest set is levels 1-6, levels 7-9, and neither (measured):
# plain, and with Encode level data on, whose flag string draws other sources
MIXED_SEEDS = {2: [0], 5: [1], 1: []}
ENCODED_MIXED_SEEDS = {7: [0], 1: [1], 2: []}


def encoded(flags: str) -> str:
    return encode(decode(flags).updated(toggles={ENCODE_LEVEL_DATA.id: ThreeState.ON}))


@cache
def plain_rom(flags: str, seed: int) -> bytes:
    return generate_rom(flags, seed, remember_repo_base_rom()).rom


def high_byte_addresses(set_index: int) -> list[int]:
    return [ROOM_BLOCK_ADDRESSES_Q1 + 2 * level + 1 for level in SET_LEVELS[set_index]]


def block(rom: bytes, start: int) -> bytes:
    return rom[start:start + ROOM_BLOCK_SIZE]


def second_quest_sets(rom: bytes) -> list[int]:
    return [set_index for set_index in range(len(SET_LEVELS))
            if {rom[address] for address in high_byte_addresses(set_index)} == {SECOND_QUEST_HIGH_BYTES[set_index]}]


def fold_ranges(sets: list[int]) -> list[tuple[int, int]]:
    """The (start, end) file ranges a fold of these sets may change."""
    ranges = [(FIRST_QUEST_BLOCKS[s], FIRST_QUEST_BLOCKS[s] + ROOM_BLOCK_SIZE) for s in sets]
    return ranges + [(address, address + 1) for s in sets for address in high_byte_addresses(s)]


def changed_outside(before: bytes, after: bytes, allowed: list[tuple[int, int]]) -> list[int]:
    return [offset for offset, (old, new) in enumerate(zip(before, after, strict=True))
            if old != new and not any(start <= offset < end for start, end in allowed)]


def check_fold(rom: bytes, sets: list[int]) -> None:
    folded = fold_second_quest_blocks(rom)
    assert second_quest_sets(rom) == sets and second_quest_sets(folded) == []
    for set_index in sets:
        assert block(folded, FIRST_QUEST_BLOCKS[set_index]) == block(rom, SECOND_QUEST_BLOCKS[set_index])
        assert {folded[address] for address in high_byte_addresses(set_index)} == {FIRST_QUEST_HIGH_BYTES[set_index]}
    assert not changed_outside(rom, folded, fold_ranges(sets))
    assert fold_second_quest_blocks(folded) == folded


def test_no_second_quest_set_is_unchanged() -> None:
    base = remember_repo_base_rom()
    assert fold_second_quest_blocks(base) == base
    baseline = plain_rom(z1r_with(), 1)
    assert fold_second_quest_blocks(baseline) == baseline


@pytest.mark.parametrize("seed", [1, 2])
def test_second_quest_folds_both_sets(seed: int) -> None:
    check_fold(plain_rom(SECOND_QUEST, seed), [0, 1])


@pytest.mark.parametrize("seed", sorted(MIXED_SEEDS))
def test_mixed_with_shapes_folds_its_second_quest_set(seed: int) -> None:
    check_fold(plain_rom(MIXED_WITH_SHAPES, seed), MIXED_SEEDS[seed])


def test_a_set_over_two_blocks_is_refused() -> None:
    rom = bytearray(plain_rom(SECOND_QUEST, 1))
    rom[high_byte_addresses(0)[0]] = FIRST_QUEST_HIGH_BYTES[0]
    with pytest.raises(ValueError, match="levels 1-6 point at room blocks"):
        fold_second_quest_blocks(bytes(rom))


def test_plain_level_data_is_what_the_encoding_receives() -> None:
    rom = plain_rom(SECOND_QUEST, 1)
    folded = fold_second_quest_blocks(rom)
    assert level_encoding.plain_level_data(rom) == folded[level_encoding.LEVEL_DATA_START:
                                                          level_encoding.LEVEL_DATA_START
                                                          + level_encoding.PLAIN_BLOCKS_SIZE]


@pytest.mark.skipif(not level_encoding.is_available(), reason="level encoding is not installed")
@pytest.mark.parametrize(("flags", "seed"),
                         [(SECOND_QUEST, 1), *((MIXED_WITH_SHAPES, seed) for seed in ENCODED_MIXED_SEEDS)])
def test_an_encoded_second_quest_rom_decodes_to_the_folded_twin(flags: str, seed: int) -> None:
    """The encoded build differs from its plain twin (the same world, encoding off), once folded,
    only where the encoding may write and in the seed's code (FP-HASH-01 hashes the finished ROM),
    and its level data decodes to the folded twin's."""
    chosen = plan(encoded(flags), seed)
    assert chosen.config.level_encoding is not None
    base = remember_repo_base_rom()
    world = build(chosen, base).world
    rom = serialize_to_rom(world, base, config=chosen.config)
    twin = serialize_to_rom(world, base, config=replace(chosen.config, level_encoding=None))
    assert second_quest_sets(twin) == ([0, 1] if flags == SECOND_QUEST else ENCODED_MIXED_SEEDS[seed])
    assert level_encoding.decode_level_data(rom, chosen.config.level_encoding) == level_encoding.plain_level_data(twin)
    allowed = [*level_encoding.changed_ranges_allowed(), (SEED_CODE_ADDRESS, SEED_CODE_ADDRESS + SEED_CODE_LENGTH)]
    assert not changed_outside(fold_second_quest_blocks(twin), rom, allowed)
