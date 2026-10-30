"""Swordlish (features-behavior.md FP-SWL-01 and FP-SWL-05; BogieSmalls', used with his
permission, 2026-10-29): the wooden-sword cave's sword is taken only with N triforce pieces, and the cave's
person says so in a text of its own. The bytes a world's swordlish_pieces writes; none when it is 0.

Aldonunez labels, at the pinned commit (file offsets, PRG0; bank 1). ZORA's routines are its own (the spec
states what they do; the add-on's routine is not used):
  - The take: UpdateCavePersonState_TalkOrShopOrDoorCharge's @TryToTake reads `LDA CaveFlags / AND #$40`
    (0x04905) and goes on to `BEQ @Take`. The pair becomes `JSR TAKE_CHECK` and two no-operations. For
    any ware but the wooden-sword cave's sword (object type $6A, item $01) the routine returns PRG0's
    `CaveFlags AND #$40`, so every other heart requirement stays PRG0's (FP-SWL-01). For the sword it
    counts the bits of InvTriforce (levels 1 to 8; starting pieces are bits like any other): with N or
    more it returns zero, and @Take takes the sword; with fewer it returns from the cave routine itself, as
    PRG0's heart check does when the hearts are short, so touching the sword does nothing.
  - The text: UpdatePersonState_Textbox loads each character's text address into [00:01] from
    PersonTextAddrs (0x04847 is Book to Understand NPCs' hook, ht-book-01), then `STA $01 / LDY
    PersonTextIndex` (0x04850). That pair becomes `JSR TEXT_ADDRESS` and two no-operations: in the
    wooden-sword cave (object type $6A on the overworld) the routine points [00:01] at the Swordlish text
    instead, so no other person, and no text slot, changes (FP-SWL-05).
Both routines and the text sit in bank 1's free blocks (docs/rom-map.md; asm/rom_space.toml sites
swordlish-take, swordlish-text-address and swordlish-text).
"""
from __future__ import annotations

from .serialize.features import encoded_refusal_text

TAKE_HOOK = 0x04905                  # @TryToTake's LDA CaveFlags / AND #$40
TAKE_HOOK_PRG0 = bytes.fromhex("AD13042940")
TEXT_HOOK = 0x04850                  # UpdatePersonState_Textbox's STA $01 / LDY PersonTextIndex
TEXT_HOOK_PRG0 = bytes.fromhex("8501AC1604")
TAKE_CHECK = 0x05F70                 # bank 1 $9F60, in the free block after DemoBackgroundPatterns
TAKE_CHECK_CPU = 0x9F60
TEXT_ADDRESS = 0x05FB0               # bank 1 $9FA0
TEXT_ADDRESS_CPU = 0x9FA0
TEXT = 0x06490                       # bank 1 $A480, in the free block before CommonCodeBlock_Bank1
TEXT_CPU = 0xA480
TEXT_SIZE = 48                       # the longest text, "BRING 8 TRIFORCES AND|YOU CAN HAVE THIS.", takes 39
JSR, NOP = 0x20, 0xEA
WOOD_SWORD_CAVE_PERSON = 0x6A        # object type of cave index 0, the wooden-sword cave (destination $10)
WOOD_SWORD = 0x01


def _call(address: int) -> bytes:
    return bytes([JSR, address & 0xFF, address >> 8, NOP, NOP])


def take_check(pieces: int) -> bytes:
    """The take's routine: Z set (A zero) to take the ware, else PRG0's CaveFlags AND #$40; with the
    wooden-sword cave's sword and fewer than `pieces` pieces held, it returns from the cave routine."""
    return bytes([
        0xAD, 0x50, 0x03,            # LDA ObjType+1     the cave's person
        0xC9, WOOD_SWORD_CAVE_PERSON,    # CMP #$6A
        0xD0, 0x24,                  # BNE @PRG0
        0xBD, 0x22, 0x04,            # LDA CaveItemIds,X  the ware touched
        0x29, 0x3F,                  # AND #$3F
        0xC9, WOOD_SWORD,            # CMP #$01
        0xD0, 0x1B,                  # BNE @PRG0
        0x98,                        # TYA               keep Y
        0x48,                        # PHA
        0xA0, 0x00,                  # LDY #0            the pieces counted
        0xAD, 0x71, 0x06,            # LDA InvTriforce
        0x0A,                        # @Next: ASL A      the next piece into carry
        0x90, 0x01,                  # BCC @Counted
        0xC8,                        # INY
        0x09, 0x00,                  # @Counted: ORA #0  any pieces left?
        0xD0, 0xF8,                  # BNE @Next
        0xC0, pieces,                # CPY #pieces       carry set: that many or more
        0x68,                        # PLA               Y back (PLA and TAY keep the carry)
        0xA8,                        # TAY
        0xB0, 0x03,                  # BCS @Take
        0x68,                        # PLA               too few: drop this call's return address
        0x68,                        # PLA
        0x60,                        # RTS               and leave the cave routine, as a heart check does
        0xA9, 0x00,                  # @Take: LDA #0     Z set: BEQ @Take takes the sword
        0x60,                        # RTS
        0xAD, 0x13, 0x04,            # @PRG0: LDA CaveFlags
        0x29, 0x40,                  # AND #$40          PRG0's heart-requirement flag
        0x60,                        # RTS
    ])


def text_address() -> bytes:
    """The text's routine: PRG0's STA $01, then in the wooden-sword cave [00:01] at the Swordlish text;
    PRG0's LDY PersonTextIndex last."""
    return bytes([
        0x85, 0x01,                  # STA $01           the address PRG0 loaded
        0xAD, 0x50, 0x03,            # LDA ObjType+1
        0xC9, WOOD_SWORD_CAVE_PERSON,    # CMP #$6A
        0xD0, 0x0C,                  # BNE @Done
        0xA5, 0x10,                  # LDA CurLevel      the overworld's caves only
        0xD0, 0x08,                  # BNE @Done
        0xA9, TEXT_CPU & 0xFF,       # LDA #<text
        0x85, 0x00,                  # STA $00
        0xA9, TEXT_CPU >> 8,         # LDA #>text
        0x85, 0x01,                  # STA $01
        0xAC, 0x16, 0x04,            # @Done: LDY PersonTextIndex
        0x60,                        # RTS
    ])


PIECES_OPERAND = TAKE_CHECK + take_check(0).index(0xC0) + 1


def swordlish_text(pieces: int) -> str:
    """FP-SWL-05: BogieSmalls' own wording (used with his permission), naming N; TRIFORCE for one."""
    noun = "TRIFORCE" if pieces == 1 else "TRIFORCES"
    return f"BRING {pieces} {noun} AND\nYOU CAN HAVE THIS."


def encoded_text(pieces: int) -> bytes:
    text = encoded_refusal_text(swordlish_text(pieces))
    assert len(text) <= TEXT_SIZE, len(text)
    return text


def swordlish_writes(pieces: int) -> list[tuple[int, bytes]]:
    """The bytes Swordlish writes, as (file offset, bytes); none with `pieces` 0 (PRG0's cave)."""
    if not pieces:
        return []
    return [(TAKE_HOOK, _call(TAKE_CHECK_CPU)), (TAKE_CHECK, take_check(pieces)),
            (TEXT_HOOK, _call(TEXT_ADDRESS_CPU)), (TEXT_ADDRESS, text_address()), (TEXT, encoded_text(pieces))]


def parsed_pieces(rom: bytes | bytearray) -> int:
    """The pieces a ROM's wooden-sword cave asks for, as this module writes them (PRG0's layout); 0 for
    anything else, so serializing the parsed world leaves it as it was."""
    if rom[TAKE_HOOK:TAKE_HOOK + len(TAKE_HOOK_PRG0)] != _call(TAKE_CHECK_CPU):
        return 0
    pieces = rom[PIECES_OPERAND]
    return pieces if swordlish_writes(pieces) and all(
        rom[offset:offset + len(data)] == data for offset, data in swordlish_writes(pieces)) else 0
