"""The beta 9 export's small settings that are fixed patches, written by the final steps after the
beta 8 patches (uphill_battle), each with its field on:

  B56  Killable Drop Items (features-behavior.md FP-KILL-01)
  B83  Hidden Numbers (FP-NUM-01), keeping ZORA's boss-sound label (owner ruling, 2026-10-22)
  B80  Rupees Affect Speed (FP-RSPD-01), with Pegasus Boots and with the Red Bubble Curse's slow speed
  B84  Prevent Clipping (FP-CLIP-01)

Every site is checked against PRG0's bytes when it is written, so writing a finished ROM again gives
the same bytes. Where the spec's bytes repeat a run of the original game's own code (the weapon tests'
calls, the step routines' tails), the run is read from the player's ROM (an OriginalRun), never stored
here. The bytes are the spec's except where ZORA's own code holds the spec's site
(docs/deviations.md "Hidden Numbers keeps the boss-sound label" and "Rupees Affect Speed with
Pegasus Boots and Slow Speed"):
  - B83's status-bar routine ends by calling CopyTripletToTextBuf and then jumping into fp-roar-01's
    FormatBombCountAndRoomLabel after its count (the spec's routine ends in that call's jump, which
    skips the label hook), so the boss-sound label keeps showing;
  - B80 with Pegasus Boots: InitLinkSpeed keeps the boots' `JSR BootsSpeed`; the rupee speed routine
    goes at the spec's $B90A, called from there, and replaces the boots' speed only when it is faster;
  - B80 with Slow Speed (C19 = 2): the ten bytes go over the "otherwise" branch of ZORA's slow-speed
    routine at $BD00 (the spec's $B900 is z1rr-coop's), and with the boots too the routine calls
    BootsSpeed, then the curse's $30, then the rupee speed.
"""
from __future__ import annotations

from .base_rom import Piece, original_bytes
from .code_patch_data import PATCHES as CODE_PATCHES
from .flags2_patch_data import PATCHES as FLAGS2_PATCHES
from .uphill_battle import LINK_SPEED_INIT, LINK_SPEED_INIT_PRG0, SLOW_SPEED_CODE, SLOW_SPEED_ROUTINE

Writes = list[tuple[int, bytes]]
JSR, JMP = 0x20, 0x4C
FREE = 0xFF
OriginalRun = tuple[int, int]                    # (file offset, length): bytes of the player's ROM
Pieces = tuple[bytes | OriginalRun, ...]


def _assembled(pieces: Pieces) -> bytes:
    """A patch's bytes: its own, with each OriginalRun read from the player's ROM."""
    return b"".join(piece if isinstance(piece, bytes) else original_bytes(*piece) for piece in pieces)


def _own_bytes(patch: tuple[tuple[int, Piece], ...], offset: int) -> bytes:
    """A patch's own bytes written at `offset` (not an Original)."""
    piece = dict(patch)[offset]
    assert isinstance(piece, bytes), f"the piece at 0x{offset:05X} is the original game's"
    return piece


# --- FP-KILL-01 (B56) -----------------------------------------------------------------------------
ITEM_TAKER_LOOP = 0x1312F                        # bank 4 $B11F: the item update's taker loop
ITEM_TAKER_LOOP_PRG0 = bytes.fromhex("3ea904850d")
# BVC; Link's taker test (PRG0's slot load and JSR $733F, then the taken-item test); the lifetime
# test; the five weapon tests as CheckMonsterCollisions calls them (PRG0's own run); JMP $7D5F
ITEM_TAKER_CODE: Pieces = (bytes.fromhex("58"), (0x13151, 10), (0x13161, 8), bytes.fromhex("45bda803c9f0b03e202d7a"),
                           (0x0725F, 27), bytes.fromhex("4c5f7d"))
ITEM_KILL_ROUTINES = 0x13F4B                     # bank 4 $BF3B, PRG0's unused $FF
# $BF3B: CMP #$60 / BEQ +3 / INC RoomKillCount / RTS; $BF43: LDA #0 / STA ObjHP,X / LDA #$C0 /
# STA ObjInvincibilityMask,X / JMP $FECA (the item and tile-object initialisation)
ITEM_KILL_CODE = bytes.fromhex("c960f003ee4f0360a9009d8504a9c09db2044ccafe")
KILL_COUNT_INCREMENT = 0x1FCD4                   # bank 7 $FCC4: INC RoomKillCount
KILL_COUNT_INCREMENT_PRG0 = bytes.fromhex("ee4f03")
KILL_COUNT_CALL = bytes.fromhex("203bbf")        # JSR $BF3B
ITEM_INIT_JUMP = 0x1FD8D                         # bank 7 $FD7C's JMP operand
ITEM_INIT_JUMP_PRG0 = bytes.fromhex("cafe")
ITEM_INIT_OPERAND = bytes.fromhex("43bf")        # JMP $BF43

# --- FP-NUM-01 (B83) ------------------------------------------------------------------------------
STATUS_BAR_COUNTS = 0x0659C                      # FormatStatusBarText after the hearts' X operand
STATUS_BAR_COUNTS_PRG0 = bytes.fromhex("ad6d06a01b")
# For each of the rupee, key and bomb places ($1B, $21, $27): STY $00 via LDA/STA, "X" in $01, "?"
# through FormatCharDoublet ($6D75), then CopyTripletToTextBuf ($6D55); the spec's last call is a JMP
STATUS_BAR_HIDDEN = bytes.fromhex(
    "a91b8500a9218501a92e20756d20556da9218500a9218501a92e20756d20556da9278500a9218501a92e20756d4c556d")
LAST_COPY_OPCODE = STATUS_BAR_COUNTS + len(STATUS_BAR_HIDDEN) - 3
# fp-roar-01's hook at FormatStatusBarText's last JMP: its operand, FormatBombCountAndRoomLabel,
# which formats the bomb count (JSR, 3 bytes) and then copies the room label record
ROAR_HOOK_OPERAND = 0x065CE
ROAR_LABEL_ENTRY = int.from_bytes(_own_bytes(CODE_PATCHES["fp-roar-01"], ROAR_HOOK_OPERAND), "little") + 3
ROAR_LABEL_JUMP = LAST_COPY_OPCODE + 3          # 0x065CC, over the hook's opcode
DECIMAL_BYTE = 0x066D5                           # FormatDecimalByte
DECIMAL_BYTE_PRG0 = bytes.fromhex("206e6e8503")
# LDA #"?" / STA $03 / LDA #" " / STA $02 / STA $01 / RTS
DECIMAL_HIDDEN = bytes.fromhex("a92e8503a9248502850160")
BOMB_PRICE_TILES = 0x1A2B2                       # FP-BOMB-01's three price tiles
BOMB_PRICE_HIDDEN = bytes.fromhex("2e2424")

# --- FP-RSPD-01 (B80) -----------------------------------------------------------------------------
RUPEE_SPEED_ROUTINE = 0x1791A                    # bank 5 $B90A, PRG0's unused $FF
RUPEE_SPEED_CALL = bytes.fromhex("200ab9ea")     # JSR $B90A / NOP
# LDA InvRupees / LSR / CLC / ADC #$60 / STA $00 / RTS
RUPEE_SPEED_CODE = bytes.fromhex("ad6d064a1869608500 60".replace(" ", ""))
# With the boots: their call first, then the rupee speed unless the boots chose a faster one:
# JSR BootsSpeed / LDA InvRupees / LSR / CLC / ADC #$60 / CMP $00 / BCC +2 / STA $00 / RTS
BOOTS_SPEED_CALL = _own_bytes(FLAGS2_PATCHES["pegasus-boots"], LINK_SPEED_INIT)[:3]      # JSR BootsSpeed
RUPEE_AFTER_BOOTS_CODE = bytes.fromhex("ad6d064a186960c5009002850060")
RUPEE_BOOTS_CALLED = RUPEE_SPEED_ROUTINE + 1     # the boots' JSR operand there (revision.MOVED_POINTERS)
SLOW_OTHERWISE = SLOW_SPEED_ROUTINE + 10         # SLOW_SPEED_CODE's LDA #$60 / STA $00 / RTS
# With the boots and the curse: JSR BootsSpeed / LDA SwordBlocked / BEQ +5 / LDA #$30 / STA $00 /
# RTS, then RUPEE_AFTER_BOOTS_CODE's rupee part
SLOW_THEN_RUPEES_CODE = bytes.fromhex("ad2e05f005a930850060")
SLOW_BOOTS_CALLED = SLOW_SPEED_ROUTINE + 1       # uphill_battle.SLOW_SPEED_CALLED

# --- FP-CLIP-01 (B84) -----------------------------------------------------------------------------
STEP_ROUTINES = 0x0684F                          # bank 1: the two routines from the first limit test
STEP_ROUTINES_PRG0 = bytes.fromhex("cd0e01f005")
STEP_ROUTINES_CODE: Pieces = (bytes.fromhex("6900cd0e01f009c900d007dd9403f005a001"), (0x06863, 19),
                              bytes.fromhex("e900cd0f01f009c900d007dd9403f005a0019d94032860"))
MOVE_OBJECT = 0x1F09E                            # MoveObject from its first limit operand
MOVE_OBJECT_PRG0 = bytes.fromhex("08a0f8e000")
MOVE_OBJECT_CODE: Pieces = (
    bytes.fromhex("10e000d0014a8d0e0109f08d0f01a50ff017a0044ab02d4ab01d4ab00d20e66fb584e900958488d0f4"),
    (0x1F0D0, 10), bytes.fromhex("88d0f46020e66fb570e900957088d0f4"), (0x1F0DA, 10), bytes.fromhex("88d0f4"))
WALK_END_TESTS = ((0x1EBDA, 0x08, 0x0A), (0x1EBDB, 0xF0, 0x90), (0x1EBDF, 0xF0, 0xB0))  # (site, PRG0, B84)


def _checked(offset: int, prg0: bytes, name: str) -> None:
    assert original_bytes(offset, len(prg0)) == prg0, f"{name} is not PRG0's"


def _free(offset: int, length: int, name: str) -> None:
    assert original_bytes(offset, length) == bytes([FREE]) * length, f"{name}'s space is not PRG0's unused space"


def killable_drop_items_writes() -> Writes:
    """FP-KILL-01: only Link takes dropped items, Link's weapons hit them as monsters (0 hit points,
    mask $C0), and a killed one becomes a new drop without counting as a kill."""
    _checked(ITEM_TAKER_LOOP, ITEM_TAKER_LOOP_PRG0, "the item update's taker loop")
    _free(ITEM_KILL_ROUTINES, len(ITEM_KILL_CODE), "FP-KILL-01's routines")
    _checked(KILL_COUNT_INCREMENT, KILL_COUNT_INCREMENT_PRG0, "the room kill count's increment")
    _checked(ITEM_INIT_JUMP, ITEM_INIT_JUMP_PRG0, "the item initialisation's jump")
    return [(ITEM_TAKER_LOOP, _assembled(ITEM_TAKER_CODE)), (ITEM_KILL_ROUTINES, ITEM_KILL_CODE),
            (KILL_COUNT_INCREMENT, KILL_COUNT_CALL), (ITEM_INIT_JUMP, ITEM_INIT_OPERAND)]


def hidden_numbers_writes() -> Writes:
    """FP-NUM-01: the status bar's three counts "X?", every decimal number "?" and the bomb upgrade's
    price "?"; the status bar then goes on to fp-roar-01's label (owner ruling: ZORA keeps it)."""
    _checked(STATUS_BAR_COUNTS, STATUS_BAR_COUNTS_PRG0, "FormatStatusBarText's counts")
    _checked(DECIMAL_BYTE, DECIMAL_BYTE_PRG0, "FormatDecimalByte")
    status_bar = bytearray(STATUS_BAR_HIDDEN)
    status_bar[-3] = JSR                         # call CopyTripletToTextBuf, then the label
    label_jump = bytes([JMP]) + ROAR_LABEL_ENTRY.to_bytes(2, "little")
    return [(STATUS_BAR_COUNTS, bytes(status_bar)), (ROAR_LABEL_JUMP, label_jump),
            (DECIMAL_BYTE, DECIMAL_HIDDEN), (BOMB_PRICE_TILES, BOMB_PRICE_HIDDEN)]


def rupee_speed_writes(slow_speed: bool, pegasus_boots: bool) -> Writes:
    """FP-RSPD-01: Link's quarter speed $60 + rupees / 2. With Slow Speed (C19 = 2, after its writes)
    the rupee speed is its routine's "otherwise" branch; with Pegasus Boots their speed stays
    whenever it is faster."""
    if slow_speed:
        if not pegasus_boots:
            assert SLOW_SPEED_CODE[10:] == LINK_SPEED_INIT_PRG0 + b"\x60", "the slow-speed routine moved"
            return [(SLOW_OTHERWISE, RUPEE_SPEED_CODE)]
        _free(SLOW_SPEED_ROUTINE, 3 + len(SLOW_THEN_RUPEES_CODE) + len(RUPEE_AFTER_BOOTS_CODE),
              "the slow-speed routine with the rupee speed")
        return [(SLOW_SPEED_ROUTINE, BOOTS_SPEED_CALL + SLOW_THEN_RUPEES_CODE + RUPEE_AFTER_BOOTS_CODE)]
    _checked(LINK_SPEED_INIT, LINK_SPEED_INIT_PRG0, "InitLinkSpeed")
    if not pegasus_boots:
        _free(RUPEE_SPEED_ROUTINE, len(RUPEE_SPEED_CODE), "FP-RSPD-01's routine")
        return [(LINK_SPEED_INIT, RUPEE_SPEED_CALL), (RUPEE_SPEED_ROUTINE, RUPEE_SPEED_CODE)]
    _free(RUPEE_SPEED_ROUTINE, 3 + len(RUPEE_AFTER_BOOTS_CODE), "FP-RSPD-01's routine with the boots")
    return [(LINK_SPEED_INIT, RUPEE_SPEED_CALL), (RUPEE_SPEED_ROUTINE, BOOTS_SPEED_CALL + RUPEE_AFTER_BOOTS_CODE)]


def prevent_clipping_writes() -> Writes:
    """FP-CLIP-01: up to four steps a frame, each ending the frame's movement when the grid offset
    reaches the limit in the moving direction or comes back to 0, and the room-to-room walk's wider
    end test."""
    _checked(STEP_ROUTINES, STEP_ROUTINES_PRG0, "the position-fraction routines")
    _checked(MOVE_OBJECT, MOVE_OBJECT_PRG0, "MoveObject")
    for site, prg0, _ in WALK_END_TESTS:
        _checked(site, bytes([prg0]), "the room-to-room walk's end test")
    return [(STEP_ROUTINES, _assembled(STEP_ROUTINES_CODE)), (MOVE_OBJECT, _assembled(MOVE_OBJECT_CODE)),
            *((site, bytes([value])) for site, _, value in WALK_END_TESTS)]
