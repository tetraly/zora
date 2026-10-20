"""Permanent Sword Beam (B52; features-behavior.md FP-BEAM-01) and OHKO (B53; FP-OHKO-01): two
fixed code patches, written after the code patches with their fields on, and taking no draw.

Aldonunez labels, at the pinned commit:
  B52: MakeSwordShot (Z_07.asm) fires a beam only at full health: it tests HeartValues ($066F) at
       CPU $F865 (file 0x1F875) and HeartPartial after it. Its first instruction, LDA HeartValues,
       becomes JMP $F87D, the @SetUp that fires the beam. The test that no beam is in flight comes
       before it and stays.
  B53: Link_BeHarmed (Z_01.asm) halves the damage in [$0E:$0D] once per ring level (LDY InvRing,
       BEQ, then LSR $0D / ROR $0E / DEY / BNE, file 0x073DB). The 11 bytes become LDA $0D;
       ORA $0E; BEQ +6; LDA #$FF; STA $0D; STA <the next byte>: any damage that is not zero takes
       $FF whole hearts, more than Link can hold, so the hit kills him; zero damage still takes
       nothing. The byte after them stays PRG0's $F9, so the last store goes to $F9, which nothing
       reads, and the BEQ lands where the ring loop's BNE ended, at @ResetHelp.
"""
from __future__ import annotations

import hashlib

from .base_rom import original_bytes

# FP-BEAM-01: MakeSwordShot's LDA HeartValues, then JMP @SetUp
BEAM_HEALTH_TEST = 0x1F875
BEAM_PRG0 = bytes.fromhex("ad6f06")              # LDA HeartValues
BEAM_PATCH = bytes.fromhex("4c7df8")             # JMP $F87D
# FP-OHKO-01: Link_BeHarmed's ring halving, then the byte its last store takes as an operand
RING_HALVING = 0x073DB
# PRG0's eleven bytes there (LDY InvRing ... BNE), checked by their SHA-256: a release ships no run
# of the original game's bytes (scripts/release_scan.py)
RING_HALVING_LENGTH = 11
RING_HALVING_PRG0_SHA256 = "3e8a19ce9dc74ebece8fa54eb4db30d6de289928c64b6ea41c963bac1abfb394"
ONE_HIT_PATCH = bytes.fromhex("a50d050ef006a9ff850d85")         # LDA $0D ... STA (zp)
assert len(ONE_HIT_PATCH) == RING_HALVING_LENGTH
KEPT_OPERAND = RING_HALVING + RING_HALVING_LENGTH               # PRG0's $F9 (BNE's offset)
KEPT_OPERAND_PRG0 = 0xF9


def permanent_sword_beam_writes() -> list[tuple[int, bytes]]:
    """FP-BEAM-01's three bytes as (file offset, bytes), checked against the player's ROM."""
    assert original_bytes(BEAM_HEALTH_TEST, len(BEAM_PRG0)) == BEAM_PRG0, "MakeSwordShot is not PRG0's"
    return [(BEAM_HEALTH_TEST, BEAM_PATCH)]


def one_hit_knock_out_writes() -> list[tuple[int, bytes]]:
    """FP-OHKO-01's eleven bytes as (file offset, bytes), checked against the player's ROM; the
    byte after them is kept."""
    assert is_prg0_ring_halving(original_bytes(RING_HALVING, RING_HALVING_LENGTH)), "Link_BeHarmed is not PRG0's"
    assert original_bytes(KEPT_OPERAND, 1)[0] == KEPT_OPERAND_PRG0, "Link_BeHarmed is not PRG0's"
    return [(RING_HALVING, ONE_HIT_PATCH)]


def is_prg0_ring_halving(data: bytes) -> bool:
    """Whether `data` is PRG0's eleven bytes at RING_HALVING."""
    return hashlib.sha256(data).hexdigest() == RING_HALVING_PRG0_SHA256
