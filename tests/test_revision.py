"""PRG1 ROMs and ROMs with modified graphics (zora/rom/revision.py; docs/design/prg1.md; owner
rulings, beta 5): identification, PRG1's layout, and generation that never knows the release.

Most cases need the PRG1 ROM beside the PRG0 base (`Legend of Zelda, The (USA) (Rev 1).nes` at the
repo root, git-ignored) and skip without it, as the PRG0 tests skip without theirs."""
from dataclasses import dataclass, field, fields, replace
from functools import cache
from typing import Any

import pytest

from tests.archipelago_cases import FLAG_CASES
from tests.needs import NEEDS_ENCODER
from zora import archipelago
from zora.flags.codec import decode
from zora.flags.fields import ENCODE_LEVEL_DATA, ThreeState
from zora.flags.presets import ZORA_PRESETS
from zora.generate import pipeline
from zora.model.canonical import canonical_bytes
from zora.rom import asnb_patch_data, code_patch_data, flags2_patch_data, layout, level_encoding, player_settings_data
from zora.rom.base_rom import BASE_ROM_PATH, PRG1_ROM_PATH, Original, Piece, piece_length, remember_base_rom
from zora.rom.code_patches import SEED_CODE_ADDRESS, SEED_CODE_LENGTH, seed_code_items
from zora.rom.parse.rom_file import parse_rom
from zora.rom.player_settings import (
    SELECT_SWAP_OFF_SITES,
    DeathWarp,
    LowHealthBeep,
    Music,
    PlayerSettings,
    SelectSwap,
    apply_player_settings,
)
from zora.rom.revision import (
    BOSS_SET_EXPANSION_SPRITES_ADDRESS,
    BOSS_SET_EXPANSION_SPRITES_SIZE,
    DMC_LEVEL_OPERAND,
    GRAPHICS_BLOCKS,
    MOVED_POINTERS,
    NES_HEADER_SIZE,
    NOT_RECOGNIZED,
    PRG1_CHANGED,
    PRG1_MOVES,
    TITLE_BLANK_TILE,
    TITLE_ROWS,
    TITLE_TRADEMARK_CELL,
    TRADEMARK_TILE,
    TRANSFER_BUF_ADDRS_SELECT_SWAP,
    WRITABLE_CHANGED,
    IdentifiedRom,
    Revision,
    RomNotRecognized,
    bank_of,
    cpu_to_file,
    identify_rom,
    in_prg0_layout,
    layout_of,
    move_of,
    prg1_offset,
)
from zora.rom.serialize.rom_file import serialize_to_rom
from zora_export.seed_document import seed_document_for
from zora_web import api

needs_both = pytest.mark.skipif(not (BASE_ROM_PATH.exists() and PRG1_ROM_PATH.exists()),
                                reason="PRG0 base or PRG1 ROM not found")
CASES = {**FLAG_CASES, **ZORA_PRESETS}
SEED_CODE = range(SEED_CODE_ADDRESS, SEED_CODE_ADDRESS + SEED_CODE_LENGTH)
TRADEMARK = range(TRADEMARK_TILE, TRADEMARK_TILE + 16)
ABSOLUTE_OPERAND_OPCODES = frozenset({0x20, 0x4C, 0x6C, 0xAD, 0xBD, 0xB9, 0x8D, 0x9D, 0x99, 0xAE, 0xBE, 0xAC, 0xBC,
                                      0x8E, 0x8C, 0xCD, 0xDD, 0xD9, 0xEE, 0xCE, 0x2D, 0x0D, 0x4D, 0x6D, 0xED})


@cache
def prg0() -> bytes:
    return BASE_ROM_PATH.read_bytes()


@cache
def prg1() -> bytes:
    return PRG1_ROM_PATH.read_bytes()


def release(revision: Revision) -> bytes:
    return prg0() if revision is Revision.PRG0 else prg1()


def patch_writes() -> list[tuple[str, int, Piece]]:
    """Every (where, file offset, piece) of the five patch tables."""
    writes = [(f"code {name}", offset, piece) for name, pieces in code_patch_data.PATCHES.items()
              for offset, piece in pieces]
    writes += [(f"2.0 flags {name}", offset, piece) for name, pieces in flags2_patch_data.PATCHES.items()
               for offset, piece in pieces]
    writes += [(f"ASNB {name}", offset, piece) for name, pieces in asnb_patch_data.PATCHES.items()
               for offset, piece in pieces]
    writes += [(f"setting {name}={value}", offset, piece)
               for name, values in player_settings_data.SETTINGS.items() for value, pieces in values.items()
               for offset, piece in pieces]
    return writes


# --- the module's constants ---------------------------------------------------------------------

def test_the_constants_are_layout_and_player_settings_ones() -> None:
    assert NES_HEADER_SIZE == layout.NES_HEADER_SIZE
    assert BOSS_SET_EXPANSION_SPRITES_ADDRESS == layout.BOSS_SET_EXPANSION_SPRITES_ADDRESS
    assert BOSS_SET_EXPANSION_SPRITES_SIZE == layout.BOSS_SET_EXPANSION_SPRITES_SIZE
    assert DMC_LEVEL_OPERAND == layout.DMC_LEVEL_OPERAND_ADDRESS
    assert TITLE_ROWS == ((layout.TITLE_SEED_ROW_ADDRESS, layout.TITLE_ROW_LENGTH),
                          (layout.TITLE_VERSION_ROW_ADDRESS, layout.TITLE_ROW_LENGTH))
    assert TRANSFER_BUF_ADDRS_SELECT_SWAP in SELECT_SWAP_OFF_SITES
    assert sum(length for _, _, length in GRAPHICS_BLOCKS) == 19_136


# --- PRG1's layout, against both ROMs -----------------------------------------------------------

@needs_both
def test_every_prg1_change_is_in_a_listed_window() -> None:
    changed = [offset for offset in range(NES_HEADER_SIZE, len(prg0())) if prg0()[offset] != prg1()[offset]]
    assert len(changed) == 5309
    assert all(any(start <= offset < end for start, end in PRG1_CHANGED) for offset in changed)


@needs_both
@pytest.mark.parametrize("move", PRG1_MOVES, ids=lambda move: f"{move.start:05X}{move.shift:+d}")
def test_each_move_is_prg0s_bytes_further_on(move: Any) -> None:
    """At least 95% of a move's bytes are PRG0's at their PRG1 offset (the rest: operands PRG1
    changed inside the moved code, the DMC level and the TM glyph)."""
    equal = sum(prg0()[offset] == prg1()[offset + move.shift] for offset in range(move.start, move.end))
    assert equal >= 0.95 * (move.end - move.start)


@needs_both
def test_the_title_screen_differs_only_by_the_trademark() -> None:
    """GameTitleTransferBuf moves 139 bytes on; its one change is the TM glyph (tile $30) beside
    the logo, which is PRG1's first tile of the boss expansion block."""
    title = range(0x1A879, 0x1ACD9)
    differing = [offset for offset in title if prg0()[offset] != prg1()[prg1_offset(offset)]]
    assert differing == [TITLE_TRADEMARK_CELL]
    assert prg1()[prg1_offset(TITLE_TRADEMARK_CELL)] == 0x30 and prg0()[TITLE_TRADEMARK_CELL] == TITLE_BLANK_TILE
    assert BOSS_SET_EXPANSION_SPRITES_ADDRESS == layout.BOSS_SET_EXPANSION_SPRITES_ADDRESS == 0x8A8F
    assert any(prg1()[offset] for offset in TRADEMARK) and not any(prg0()[offset] for offset in TRADEMARK)
    assert not any(prg1()[offset] for offset in range(TRADEMARK_TILE + 16, TRADEMARK_TILE + 0x200))


def is_shifted_pointer_byte(at: int) -> bool:
    """`at` (in a move) is a byte of a little-endian address into moved code that PRG1 holds
    moved with it: the address's PRG0 value plus its move's shift."""
    for low in (at - 1, at):
        address = prg0()[low] | prg0()[low + 1] << 8
        if address < 0x8000:
            continue
        move = move_of(cpu_to_file(bank_of(low), address))
        if move is None:
            continue
        moved = prg1()[prg1_offset(low)] | prg1()[prg1_offset(low) + 1] << 8
        if moved == address + move.shift:
            return True
    return False


@needs_both
def test_every_patch_piece_in_moved_code_lands_on_the_same_code() -> None:
    """Every patch write in a move replaces, and every Original in one reads, at PRG1's offset
    the bytes it does on PRG0; a write outside the moves touches PRG1's changes only where
    revision.WRITABLE_CHANGED allows it. A new patch hooking moved code without a map entry
    fails here. A write may replace a pointer into the moved code that PRG1 shifted with it
    (Pegasus Boots replaces WieldBoomerang's `LDA BoomerangLimits, Y`): the write's own bytes
    land as they are, and test_no_patch_operand_points_into_moved_code_unlisted checks its own
    operands."""
    for where, offset, piece in patch_writes():
        spans = [(offset, piece_length(piece))]
        if isinstance(piece, Original):
            spans.append((piece.source, piece.length))
        for start, length in spans:
            for at in range(start, start + length):
                if move_of(at) is not None:
                    replaced_pointer = not isinstance(piece, Original) and is_shifted_pointer_byte(at)
                    assert prg0()[at] == prg1()[prg1_offset(at)] or replaced_pointer, (where, hex(at))
                elif prg0()[at] != prg1()[at]:
                    assert any(lo <= at < hi for lo, hi in WRITABLE_CHANGED), (where, hex(at))


@needs_both
def test_no_patch_operand_points_into_moved_code_unlisted() -> None:
    """A patch's absolute operand (JSR, JMP, loads, stores) that points into code PRG1 moves,
    written outside that code, must be in MOVED_POINTERS so the move adjusts it. A
    heuristic: any opcode byte followed by such an address counts. Every write to
    TransferBufAddrs (pointers into PRG1's moved buffers) is one too."""
    found = set()
    for where, offset, piece in patch_writes():
        if isinstance(piece, Original):
            continue
        for index in range(len(piece) - 2):
            site = offset + index + 1
            if piece[index] not in ABSOLUTE_OPERAND_OPCODES or move_of(site) is not None:
                continue
            target = piece[index + 1] | piece[index + 2] << 8
            if target >= 0x8000 and move_of(cpu_to_file(bank_of(site), target)) is not None:
                found.add(site)
                assert site in MOVED_POINTERS, (where, hex(site), hex(target))
    transfer_buf_addrs = range(0x1A010, 0x1A010 + 2 * 48)
    pointers = {offset for _where, offset, _piece in patch_writes() if offset in transfer_buf_addrs}
    assert pointers == {TRANSFER_BUF_ADDRS_SELECT_SWAP}
    assert found | pointers == set(MOVED_POINTERS)


# --- identification -----------------------------------------------------------------------------

@needs_both
@pytest.mark.parametrize("revision", list(Revision))
def test_both_releases_are_recognized_with_or_without_a_header(revision: Revision) -> None:
    rom = release(revision)
    expected = IdentifiedRom(revision, modified_graphics=False)
    assert identify_rom(rom) == identify_rom(rom[NES_HEADER_SIZE:]) == expected
    other_header = rom[:7] + bytes([0x08]) + rom[8:]           # another dumper's header bytes
    assert identify_rom(other_header) == expected
    assert expected.message == f"This is a {revision.value} ROM"


@needs_both
@pytest.mark.parametrize("revision", list(Revision))
@pytest.mark.parametrize("block", GRAPHICS_BLOCKS, ids=lambda block: block[0])
def test_changed_tiles_in_any_pattern_block_are_modified_graphics(revision: Revision,
                                                                  block: tuple[str, int, int]) -> None:
    _name, offset, length = block
    rom = bytearray(release(revision))
    for at in range(NES_HEADER_SIZE + offset, NES_HEADER_SIZE + offset + length, 7):
        rom[at] ^= 0x5A
    identity = identify_rom(bytes(rom))
    assert identity == IdentifiedRom(revision, modified_graphics=True)
    assert identity.message == f"This is a {revision.value} ROM with modified graphics"


@needs_both
@pytest.mark.parametrize("revision", list(Revision))
@pytest.mark.parametrize("offset", [0x1BC4, 0x14E25, 0x18710, layout.TITLE_SEED_ROW_ADDRESS + 4, 0x1FFFF],
                         ids=["audio", "statistics", "level data", "title", "last byte"])
def test_a_changed_byte_outside_the_graphics_is_refused(revision: Revision, offset: int) -> None:
    rom = bytearray(release(revision))
    rom[prg1_offset(offset) if revision is Revision.PRG1 else offset] ^= 0x01
    with pytest.raises(RomNotRecognized) as refused:
        identify_rom(bytes(rom))
    assert str(refused.value) == NOT_RECOGNIZED == ("ROM not recognized. If you believe this is in error, "
                                                    "please file a bug in the ZORA Discord")


@needs_both
def test_the_page_gets_the_same_answer() -> None:
    assert api.identify_rom(prg1()) == {"recognized": True, "revision": "PRG1", "modifiedGraphics": False,
                                         "message": "This is a PRG1 ROM"}
    assert api.identify_rom(graphics_inverted(prg0()))["message"] == "This is a PRG0 ROM with modified graphics"
    assert api.identify_rom(prg0()[:-1] + b"\x00") == {"recognized": False, "message": NOT_RECOGNIZED}


def test_a_rom_of_another_size_is_refused() -> None:
    with pytest.raises(RomNotRecognized):
        identify_rom(bytes(0x20010))
    with pytest.raises(RomNotRecognized):
        identify_rom(b"NES\x1a" + bytes(100))


# --- generation never knows the release ---------------------------------------------------------

def same_result(left: Any, right: Any, tiles_inverted: bool = False) -> bool:
    """GenerationResult equality, its enemy pools by their fields (EnemyPools has no __eq__).
    With `tiles_inverted`, the group passes' staged tiles are compared by where they go, and
    `right`'s must hold `left`'s data inverted (the player's own tiles)."""
    for compared in fields(left):
        mine, theirs = getattr(left, compared.name), getattr(right, compared.name)
        if compared.name == "pools":
            mine, theirs = vars(mine), vars(theirs)
        if compared.name == "groups" and tiles_inverted and mine is not None:
            mine_tiles, their_tiles = mine.staged.tiles, theirs.staged.tiles
            if [tile[:-1] for tile in mine_tiles] != [tile[:-1] for tile in their_tiles]:
                return False
            pairs = zip(mine_tiles, their_tiles, strict=True)
            if any(bytes(value ^ 0xFF for value in a[-1]) != b[-1] for a, b in pairs):
                return False
            mine = replace(mine, staged=replace(mine.staged, tiles=[]))
            theirs = replace(theirs, staged=replace(theirs.staged, tiles=[]))
        if mine != theirs:
            return False
    return True


def moved_to_prg1(out0: bytes, base0: bytes, base1: bytes) -> bytes:
    """What the PRG1 ROM must be, from PRG0's output: every byte ZORA changed on PRG0 at its
    PRG1 offset over the PRG1 ROM, the moved-code operands moved, and the title's TM glyph
    blanked when ZORA changed the title or its tile. Independent of revision.back_to_revision
    but for the move table."""
    written = {offset for offset in range(len(base0)) if out0[offset] != base0[offset]}
    if written & set(TRADEMARK):
        written |= set(TRADEMARK)
    expected = bytearray(base1)
    for offset in written:
        expected[prg1_offset(offset)] = out0[offset]
    for site in MOVED_POINTERS:
        if written & {site, site + 1}:
            target = out0[site] | out0[site + 1] << 8
            move = move_of(cpu_to_file(bank_of(site), target))
            target += move.shift if move else 0
            expected[site:site + 2] = bytes([target & 0xFF, target >> 8])
    title = {offset for start, length in TITLE_ROWS for offset in range(start, start + length)}
    if written & (title | set(TRADEMARK)):
        expected[prg1_offset(TITLE_TRADEMARK_CELL)] = TITLE_BLANK_TILE
    return bytes(expected)


def assert_same(actual: bytes, expected: bytes) -> None:
    differing = [hex(offset) for offset in range(len(expected)) if actual[offset] != expected[offset]]
    assert not differing, differing[:20]


@needs_both
def test_the_layout_is_read_from_the_title_buffer() -> None:
    """Either release, a finished ROM of either, and PRG1 moved into PRG0's layout."""
    assert layout_of(prg0()) is Revision.PRG0 and layout_of(prg1()) is Revision.PRG1
    assert layout_of(in_prg0_layout(prg1(), Revision.PRG1)) is Revision.PRG0
    assert layout_of(pipeline.generate_rom(CASES["baseline"][0], 1, prg1()).rom) is Revision.PRG1
    assert layout_of(bytes(0x20010)) is None


@needs_both
def test_both_releases_parse_into_the_same_world() -> None:
    assert parse_rom(prg0()) == parse_rom(prg1())


@needs_both
@pytest.mark.parametrize("seed", [1, 2])
@pytest.mark.parametrize("case", list(CASES))
def test_a_seed_generates_the_same_game_on_both_releases(case: str, seed: int) -> None:
    """The plan takes no ROM; the generated world and every draw and counter are equal; the PRG1
    ROM is the PRG0 output moved to PRG1's places, the seed's code included. A case with Encode level
    data on (the community presets) needs the private encoder, which a release tree lacks."""
    if decode(CASES[case][0]).toggle(ENCODE_LEVEL_DATA) is not ThreeState.OFF and not level_encoding.is_available():
        pytest.skip(NEEDS_ENCODER)
    chosen = pipeline.plan(CASES[case][0], seed, CASES[case][1])
    built0, built1 = pipeline.build(chosen, prg0()), pipeline.build(chosen, prg1())
    assert built0.world == built1.world
    assert same_result(built0.result, built1.result)
    assert built0.places == built1.places
    out0, out1 = pipeline.finish(built0, prg0()), pipeline.finish(built1, prg1())
    assert_same(out1, moved_to_prg1(out0, prg0(), prg1()))


@needs_both
@pytest.mark.parametrize("case", ["baseline", "every ZORA flag on"])
def test_a_finished_prg1_rom_reads_as_its_prg0_twin(case: str) -> None:
    """The seed document (the page's seed report) of a finished PRG1 ROM is its PRG0 twin's, and
    a finished PRG1 ROM parsed and written again is unchanged (the playtest round trip)."""
    flags, zora_flags = CASES[case]
    out0 = pipeline.generate_rom(flags, 3, prg0(), zora_flag_string=zora_flags).rom
    out1 = pipeline.generate_rom(flags, 3, prg1(), zora_flag_string=zora_flags).rom
    document0, document1 = (seed_document_for(out, flags, 3, zora_flags) for out in (out0, out1))
    assert document0 == document1
    config = pipeline.plan(flags, 3, zora_flags).config
    assert_same(serialize_to_rom(parse_rom(out1, config), out1, config=config), out1)


COSMETIC_SETTINGS = {
    "defaults": PlayerSettings(),
    "music off, select pauses, beep kept": PlayerSettings(
        music=Music.OFF, select_swap=SelectSwap.OFF, low_health_beep=LowHealthBeep.KEPT),
    "swap only, other warp, colors, words, flashing": PlayerSettings(
        select_swap=SelectSwap.SWAP_ONLY, death_warp=DeathWarp.CONTROLLER2_UP_A, reduce_flashing=True,
        tunic_colors=(0x1A, 0x21, 0x06), heart_color=0x2A, level_word="ZONE", boss_sound_word="RANDOM"),
}


@needs_both
@pytest.mark.parametrize("settings", list(COSMETIC_SETTINGS))
def test_player_settings_land_on_prg1s_code(settings: str) -> None:
    """Music: Off's jump into the moved audio code, the statistics screen and the boss sound
    word in the moved game-over code, and Select Swap's TransferBufAddrs entry."""
    chosen = pipeline.plan(CASES["baseline"][0], 1, CASES["baseline"][1])
    player = COSMETIC_SETTINGS[settings]
    out0 = pipeline.finish(pipeline.build(chosen, prg0()), prg0(), player_settings=player)
    out1 = pipeline.finish(pipeline.build(chosen, prg1()), prg1(), player_settings=player)
    assert_same(out1, moved_to_prg1(out0, prg0(), prg1()))
    plain1 = pipeline.finish(pipeline.build(chosen, prg1()), prg1())
    assert apply_player_settings(plain1, player) == out1        # a finished PRG1 ROM styled again
    if player.music is Music.OFF:
        assert out1[0x02027:0x0202A] == bytes([0x20, 0x42, 0x9D]) and out0[0x02027:0x0202A] == bytes([0x20, 0x46, 0x9D])
    if player.select_swap is SelectSwap.OFF:
        site = TRANSFER_BUF_ADDRS_SELECT_SWAP
        assert out1[site:site + 2] == prg1()[site:site + 2] and out0[site:site + 2] == prg0()[site:site + 2]


def graphics_inverted(rom: bytes) -> bytes:
    """`rom` with every byte of every pattern block inverted: modified graphics."""
    image = bytearray(rom)
    for _name, offset, length in GRAPHICS_BLOCKS:
        start = NES_HEADER_SIZE + offset
        image[start:start + length] = bytes(value ^ 0xFF for value in image[start:start + length])
    return bytes(image)


def in_graphics(offset: int) -> bool:
    return any(NES_HEADER_SIZE + start <= offset < NES_HEADER_SIZE + start + length
               for _name, start, length in GRAPHICS_BLOCKS)


@needs_both
@pytest.mark.parametrize("revision", list(Revision))
@pytest.mark.parametrize("case", ["every ZORA flag on", "All Swords No Boards"])
def test_modified_graphics_follow_into_the_tile_copies(case: str, revision: Revision) -> None:
    """With every tile inverted, the draws are the same and the output is the vanilla output with
    every graphics byte inverted: each tile ZORA copies (enemy and boss groups, Oops All) is the
    player's own, and nothing else changes."""
    base = release(revision)
    chosen = pipeline.plan(CASES[case][0], 1, CASES[case][1])
    plain, modified = pipeline.build(chosen, base), pipeline.build(chosen, graphics_inverted(base))
    assert same_result(plain.result, modified.result, tiles_inverted=True)
    out, out_modified = pipeline.finish(plain, base), pipeline.finish(modified, graphics_inverted(base))
    differing = [hex(offset) for offset in range(len(out))
                 if out_modified[offset] != (out[offset] ^ 0xFF if in_graphics(offset) else out[offset])]
    assert not differing, differing[:20]


# --- the seed's code (FP-HASH-01; owner ruling, beta 5) -----------------------------------------

@needs_both
@pytest.mark.parametrize("case", ["baseline", "every ZORA flag on", "All Swords No Boards"])
def test_the_seed_code_is_the_same_on_every_release_graphics_and_setting(case: str) -> None:
    """PRG0 and PRG1, each as released and with every tile inverted, each with several cosmetic
    player settings: one code. It is the one the model gives (seed_code_items)."""
    flags, zora_flags = CASES[case]
    codes = {}
    for revision in Revision:
        for graphics in ("vanilla graphics", "modified graphics"):
            base = release(revision) if graphics == "vanilla graphics" else graphics_inverted(release(revision))
            for settings, player in COSMETIC_SETTINGS.items():
                rom = pipeline.generate_rom(flags, 5, base, player, zora_flags)
                shown = bytes(rom.rom[SEED_CODE_ADDRESS:SEED_CODE_ADDRESS + SEED_CODE_LENGTH])
                codes[(revision.value, graphics, settings)] = (rom.code, shown)
    assert len(set(codes.values())) == 1, codes
    chosen = pipeline.plan(flags, 5, zora_flags)
    built = pipeline.build(chosen, prg1())
    config = replace(chosen.config, revision=Revision.PRG1, modified_graphics=True)
    assert seed_code_items(built.world, config) == next(iter(codes.values()))[1]


@needs_both
def test_the_seed_code_changes_with_the_game() -> None:
    """Another seed, other flags, another Archipelago slot name: another code (a 1 in 27^4 chance
    of a match aside, these were checked)."""
    flags, zora_flags = CASES["baseline"]
    code = pipeline.generate_rom(flags, 5, prg1(), zora_flag_string=zora_flags).code
    assert pipeline.generate_rom(flags, 6, prg1(), zora_flag_string=zora_flags).code != code
    assert pipeline.generate_rom(*CASES["every ZORA flag on"][:1], 5, prg1(),
                                 zora_flag_string=CASES["every ZORA flag on"][1]).code != code
    result = archipelago.build_from_strings(flags, zora_flags, 5, prg1())
    slots = {archipelago.finish(result, own_items(result), ap_name=name)[SEED_CODE_ADDRESS:
                                                                         SEED_CODE_ADDRESS + SEED_CODE_LENGTH]
             for name in (b"Link", b"Zelda")}
    assert len(slots) == 2


def test_the_fixed_form_follows_equality() -> None:
    """Equal values write the same bytes, a changed compared field changes them, a back-reference
    that == leaves out is left out, and an unknown type is refused."""
    @dataclass
    class Node:
        name: str
        items: list[int]
        parent: object = field(default=None, compare=False)

    assert canonical_bytes(Node("a", [1, 2])) == canonical_bytes(Node("a", [1, 2], parent=object()))
    assert canonical_bytes(Node("a", [1, 2])) != canonical_bytes(Node("a", [12]))
    assert canonical_bytes(("ab", "c")) != canonical_bytes(("a", "bc"))
    assert canonical_bytes({2: "x", 1: "y"}) == canonical_bytes({1: "y", 2: "x"})
    with pytest.raises(TypeError):
        canonical_bytes(object())


# --- Archipelago: each player bakes from their own release --------------------------------------

def own_items(result: archipelago.BuildResult) -> dict[str, str]:
    """Every place keeps the item ZORA put there."""
    return {place.name: item for place, item in zip(result.places, result.pool, strict=True)}


@needs_both
def test_two_players_on_different_releases_in_one_process() -> None:
    """Two slots built one after the other, PRG0 and PRG1, finished in the other order with the
    other release remembered as the process's fallback: each ROM is the one its player gets
    alone, on their own release."""
    flags, zora_flags = CASES["every ZORA flag on"]
    alone = {revision: archipelago.build_from_strings(flags, zora_flags, 7, release(revision)) for revision in Revision}
    expected = {revision: archipelago.finish(result, own_items(result)) for revision, result in alone.items()}
    first = archipelago.build_from_strings(flags, zora_flags, 7, prg0())
    second = archipelago.build_from_strings(flags, zora_flags, 7, prg1())
    remember_base_rom(prg0())
    baked1 = archipelago.finish(second, own_items(second))
    remember_base_rom(prg1())
    baked0 = archipelago.finish(first, own_items(first))
    remember_base_rom(prg0())
    assert baked0 == expected[Revision.PRG0] and baked1 == expected[Revision.PRG1]
    assert identify_rom(prg1()).revision is Revision.PRG1
    assert baked1[prg1_offset(0x01BC4)] == prg1()[prg1_offset(0x01BC4)]       # PRG1's own audio bytes kept


def test_generation_refuses_a_rom_it_does_not_recognize() -> None:
    chosen = pipeline.plan(CASES["baseline"][0], 1, CASES["baseline"][1])
    with pytest.raises(RomNotRecognized):
        pipeline.build(chosen, bytes(0x20010))
