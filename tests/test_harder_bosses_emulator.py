"""Harder Bosses and Harder Ganon in the emulator (docs/zora-extras.md section 21; docs/z1m1/harder-bosses.md).

One world (seed 6 for the bosses, seed 5's Ganon room for Ganon), the ROM patched with the setting's
writes (a ZORA flag moves the seed, so the generated ROM is a different world; tests/test_harder_bosses.py
checks that it carries the same writes). Link is invincible in the boss's room, and the boss is watched:

  - Manhandla and Digdogger (level 3): they move faster (their mean step per frame, measured
    0.68 to 1.26 and 0.46 to 2.64).
  - Gohma (level 3): she fires more often (24 fireballs in 1500 frames, 51).
  - Aquamentus: the gap between his volleys falls with the level (165, 132, 56 and 35 frames).
  - Ganon, set to the sword fight: with Harder Ganon at levels 1 to 3 he gains that many hit points
    every 32 frames while below $E0; the time he shows after a hit is drawn around PRG0's $40 with the
    level's spread; he jumps to $30-$B0 by $65-$A5 in a share of the checks while brown; and a Ganon
    room (layout $28) throws statue fireballs, at a rate that rises with the level (none when off)."""
from collections import Counter
from functools import cache

import pytest

from tests.emulator import OBJ_STATE, OBJ_TIMER, OBJ_TYPE, OBJ_X, OBJ_Y, Emulator
from tests.needs import needs_base_rom
from tests.test_oops_all_emulator import INVINCIBLE, LINK_INVINCIBILITY_TIMER, enter_room
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import build, finish, plan
from zora.model.enums import Enemy
from zora.model.game_world import GameWorld
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.harder_bosses import harder_boss_writes, harder_ganon_writes

pytestmark = [needs_base_rom, pytest.mark.slow]

BOSS_SEED, GANON_SEED = 6, 5
BOSS_ROOMS = {                  # (level, room, enemies): seed 6's rooms, found by scanning the built world
    "manhandla": (1, 77, (Enemy.MANHANDLA,)),
    "aquamentus": (3, 74, (Enemy.AQUAMENTUS,)),
    "digdogger": (4, 118, (Enemy.TRIPLE_DIGDOGGER, Enemy.SINGLE_DIGDOGGER)),
    "gohma": (8, 7, (Enemy.BLUE_GOHMA, Enemy.RED_GOHMA)),
}
GANON_ROOM = (9, 49)            # seed 5's level 9: a layout $28 room
OTHER_LAYOUT = (1, (9, 19))     # seed 1's level 9: Ganon stands in a circle moat room
FIREBALL_TYPES = (0x55, 0x56)
GANON, GANON_HP, GANON_SCENE_PHASE, GANON_PHASE, INVINCIBILITY, INV_ARROW = 0x3E, 0x485, 0x445, 0x42C, 0x4F0, 0x659
BROWN = 0xFF
FRAMES = 1500


@cache
def world_rom(seed: int) -> tuple[bytes, GameWorld]:
    base = remember_repo_base_rom()
    built = build(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, seed, ""), base)
    return finish(built, base), built.world


def patched(seed: int, bosses: int = 0, ganon: int = 0) -> bytes:
    rom = bytearray(world_rom(seed)[0])
    for offset, data in [*(harder_boss_writes(bosses) if bosses else []),
                         *(harder_ganon_writes(ganon) if ganon else [])]:
        rom[offset:offset + len(data)] = data
    return bytes(rom)


def slot_of(emu: Emulator, enemy_type: int) -> int:
    return next(slot for slot in range(1, 12) if emu[OBJ_TYPE + slot] == enemy_type)


def watch(rom: bytes, name: str, frames: int = FRAMES) -> tuple[float, list[int]]:
    """The boss's mean step per frame (sum of both axes) and the frames a new fireball appeared on."""
    level, room, kinds = BOSS_ROOMS[name]
    emu = enter_room(rom, level, room)
    boss_types = {int(kind) for kind in kinds}
    steps: list[int] = []
    shots: list[int] = []
    last: dict[int, tuple[int, int]] = {}
    fireballs = 0
    for frame in range(frames):
        emu[LINK_INVINCIBILITY_TIMER] = INVINCIBLE
        emu.run(1)
        now = {slot: (emu[OBJ_X + slot], emu[OBJ_Y + slot]) for slot in range(1, 12)
               if emu[OBJ_TYPE + slot] in boss_types}
        steps += [abs(x - last[slot][0]) + abs(y - last[slot][1]) for slot, (x, y) in now.items()
                  if slot in last and abs(x - last[slot][0]) < 40 and abs(y - last[slot][1]) < 40]
        last = now
        count = sum(1 for slot in range(1, 12) if emu[OBJ_TYPE + slot] in FIREBALL_TYPES)
        if count > fireballs:
            shots.append(frame)
        fireballs = count
    return sum(steps) / max(1, len(steps)), shots


@cache
def boss_watch(name: str, level: int, frames: int = FRAMES) -> tuple[float, list[int]]:
    return watch(patched(BOSS_SEED, bosses=level), name, frames)


def test_manhandla_and_digdogger_move_faster_at_level_3() -> None:
    for name, factor in (("manhandla", 1.5), ("digdogger", 3.0)):
        off, level_3 = boss_watch(name, 0)[0], boss_watch(name, 3)[0]
        assert level_3 > factor * off, (name, off, level_3)
        assert boss_watch(name, 1)[0] > off, name


def test_gohma_fires_more_often_at_level_3() -> None:
    off, level_3 = len(boss_watch("gohma", 0)[1]), len(boss_watch("gohma", 3)[1])
    assert level_3 > 1.7 * off, (off, level_3)


def test_aquamentus_volleys_come_sooner_with_the_level() -> None:
    gaps = []
    for level in (0, 1, 2, 3):
        shots = boss_watch("aquamentus", level, 2400)[1]
        gaps.append((shots[-1] - shots[0]) / (len(shots) - 1))
    assert gaps[0] > gaps[1] > gaps[2] > gaps[3] and gaps[3] < gaps[0] / 3, gaps


class GanonFight:
    """Link in Ganon's room, the fight (scene phase 2) forced, Ganon in the sword phase."""

    def __init__(self, level: int, seed: int = GANON_SEED, room: tuple[int, int] = GANON_ROOM) -> None:
        self.level = level
        self.emu = enter_room(patched(seed, ganon=level), *room)
        self.emu.run(5)
        self.slot = slot_of(self.emu, GANON)
        self.start()

    def start(self, state: int = 0) -> None:
        emu, slot = self.emu, self.slot
        emu[GANON_SCENE_PHASE] = 2
        emu[GANON_PHASE + slot], emu[OBJ_TIMER + slot], emu[OBJ_STATE + slot] = 0, 0, state

    def frames(self, count: int, keep_state: int | None = None) -> None:
        for _ in range(count):
            self.emu[LINK_INVINCIBILITY_TIMER] = INVINCIBLE
            if keep_state is not None:
                self.emu[OBJ_STATE + self.slot] = keep_state
            self.emu.run(1)


@pytest.mark.parametrize("level", [0, 1, 2, 3])
def test_ganon_heals_the_level_every_32_frames(level: int) -> None:
    fight = GanonFight(level)
    fight.emu[GANON_HP + fight.slot] = 0x80
    seen = []
    for _ in range(6):
        fight.frames(32)
        seen.append(fight.emu[GANON_HP + fight.slot])
    assert seen == [0x80 + level * step for step in range(1, 7)]


def test_a_ganon_at_no_hit_points_is_not_healed() -> None:
    """Set Gannon HP to 0 (B41) leaves him at 0: he is not healed back into a fight."""
    fight = GanonFight(3)
    fight.emu[GANON_HP + fight.slot] = 0
    fight.frames(32 * 6)
    assert fight.emu[GANON_HP + fight.slot] == 0


def test_ganon_stops_healing_at_e0() -> None:
    fight = GanonFight(3)
    fight.emu[GANON_HP + fight.slot] = 0xDE
    fight.frames(32 * 4)
    assert 0xE0 <= fight.emu[GANON_HP + fight.slot] <= 0xE2          # the last heal may overshoot by 2


@pytest.mark.parametrize("level,low,high", [(0, 0x40, 0x40), (1, 0x38, 0x48), (2, 0x30, 0x50), (3, 0x20, 0x60)])
def test_ganons_visible_time_is_drawn_around_40(level: int, low: int, high: int) -> None:
    fight = GanonFight(level)
    emu, slot = fight.emu, fight.slot
    times = []
    for trial in range(300):
        emu[LINK_INVINCIBILITY_TIMER] = INVINCIBLE
        emu[OBJ_TIMER + slot], emu[OBJ_STATE + slot], emu[INVINCIBILITY + slot] = 0, 0, 5    # as if just hit
        emu[GANON_HP + slot] = 0xF0
        emu.run(1)
        times.append(emu[OBJ_TIMER + slot])
        emu.run(1 + trial % 7)
    assert low <= min(times) and max(times) <= high
    assert abs(sum(times) / len(times) - 0x40) < 3                    # the same average as PRG0
    if level:
        assert min(times) < low + 4 and max(times) > high - 4          # the range is used


@pytest.mark.parametrize("level,expected", [(0, 0), (1, 12.5), (2, 25), (3, 37.5)])
def test_ganon_jumps_while_brown(level: int, expected: float) -> None:
    fight = GanonFight(level)
    fight.start(state=BROWN)
    fight.emu[INV_ARROW] = 2
    emu, slot = fight.emu, fight.slot
    last = (emu[OBJ_X + slot], emu[OBJ_Y + slot])
    spots = []
    for _ in range(1600):
        fight.frames(1, keep_state=BROWN)
        spot = (emu[OBJ_X + slot], emu[OBJ_Y + slot])
        if spot != last:
            spots.append(spot)
        last = spot
    assert abs(len(spots) - expected) <= 8 if level else not spots
    assert all(0x30 <= x <= 0xB0 and 0x65 <= y <= 0xA5 for x, y in spots)


@pytest.mark.parametrize("seed,room", [(GANON_SEED, GANON_ROOM), OTHER_LAYOUT])
@pytest.mark.parametrize("level", [0, 1, 2, 3])
def test_ganons_room_throws_statue_fireballs(level: int, seed: int, room: tuple[int, int]) -> None:
    """Whatever the room's layout: seed 5's is Z1M1's $28, seed 1's a circle moat room (ZORA keys the fireballs
    to Ganon, where Z1M1 keys them to the layout)."""
    fight = GanonFight(level, seed, room)
    emu = fight.emu
    seen: Counter[int] = Counter()
    last = 0
    for _ in range(FRAMES):
        fight.frames(1)
        count = sum(1 for slot in range(1, 12) if emu[OBJ_TYPE + slot] == 0x55)
        seen[0] += max(0, count - last)
        last = count
    assert (seen[0] == 0) == (level == 0), (level, seen[0])
    if level == 3:
        assert seen[0] > 20
