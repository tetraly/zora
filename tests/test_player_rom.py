"""The player's ROM (zora/rom/base_rom.py): generation remembers the ROM it is given before
any read, and player_rom() refuses when none was remembered (no fallback to a file on disk).
Each case runs in a fresh process, where nothing was remembered, with the repo-root path
pointed at a file that does not exist."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from zora.generate.pipeline import generate_rom
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom

REPO = Path(__file__).resolve().parent.parent
FLAGS = "8hq4BeR1JXo89BJ2!TFpTP02u8UJ3A"     # level encoding off
SEED = 12345
FRESH = """
import hashlib, sys
from pathlib import Path
import zora.rom.base_rom as base_rom
base_rom.BASE_ROM_PATH = Path("no such ROM.nes")
rom = sys.stdin.buffer.read()
"""


def _fresh(code: str, rom: bytes = b"") -> subprocess.CompletedProcess[bytes]:
    return subprocess.run([sys.executable, "-c", FRESH + code], input=rom, capture_output=True, cwd=REPO,
                          check=False)


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("vanilla ROM missing")
    return remember_repo_base_rom()


def test_player_rom_refuses_when_nothing_was_remembered() -> None:
    result = _fresh("from zora.rom.base_rom import NoPlayerRom, player_rom\n"
                    "try:\n    player_rom()\nexcept NoPlayerRom:\n    print('refused')\n")
    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout.decode().strip() == "refused"


@pytest.mark.parametrize("entry", ["generate_rom", "generate_world"])
def test_generation_remembers_the_rom_it_is_given(base: bytes, entry: str) -> None:
    code = {
        "generate_rom": f"from zora.generate.pipeline import generate_rom\n"
                        f"print(hashlib.sha1(generate_rom({FLAGS!r}, {SEED}, rom).rom).hexdigest())\n",
        "generate_world": f"from zora.generate.pipeline import generate_world, plan\n"
                          f"world, _ = generate_world(plan({FLAGS!r}, {SEED}), rom)\n"
                          f"print(base_rom.player_rom() == rom)\n",
    }[entry]
    result = _fresh(code, base)
    assert result.returncode == 0, result.stderr.decode()
    expected = hashlib.sha1(generate_rom(FLAGS, SEED, base).rom).hexdigest() if entry == "generate_rom" else "True"
    assert result.stdout.decode().strip() == expected


# The Archipelago client (docs/archipelago.md "Interface"): a client process that never built a
# ROM, started on its own or restarted mid-game, calls client_ready(rom) before receive().
RECEIVED = ["Bow", "Heart Container", "Blue Potion", "Wood Sword"]
RECEIVE = f"""
import json
from zora import archipelago
from zora.rom import inventory
ram = {{address: 0 for address in range(inventory.ITEMS, inventory.MAX_BOMBS + 1)}}
ram[inventory.ITEMS + inventory.HEART_VALUES_SLOT] = 0x22
given = []
for name in {RECEIVED!r}:
    writes = archipelago.receive(name, ram)
    ram.update(writes)
    given.append(sorted(writes.items()))
print(json.dumps(given))
"""


def _received_in_this_process() -> list[list[list[int]]]:
    from zora import archipelago
    from zora.rom import inventory
    ram = {address: 0 for address in range(inventory.ITEMS, inventory.MAX_BOMBS + 1)}
    ram[inventory.ITEMS + inventory.HEART_VALUES_SLOT] = 0x22
    given = []
    for name in RECEIVED:
        writes = archipelago.receive(name, ram)
        ram.update(writes)
        given.append([list(write) for write in sorted(writes.items())])
    return given


def test_a_fresh_client_receives_after_client_ready(base: bytes) -> None:
    result = _fresh("from zora import archipelago\narchipelago.client_ready(rom)\n" + RECEIVE, base)
    assert result.returncode == 0, result.stderr.decode()
    given = json.loads(result.stdout.decode())
    assert given == _received_in_this_process()
    assert all(given), given                  # each item wrote something


def test_a_fresh_client_without_client_ready_is_told_to_call_it() -> None:
    result = _fresh("from zora import archipelago\n"
                    "try:\n    archipelago.receive('Bow', {})\n"
                    "except archipelago.ClientNotReady as refusal:\n    print(refusal)\n")
    assert result.returncode == 0, result.stderr.decode()
    assert "client_ready(rom)" in result.stdout.decode()


def test_client_ready_refuses_a_rom_that_is_not_prg0(base: bytes) -> None:
    from zora import archipelago
    from zora.rom.base_rom import BaseRomMismatch
    with pytest.raises(BaseRomMismatch):
        archipelago.client_ready(base[:-1] + bytes([base[-1] ^ 1]))
