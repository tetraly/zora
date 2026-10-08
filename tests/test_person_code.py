"""PS-MERCH-04 / PS-BOMB-03 in the data layer: the typed toll and
bomb-upgrade fields serialize to the spec's bytes and parse back."""
import os
from pathlib import Path

import pytest

from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.model.game_world import GameWorld
from zora.model.rooms import LifeOrMoneyToll
from zora.model.enums import TollOption
from zora.rom.parse.rom_file import load_rom, parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom


def _vanilla_rom() -> bytes:
    env = os.environ.get("ZORA_VANILLA_ROM")
    cand = Path(env) if env else BASE_ROM_PATH
    if not cand.exists():
        pytest.skip("vanilla ROM missing")
    verify_base_rom(cand)
    return load_rom(cand)


def _serialized(gw: GameWorld) -> bytes:
    rom = _vanilla_rom()
    return serialize_to_rom(gw, rom)


def test_toll_writes_round_trip() -> None:
    # PS-MERCH-04 / PS-BOMB-03: the typed fields serialize to the spec's
    # bytes and parse back to the same fields
    gw = parse_rom(_vanilla_rom())
    assert gw.life_or_money_toll is None and gw.bomb_upgrade_levels is None
    gw.life_or_money_toll = LifeOrMoneyToll(TollOption.LIFE, TollOption.KEYS, key_cost=3)
    out = _serialized(gw)
    assert out[0x04046:0x04048] == bytes([0xB0, 0x8C])            # person text slot 27
    assert out[0x04C1C:0x04C2F] == bytes([0xAD, 0x64, 0x06, 0xD0, 0x0B, 0xAD, 0x6E,
                                          0x06, 0x38, 0xE9, 3, 0x90, 0xEE, 0x8D,
                                          0x6E, 0x06, 0x4C, 0x4D, 0x8C])
    assert out[0x04C35] == 0x30                                   # vanilla hearts $FF -> 34
    assert out[0x1A2C0:0x1A2C3] == bytes([0x24, 0x62, 3])
    assert out[0x04BD9:0x04BDB] == bytes([0x1A, 0x19])
    assert parse_rom(out).life_or_money_toll == gw.life_or_money_toll
    gw.life_or_money_toll = LifeOrMoneyToll(TollOption.MAX_BOMBS, TollOption.MONEY,
                                            money_cost=47)
    gw.bomb_upgrade_levels = (5, 5)
    out = _serialized(gw)
    assert out[0x04C1D] == 47 and out[0x04C1C] == 0xA9            # LDA #47
    assert out[0x04C2F:0x04C3D] == bytes([0xCE, 0x7C, 0x06, 0xAD, 0x58, 0x06, 0xF0,
                                          0x03, 0xCE, 0x58, 0x06, 0x4C, 0x4D, 0x8C])
    assert out[0x1A2C1:0x1A2C3] == bytes([4, 7])
    assert out[0x04BD9] == 0x00
    assert out[0x04AED:0x04AEF] == bytes([0xEA, 0xEA])
    assert out[0x04AF0] == 5 and out[0x04AF4] == 5
    back = parse_rom(out)
    assert (back.life_or_money_toll, back.bomb_upgrade_levels) == \
        (gw.life_or_money_toll, gw.bomb_upgrade_levels)
    # "LEAVE YOUR MAX BOMBS" / "OR MONEY", centred with the $25 pad tile
    text = out[0x04CC0:0x04CC0 + 38]
    assert text[:2] == bytes([0x25, 0x25]) and text[21] & 0xC0 == 0x80
    assert text[-1] & 0xC0 == 0xC0


