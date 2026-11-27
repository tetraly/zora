"""The client's writes in the emulator, in a room that lags (2.0.2; found in testing by wolf2k): level 4
room $6F of a multiworld ROM (the Item Counter case's defaults, seed 8), where many sprites make about 2 frames
in 5 end with the game's update still running. At each frame boundary, as the connector writes between frames,
the client's plan (zora.archipelago.hud_writes and hud_guard_sets, which archipelago/client.py hud_write tries in
turn) is applied from a saved state, and what reached the PPU is compared with the same frames without it:

- with the frame guard, every write the guards let through puts the line in the HUD row and changes nothing
  else (CHR RAM identical, the nametables differing only in that row), and no write lands mid-update, so a
  write that succeeds is never overwritten by the game;
- without it (the guards before 2.0.2), writes on frames that lag garble the screen: the status-bar text stores
  the key count over the record's end, and the NMI sends RAM past the buffer to the nametables and CHR RAM;
- client_step's writes (a received item with its arrival sound and count, a DeathLink death) are guarded the
  same way: decided only on a finished frame, and each holds after the frame that follows. Mid-update, the rest
  of the update could undo one (Link_BeHarmed's LDA/SBC/STA of HeartValues over a given Heart Container, a
  mode change over a death).
"""
from collections.abc import Iterator, Sequence
from functools import cache

import pytest

from tests.emulator import Emulator
from tests.test_archipelago_item_counter import CASES, multiworld_assignment
from tests.test_item_counter_emulator import enter
from zora import archipelago
from zora.archipelago import ClientMemory, ClientTables, ReceivedItem, ServerView
from zora.flags import codec
from zora.flags import form as flag_form
from zora.rom import inventory
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom

pytestmark = [pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM"), pytest.mark.slow]

SEED = 8
LEVEL, ROOM = 4, 0x6F
BOUNDARIES = 300
LINE = "SENT BOW TO ANOTHER PLAYER"
HEART_VALUES = inventory.ITEMS + inventory.HEART_VALUES_SLOT
THREE_HEARTS = 0x22
LINK_INVINCIBILITY_TIMER = 0x4F0
INVINCIBLE = 0xFF
HUD_ROW_START = archipelago.HUD_ROW - 0x2000     # its offset in the first nametable (the status bar's)
HUD_ROW = range(HUD_ROW_START, HUD_ROW_START + archipelago.HUD_WIDTH)


@cache
def hud_rom() -> bytes:
    """The Item Counter case's ROM as written (2.0.2): the page's preset with the counter on. Built from the flag
    strings, not the options: Archipelago's options read the preset's magical-sword 14 hearts as 12 since
    2026-11-23, which makes another seed, whose room $6F does not lag. Triforce Shuffle and Map & Compass Shuffle
    Off, as the ROM was written: Archipelago's default is Anywhere since 2026-11-25, another seed again."""
    base = remember_repo_base_rom()
    zora = archipelago.flag_strings({**CASES["defaults"], "triforce_shuffle": "off", "map_compass_shuffle": "off"})[1]
    strings = codec.canonicalize(flag_form.metadata()["defaultFlags"]), zora
    result = archipelago.build_from_strings(*strings, SEED, base)
    assignment, received = multiworld_assignment(result)
    return archipelago.rom_from_recipe(archipelago.recipe(result, assignment, received), base)


def keep_link_alive(emu: Emulator) -> None:
    emu[HEART_VALUES], emu[LINK_INVINCIBILITY_TIMER] = THREE_HEARTS, INVINCIBLE


def step(emu: Emulator, frames: int = 1) -> None:
    for _ in range(frames):
        keep_link_alive(emu)
        emu.run(1)


def guarded_write(emu: Emulator, writes: Sequence[archipelago.HudBytes],
                  guards: Sequence[archipelago.HudBytes]) -> bool:
    """The connector's guarded_write, at one frame boundary: every guard's bytes as expected, then every write."""
    if any(emu[address + offset] != value for address, data in guards for offset, value in enumerate(data)):
        return False
    for address, data in writes:
        for offset, value in enumerate(data):
            emu[address + offset] = value
    return True


def write_line(emu: Emulator, guard_sets: Sequence[Sequence[archipelago.HudBytes]]) -> bool:
    """hud_write's loop: the first guard set that holds writes the line."""
    writes = archipelago.hud_writes(LINE)
    return any(guarded_write(emu, writes, guards) for guards in guard_sets)


def without_frame_guard(control: int) -> tuple[tuple[archipelago.HudBytes, ...], ...]:
    """The guards as they were before 2.0.2: the same sets, CurPpuControl neither read nor guarded."""
    finished = control | inventory.NMI_ENABLED
    return tuple(tuple(guard for guard in guards if guard[0] != inventory.CUR_PPU_CONTROL)
                 for guards in archipelago.hud_guard_sets(finished))


def frames_to_send(emu: Emulator) -> int:
    """Frames until the NMI has sent the buffer: one, plus each frame the running update still takes."""
    frames = 1
    probe = emu.save()
    while not inventory.frame_finished({inventory.CUR_PPU_CONTROL: emu[inventory.CUR_PPU_CONTROL]}):
        step(emu)
        frames += 1
    emu.load(probe)
    return frames


def effect(emu: Emulator, frames: int) -> tuple[bytes, bytes]:
    """CHR RAM and the nametables `frames` frames on, from the state `emu` holds (which it then holds again)."""
    state = emu.save()
    step(emu, frames)
    seen = emu.pattern_tables(), emu.ciram()
    emu.load(state)
    return seen


def boundaries() -> Iterator[Emulator]:
    """The console at each frame boundary in the room, Link standing among the monsters."""
    emu = enter(hud_rom(), LEVEL, ROOM)
    for _ in range(BOUNDARIES):
        keep_link_alive(emu)
        yield emu
        emu.run(1)


def try_write(emu: Emulator, guard_sets: Sequence[Sequence[archipelago.HudBytes]]) -> tuple[bool, bool, bool]:
    """From the state at this boundary: (written, lagging, clean). Clean: CHR RAM as without the write, the
    nametables differing only in the HUD row, which holds the line."""
    lagging = not inventory.frame_finished({inventory.CUR_PPU_CONTROL: emu[inventory.CUR_PPU_CONTROL]})
    state = emu.save()
    frames = frames_to_send(emu)
    without = effect(emu, frames)
    written = write_line(emu, guard_sets)
    clean = True
    if written:
        tiles, nametables = effect(emu, frames)
        changed = {index for index, (a, b) in enumerate(zip(nametables, without[1], strict=True)) if a != b}
        row = nametables[HUD_ROW.start:HUD_ROW.stop]
        line = list(archipelago.hud_record(LINE)[3:-1])
        clean = tiles == without[0] and changed <= set(HUD_ROW) and list(row) == line
    emu.load(state)
    return written, lagging, clean


def test_the_room_lags() -> None:
    """The race needs frames that end mid-update; the room has many, and none is written to."""
    lagging = sum(not inventory.frame_finished({inventory.CUR_PPU_CONTROL: emu[inventory.CUR_PPU_CONTROL]})
                  for emu in boundaries())
    assert lagging >= BOUNDARIES // 5


def test_every_write_lands_whole_between_frames() -> None:
    results = [try_write(emu, archipelago.hud_guard_sets(emu[inventory.CUR_PPU_CONTROL])) for emu in boundaries()]
    written = [(lagging, clean) for done, lagging, clean in results if done]
    assert len(written) >= BOUNDARIES // 5            # finished frames whose buffer is empty or holds the text
    assert not any(lagging for lagging, _clean in written)                        # never mid-update
    assert all(clean for _lagging, clean in written)                              # never overwritten or garbled


def test_without_the_frame_guard_frames_that_lag_garble_the_screen() -> None:
    """The bug: the same writes without the frame guard, on frames that lag."""
    results = [try_write(emu, without_frame_guard(emu[inventory.CUR_PPU_CONTROL])) for emu in boundaries()]
    garbled = [lagging for done, lagging, clean in results if done and not clean]
    assert garbled and all(garbled)                                               # only ever on frames that lag


GIVE_TABLES = ClientTables({}, inventory.GiveRules())
CONTAINERS_MASK = 0xF0
NINE_HEARTS = 0x88                          # nine containers, nine hearts: Link takes the monsters' hits and lives


@pytest.mark.parametrize("death", [False, True], ids=["heart container", "deathlink death"])
def test_received_items_and_deaths_wait_for_a_finished_frame(death: bool) -> None:
    server = ServerView((ReceivedItem("Heart Container"),))
    memory = ClientMemory(pending_death=True) if death else archipelago.NO_MEMORY
    emu = enter(hud_rom(), LEVEL, ROOM)
    written = 0
    for _ in range(BOUNDARIES):
        emu[HEART_VALUES] = NINE_HEARTS
        ram = {address: emu[address] for address in GIVE_TABLES.addresses()}
        decision = archipelago.client_step(ram, ram, server, GIVE_TABLES, memory)
        finished = inventory.frame_finished(ram)
        assert bool(decision.writes) == finished
        if finished:
            state = emu.save()
            assert guarded_write(emu, [(address, (value,)) for address, value in decision.writes],
                                 [(address, (value,)) for address, value in decision.guards])
            emu.run(1)
            if death:
                assert emu[inventory.GAME_MODE] == archipelago.DEATH_MODE
            else:
                assert emu[HEART_VALUES] & CONTAINERS_MASK == (NINE_HEARTS & CONTAINERS_MASK) + 0x10
                assert emu[archipelago.RECEIVED_COUNT] == 1
            written += 1
            emu.load(state)
        emu.run(1)
    assert written >= BOUNDARIES // 2
