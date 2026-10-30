"""Harder Bosses and Harder Ganon (ZORA version 14; docs/zora-extras.md section 21): the writes, the
flag fields and the generated ROM. The emulator checks are tests/test_harder_bosses_emulator.py."""
import pytest

from tests.needs import needs_base_rom
from zora.flags import zora_flags
from zora.flags.zora_flags import HarderLevel, ZoraFlags
from zora.generate.pipeline import build, finish, plan
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.rom import harder_bosses as hb
from zora.rom.base_rom import piece_bytes, remember_repo_base_rom
from zora.rom.flags2_patch_data import PATCHES

NEEDS_ROM = needs_base_rom


def test_the_fields_are_appended_at_version_14_and_off_by_default() -> None:
    fields = {field.name: field for field in zora_flags.FIELDS}
    for name in ("harder_bosses", "harder_ganon"):
        assert fields[name].version == 14 and fields[name].slots == len(HarderLevel) == 4
        assert getattr(zora_flags.DEFAULT, name) is HarderLevel.OFF
    assert zora_flags.CURRENT_VERSION >= 14
    assert zora_flags.encode(ZoraFlags()) == ""            # every older string keeps its spelling


@pytest.mark.parametrize("bosses", list(HarderLevel))
@pytest.mark.parametrize("ganon", list(HarderLevel))
def test_the_strings_round_trip(bosses: HarderLevel, ganon: HarderLevel) -> None:
    flags = ZoraFlags(harder_bosses=bosses, harder_ganon=ganon)
    text = zora_flags.encode(flags)
    assert zora_flags.decode(text) == flags
    assert text == "" or text.startswith("14.")            # the lowest version holding the field


@pytest.mark.parametrize("level,digdogger,manhandla,gohma,aquamentus", [
    (1, (0x64, 0xA4), 0xA0, 0x35, b"\xEA\xEA"),
    (2, (0x88, 0xC8), 0xC0, 0x29, b"\x4A\xEA"),
    (3, (0xAC, 0xEC), 0xE0, 0x1D, b"\x4A\x4A"),
])
def test_harder_bosses_writes_z1m1s_values(level: int, digdogger: tuple[int, int], manhandla: int, gohma: int,
                                           aquamentus: bytes) -> None:
    """docs/z1m1/harder-bosses.md section 1's table."""
    assert dict(hb.harder_boss_writes(level)) == {
        0x116C4: bytes([digdogger[0]]), 0x116E9: bytes([digdogger[1]]), 0x12169: bytes([manhandla]),
        0x123C6: bytes([gohma]), 0x11805: aquamentus}


@needs_base_rom
def test_the_boss_sites_hold_prg0s_operands() -> None:
    """Each site is an LDA #imm's operand (or Aquamentus' ORA #$70) in PRG0, so only the operand changes."""
    rom = remember_repo_base_rom()
    for operand_site, vanilla in ((0x116C4, 0x40), (0x116E9, 0x80), (0x12169, 0x80), (0x123C6, 0x41)):
        assert rom[operand_site - 1] == 0xA9 and rom[operand_site] == vanilla
    assert hb.aquamentus_timer_run(rom) == hb.PRG0_AQUAMENTUS_TIMER_RUN


def test_the_ganon_level_byte_is_the_patchs_first_byte() -> None:
    level_byte = piece_bytes(next(piece for offset, piece in PATCHES[hb.GANON_PATCH]
                                  if offset == hb.GANON_LEVEL_OFFSET))
    assert level_byte[:1] == b"\x01"                  # the patch is built for level 1
    for level in hb.LEVELS:
        writes = dict(hb.harder_ganon_writes(level))
        assert writes[hb.GANON_LEVEL_OFFSET][0] == level
        assert writes[hb.GANON_LEVEL_OFFSET][1:] == level_byte[1:]


def test_off_writes_nothing() -> None:
    assert hb.harder_writes(0, 0) == []


@needs_base_rom
@pytest.mark.parametrize("flags", [ZoraFlags(harder_bosses=HarderLevel.LEVEL_3),
                                   ZoraFlags(harder_ganon=HarderLevel.LEVEL_2),
                                   ZoraFlags(harder_bosses=HarderLevel.LEVEL_1, harder_ganon=HarderLevel.LEVEL_3)])
def test_a_generated_rom_carries_the_writes(flags: ZoraFlags) -> None:
    base = remember_repo_base_rom()
    built = build(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, zora_flags.encode(flags)), base)
    rom = finish(built, base)
    for offset, data in hb.harder_writes(int(flags.harder_bosses), int(flags.harder_ganon)):
        assert rom[offset:offset + len(data)] == data, hex(offset)
    # the Ganon patch's hooks are in, and PRG0's bytes are where the setting is off
    assert hb.has_ganon_fight_hook(rom) == bool(flags.harder_ganon)
    control = finish(build(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, ""), base), base)
    assert control[hb.DIGDOGGER_LOW_SPEED] == 0x40 and not hb.has_ganon_fight_hook(control)
