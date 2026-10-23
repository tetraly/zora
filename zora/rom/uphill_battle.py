"""The beta 8 export's fixed code and data patches (the rest of the Uphill Battle tournament set),
written by the final steps after the code patches, each with its field on:

  B07  Recorder to Unbeaten Dungeons (overworld-behavior.md OW-WARP-02)
  B24  Hide Dungeon Numbers (features-behavior.md FP-LEVEL-02)
  B55  Hidden Health (FP-HIDE-01), after the player settings, which it overrides
  C19  Red Bubble Curse at 1 or 2 (FP-BUBL-01)
  B47  Replace Book Fire with Explosion's blast (FP-BOOK-02)
  B39  Make Important Items Drops and B44 Randomize Item Drop Rate (post-shapes-b8.md PS-EDROP-01,
       PS-EDROP-02), drawn from their own stream (enemy_drop_rng; no draw of the generation's)

Every site is checked against PRG0's bytes when it is written (the player's ROM, in PRG0's layout).

Where ZORA's ROM map has the spec's free space taken, the routine moves (docs/deviations.md "Beta 8
patches: where their routines live"):
  - B47's routine is 12 bytes in the unused end of the common code bank 1 copies to RAM ($B751 in
    bank 1, run at $7EE1; the spec's $FFD7 in bank 7 is fp-hot-01's and z1rr-coop's), ending in a
    jump to PlayEffect, which ORs the effect into EffectRequest where the spec's routine stores it;
  - C19 = 1's bank-7 stub (the spec's $FAE5, z1rr-coop's reserve) is 9 bytes at the end of that same
    copied block ($B767, run at $7EF7), and its bank-2 routine, at the spec's $BF20, opens with the
    TXA the stub leaves out;
  - C19 = 2's routine goes to bank 5's $BD00 (the spec's $B900 overlaps z1rr-coop's $B8F0-$B901).
  C19 = 2's hook is InitLinkSpeed's first instructions, the spec's site, which z1rr-coop also hooks.
"""
from __future__ import annotations

from ..generate.rng import IntRng
from .base_rom import original_bytes
from .layout import LEVEL_INFO_ADDRESS, LEVEL_INFO_SIZE, LOW_HEALTH_BEEP_OPERAND_ADDRESS

Writes = list[tuple[int, bytes]]

# --- OW-WARP-02 (B07): the whirlwind reads ~InvTriforce -------------------------------------------
RECORDER_TRIFORCE_LOAD = 0x060CC                 # bank 1 $A0BC: LDA InvTriforce
RECORDER_TRIFORCE_LOAD_PRG0 = bytes.fromhex("ad7106")
RECORDER_COMPLEMENT_CALL = bytes.fromhex("20f09f")           # JSR $9FF0
RECORDER_COMPLEMENT_ROUTINE = 0x06000            # bank 1 $9FF0, PRG0 $FF
RECORDER_COMPLEMENT = bytes.fromhex("ad710649ff60")          # LDA InvTriforce / EOR #$FF / RTS

# --- FP-LEVEL-02 (B24): levels 1 to 8 show "?" ----------------------------------------------------
LEVEL_NUMBER_OFFSET = 0x33                       # LevelInfo_LevelNumber
QUESTION_MARK_TILE = 0x2E
HIDDEN_NUMBER_LEVELS = range(1, 9)

# --- FP-HIDE-01 (B55) -----------------------------------------------------------------------------
HEART_COLOR_OFFSET = 8                           # FP-SET-03's byte in each level information
LEVEL_INFORMATIONS = 10
HIDDEN_HEART_COLOR = 0x36
BEEP_NEVER = 0x00

# --- FP-BUBL-01 (C19) -----------------------------------------------------------------------------
SWORD_BLOCK_TEST = 0x172B3                       # bank 5 $B2A3: ORA SwordBlocked
SWORD_BLOCK_TEST_PRG0 = bytes.fromhex("0d2e05")
NOPS = bytes.fromhex("eaeaea")
INPUT_DIR_STORE = 0x1EC6F                        # bank 7 $EC5F: STA ObjInputDir
INPUT_DIR_STORE_PRG0 = bytes.fromhex("8df803")
INVERT_STUB = 0x07777                            # bank 1 $B767, copied to RAM $7EF7
INVERT_STUB_CALL = bytes.fromhex("20f77e")       # JSR $7EF7
# TAX / LDA #$02 / JSR SwitchBank / JMP $BF20 (the spec's TXA moves into the routine)
INVERT_STUB_CODE = bytes.fromhex("aaa90220acff4c20bf")
INVERT_ROUTINE = 0x0BF30                         # bank 2 $BF20
# TXA, then the spec's routine: with SwordBlocked set and the submenu closed, swap left and
# right and up and down in the stored direction
INVERT_ROUTINE_CODE = bytes.fromhex("8aae2e05f018a6e1d014aa2903f0048a4903aa8aaa290cf0048a490caa8a8df80360")
LINK_SPEED_INIT = 0x17376                        # bank 5 $B366: LDA #$60 / STA $00 (InitLinkSpeed)
LINK_SPEED_INIT_PRG0 = bytes.fromhex("a9608500")
SLOW_SPEED_CALL = bytes.fromhex("2000bdea")      # JSR $BD00 / NOP
SLOW_SPEED_ROUTINE = 0x17D10                     # bank 5 $BD00
SLOW_SPEED_CODE = bytes.fromhex("ad2e05f005a9308500 60a9608500 60".replace(" ", ""))
# With Pegasus Boots, whose `JSR BootsSpeed / NOP` already holds InitLinkSpeed's four bytes: the
# routine calls BootsSpeed first, then halves the speed while the flag is set (the curse wins over
# the boots): JSR BootsSpeed / LDA SwordBlocked / BEQ +4 / LDA #$30 / STA $00 / RTS.
JSR, NOP = 0x20, 0xEA
SLOW_AFTER_BOOTS_CODE = bytes.fromhex("ad2e05f004a930850060")
SLOW_SPEED_CALLED = SLOW_SPEED_ROUTINE + 1       # the boots' JSR operand there (revision.MOVED_POINTERS)
INVERTED_CONTROLS, SLOW_SPEED = 1, 2

# --- FP-BOOK-02 (B47's blast) ---------------------------------------------------------------------
WIELD_CANDLE_OPERAND = 0x1F3FB                   # HandleShotBlocked's JSR WieldCandle operand
WIELD_CANDLE_OPERAND_PRG0 = bytes.fromhex("4f71")
BLAST_CALL_OPERAND = bytes.fromhex("e17e")       # JSR $7EE1
BLAST_ROUTINE = 0x07761                          # bank 1 $B751, copied to RAM $7EE1
# JSR WieldCandle / LDA #$12 / STA ObjState,X / LDA #$10 / JMP PlayEffect ($6D80 in RAM)
BLAST_ROUTINE_CODE = bytes.fromhex("204f71a91295aca9104c806d")
FIRE_STATE_TEST = 0x1F407                        # CMP #$21 operand
FIRE_STATE_PRG0, BLAST_STATE = 0x21, 0x12
FIRE_DURATION = 0x1F41E                          # LDA #$4F operand
FIRE_DURATION_PRG0, BLAST_DURATION = 0x4F, 0x18

# --- PS-EDROP-01 and PS-EDROP-02 (B39, B44) -------------------------------------------------------
DROP_RATES = 0x1304E                             # DropItemRates, one byte per monster group
DROP_RATE_COUNT = 4
DROP_ITEM_TABLE = 0x13052                        # DropItemTable, four rows of ten
DROP_ITEM_COUNT = 40
RUPEE, HEART = 0x18, 0x22
# PS-EDROP-01's fifteen codes in order: recorder, raft, both boomerangs, ladder, wand, bow, red ring,
# magical key, red candle, silver arrow, book, bait, power bracelet, magical sword (not under C07 = 3)
IMPORTANT_DROPS = (0x05, 0x0C, 0x1D, 0x1E, 0x0D, 0x10, 0x0A, 0x13, 0x0B, 0x07, 0x09, 0x11, 0x04, 0x14, 0x03)
MAGICAL_SWORD = 0x03
DROP_RATE_LOWEST, DROP_RATE_HIGHEST = 0x50, 0xAF


def _checked(offset: int, prg0: bytes, name: str) -> None:
    assert original_bytes(offset, len(prg0)) == prg0, f"{name} is not PRG0's"


def _free(offset: int, length: int, name: str) -> None:
    assert original_bytes(offset, length) == b"\xff" * length, f"{name}'s space is not PRG0's unused space"


def recorder_to_unbeaten_writes() -> Writes:
    """OW-WARP-02: the whirlwind routine reads the complement of InvTriforce."""
    _checked(RECORDER_TRIFORCE_LOAD, RECORDER_TRIFORCE_LOAD_PRG0, "the recorder's Triforce test")
    _free(RECORDER_COMPLEMENT_ROUTINE, len(RECORDER_COMPLEMENT), "OW-WARP-02")
    return [(RECORDER_TRIFORCE_LOAD, RECORDER_COMPLEMENT_CALL), (RECORDER_COMPLEMENT_ROUTINE, RECORDER_COMPLEMENT)]


def hide_dungeon_numbers_writes() -> Writes:
    """FP-LEVEL-02: levels 1 to 8's LevelInfo_LevelNumber becomes the question-mark tile; the
    overworld's (0) and level 9's keep theirs."""
    return [(LEVEL_INFO_ADDRESS + level * LEVEL_INFO_SIZE + LEVEL_NUMBER_OFFSET, bytes([QUESTION_MARK_TILE]))
            for level in HIDDEN_NUMBER_LEVELS]


def hidden_health_writes() -> Writes:
    """FP-HIDE-01: the ten heart colours $36 and the low-health tone never requested, over the
    player's heart colour and beep (written after the player settings)."""
    return [*((LEVEL_INFO_ADDRESS + level * LEVEL_INFO_SIZE + HEART_COLOR_OFFSET, bytes([HIDDEN_HEART_COLOR]))
              for level in range(LEVEL_INFORMATIONS)),
            (LOW_HEALTH_BEEP_OPERAND_ADDRESS, bytes([BEEP_NEVER]))]


def red_bubble_writes(curse: int, rom: bytes | bytearray) -> Writes:
    """FP-BUBL-01: under C19 = 1 and 2 the sword no longer reads SwordBlocked; 1 inverts the stored
    direction while it is set (the submenu closed), 2 sets Link's speed to $30 while it is set (on
    the image `rom` as the code patches leave it: after Pegasus Boots' speed, when the boots hold
    InitLinkSpeed)."""
    _checked(SWORD_BLOCK_TEST, SWORD_BLOCK_TEST_PRG0, "Link_HandleInput's sword-block test")
    writes = [(SWORD_BLOCK_TEST, NOPS)]
    if curse == INVERTED_CONTROLS:
        _checked(INPUT_DIR_STORE, INPUT_DIR_STORE_PRG0, "the input direction store")
        _free(INVERT_STUB, len(INVERT_STUB_CODE), "FP-BUBL-01's stub")
        _free(INVERT_ROUTINE, len(INVERT_ROUTINE_CODE), "FP-BUBL-01's bank-2 routine")
        writes += [(INPUT_DIR_STORE, INVERT_STUB_CALL), (INVERT_STUB, INVERT_STUB_CODE),
                   (INVERT_ROUTINE, INVERT_ROUTINE_CODE)]
    elif curse == SLOW_SPEED:
        _checked(LINK_SPEED_INIT, LINK_SPEED_INIT_PRG0, "InitLinkSpeed")
        _free(SLOW_SPEED_ROUTINE, len(SLOW_SPEED_CODE), "FP-BUBL-01's speed routine")
        writes += [(LINK_SPEED_INIT, SLOW_SPEED_CALL), (SLOW_SPEED_ROUTINE, slow_speed_code(rom))]
    else:
        raise ValueError(f"C19 = {curse} writes nothing")
    return writes


def slow_speed_code(rom: bytes | bytearray) -> bytes:
    """C19 = 2's routine: the spec's, or with Pegasus Boots' call in InitLinkSpeed that call first."""
    site = bytes(rom[LINK_SPEED_INIT:LINK_SPEED_INIT + len(LINK_SPEED_INIT_PRG0)])
    if site == SLOW_SPEED_CALL:
        # a finished ROM written again: the routine there starts with the boots' call when it has one
        written = bytes(rom[SLOW_SPEED_ROUTINE:SLOW_SPEED_ROUTINE + 3])
        return written + SLOW_AFTER_BOOTS_CODE if written[0] == JSR else SLOW_SPEED_CODE
    if site == LINK_SPEED_INIT_PRG0:
        return SLOW_SPEED_CODE
    assert site[0] == JSR and site[3] == NOP, "InitLinkSpeed holds neither PRG0's code nor Pegasus Boots' call"
    return site[:3] + SLOW_AFTER_BOOTS_CODE


def book_explosion_writes() -> Writes:
    """FP-BOOK-02's blast: the wand's stopped shot with the Book makes a bomb at its blast stage,
    lasting $18 frames, in a bomb-or-fire slot (the second one when neither is free)."""
    _checked(WIELD_CANDLE_OPERAND, WIELD_CANDLE_OPERAND_PRG0, "HandleShotBlocked's WieldCandle call")
    _checked(FIRE_STATE_TEST, bytes([FIRE_STATE_PRG0]), "HandleShotBlocked's fire test")
    _checked(FIRE_DURATION, bytes([FIRE_DURATION_PRG0]), "HandleShotBlocked's fire duration")
    _free(BLAST_ROUTINE, len(BLAST_ROUTINE_CODE), "FP-BOOK-02's routine")
    return [(WIELD_CANDLE_OPERAND, BLAST_CALL_OPERAND), (BLAST_ROUTINE, BLAST_ROUTINE_CODE),
            (FIRE_STATE_TEST, bytes([BLAST_STATE])), (FIRE_DURATION, bytes([BLAST_DURATION]))]


def important_item_drops(table: bytearray, rng: IntRng, swordless: bool) -> None:
    """PS-EDROP-01: each of the fifteen codes (the magical sword left out under C07 = 3) takes a
    slot drawn uniformly, drawn again until the slot holds a rupee or a heart."""
    for code in IMPORTANT_DROPS:
        if swordless and code == MAGICAL_SWORD:
            continue
        while True:
            slot = rng.below(DROP_ITEM_COUNT)
            if table[slot] in (RUPEE, HEART):
                table[slot] = code
                break


def random_drop_rates(rng: IntRng) -> bytes:
    """PS-EDROP-02: each group's rate drawn uniformly from 80 to 175."""
    return bytes(DROP_RATE_LOWEST + rng.below(DROP_RATE_HIGHEST - DROP_RATE_LOWEST + 1)
                 for _ in range(DROP_RATE_COUNT))


def enemy_drop_writes(rng: IntRng, important_items: bool, rates: bool, swordless: bool) -> Writes:
    """B39's table, then B44's rates, from PRG0's table (no other pass changes it)."""
    writes: Writes = []
    if important_items:
        table = bytearray(original_bytes(DROP_ITEM_TABLE, DROP_ITEM_COUNT))
        important_item_drops(table, rng, swordless)
        writes.append((DROP_ITEM_TABLE, bytes(table)))
    if rates:
        writes.append((DROP_RATES, random_drop_rates(rng)))
    return writes
