"""Harder Bosses and Harder Ganon (ZORA flags harder_bosses and harder_ganon, levels 1 to 3;
docs/zora-extras.md section 21), from Z1M1 (MetalMachine; launcher 72cf4c5a GameBuilder.cs:1177-1203,
asm 843932c src/zelda/patches.asm:1901-2074; docs/z1m1/harder-bosses.md).

Harder Bosses is five data patches in PRG0's boss code: Digdogger's two speed targets, Manhandla's
speed, Gohma's fireball timer and Aquamentus' fireball timer. Harder Ganon is asm/flags2's
harder-ganon patch with its level byte set. Neither changes a boss's hit points or damage, the item
logic or the hints."""
from __future__ import annotations

from .base_rom import piece_bytes
from .flags2_patch_data import PATCHES

LEVELS = (1, 2, 3)

# Operands of LDA #imm in PRG0 (Z1M1's EnemyData.cs:81-88; the file offsets include the header).
DIGDOGGER_LOW_SPEED = 0x116C4           # the speed Digdogger slows to: PRG0 $40
DIGDOGGER_HIGH_SPEED = 0x116E9          # the speed he speeds up to: PRG0 $80 (children add $100 to both)
MANHANDLA_SPEED = 0x12169               # PRG0 $80
GOHMA_FIREBALL_TIMER = 0x123C6          # frames between fireballs (lower is more often): PRG0 $41
# Aquamentus' fireball timer is `ORA #$70` (09 70): a random value of at least $70. The harder ones
# shorten it with two instructions, NOP NOP (random), LSR NOP (half) and LSR LSR (a quarter).
AQUAMENTUS_FIREBALL_TIMER = 0x11805
NOP, LSR_A = 0xEA, 0x4A
AQUAMENTUS_TIMER_CODE = {1: bytes([NOP, NOP]), 2: bytes([LSR_A, NOP]), 3: bytes([LSR_A, LSR_A])}

# PRG0's whole instruction run around it, LDA $18,X / ORA #$70 / STA $28,X.
AQUAMENTUS_TIMER_RUN = range(AQUAMENTUS_FIREBALL_TIMER - 2, AQUAMENTUS_FIREBALL_TIMER + 4)
PRG0_AQUAMENTUS_TIMER_RUN = bytes.fromhex("B5 18 09 70 95 28")

# harder-ganon's first byte, GanonLevel (bank 4 $BB00): the level the seed runs.
GANON_PATCH = "harder-ganon"
GANON_LEVEL_OFFSET = 0x13B10
# Its "ganon-fight" hook: Ganon_ScenePhase2's JSR Ganon_CheckCollisions ($AEE4) in PRG0, which the
# patch replaces with JSR GanonRegenerates.
GANON_FIGHT_HOOK = range(0x12CF9, 0x12CFC)
PRG0_GANON_FIGHT_CALL = bytes.fromhex("20 E4 AE")


def harder_boss_writes(level: int) -> list[tuple[int, bytes]]:
    """Harder Bosses at `level` (1 to 3), as (file offset, bytes)."""
    return [
        (DIGDOGGER_LOW_SPEED, bytes([0x40 + 0x24 * level])),
        (DIGDOGGER_HIGH_SPEED, bytes([0x80 + 0x24 * level])),
        (MANHANDLA_SPEED, bytes([0x80 + 0x20 * level])),
        (GOHMA_FIREBALL_TIMER, bytes([0x41 - 0x0C * level])),
        (AQUAMENTUS_FIREBALL_TIMER, AQUAMENTUS_TIMER_CODE[level]),
    ]


def harder_ganon_writes(level: int) -> list[tuple[int, bytes]]:
    """Harder Ganon at `level` (1 to 3): the patch with GanonLevel set."""
    writes = []
    for offset, piece in PATCHES[GANON_PATCH]:
        data = bytearray(piece_bytes(piece))
        if offset <= GANON_LEVEL_OFFSET < offset + len(data):
            data[GANON_LEVEL_OFFSET - offset] = level
        writes.append((offset, bytes(data)))
    return writes


def harder_writes(harder_bosses: int, harder_ganon: int) -> list[tuple[int, bytes]]:
    """The writes of both settings (0 is off)."""
    return [*(harder_boss_writes(harder_bosses) if harder_bosses else []),
            *(harder_ganon_writes(harder_ganon) if harder_ganon else [])]


def aquamentus_timer_run(rom: bytes) -> bytes:
    """The instruction run holding Aquamentus' fireball timer, as `rom` has it."""
    return rom[AQUAMENTUS_TIMER_RUN.start:AQUAMENTUS_TIMER_RUN.stop]


def has_ganon_fight_hook(rom: bytes) -> bool:
    """Whether `rom` has Harder Ganon's ganon-fight hook in place of PRG0's call."""
    return rom[GANON_FIGHT_HOOK.start:GANON_FIGHT_HOOK.stop] != PRG0_GANON_FIGHT_CALL
