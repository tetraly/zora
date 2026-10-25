"""Console play (docs/archipelago.md "Console play"): z1rr-coop's EverDrive N8 Pro patch, which its
bridge applies to a finished Archipelago ROM, read from z1rr-coop's checkout beside this one
(ZORA_Z1RR_COOP, default ../z1rr-coop; skipped without it). With the patch's revision 1:

  - every byte it writes lies in tests/test_coop_reserved.py's table;
  - its manifest accepts Archipelago ROMs, with Pegasus Boots and Red Bubble Curse: Slow Speed on
    too, and it leaves their bank 5 (InitLinkSpeed's hook) as ZORA wrote it;
  - in the emulator (no EverDrive: the patch's USB drain reads "no message") a played session on
    the patched ROM leaves the statistics screen's block and the game's RAM as on the unpatched ROM."""
import io
import json
import os
from functools import cache
from pathlib import Path

import pytest

from tests.emulator import Emulator
from tests.test_archipelago_interface import by_name
from tests.test_coop_reserved import RESERVED_BYTES
from tests.test_stats_screen import STATS_BLOCK, STATS_SIZE
from tests.test_stats_screen_play import assert_the_clock_kept_time, play_a_session
from zora import archipelago
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.revision import NES_HEADER_SIZE

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

REPO = Path(__file__).resolve().parent.parent
Z1RR_COOP = Path(os.environ.get("ZORA_Z1RR_COOP") or REPO.parent / "z1rr-coop")
PATCHES = Z1RR_COOP / "bridge" / "bridge_core" / "patches"
SEED = 1
BANK_SIZE = 0x4000
BANK_5 = range(NES_HEADER_SIZE + 5 * BANK_SIZE, NES_HEADER_SIZE + 6 * BANK_SIZE)
SPEED_FEATURES = {"pegasus_boots": "on", "red_bubble_curse": "slow_speed"}
SETUP_LATCH, SETUP_DONE = 0x07FF, 0xAB         # the patch's once-only setup has run
STACK = range(0x0100, 0x0200)                   # the patch's calls go one level deeper


@cache
def game_rom(speed_features: bool = False) -> bytes:
    """Seed 1 finished as an Archipelago game with its own items: Archipelago's default options, or
    those with Pegasus Boots and Slow Speed on."""
    values = SPEED_FEATURES if speed_features else {}
    result = archipelago.build_from_strings(*archipelago.flag_strings(values), SEED, remember_repo_base_rom())
    return archipelago.finish(result, by_name(result))


def coop_patch() -> tuple[list[tuple[int, bytes]], dict[str, str]]:
    """The shipped IPS's records (offset, bytes) and its manifest's expected bytes by offset."""
    ips_path = PATCHES / "zelda_z1rr_coop.ips"
    if not ips_path.exists():
        pytest.skip(f"z1rr-coop is not at {Z1RR_COOP} (set ZORA_Z1RR_COOP)")
    data = io.BytesIO(ips_path.read_bytes())
    assert data.read(5) == b"PATCH"
    records = []
    while (head := data.read(3)) != b"EOF":
        offset, size = int.from_bytes(head, "big"), int.from_bytes(data.read(2), "big")
        if size:
            records.append((offset, data.read(size)))
        else:
            run, fill = int.from_bytes(data.read(2), "big"), data.read(1)
            records.append((offset, fill * run))
    manifest = json.loads((PATCHES / "zelda_z1rr_coop.expected.json").read_text())["expected"]
    return records, manifest


def patched(rom: bytes) -> bytes:
    out = bytearray(rom)
    for offset, data in coop_patch()[0]:
        out[offset:offset + len(data)] = data
    return bytes(out)


def test_every_patch_byte_is_reserved() -> None:
    records, _ = coop_patch()
    outside = [f"0x{offset + i:05X}" for offset, data in records for i in range(len(data))
               if offset + i not in RESERVED_BYTES]
    assert not outside, outside[:8]


@pytest.mark.parametrize("speed_features", [False, True])
def test_the_patch_accepts_the_rom(speed_features: bool) -> None:
    rom = game_rom(speed_features)
    _, manifest = coop_patch()
    refused = [site for site, want in manifest.items()
               if rom[int(site, 16):int(site, 16) + len(want) // 2].hex() != want.lower()]
    assert not refused


def test_the_speed_features_keep_their_hook() -> None:
    rom = game_rom(speed_features=True)
    assert patched(rom)[BANK_5.start:BANK_5.stop] == rom[BANK_5.start:BANK_5.stop]


@pytest.mark.slow
def test_a_session_on_the_patched_rom_keeps_the_statistics() -> None:
    rom = game_rom()
    runs = []
    for image in (rom, patched(rom)):
        emu = Emulator(image)
        emu.new_game()
        played, counted = play_a_session(emu)
        assert_the_clock_kept_time(played, counted)
        runs.append((bytes(emu[STATS_BLOCK + i] for i in range(STATS_SIZE)),
                     {address: emu[address] for address in range(SETUP_LATCH) if address not in STACK},
                     emu[SETUP_LATCH]))
    (stats, ram, _), (patched_stats, patched_ram, latch) = runs
    assert latch == SETUP_DONE                  # the patch's main-loop hook ran in play
    assert patched_stats == stats
    assert [hex(a) for a in ram if ram[a] != patched_ram[a]] == []
