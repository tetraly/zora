"""The life-or-money toll (PS-MERCH-04) and the bomb-upgrade person levels
(PS-BOMB-03): the fixed-offset PRG0 code and text bytes those entries
change, decoded into GameWorld fields and encoded back. Data layer: this module is
the only place these byte patterns live. Headered file offsets; aldonunez
labels where the pinned disassembly has one.
"""
from ..model.enums import TollOption, UnderworldPersonInit
from ..model.rooms import LifeOrMoneyToll
from .layout import (
    LIFE_OR_MONEY_COST_TEXT_ADDRESS,
    LIFE_OR_MONEY_ITEM_TYPES_ADDRESS,
    LIFE_OR_MONEY_PAYMENT_ADDRESS,
    PERSON_INIT_JUMP_TABLE_ADDRESS,
    PERSON_UPDATE_BRANCH_ADDRESS,
    TOLL_TEXT_ADDRESS,
    TOLL_TEXT_POINTER,
    TOLL_TEXT_POINTER_ADDRESS,
)
from .text_encoding import CHAR_TO_BYTE, QUOTE_END_BITS, QUOTE_LINE1_BIT

# --- UpdateUnderworldPerson_Full (PS-BOMB-03) --------------------------------
BOMB_BRANCH_NOPS = bytes([0xEA, 0xEA])        # replaces the vanilla BCC $90 $08
FIRST_BOMB_LEVEL_OPERAND = 0x04AF0            # CMP operand, vanilla level 5
SECOND_BOMB_LEVEL_OPERAND = 0x04AF4           # CMP operand, vanilla level 7

# --- the payment routine (UpdateUnderworldPersonLifeOrMoneyState_2) ---------
MONEY_CHECK = LIFE_OR_MONEY_PAYMENT_ADDRESS   # 0x04C1C: vanilla LDA #$32 ...
MONEY_PRICE_OPERAND = 0x04C1D                 # vanilla $32 = 50 rupees
HEART_PAYMENT = 0x04C2F                       # the heart-container payment
HEART_COUNT_OPERAND = 0x04C35                 # vanilla $30
# pay with a max-bombs container instead (14 bytes)
MAX_BOMBS_PAYMENT = bytes([0xCE, 0x7C, 0x06, 0xAD, 0x58, 0x06, 0xF0, 0x03,
                           0xCE, 0x58, 0x06, 0x4C, 0x4D, 0x8C])
KEY_COST_OFFSET = 10                          # the key count inside KEYS_PAYMENT


def keys_payment(key_cost: int) -> bytes:
    """Pay key_cost keys unless the magic key is held (19 bytes)."""
    return bytes([0xAD, 0x64, 0x06, 0xD0, 0x0B, 0xAD, 0x6E, 0x06, 0x38, 0xE9,
                  key_cost, 0x90, 0xEE, 0x8D, 0x6E, 0x06, 0x4C, 0x4D, 0x8C])


KEYS_PAYMENT_HEAD = keys_payment(0)[:3]

# --- LifeOrMoneyItemTypes / LifeOrMoneyCostTextTransferBuf ------------------
FIRST_ITEM_TYPE = LIFE_OR_MONEY_ITEM_TYPES_ADDRESS        # vanilla $1A heart container
SECOND_ITEM_TYPE = LIFE_OR_MONEY_ITEM_TYPES_ADDRESS + 1
NO_ITEM_TYPE = 0x00
KEY_ITEM_TYPE = 0x19
COST_TEXT_ICON = LIFE_OR_MONEY_COST_TEXT_ADDRESS + 10     # "x" icon + two digits
COST_TEXT_TENS = LIFE_OR_MONEY_COST_TEXT_ADDRESS + 11
ICON_TILES = (0x24, 0x62)                                 # blank, "x"

TOLL_LINE_WIDTH = 24
# Lines are centred with the blank pad tile $25, not the space $24 that
# separates words (final corpus: 1,000/1,000 toll texts; the spec's
# "spaces" is this tile — QUESTIONS #50.1).
TEXT_PAD_TILE = CHAR_TO_BYTE["~"]
MAX_STARTING_HEARTS = 32       # a starting-hearts byte above this reads as 34
STARTING_HEARTS_CAP = 34


PERSON_INIT_LEVELS = range(1, 9)            # jump-table entries 1-8
JUMP_TABLE_ENTRY_SIZE = 2                   # .ADDR: low byte, then high


def person_inits(jump_table: bytes) -> tuple[UnderworldPersonInit, ...]:
    """Levels 1-8's person init routines, from the jump table's low bytes."""
    return tuple(UnderworldPersonInit(jump_table[JUMP_TABLE_ENTRY_SIZE * level])
                 for level in PERSON_INIT_LEVELS)


def person_init_writes(inits: tuple[UnderworldPersonInit, ...]) -> list[tuple[int, bytes]]:
    """PS-HINT-06: the eight low bytes (the high bytes stay $8A)."""
    return [(PERSON_INIT_JUMP_TABLE_ADDRESS + JUMP_TABLE_ENTRY_SIZE * level, bytes([init]))
            for level, init in zip(PERSON_INIT_LEVELS, inits, strict=True)]


def bomb_upgrade_levels(branch: bytes) -> tuple[int, int] | None:
    """The two levels whose persons take the bomb-upgrade path, or None for
    the vanilla code (branch = the 8 bytes at PERSON_UPDATE_BRANCH_ADDRESS)."""
    if branch[:2] != BOMB_BRANCH_NOPS:
        return None
    return (branch[FIRST_BOMB_LEVEL_OPERAND - PERSON_UPDATE_BRANCH_ADDRESS],
            branch[SECOND_BOMB_LEVEL_OPERAND - PERSON_UPDATE_BRANCH_ADDRESS])


def life_or_money_toll(payment: bytes, text_pointer: bytes) -> LifeOrMoneyToll | None:
    """Decode the toll from the payment routine's bytes; None when person
    text slot 27 does not point at the toll text (the vanilla merchant)."""
    if text_pointer != TOLL_TEXT_POINTER:
        return None
    heart_payment = payment[HEART_PAYMENT - MONEY_CHECK:][:len(MAX_BOMBS_PAYMENT)]
    first = TollOption.MAX_BOMBS if heart_payment == MAX_BOMBS_PAYMENT else TollOption.LIFE
    if payment[:len(KEYS_PAYMENT_HEAD)] == KEYS_PAYMENT_HEAD:
        return LifeOrMoneyToll(first, TollOption.KEYS, key_cost=payment[KEY_COST_OFFSET])
    if payment[:len(MAX_BOMBS_PAYMENT)] == MAX_BOMBS_PAYMENT:
        return LifeOrMoneyToll(first, TollOption.MAX_BOMBS)
    return LifeOrMoneyToll(first, TollOption.MONEY,
                           money_cost=payment[MONEY_PRICE_OPERAND - MONEY_CHECK])


def toll_text(toll: LifeOrMoneyToll) -> bytes:
    """"LEAVE YOUR X" / "OR Y", each line led by (24 - length) div 2 pad
    tiles, in the person-text encoding (line-end flags on each line's last
    byte)."""
    def line(text: str) -> list[int]:
        pad = [TEXT_PAD_TILE] * ((TOLL_LINE_WIDTH - len(text)) // 2)
        return pad + [CHAR_TO_BYTE[ch] for ch in text]
    first = line("LEAVE YOUR " + toll.first.value)
    second = line("OR " + toll.second.value)
    first[-1] |= QUOTE_LINE1_BIT
    second[-1] |= QUOTE_END_BITS
    return bytes(first + second)


def heart_count_operand(starting_hearts: int) -> int:
    """The life toll's heart-container count operand, from the
    starting-hearts byte."""
    hearts = STARTING_HEARTS_CAP if starting_hearts > MAX_STARTING_HEARTS else starting_hearts
    return (hearts & 0xF0) + 0x10


def encode(toll: LifeOrMoneyToll | None, bomb_levels: tuple[int, int] | None,
           starting_hearts: int) -> list[tuple[int, bytes]]:
    """PS-MERCH-04's and PS-BOMB-03's writes as (file offset, bytes); every
    other byte is left as the base ROM has it. PS-BOMB-03's jump-table
    writes are omitted (MAY: the hint pass rewrites them, person_init_writes)."""
    writes: list[tuple[int, bytes]] = []
    if bomb_levels is not None:
        writes += [(PERSON_UPDATE_BRANCH_ADDRESS, BOMB_BRANCH_NOPS),
                   (FIRST_BOMB_LEVEL_OPERAND, bytes([bomb_levels[0]])),
                   (SECOND_BOMB_LEVEL_OPERAND, bytes([bomb_levels[1]]))]
    if toll is None:
        return writes
    writes.append((TOLL_TEXT_ADDRESS, toll_text(toll)))
    if toll.first == TollOption.LIFE:
        writes.append((HEART_COUNT_OPERAND, bytes([heart_count_operand(starting_hearts)])))
    else:
        writes += [(HEART_PAYMENT, MAX_BOMBS_PAYMENT), (FIRST_ITEM_TYPE, bytes([NO_ITEM_TYPE]))]
    if toll.second == TollOption.MAX_BOMBS:
        writes += [(MONEY_CHECK, MAX_BOMBS_PAYMENT),
                   (COST_TEXT_ICON, bytes([*ICON_TILES, 1])),
                   (SECOND_ITEM_TYPE, bytes([NO_ITEM_TYPE]))]
    elif toll.second == TollOption.KEYS:
        assert toll.key_cost is not None
        writes += [(MONEY_CHECK, keys_payment(toll.key_cost)),
                   (COST_TEXT_ICON, bytes([*ICON_TILES, toll.key_cost])),
                   (SECOND_ITEM_TYPE, bytes([KEY_ITEM_TYPE]))]
    else:
        assert toll.money_cost is not None
        writes += [(MONEY_PRICE_OPERAND, bytes([toll.money_cost])),
                   (COST_TEXT_TENS, bytes(divmod(toll.money_cost, 10)))]
    return writes


def life_toll_heart_count_operand(rom: bytes) -> int:
    """The life toll's heart-container count operand as a finished ROM holds it (PS-MERCH-04)."""
    return rom[HEART_COUNT_OPERAND]


def text_pointer_write(toll: LifeOrMoneyToll | None) -> list[tuple[int, bytes]]:
    """Person text slot 27 -> the toll text. It lies inside the quotes block,
    so it is written after the quotes."""
    return [] if toll is None else [(TOLL_TEXT_POINTER_ADDRESS, TOLL_TEXT_POINTER)]
