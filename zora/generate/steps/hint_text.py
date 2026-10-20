"""Consternation hint-text generation (hints-behavior.md @ 6c6506b).

This pass runs after the late gate and the map move (HT-TEXT-04: after the
item and map passes).  It composes 45 person-text slots, shuffles the dungeon
hint pointers, writes the selector tables, and records everything the
serializer needs for HintMode.CONSTERNATION.
"""
import copy
import re
import textwrap
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import TypeVar

from ...model.enums import Destination, Enemy, Item, RoomAction
from ...model.game_world import GameWorld
from ...model.levels import Level
from ...model.overworld import HintShop, ItemCave, Quote, Screen
from ...model.rooms import DARK_BIT, Room
from ...rom.layout import CONSTERNATION_HINT_SLOTS, TOLL_TEXT_POINTER, cpu_address_in_bank1, place_hint_texts
from ...rom.text_encoding import CHAR_TO_BYTE, QUOTE_BLANK, QUOTE_END_BITS, QUOTE_LINE1_BIT, QUOTE_LINE2_BIT
from ..dungeon_walk import item_cellar, item_room, walk_level
from ..rng import IntRng, Rng
from .assign_hints_for_hint_type import HintAssignmentResult
from .cave_entries import recorder_screens
from .change_sword_hearts import MAGICAL_SWORD_HEARTS, WHITE_SWORD_HEARTS
from .item_shuffle_result import ItemShuffleResult, TrackedPlace
from .mixed_overworld_quest import door_screen
from .overworld_gates import NO_GATES, OverworldGates
from .person_appearances import person_appearance
from .randomize_mazes import MAZE_HINT_PRICE

LINE_WIDTH = 24
T = TypeVar("T")
PAD_TILE = CHAR_TO_BYTE["~"]

SLOT_COUNT = 45
TOLL_SLOT = 27
REFUSAL_SLOT = 34          # FP-TRIF-01's level-9 refusal text replaces its pointer
UNSHOWN_SLOTS = frozenset({TOLL_SLOT, REFUSAL_SLOT})



# -----------------------------------------------------------------------------
# Text encoding (HT-TEXT-01)
# -----------------------------------------------------------------------------

# HT-TEXT-01: the characters that emit a tile (letters fold to upper case);
# any other character emits none.
# Owner ruling (2026-10-02): a deliberate departure from HT-TEXT-01, for
# ZORA-authored wording only. The comma ($28) and the double quote mark
# ($2D) emit their tiles too: PRG0's font has both (vanilla's own person
# text uses $28), and the owner confirmed from play that they display
# correctly. The colon stays unsupported: the font has no tile for it.
SHOWN_CHARACTERS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .!'?-" + ',"')


def _encode_line(line: str) -> list[int]:
    cleaned = "".join(
        character.upper() if character.isalpha() else character
        for character in line
        if character.upper() in SHOWN_CHARACTERS
    )
    padding = max(0, (LINE_WIDTH - len(cleaned)) // 2)
    return [PAD_TILE] * padding + [CHAR_TO_BYTE[character] for character in cleaned]


def encode_text(lines: list[str]) -> list[int]:
    """Encode up to three lines with the spec's line-break and end flags."""
    non_empty = [line for line in lines if line]
    if not non_empty:
        return [QUOTE_BLANK]
    encoded: list[int] = []
    for position, line in enumerate(non_empty):
        encoded.extend(_encode_line(line))
        if position < len(non_empty) - 1:
            encoded[-1] |= (QUOTE_LINE1_BIT if position == 0 else QUOTE_LINE2_BIT)
    if encoded:
        encoded[-1] |= QUOTE_END_BITS
    return encoded


# -----------------------------------------------------------------------------
# The random pool (HT-TEXT-02)
# -----------------------------------------------------------------------------

# The routing classes (HT-TEXT-02's routes) and the slots each can reach.
# HT-TEXT-02 routes every pool string either by the base draw (uniform on
# 1..44: "unrouted", and the 51 strings that keep the base draw) or to a
# fixed slot, a pair or a range. Two owner-ruling classes come on top
# (docs/ui-provenance.md): slot 0's own quotes, which replace the greeting,
# and three quotes added to slot 9's general draw.
UNROUTED = "unrouted"
# Slot 0's two classes: the wood sword cave's own quotes (owner ruling), and with Book to
# Understand NPCs (B48, HT-BOOK-02) the lines in which the speaker cannot be understood, which
# take slot 0 in their place and are drawn nowhere without B48
WOOD_SWORD_SLOT_0_CLASS = "slot 0 (owner ruling)"
BOOK_SLOT_0_CLASS = "slot 0 with the Book"
POOL_CLASSES: dict[str, tuple[int, ...]] = {
    UNROUTED: tuple(range(1, 45)),
    WOOD_SWORD_SLOT_0_CLASS: (0,),
    BOOK_SLOT_0_CLASS: (0,),
    "slot 9 (owner ruling)": (9,),
    **{f"slot {slot}": (slot,) for slot in (2, 4, 5, 6, 8, 16, 17, 18, 19, 20, 21, 24, 25, 27, 34)},
    "slot 1 or 19": (1, 19),
    "slot 14 or 15": (14, 15),
    "slots 10-13": tuple(range(10, 14)),
    "slots 20-31": tuple(range(20, 32)),
    "slots 34-37": tuple(range(34, 38)),
    "slot 8, 16 or 14/15": (8, 16, 14, 15),
}

# The sword caves' person texts, and the heart counts FP-SWORD-01 can ask
# for there: a heart-count quote is shown only in its cave's slot, and only
# when the cave asks for the count it names.
WHITE_SWORD_TEXT_SLOT = 19
MAGICAL_SWORD_TEXT_SLOT = 1
HEART_CAVES = {"white sword": (WHITE_SWORD_TEXT_SLOT, WHITE_SWORD_HEARTS),
               "magical sword": (MAGICAL_SWORD_TEXT_SLOT, MAGICAL_SWORD_HEARTS)}
HEARTS_NOTE = re.compile(r"(white sword|magical sword) (\d+) hearts")
RESERVED_NOTE = "reserved"
PLACEHOLDER_NOTE = "placeholder"
PLACEHOLDER_TEXT = "INSERT COMMUNITY HINT"
# Wording written by Claude until the owner's replaces it (owner ruling, 2026-10-12)
STAND_IN_NOTE = "stand-in"

POOL_FILE = "hint_pool.txt"
POOL_COMMENT = "#"
POOL_COLUMNS = "\t"
POOL_LINE_BREAK = "|"
MAX_LINES = 3


def quote_problems(lines: list[str]) -> list[str]:
    """Why a quote cannot be shown as written (HT-TEXT-01, HT-TEXT-02): none when it can."""
    problems = []
    if len(lines) > MAX_LINES:
        problems.append(f"{len(lines)} lines (at most {MAX_LINES})")
    for line in lines:
        if len(line) > LINE_WIDTH:
            problems.append(f"line {line!r} is {len(line)} characters (at most {LINE_WIDTH})")
        unshown = sorted({ch for ch in line if ch.upper() not in SHOWN_CHARACTERS})
        if unshown:
            problems.append(f"no tile for {''.join(unshown)!r}")
    return problems


@dataclass(frozen=True)
class PoolEntry:
    """One quote of zora/generate/steps/hint_pool.txt and where it may be shown."""
    routing_class: str
    lines: tuple[str, ...]
    # (cave text slot, hearts) for a heart-count quote
    hearts: tuple[int, int] | None = None
    reserved: bool = False
    placeholder: bool = False
    stand_in: bool = False

    def slots(self, white_hearts: int, magical_hearts: int, book_needed: bool = False) -> tuple[int, ...]:
        """The slots this quote may be shown in, in a seed whose sword caves
        ask for these heart counts. Reserved quotes and slots 27 and 34 are
        never drawn: their final pointers are replaced (HT-TEXT-02). book_needed: Book to
        Understand NPCs (B48), whose lines take slot 0 from the wood sword cave's quotes
        (HT-BOOK-02)."""
        if self.reserved or self.routing_class == (WOOD_SWORD_SLOT_0_CLASS if book_needed else BOOK_SLOT_0_CLASS):
            return ()
        if self.hearts is not None:
            slot, count = self.hearts
            asked = white_hearts if slot == WHITE_SWORD_TEXT_SLOT else magical_hearts
            return (slot,) if count == asked else ()
        return shown_class_slots(self.routing_class)


def shown_class_slots(routing_class: str) -> tuple[int, ...]:
    """The slots a class's quotes can be shown in (its route, less 27 and 34)."""
    return tuple(slot for slot in POOL_CLASSES[routing_class] if slot not in UNSHOWN_SLOTS)


def _pool_entry(row: str) -> PoolEntry:
    routing_class, quote, note = [*row.split(POOL_COLUMNS), ""][:3]
    if routing_class not in POOL_CLASSES:
        raise ValueError(f"{POOL_FILE}: {row!r}: unknown routing class {routing_class!r}")
    lines = quote.split(POOL_LINE_BREAK)
    problems = quote_problems(lines)
    if problems:
        raise ValueError(f"{POOL_FILE}: {quote!r} cannot be shown as written: {'; '.join(problems)}")
    hearts = None
    if (match := HEARTS_NOTE.fullmatch(note)) is not None:
        slot, counts = HEART_CAVES[match.group(1)]
        if int(match.group(2)) not in counts or slot not in POOL_CLASSES[routing_class]:
            raise ValueError(f"{POOL_FILE}: {row!r}: no such heart requirement in this class")
        hearts = (slot, int(match.group(2)))
    elif note not in ("", RESERVED_NOTE, PLACEHOLDER_NOTE, STAND_IN_NOTE):
        raise ValueError(f"{POOL_FILE}: {row!r}: unknown note {note!r}")
    reserved = note == RESERVED_NOTE
    if reserved != (not shown_class_slots(routing_class)):
        raise ValueError(f"{POOL_FILE}: {row!r}: only the classes of slots 27 and 34 are reserved")
    return PoolEntry(routing_class, tuple(lines), hearts, reserved, note == PLACEHOLDER_NOTE, note == STAND_IN_NOTE)


def load_pool() -> tuple[PoolEntry, ...]:
    """The quotes of zora/generate/steps/hint_pool.txt in file order; refuses one it cannot
    show, an unknown class or note, and a repeated quote."""
    from importlib.resources import files
    # This package by its own name, which is not "zora.generate.steps" when zora/ is copied in
    # under another one (Archipelago, perhaps from a zip).
    rows = files(__package__).joinpath(POOL_FILE).read_text(encoding="utf-8").splitlines()
    entries = tuple(_pool_entry(row) for row in rows if row and not row.startswith(POOL_COMMENT))
    repeated = [lines for lines, count in Counter(entry.lines for entry in entries).items() if count > 1]
    if repeated:
        raise ValueError(f"{POOL_FILE}: quotes listed twice: {repeated}")
    if not entries:
        raise ValueError(f"{POOL_FILE} holds no quotes")
    return entries


POOL = load_pool()


# -----------------------------------------------------------------------------
# Region table (HT-APP-A1)
# -----------------------------------------------------------------------------

REGION_TABLE: tuple[int, ...] = (
    1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 5, 9, 9, 9, 7, 7,
    1, 1, 1, 1, 1, 1, 1, 6, 6, 6, 6, 9, 9, 9, 7, 7,
    2, 2, 2, 2, 2, 2, 5, 6, 10, 10, 10, 10, 10, 7, 7, 7,
    2, 2, 2, 2, 5, 5, 5, 5, 5, 5, 10, 10, 8, 8, 7, 7,
    2, 2, 5, 5, 5, 5, 5, 5, 5, 10, 10, 10, 8, 8, 8, 7,
    2, 3, 3, 3, 5, 5, 5, 4, 4, 5, 5, 8, 8, 8, 8, 7,
    2, 3, 3, 3, 3, 6, 4, 4, 4, 5, 5, 8, 8, 8, 8, 7,
    3, 3, 3, 3, 3, 6, 4, 4, 4, 4, 4, 7, 7, 7, 7, 7,
)


def region_of_screen(screen: int) -> int:
    return REGION_TABLE[screen]


# -----------------------------------------------------------------------------
# Item / boss / person / family names (HT-HINT-01)
# -----------------------------------------------------------------------------

# HT-HINT-01's item-name table: one name per game item code $00-$23 (36).
ITEM_NAMES: tuple[str, ...] = (
    "BOMBS", "WOOD SWORD", "WHITE SWORD", "MAGICAL SWORD", "BAIT",
    "RECORDER", "BLUE CANDLE", "RED CANDLE", "WOOD ARROWS", "SILVER ARROWS",
    "BOW", "MAGICAL KEY", "RAFT", "LADDER", "TRIFORCE OF POWER",
    "FIVE RUPEES", "WAND", "BOOK", "BLUE RING", "RED RING",
    "POWER BRACELET", "LETTER", "COMPASS", "MAP",
    "RUPEE", "KEY", "HEART CONTAINER", "TRIFORCE PIECE",
    "MAGICAL SHIELD", "WOOD BOOMERANG", "MAGICAL BOOMERANG", "BLUE POTION",
    "RED POTION", "CLOCK", "HEART", "FAIRY",
)
assert len(ITEM_NAMES) == 36


def item_name(code: int) -> str:
    return ITEM_NAMES[code]


# PI-TEXT-01 (docs/design/progressive-items-plan.md section 7): with Progressive Items on, hint
# text names an upgrade-line item by its line.
UPGRADE_LINES: dict[int, str] = {
    **dict.fromkeys((Item.WOOD_SWORD, Item.WHITE_SWORD, Item.MAGICAL_SWORD), "SWORD"),
    **dict.fromkeys((Item.BLUE_CANDLE, Item.RED_CANDLE), "CANDLE"),
    **dict.fromkeys((Item.WOOD_ARROWS, Item.SILVER_ARROWS), "ARROW"),
    **dict.fromkeys((Item.BLUE_RING, Item.RED_RING), "RING"),
    **dict.fromkeys((Item.WOOD_BOOMERANG, Item.MAGICAL_BOOMERANG), "BOOMERANG"),
}
ARROW_LINE = frozenset(item for item, line in UPGRADE_LINES.items() if line == "ARROW")

# Pegasus Boots (owner spec, 2026-10-17; names, owner decision 2026-10-18): the boomerangs' items are
# the boots, each with its own verb (plural), and their upgrade line is the boots'.
BOOTS_NAMES: dict[int, str] = {Item.WOOD_BOOMERANG: "PEGASUS BOOTS", Item.MAGICAL_BOOMERANG: "MAGICAL BOOTS"}
BOOTS_VERBS: dict[int, str] = {Item.WOOD_BOOMERANG: "WAIT", Item.MAGICAL_BOOMERANG: "RACE"}
BOOMERANG_LINE, BOOTS_LINE = "BOOMERANG", "BOOTS"


# Archipelago (docs/archipelago.md, owner decisions 2026-10-08): how hint text names a place
# holding another player's item, never by the code the ROM shows there. The apostrophe is the
# font's $2A tile, as in vanilla's "IT'S DANGEROUS TO GO ALONE!".
FOREIGN_NAME = "ANOTHER PLAYER'S ITEM"


def wrapped(line: str) -> list[str]:
    """A text wrapped at the line width, in at most three lines."""
    lines = textwrap.wrap(line, LINE_WIDTH)
    assert len(lines) <= MAX_LINES, line
    return lines


@dataclass(frozen=True)
class ItemNames:
    """How hint text names an item: by its own name (HT-HINT-01), or with Progressive Items on
    an upgrade-line item by its line (PI-TEXT-01). The vanilla names give today's texts.
    foreign_code (Archipelago's FINISH only; None in ZORA): the code another player's item is
    written as; a place holding it is named FOREIGN_NAME, as noun and phrase alike."""
    progressive_items: bool = False
    foreign_code: int | None = None
    # Swords (C07) at Wood Sword Only or Swordless (FP-WOOD-02): item $02 is a bomb upgrade
    bomb_upgrade: bool = False
    # Pegasus Boots: the boomerangs' items are the boots (BOOTS_NAMES)
    pegasus_boots: bool = False

    def is_foreign(self, code: int) -> bool:
        return self.foreign_code is not None and code == self.foreign_code

    def is_boots(self, code: int) -> bool:
        return self.pegasus_boots and code in BOOTS_NAMES

    def name(self, code: int) -> str:
        """The item's own name (HT-HINT-01's, or the boots')."""
        return BOOTS_NAMES[code] if self.is_boots(code) else item_name(code)

    def _is_bomb_upgrade(self, code: int) -> bool:
        return self.bomb_upgrade and code == Item.WHITE_SWORD

    def _line(self, code: int) -> str | None:
        line = UPGRADE_LINES.get(code) if self.progressive_items else None
        return BOOTS_LINE if line == BOOMERANG_LINE and self.pegasus_boots else line

    def label(self, code: int) -> str:
        """The item as a noun: SILVER ARROWS, or ARROW UPGRADE."""
        if self.is_foreign(code):
            return FOREIGN_NAME
        if self._is_bomb_upgrade(code):
            return BOMB_UPGRADE_NAME
        line = self._line(code)
        return self.name(code) if line is None else f"{line} UPGRADE"

    def phrase(self, code: int) -> str:
        """The item with its article: THE SILVER ARROWS, or AN ARROW UPGRADE."""
        if self.is_foreign(code):
            return FOREIGN_NAME
        if self._is_bomb_upgrade(code):
            return f"A {BOMB_UPGRADE_NAME}"
        line = self._line(code)
        if line is None:
            return f"THE {self.name(code)}"
        return f"{'AN' if line[0] in 'AEIOU' else 'A'} {line} UPGRADE"

    def fit(self, line: str, first: str, second: str) -> list[str]:
        """A text on one line, else on two (_fit). The progressive wording is wrapped at the
        line width instead, in at most three lines; so is a two-line split that would not fit,
        which only another player's item (foreign_code) makes."""
        if self.progressive_items:
            return wrapped(line)
        if self.foreign_code is not None and max(len(first), len(second)) > LINE_WIDTH:
            return wrapped(line)
        return _fit(line, first, second)


# FP-WOOD-02: item $02's name under Wood Sword Only and Swordless (the spec leaves the wording open)
BOMB_UPGRADE_NAME = "BOMB UPGRADE"
VANILLA_NAMES = ItemNames()
PROGRESSIVE_NAMES = ItemNames(progressive_items=True)


# -----------------------------------------------------------------------------
# ZORA's hint wording (owner, 2026-10-09): the item-location and level-location hints. Which
# hints appear and what they point to are HT-HINT-01's; only the words are ZORA's own (the spec
# gives no reference text; HT-APP-A1 numbers the regions).
# -----------------------------------------------------------------------------

# An item-location hint: "THE <ITEM> <VERB> IN LEVEL-N.", by ZORA's item names (ITEM_NAMES), one
# fixed verb per item, agreeing with the name in number (owner, 2026-10-09).
ITEM_VERBS: dict[int, str] = {
    Item.RAFT: "RESTS", Item.LADDER: "LIES", Item.BOW: "BIDES", Item.SILVER_ARROWS: "POINT",
    Item.WOOD_ARROWS: "AWAIT", Item.RECORDER: "RESOUNDS", Item.WAND: "WAITS", Item.BOOK: "IS BOUND",
    Item.BLUE_CANDLE: "FLICKERS", Item.RED_CANDLE: "SMOULDERS", Item.MAGICAL_KEY: "IS KEPT",
    Item.POWER_BRACELET: "PERSISTS", Item.WOOD_BOOMERANG: "BECKONS", Item.MAGICAL_BOOMERANG: "WHIRLS",
    Item.LETTER: "LINGERS", Item.WHITE_SWORD: "SHINES", Item.MAGICAL_SWORD: "SLUMBERS", Item.BLUE_RING: "BIDES",
    Item.RED_RING: "RADIATES", Item.HEART_CONTAINER: "HIDES", Item.BAIT: "BECKONS",
}
# With Progressive Items on, an upgrade-line item is named by its line (PI-TEXT-01), with its
# article: "A SWORD UPGRADE SLUMBERS".
LINE_VERBS: dict[str, str] = {"SWORD": "SLUMBERS", "ARROW": "AWAITS", "CANDLE": "FLICKERS", "RING": "RADIATES",
                              "BOOMERANG": "BECKONS", BOOTS_LINE: "AWAITS"}
FOREIGN_VERB = "AWAITS"                  # ANOTHER PLAYER'S ITEM AWAITS (no "THE")
FALLBACK_VERB = "WAITS"                  # an item the owner's list does not name

# A level-location hint: "LEVEL-N LIES <PHRASE>." by the region of the level's door screen.
REGION_PHRASES: dict[int, str] = {
    1: "HIGH IN DEATH MOUNTAIN", 2: "BY THE GRAVEYARD", 3: "IN THE DEAD WOODS", 4: "NEAR START",
    5: "AROUND A LAKE", 6: "ALONG A RIVER", 7: "BY THE COAST", 8: "HIDDEN IN A FOREST",
    9: "UP IN THE LOST HILLS", 10: "IN THE DRY DESERT",
}

# The openers a reworded hint may start with, when it still fits the box with one more line. The
# owner's ten, with "THAT" where it joins naturally. The font has no colon, so the two colon
# forms end with a comma, and "TRAVELERS SPEAK OF" (which cannot take a full sentence) says
# "TRAVELERS SAY THAT".
OPENERS = (
    "IT IS SAID THAT", "LEGEND TELLS THAT", "AN OLD TALE SAYS THAT", "I HAVE HEARD THAT",
    "AN ELDER ONCE SAID THAT", "MARK MY WORDS,", "HEED THIS, YOUNG ONE,", "THE WIND WHISPERS THAT",
    "THE STONES REMEMBER THAT", "TRAVELERS SAY THAT",
)


def item_location_sentence(code: int, level: int, names: ItemNames = VANILLA_NAMES) -> str:
    """An item-location hint: the item, its verb, and its level (the player level, SH-NUM-03)."""
    if names.is_foreign(code):
        return f"{FOREIGN_NAME} {FOREIGN_VERB} IN LEVEL-{level}."
    line = names._line(code)
    if line is not None:
        return f"{names.phrase(code)} {LINE_VERBS.get(line, FALLBACK_VERB)} IN LEVEL-{level}."
    if names.is_boots(code):
        return f"THE {names.name(code)} {BOOTS_VERBS[code]} IN LEVEL-{level}."
    if code in ITEM_VERBS:
        return f"THE {item_name(code)} {ITEM_VERBS[code]} IN LEVEL-{level}."
    return f"{names.phrase(code)} {FALLBACK_VERB} IN LEVEL-{level}."


def level_location_sentence(level: int, region: int) -> str:
    """A level-location hint: the level (the player level, SH-NUM-03) and the region of its door
    screen."""
    return f"LEVEL-{level} LIES {REGION_PHRASES[region]}."


def region_phrase(region: int) -> str:
    """A people hint's place: its region's phrase (region 0, no such screen, as before)."""
    return REGION_PHRASES.get(region, f"IN REGION {region}")


def hint_lines(sentence: str) -> list[str]:
    """A sentence broken at word boundaries within the box's width, in at most three lines (a
    hyphen never breaks a line: "LEVEL-3" stays whole)."""
    lines = textwrap.wrap(sentence, LINE_WIDTH, break_on_hyphens=False)
    assert len(lines) <= MAX_LINES, sentence
    return lines


def with_opener(opener: str, sentence: str) -> list[str] | None:
    """The sentence with an opener before it, when the sentence alone leaves the box one more
    line and both together still fit; else None."""
    if len(hint_lines(sentence)) >= MAX_LINES:
        return None
    lines = textwrap.wrap(f"{opener} {sentence}", LINE_WIDTH, break_on_hyphens=False)
    return lines if len(lines) <= MAX_LINES else None


def add_openers(final_texts: list[list[str]], overlay_flags: list[bool], sentences: list[str | None],
                rng: Rng) -> None:
    """Openers for the reworded hints that are shown, in slot order: the openers in an order drawn
    from `rng` (a copy of the hint step's stream, so no other draw moves), each used at most once;
    a hint that cannot take one leaves it for the next, and hints past the tenth go without."""
    openers = list(OPENERS)
    for position in range(len(openers)):
        other = position + rng.below(len(openers) - position)
        openers[position], openers[other] = openers[other], openers[position]
    for slot, sentence in enumerate(sentences):
        if not openers:
            return
        if sentence is None or not overlay_flags[slot]:
            continue
        lines = with_opener(openers[0], sentence)
        if lines is not None:
            final_texts[slot] = lines
            openers.pop(0)


# HT-HINT-01: a fixed label per level 1-8, whichever boss the level holds.
# Levels 4 and 8 share one creature, so the labels do not tell them apart;
# every label's text is still its own level's.
BOSS_LABELS: dict[int, str] = {
    1: "AQUAMENTUS", 2: "DODONGO", 3: "GOHMA", 4: "MANHANDLA",
    5: "DIGDOGGER", 6: "GLEEOK", 7: "MOLDORM", 8: "LURKING MANHANDLA",
}

# The four person sprites (ObjAnimations $58-$5B) and the name a hint gives each. Owner
# decision (2026-10-12): both elder sprites are THE ELDER, so a hint no longer tells those two
# apart.
PERSON_NAMES: dict[int, str] = {
    0x58: "ELDER", 0x59: "ELDER", 0x5A: "MERCHANT", 0x5B: "MOBLIN",
}
MOBLIN_SPRITE = 0x5B
SAME_FORM = "SAME"
HUMAN_FORM = "HUMAN"


def sprite_form(sprite: int) -> str:
    """A target sprite's name form, by its sprite ("$58"): the measured category, whatever
    name the hint gives it."""
    return f"${sprite:02X}"


def name_form(giver: int, target: int) -> str:
    """HT-HINT-01's name form of a (giver, target) pair: "same" when both
    bytes are equal, else "the human" when the giver is the Moblin, else
    the target's own sprite."""
    if giver == target:
        return SAME_FORM
    if giver == MOBLIN_SPRITE:
        return HUMAN_FORM
    return sprite_form(target)


def person_name(giver: int, target: int) -> str:
    """The pair's name as an object ("ME" for the same form)."""
    form = name_form(giver, target)
    if form == SAME_FORM:
        return "ME"
    return f"THE {HUMAN_FORM if form == HUMAN_FORM else PERSON_NAMES[target]}"


COMPASS_FAMILIES: tuple[tuple[frozenset[int], str], ...] = (
    (frozenset({0x13}), "ZOL"),
    (frozenset({0x14, 0x15}), "GEL"),
    (frozenset({0x17}), "LIKE LIKE"),
    (frozenset({0x23, 0x24}), "WIZZROBE"),
    (frozenset({0x3A, 0x3B}), "LANMOLA"),
    (frozenset({0x47, 0x48}), "PATRA"),
    (frozenset({0x1B, 0x1C, 0x1D}), "KEESE"),
    (frozenset({0x12}), "VIRE"),
    (frozenset({0x37}), "ZELDA"),
    (frozenset({0x00}), "NOTHING"),
    (frozenset({0x05, 0x06}), "GORIYA"),
    (frozenset({0x0B, 0x0C}), "DARKNUT"),
    (frozenset({0x16}), "POLS VOICE"),
    (frozenset({0x27}), "WALLMASTER"),
    (frozenset({0x28}), "ROPE"),
    (frozenset({0x2A}), "STALFOS"),
    (frozenset({0x2B, 0x2C, 0x2D}), "BUBBLE"),
    (frozenset({0x30}), "GIBDO"),
    (frozenset({0x35}), "RUPEE"),
    (frozenset({0x41}), "MOLDORM"),
    (frozenset({0x25, 0x49, 0x4A}), "TRAP"),
    (frozenset({0x01, 0x02}), "LYNEL"),
    (frozenset({0x03, 0x04}), "MOBLIN"),
    (frozenset({0x07, 0x08, 0x09, 0x0A}), "OCTOROK"),
    (frozenset({0x0D, 0x0E}), "TEKTITE"),
    (frozenset({0x0F, 0x10}), "LEEVER"),
    (frozenset({0x1A}), "PEAHAT"),
    (frozenset({0x3D}), "AQUAMENTUS"),
    (frozenset({0x3C}), "MANHANDLA"),
    (frozenset({0x38, 0x39}), "DIGDOGGER"),
    (frozenset({0x33, 0x34}), "GOHMA"),
    (frozenset({0x31, 0x32}), "DODONGO"),
    (frozenset({0x42, 0x43, 0x44, 0x45}), "GLEEOK"),
)


FIRST_MIXED_LIST = 0x62               # list ids $62+ name a mixed list
MIXED_LIST_SKIPPED = frozenset({0x00, 0x2B, 0x2C, 0x2D, 0x4A})   # not a list's family


def compass_family_name(monster_id: int, gw: GameWorld) -> str:
    """HT-HINT-01: the compass room's monster family, resolving mixed lists
    to the first non-sentinel member."""
    if monster_id >= FIRST_MIXED_LIST:
        # the shipped list (the group passes redraw it, PS-EGRP-04), read
        # through ObjListAddrs as the game does
        from .shuffle_overworld_monsters import mixed_list
        monster_id = next((member for member in mixed_list(gw, monster_id)
                           if member not in MIXED_LIST_SKIPPED), monster_id)
    for family_ids, name in COMPASS_FAMILIES:
        if monster_id in family_ids:
            return name
    return f"FAMILY{monster_id:02X}"


# -----------------------------------------------------------------------------
# Overworld / level helpers
# -----------------------------------------------------------------------------

RAFT_SCREENS = frozenset({47, 69})
# The graveyard's two screens, in HT-HINT-01's bracelet door set: the original randomizer's "feat of
# strength" there is pushing a gravestone, which needs no bracelet (owner ruling, 2026-10-10; emulator: a door
# on $20 or $21 opens without it). Their door hints say so (GRAVESTONE_TEXT).
GRAVESTONE_SCREENS = frozenset({0x20, 0x21})
LADDER_SCREENS = frozenset({24, 25})
BRACELET_SCREENS = frozenset({9, 17, 27, 29, 32, 33, 35, 73, 121})
BRACELET_SCREENS_NO_32_33 = frozenset({9, 17, 27, 29, 35, 73, 121})

MONSTER_BIT_LIST = 0x40              # a monster list id's bit 6: the D byte's bit 7
ITEM_CODE_MASK = 0x3F                 # a ware byte's item code (top two bits: flags)
REQUIREMENT_TEXT_COUNT = 10
# The ten requirement texts' slots in drawn order (the third moves to 12, HT-HINT-02)
REQUIREMENT_SLOTS = (24, 29, 38, 39, 40, 41, 42, 43, 26, 30)
# Tracked items the hints never name (owner design, 2026-10-17; docs/zora-extras.md section 13):
# Shuffle Major Shop Items' baits
UNHINTED_ITEMS = frozenset({Item.BAIT})


def _hidden_flag(screen: Screen) -> bool:
    from ...model.enums import QuestVisibility
    return screen.quest_visibility in (QuestVisibility.SECOND_QUEST, QuestVisibility.NEITHER_QUEST)


def _door_screen(gw: GameWorld, level: int) -> int | None:
    """HT-HINT-01's door screen: the level's door (2nd Quest's leftover codes on 11 and 66 are
    not doors, OW-QST-05)."""
    return door_screen(gw.overworld, level)


def _white_sword_screen(gw: GameWorld) -> int | None:
    for screen in gw.overworld.screens:
        if screen.destination == Destination.WHITE_SWORD_CAVE and not _hidden_flag(screen):
            return screen.screen_num
    return None


def _level9_extents(gw: GameWorld) -> tuple[int, int]:
    columns = [room.room_num % 16 for room in gw.levels[8].rooms]
    return min(columns), max(columns)


def _quadrant(gw: GameWorld, room_num: int) -> str:
    row, column = divmod(room_num, 16)
    leftmost, rightmost = _level9_extents(gw)
    left_edge = leftmost - 1 if (rightmost - leftmost) < 6 else leftmost
    north_south = "NORTH" if row < 4 else "SOUTH"
    east_west = "WEST" if column - left_edge < 4 else "EAST"
    return f"{north_south}-{east_west}"


# -----------------------------------------------------------------------------
# Requirement candidates (HT-HINT-01)
# -----------------------------------------------------------------------------

class Form:
    """HT-HINT-01's requirement-family forms (the spec's Check names them)."""
    BOSS = "boss"
    LADDER = "ladder"
    BRACELET = "bracelet"
    NO_BRACELET = "no bracelet"
    RAFT = "raft"
    NO_RAFT = "no raft"
    RECORDER = "recorder"
    BOW = "bow"


FORMS = (Form.BOSS, Form.LADDER, Form.BRACELET, Form.NO_BRACELET, Form.RAFT, Form.NO_RAFT,
         Form.RECORDER, Form.BOW)
INSIDE_MEANS = ((Item.RECORDER, Form.RECORDER), (Item.BOW, Form.BOW), (Item.LADDER, Form.LADDER))


# The forms of the items the owner's overworld gates ask for (a maze's hint has none).
GATE_FORMS = {Item.RAFT: Form.RAFT, Item.LADDER: Form.LADDER, Item.POWER_BRACELET: Form.BRACELET}
ScreenMeans = tuple[tuple[frozenset[int], str], ...]


def gated_screens(gates: OverworldGates) -> dict[str, frozenset[int]]:
    """Bug fix (2.0 beta 2 report): the screens the owner's overworld gates put behind each
    means (Extra Raft Blocks, Extra Power Bracelet Blocks, Randomize Dead Woods' west half when no
    shortcut or bridge opens it;
    overworld_gates.py, the acceptance check's own sets), empty for a means no gate asks for.
    HT-HINT-01's screen sets are PRG0's; without these a door on a new raft block got "THE
    PRINCESS NEEDS NO RAFT" (now "THE HERO'S PATH NEEDS NO RAFT")."""
    gated = dict.fromkeys(GATE_FORMS.values(), frozenset[int]())
    for screens, need in gates.screen_needs():
        if need in GATE_FORMS:
            gated[GATE_FORMS[Item(need)]] |= screens
    return gated


def door_means(recorder: frozenset[int], gates: OverworldGates = NO_GATES) -> ScreenMeans:
    """1. the door-screen means; `recorder`: the Recorder set (eleven screens under C01 = 2,
    OW-MIX-08); with the overworld gates' screens added (gated_screens)."""
    gated = gated_screens(gates)
    return ((RAFT_SCREENS | gated[Form.RAFT], Form.RAFT), (recorder, Form.RECORDER),
            (LADDER_SCREENS | gated[Form.LADDER], Form.LADDER),
            (BRACELET_SCREENS | gated[Form.BRACELET], Form.BRACELET))


def white_sword_means(recorder: frozenset[int], gates: OverworldGates = NO_GATES) -> ScreenMeans:
    """3. the white-sword cave: the first means that holds, in this order (the overworld gates'
    screens added, gated_screens)."""
    gated = gated_screens(gates)
    return ((RAFT_SCREENS | gated[Form.RAFT], Form.RAFT),
            (LADDER_SCREENS | gated[Form.LADDER], Form.LADDER),
            (recorder, Form.RECORDER), (BRACELET_SCREENS_NO_32_33 | gated[Form.BRACELET], Form.BRACELET))


def door_needs(gw: GameWorld, gates: OverworldGates, door: int, screens: frozenset[int],
               mazes_followed: frozenset[int] = frozenset()) -> bool:
    """A door needs the means of `screens`: it is on one of them, or behind a gated maze whose
    hint every door of the hint shop selling the maze's path needs in turn (the acceptance check
    asks for the hint, held once its shop's door is reached; one maze's shop can sit behind the
    other maze). Bug fix as gated_screens."""
    if door in screens:
        return True
    hint_shops = dict(gates.maze_hints())
    for maze_screens, hint in gates.screen_needs():
        if hint in hint_shops and hint not in mazes_followed and door in maze_screens:
            shop_doors = [screen.screen_num for screen in gw.overworld.screens
                          if screen.destination == hint_shops[hint] and not _hidden_flag(screen)]
            if shop_doors and all(door_needs(gw, gates, shop_door, screens, mazes_followed | {hint})
                                  for shop_door in shop_doors):
                return True
    return False


@dataclass(frozen=True)
class Requirement:
    """One HT-HINT-01 requirement candidate: its form, the item it names
    (None for the not-needed fallbacks), the boss form's player level (SH-NUM-03), whether
    it is the white-sword cave's, and whether its door is under a gravestone
    (a bracelet door on GRAVESTONE_SCREENS); only the wording differs."""
    form: str
    item: int | None = None
    level: int | None = None
    white_sword_cave: bool = False
    gravestone: bool = False

    @property
    def key(self) -> tuple[str, int | None, int | None]:
        """What the text conveys: the form, the item and the boss level."""
        return self.form, self.item, self.level


# Owner-ruled deviation (HT-HINT-01, owner ruling 2026-10-11; docs/deviations.md): a paired
# second-quest data level's four inside-dungeon walks cover its own rooms from its own start room,
# as an unpaired level's do, so it forms inside-dungeon candidates. The original randomizer's
# walks form none. An internal measurement switch, not a setting: False gives the original
# randomizer's walks, so the hint rows compare with the corpus (scripts/compare_corpus.py --reference-paired-hints).
PAIRED_LEVELS_WALK_THEIR_OWN_ROOMS = True


def is_paired(level: Level) -> bool:
    """HT-HINT-01's second-quest level in a pair: data level d, shown to the player as its
    partner's number (SH-NUM-03: data levels 2 and 3, 4 and 5, 7 and 8 of a second-quest set)."""
    return level.rom_level_num != level.level_num


def level_shown_as(levels: Sequence[Level], player_level: int) -> Level:
    """The data level whose entry shows `player_level` (SH-NUM-03)."""
    return next(level for level in levels if level.rom_level_num == player_level)


@dataclass(frozen=True)
class ItemPlace:
    """Where a level holds an item: a room, or an item cellar (by its cell)."""
    level: Level
    room: int | None = None
    cellar: int | None = None


def _level(levels: Sequence[Level], level_num: int) -> Level:
    return next(level for level in levels if level.level_num == level_num)


def item_place(levels: Sequence[Level], level_num: int, item: int) -> ItemPlace | None:
    """A finished ROM's reading of the tested room, which has no item records: the level's room
    holding the item, else its item cellar (by its cell). On the corpus the room the tested-room
    rule finds is the only room of its level holding the item (HT-HINT-01's tested-room Check)."""
    level = _level(levels, level_num)
    room = item_room(level, item)
    if room is not None:
        return ItemPlace(level, room=room)
    cellar = item_cellar(level, item)
    return None if cellar is None else ItemPlace(level, cellar=cellar)


def _partner(levels: Sequence[Level], level: Level) -> Level:
    """A paired level's partner: data level p, the level shown as data level d's number."""
    return _level(levels, level.rom_level_num)


def tested_place(levels: Sequence[Level], record: TrackedPlace,
                 walk_own_rooms: bool = True) -> ItemPlace | None:
    """HT-HINT-01 item 2's tested room, every level alike: an item cellar keeps its record (the
    re-deal leaves cellars alone); otherwise the record's own room when its whole item byte still
    equals the recorded byte, else the first of the walked level's own rooms, in room order
    (no cellars, no rooms outside the level), whose whole item byte does; None when none does.
    The walked level is the record's own, but a paired level's partner when not
    `walk_own_rooms` (the original randomizer's walk). A record without its room (an assigned world's
    rebuilt records, finish.rebuild_tracking) is read as a finished ROM is (item_place)."""
    assert record.level is not None
    level = _level(levels, record.level)
    if record.cellar is not None:
        return ItemPlace(level, cellar=record.cellar)
    if record.room is None or record.item_byte is None:
        return item_place(levels, record.level, record.item)
    recorded = record.item_byte
    if recorded >= DARK_BIT:              # "a recorded byte of $80 or more never counts as equal"
        return None
    if level.block.room(record.room).item_byte == recorded:
        return ItemPlace(level, room=record.room)
    walked = level if walk_own_rooms or not is_paired(level) else _partner(levels, level)
    room = next((room.room_num for room in walked.rooms if room.item_byte == recorded), None)
    return None if room is None else ItemPlace(level, room=room)


SWORD_ONLY = frozenset({Item.WOOD_SWORD})


def _enterable(place: ItemPlace, carried: frozenset[int]) -> bool:
    """HT-HINT-01 rule 2's probe: the inventory walk (VA-REJ-17/18) with the
    carried items and last-boss shutters open enters the record's own room
    (for a cellar item, the cellar's room over its stair link). Reaching is
    entering: no arrival-side test, and the room's own monsters need not be
    beaten."""
    target = place.room if place.room is not None else place.cellar
    walk = walk_level(place.level, carried, is_last_boss_open=True, uses_families=True, target=target)
    return target in walk.reached


def inside_dungeon_needs(place: ItemPlace, item: int, walk_own_rooms: bool = True) -> list[str]:
    """HT-HINT-01 rule 2: when the sword alone cannot enter the item's room,
    each of the recorder, bow and ladder that can (with the sword) forms a
    candidate; a means equal to the item itself is skipped. The candle plays
    no part in the walk. A paired level walks its own rooms (owner-ruled deviation) unless not
    `walk_own_rooms`: then the original randomizer's walks, over its partner's rooms (sword only, from
    the partner's start room; with one means, from the level's own start room, which is not one
    of them), enter only a tested room that is the level's own start room."""
    if not walk_own_rooms and is_paired(place.level):
        if place.room != place.level.entrance_room:
            return []
        return [form for means, form in INSIDE_MEANS if means != item]
    if sword_enters(place):
        return []
    return [form for means, form in INSIDE_MEANS
            if means != item and _enterable(place, SWORD_ONLY | {int(means)})]


def sword_enters(place: ItemPlace) -> bool:
    """HT-HINT-01 rule 2's first probe: the sword alone enters the room."""
    return _enterable(place, SWORD_ONLY)


def coast_item(gw: GameWorld) -> int:
    """The item given at the coast (the immediate operand at 0x1789A)."""
    from ...model.overworld import OverworldItem
    coast = gw.overworld.get_cave(Destination.COAST_ITEM, OverworldItem)
    assert coast is not None
    return int(coast.item)


def requirement_candidates(gw: GameWorld, level_items: list[tuple[int, int]],
                           names_hearts: bool = False, gates: OverworldGates = NO_GATES,
                           records: Sequence[TrackedPlace] | None = None,
                           walk_own_rooms: bool = True) -> list[Requirement]:
    """HT-HINT-01's requirement candidates 1-5, in order, before the
    shuffle. level_items: (item, data level) for each item the item shuffle
    records in a level; `records`: those records, in the same order, for the tested room
    (tested_place), or None to read it from the world as a finished ROM is (item_place).
    `walk_own_rooms`: PAIRED_LEVELS_WALK_THEIR_OWN_ROOMS. Heart containers are named only when `names_hearts`:
    within each dungeon (C06 = 2, PS-ITW-05; HT-HINT-01 rules 1 and 5 except
    them only under C06 = 3). Under C06 = 3 ZORA leaves them out of rule 2
    as well, as before; the corpus shows no such text (PS-ITW-05: CP-5 0). `gates`: the owner's
    overworld gates, whose screens count as their means' everywhere here (gated_screens)."""
    level_records: Sequence[TrackedPlace | None] = [None] * len(level_items) if records is None else records
    named_records = [(item, level, record) for (item, level), record in zip(level_items, level_records, strict=True)
                     if names_hearts or item != Item.HEART_CONTAINER]
    named = [(item, level) for item, level, _record in named_records]
    recorder = recorder_screens(gw.overworld)
    candidates: list[Requirement] = []
    recorded: set[str] = set()
    # 1. door-screen requirements; a screen can satisfy more than one
    for item, level in named:
        screen = _door_screen(gw, level)
        for screens, form in door_means(recorder, gates):
            if screen in screens:
                candidates.append(Requirement(form, item,
                                              gravestone=form == Form.BRACELET and screen in GRAVESTONE_SCREENS))
                recorded.add(form)
    # 2. inside-dungeon requirements
    for item, level, record in named_records:
        place = (item_place(gw.levels, level, item) if record is None
                 else tested_place(gw.levels, record, walk_own_rooms))
        if place is not None:
            candidates.extend(Requirement(form, item) for form in inside_dungeon_needs(place, item, walk_own_rooms))
    # 3. the white-sword cave
    white_sword_screen = _white_sword_screen(gw)
    cave = gw.overworld.get_cave(Destination.WHITE_SWORD_CAVE, ItemCave)
    if white_sword_screen is not None and cave is not None:
        white_sword_form = next((means_form for screens, means_form in white_sword_means(recorder, gates)
                                 if white_sword_screen in screens), None)
        if white_sword_form is not None:
            candidates.append(Requirement(white_sword_form, cave.item & ITEM_CODE_MASK, white_sword_cave=True))
            recorded.add(white_sword_form)
    # 4. fallbacks; a means is also recorded when any door needs it (door_needs)
    doors = {_door_screen(gw, level) for level in range(1, 10)}
    gated = gated_screens(gates)
    for screens, form in ((RAFT_SCREENS | gated[Form.RAFT], Form.RAFT),
                          (BRACELET_SCREENS_NO_32_33 | gated[Form.BRACELET], Form.BRACELET)):
        if any(door_needs(gw, gates, door, screens) for door in doors if door is not None):
            recorded.add(form)
    if Form.BRACELET not in recorded:
        candidates.append(Requirement(Form.NO_BRACELET))
    if Form.RAFT not in recorded:
        candidates.append(Requirement(Form.NO_RAFT))
    candidates.append(Requirement(Form.LADDER, coast_item(gw)))
    # 5. boss forms: levels 1-8 only, each with the label of the player level the item is in
    candidates.extend(Requirement(Form.BOSS, item, _level(gw.levels, level).rom_level_num)
                      for item, level in named if level != 9)
    return candidates


# A bracelet door on the graveyard (GRAVESTONE_SCREENS), with the item's own article.
GRAVESTONE_TEXT = "THE PATH TO {item} LIES BENEATH A GRAVESTONE."
# Owner decision (2026-10-12): "THE HERO'S PATH" (it was "THE PRINCESS").
NOT_NEEDED_TEXT = {Form.NO_BRACELET: ["THE HERO'S PATH", "NEEDS NO BRACELET"],
                   Form.NO_RAFT: ["THE HERO'S PATH", "NEEDS NO RAFT"]}


def _fit(line: str, first: str, second: str) -> list[str]:
    return [line] if len(line) <= LINE_WIDTH else [first, second]


def requirement_text(candidate: Requirement, names: ItemNames = VANILLA_NAMES) -> list[str]:
    """ZORA's own wording for a requirement candidate."""
    if candidate.form in NOT_NEEDED_TEXT:
        return NOT_NEEDED_TEXT[candidate.form]
    assert candidate.item is not None
    item, phrase = names.label(candidate.item), names.phrase(candidate.item)
    if candidate.form == Form.BOSS:
        assert candidate.level is not None
        return hint_lines(item_location_sentence(candidate.item, candidate.level, names))
    if candidate.gravestone:
        return hint_lines(GRAVESTONE_TEXT.format(item=phrase))
    means = candidate.form.upper()
    if candidate.white_sword_cave and names.is_foreign(candidate.item):
        return ["THE CAVE WITH", phrase, f"NEEDS THE {means}"]
    if candidate.white_sword_cave:
        return names.fit(f"THE {item} CAVE NEEDS THE {means}", f"THE {item} CAVE", f"NEEDS THE {means}")
    return names.fit(f"{phrase} NEEDS THE {means}", phrase, f"NEEDS THE {means}")


def draw_requirements(candidates: list[Requirement], rng: Rng) -> list[Requirement]:
    """HT-HINT-01: shuffle the candidate list (other uniform on
    position..count-1) and take the first ten."""
    count = len(candidates)
    for position in range(count):
        other = position + rng.below(count - position)
        candidates[position], candidates[other] = candidates[other], candidates[position]
    return candidates[:REQUIREMENT_TEXT_COUNT]


# -----------------------------------------------------------------------------
# Pool routing
# -----------------------------------------------------------------------------

def place_pool(rng: Rng, white_hearts: int, magical_hearts: int,
               book_needed: bool = False) -> dict[int, list[list[str]]]:
    """HT-TEXT-02 steps 1-3: route every pool quote to a slot's candidate list.

    Owner rulings (docs/ui-provenance.md), departing from the spec's
    independent draws: within each routing class, a quote goes to one of
    the class's slots that holds none of its quotes yet, while any is left,
    and only then uniformly among all of them. A class with as many quotes
    as slots therefore gives each of its slots one, so no shown slot is ever
    left without candidates (the spec's greeting fallback never happens),
    and each quote is in at most one list, so no quote shows twice in a
    seed. The draws stay uniform, in pool (file) order."""
    candidates: dict[int, list[list[str]]] = {slot: [] for slot in range(SLOT_COUNT)}
    filled: dict[str, set[int]] = defaultdict(set)
    for entry in POOL:
        slots = entry.slots(white_hearts, magical_hearts, book_needed)
        if not slots:
            continue
        open_slots = [slot for slot in slots if slot not in filled[entry.routing_class]] or list(slots)
        slot = open_slots[rng.below(len(open_slots))] if len(open_slots) > 1 else open_slots[0]
        filled[entry.routing_class].add(slot)
        candidates[slot].append(list(entry.lines))
    return candidates


# -----------------------------------------------------------------------------
# Main pass
# -----------------------------------------------------------------------------

@dataclass
class HintTextResult:
    quotes: list[Quote]
    pointers: tuple[int, ...]
    text_bytes: tuple[bytes, ...]
    white_sword_selector: int
    hint_shop_offer_selectors: tuple[int, ...]
    underworld_selectors_a: bytes
    underworld_selectors_b: bytes
    hint_shop_prices: tuple[int, ...]
    overlay_flags: tuple[bool, ...]
    # The texts that tell where a level is, by the slot holding them: the player level they name
    # (only those the helpful overlay chose), and the pool quote each gives way to inside that
    # level (keep_level_hints_out_of_their_levels).
    level_location_slots: dict[int, int] = field(default_factory=dict)
    level_text_alternatives: dict[int, list[str]] = field(default_factory=dict)
    # Each listed dungeon person room's player level and the slot it shows (HT-SEL-01), before
    # B19's pointer exchange.
    room_slots: tuple[tuple[int, int], ...] = ()


# HT-HINT-01's three name pairs as (giver, target) cave person object types:
# entries 10, 11 and 12 (texts 6, 7 and 3).
NAME_PAIR_TYPES = ((115, 117), (116, 110), (112, 109))


def _replace_26_to_4c(data: bytes) -> bytearray:
    return bytearray(0x4C if value == 0x26 else value for value in data)


# A selector is twice its text's slot (PersonTextAddrs is two bytes a text).
SELECTOR_TO_SLOT = 2

# HT-SEL-01: each level's primary selector, levels 1-8, and the spares in their order.
PRIMARY_SELECTORS = (0x26, 0x28, 0x2A, 0x2C, 0x2E, 0x38, 0x3E, 0x42)
SPARE_SELECTORS = (0x30, 0x3A, 0x40, 0x34, 0x3C)
FIRST_PERSON_CODE = 0x0B       # a family's entry i belongs to person code $0B + i
FAMILY_ENTRIES = 8             # the first eight entries are the person-code entries


def _build_selector_tables(gw: GameWorld, hint_assignment: HintAssignmentResult) -> tuple[bytes, bytes]:
    """HT-SEL-01: the hint rooms' selectors, walking the hint list in PS-HINT-05's order. A
    level's first listed room takes the level's primary selector, each further room the next
    spare; a level with no listed room adds its primary to the end of the spares, in level
    order. The selector goes into the level's family (B for a helpful level, A otherwise) at
    the room's person code less $0B; entries no room writes keep PRG0's bytes. The $26-to-$4C
    replacement comes after the writes, so level 1's primary ships as $4C (corpus: level 1's
    persons show text 38, never 19)."""
    tables = {False: bytearray(gw.underworld_text_selectors_a or bytes(FAMILY_ENTRIES)),
              True: bytearray(gw.underworld_text_selectors_b or bytes(FAMILY_ENTRIES))}
    listed_levels = {level for level, _code in hint_assignment.hint_ids}
    spares = [*SPARE_SELECTORS, *(PRIMARY_SELECTORS[level - 1] for level in range(1, FAMILY_ENTRIES + 1)
                                  if level not in listed_levels)]
    seen: set[int] = set()
    for level, code in hint_assignment.hint_ids:
        if level not in seen:
            seen.add(level)
            selector = PRIMARY_SELECTORS[level - 1]
        elif spares:
            selector = spares.pop(0)
        else:
            continue
        entry = code - FIRST_PERSON_CODE
        # A helpful counter that ran past $12 names no person-code entry; not reached in the
        # corpus (every listed code is $0B-$12).
        if entry < FAMILY_ENTRIES:
            tables[level in hint_assignment.helpful][entry] = selector
    return bytes(_replace_26_to_4c(bytes(tables[False]))), bytes(_replace_26_to_4c(bytes(tables[True])))


# The sword caves' own texts (owner decision, 2026-10-17): each cave shows a quote about the heart
# containers it asks for, one of the pool's for that count, or this line when the pool has none (the
# magical-sword cave's 13 and 14).
HEARTS_NEEDED_TEXT = "{hearts} HEARTS NEEDED"


def sword_cave_heart_quotes(slot: int, hearts: int) -> list[list[str]]:
    """The candidates of a sword cave's slot (WHITE_SWORD_TEXT_SLOT or MAGICAL_SWORD_TEXT_SLOT)
    whose cave asks for `hearts`: the pool's heart-count quotes for it, in pool order, else
    HEARTS_NEEDED_TEXT."""
    return ([list(entry.lines) for entry in POOL if entry.hearts == (slot, hearts)]
            or [[HEARTS_NEEDED_TEXT.format(hearts=hearts)]])


# HT-HINT-01's level-location entries: the slot of each level's text, levels 1-9.
LEVEL_LOCATION_SLOTS = (33, 19, 20, 21, 22, 23, 28, 31, 32)
# HT-HINT-01's person-name entries 10, 11 and 12 (texts 6, 7 and 3).
SHOW_SLOT, MEET_SLOT, HOLDER_SLOT = 6, 7, 3
# The level-9 trio's slots: three of its four texts, one dropped at random.
LEVEL9_TRIO_SLOTS = (35, 36, 37)
# HT-HINT-02's relocation before the overlay: 38 -> 12, 19 -> 38, 19 emptied.
RELOCATED_TO_12, RELOCATED_TO_38, EMPTIED_SLOT = 38, 19, 19
# HT-SEL-02: each hint-shop offer price is drawn uniformly from 10..60.
HINT_PRICE_LOW, HINT_PRICE_CHOICES = 10, 51
WHITE_SWORD_SELECTOR = 0x66
HINT_SHOP_OFFER_SELECTORS = (0x18, 0x4E, 0x50, 0x52, 0x54, 0x56)


def relocate(texts: list[T | None]) -> None:
    """HT-HINT-02's relocation before the overlay: 38 -> 12, 19 -> 38, 19 emptied."""
    texts[12] = texts[RELOCATED_TO_12]
    texts[38] = texts[RELOCATED_TO_38]
    texts[EMPTIED_SLOT] = None


def hinted_level_records(item_shuffle_result: ItemShuffleResult) -> list[TrackedPlace]:
    """The tracked records in a level that a requirement text may name: none of UNHINTED_ITEMS."""
    return [record for record in item_shuffle_result.tracked
            if record.level is not None and record.item not in UNHINTED_ITEMS]


def generate_hint_text(gw: GameWorld, item_shuffle_result: ItemShuffleResult, hint_assignment: HintAssignmentResult,
                       rng: Rng, names: ItemNames = VANILLA_NAMES,
                       maze_offers: dict[int, list[str]] | None = None,
                       gates: OverworldGates = NO_GATES,
                       every_helpful_hint: bool = False, book_needed: bool = False) -> HintTextResult:
    """HT-TEXT and HT-HINT. every_helpful_hint: Helpful hints (C03 = 1, HT-HINT-04), where every
    slot with a helpful text shows it, with no overlay coin. book_needed: Book to Understand NPCs (B48, HT-BOOK-02),
    slot 0's candidates are the lines in which the speaker cannot be understood.
    names: how the texts name items (PI-TEXT-01; the vanilla names give HT-HINT-01's).
    gates: the owner's overworld gates, for the requirement candidates.

    The random draws, in order: the hint-shop prices, the level-9 trio's
    dropped text, the requirement texts, the pool routing, and per slot the
    overlay coin and the pool pick."""
    opener_rng = copy.deepcopy(rng)          # the openers' order, from a copy: no other draw moves
    hint_prices = draw_hint_shop_prices(gw, rng)

    # Owner ruling: slot 0 (the wood sword cave) shows only its own pool
    # quotes; HT-HINT-01's greeting (entry 0) and HT-TEXT-02's greeting
    # candidate are never written (docs/ui-provenance.md).
    slot_texts: list[list[str] | None] = [None] * SLOT_COUNT
    # the reworded hints' sentences (item and level location), for their openers
    sentences: list[str | None] = [None] * SLOT_COUNT
    # the player level each level-location text names, by slot
    level_slots: list[int | None] = [None] * SLOT_COUNT
    write_level_location_texts(gw, slot_texts, sentences, level_slots)
    write_person_name_texts(gw, slot_texts, names)

    trio = level9_trio_texts(gw, item_shuffle_result, names)
    trio.pop(1 + rng.below(3))
    for slot, text in zip(LEVEL9_TRIO_SLOTS, trio, strict=True):
        slot_texts[slot] = text

    records = hinted_level_records(item_shuffle_result)
    level_items = [(record.item, record.level) for record in records if record.level is not None]
    requirements = draw_requirements(
        requirement_candidates(gw, level_items, names_hearts=not item_shuffle_result.heart_rooms_pooled, gates=gates,
                               records=records, walk_own_rooms=PAIRED_LEVELS_WALK_THEIR_OWN_ROOMS),
        rng)
    # fewer than ten candidates fill fewer slots (draw_requirements takes at most ten)
    for slot, candidate in zip(REQUIREMENT_SLOTS, requirements, strict=False):
        slot_texts[slot] = requirement_text(candidate, names)
        if candidate.form == Form.BOSS:
            assert candidate.item is not None and candidate.level is not None
            sentences[slot] = item_location_sentence(candidate.item, candidate.level, names)

    # Relocation before overlay (HT-HINT-02), the sentences with their texts.
    relocate(slot_texts)
    relocate(sentences)
    relocate(level_slots)

    pool_candidates = route_pool_candidates(gw, rng, book_needed)
    final_texts, overlay_flags = select_final_texts(slot_texts, pool_candidates, rng, every_helpful_hint)
    add_openers(final_texts, overlay_flags, sentences, opener_rng)
    level_location_slots = {slot: level for slot, level in enumerate(level_slots)
                            if level is not None and overlay_flags[slot]}
    alternatives = level_text_alternatives(level_location_slots, pool_candidates, rng)

    return replace(_hint_text_result(gw, item_shuffle_result, hint_assignment, final_texts, overlay_flags,
                                     HINT_SHOP_OFFER_SELECTORS, tuple(hint_prices), maze_offers),
                   level_location_slots=level_location_slots, level_text_alternatives=alternatives)


def generate_community_hint_text(gw: GameWorld, item_shuffle_result: ItemShuffleResult,
                                 hint_assignment: HintAssignmentResult, rng: Rng,
                                 names: ItemNames = VANILLA_NAMES,
                                 maze_offers: dict[int, list[str]] | None = None,
                                 book_needed: bool = False) -> HintTextResult:
    """FL-ALT-04 (C03 = 2, community hints): the helpful texts (HT-HINT-01) are not made and the
    mixed overlay (HT-HINT-02) does not run, nor its moves between slots 38, 12 and 19: each
    slot shows one candidate drawn from its own pool list (HT-TEXT-02). The two hint shops are
    not rewritten: they keep PRG0's offer selectors and prices (HT-SEL-02's hint-shop part and
    HT-HINT-03's price draw do not apply). Unchanged: the pool, its routing and its fixed
    additions, the fit rule, the hint-room selectors (HT-SEL-01), the white-sword cave selector,
    and the pointer exchange (HT-TEXT-04, shuffle_dungeon_text, run on this result).

    Owner rulings kept (docs/ui-provenance.md), departing from FL-ALT-04: the pool is ZORA's
    (owner quotes and numbered placeholders); slot 0, the wood sword cave, shows one of the
    owner's seven quotes, never the greeting; slot 9 has its three added quotes; place_pool's
    routing gives every shown slot a candidate, so the greeting fallback never happens.
    names and book_needed as in generate_hint_text.

    The random draws, in order: the pool routing, then per slot the pool pick."""
    pool_candidates = route_pool_candidates(gw, rng, book_needed)
    final_texts, overlay_flags = select_final_texts([None] * SLOT_COUNT, pool_candidates, rng)
    assert gw.hint_shop_offer_selectors is not None, "the base ROM's hint-shop offer selectors"
    return _hint_text_result(gw, item_shuffle_result, hint_assignment, final_texts, overlay_flags,
                             gw.hint_shop_offer_selectors, tuple(hint_shop_prices(gw)), maze_offers)


def _hint_text_result(gw: GameWorld, item_shuffle_result: ItemShuffleResult, hint_assignment: HintAssignmentResult,
                      final_texts: list[list[str]], overlay_flags: list[bool],
                      hint_shop_offer_selectors: tuple[int, ...], hint_prices: tuple[int, ...],
                      maze_offers: dict[int, list[str]] | None = None) -> HintTextResult:
    """The texts encoded and placed, and the selector tables (no draws). maze_offers (Randomize
    Lost Hills / Dead Woods, owner design): a hint shop offer's new text, written into the slot
    that offer shows, overriding it, and the offer priced at 1 rupee."""
    prices = list(hint_prices)
    for offer, lines in (maze_offers or {}).items():
        final_texts[hint_shop_offer_selectors[offer] // SELECTOR_TO_SLOT] = lines
        prices[offer] = MAZE_HINT_PRICE
    hint_prices = tuple(prices)
    encoded, pointers = encode_hint_texts(final_texts, item_shuffle_result)
    quotes = [Quote(quote_id=i, text="|".join(final_texts[i])) for i in range(SLOT_COUNT)]
    selectors_a, selectors_b = _build_selector_tables(gw, hint_assignment)
    room_slots = tuple((_level(gw.levels, level).rom_level_num,
                        (selectors_b if level in hint_assignment.helpful else selectors_a)[code - FIRST_PERSON_CODE]
                        // SELECTOR_TO_SLOT)
                       for level, code in hint_assignment.hint_ids if code - FIRST_PERSON_CODE < FAMILY_ENTRIES)
    return HintTextResult(
        quotes=quotes,
        pointers=tuple(pointers),
        text_bytes=tuple(bytes(e) for e in encoded),
        white_sword_selector=WHITE_SWORD_SELECTOR,
        hint_shop_offer_selectors=hint_shop_offer_selectors,
        underworld_selectors_a=selectors_a,
        underworld_selectors_b=selectors_b,
        hint_shop_prices=hint_prices,
        overlay_flags=tuple(overlay_flags),
        room_slots=room_slots,
    )


# ZORA deviation (owner request, beta 7; docs/deviations.md "No level-N hints inside level N"): a
# person inside a level never tells where that same level is. After B19's pointer exchange, a
# dungeon person room that would show where its own level is trades its text pointer with another
# dungeon person room's, so the text is still shown, in another level. Only when no room can trade
# does the text give way to a pool quote for its slot, drawn on a copy of the hint step's stream,
# so no other draw moves.

def level_text_alternatives(level_location_slots: dict[int, int], pool_candidates: dict[int, list[list[str]]],
                            rng: Rng) -> dict[int, list[str]]:
    """Each level-location slot's pool quote, in slot order, from a copy of `rng`."""
    alternative_rng = copy.deepcopy(rng)
    return {slot: pool_candidates[slot][alternative_rng.below(len(pool_candidates[slot]))]
            for slot in sorted(level_location_slots) if pool_candidates[slot]}


def keep_level_hints_out_of_their_levels(hint_text: HintTextResult) -> HintTextResult:
    """No dungeon person room shows where its own level is (no draws). Each room slot whose text
    names a level some room showing that slot is in trades pointers with the first room slot, in
    room order, where both texts then sit outside the levels they name; a slot no room can trade
    with keeps its pointer and its text becomes its pool quote (the texts laid out again, the
    pointers following them). Unchanged when no room shows its own level's text."""
    original_slot_of = _original_slot_of(hint_text.text_bytes)
    levels_showing: dict[int, set[int]] = defaultdict(set)
    for level, slot in hint_text.room_slots:
        levels_showing[slot].add(level)
    room_slots = list(levels_showing)
    pointers = list(hint_text.pointers)

    def misplaced(slot: int, pointer: int) -> bool:
        source = original_slot_of.get(pointer)
        return source is not None and hint_text.level_location_slots.get(source) in levels_showing[slot]

    stranded = []
    for slot in room_slots:
        if not misplaced(slot, pointers[slot]):
            continue
        partner = next((other for other in room_slots if other != slot
                        and not misplaced(slot, pointers[other]) and not misplaced(other, pointers[slot])), None)
        if partner is None:
            stranded.append(original_slot_of[pointers[slot]])
        else:
            pointers[slot], pointers[partner] = pointers[partner], pointers[slot]
    traded = replace(hint_text, pointers=tuple(pointers))
    return _with_pool_quotes(traded, original_slot_of, sorted(set(stranded)))


def _with_pool_quotes(hint_text: HintTextResult, original_slot_of: dict[int, int], slots: list[int]) -> HintTextResult:
    """These slots' own texts replaced by their pool quotes (level_text_alternatives), the texts
    laid out again and the pointers following them."""
    slots = [slot for slot in slots if slot in hint_text.level_text_alternatives]
    if not slots:
        return hint_text
    text_bytes, quotes = list(hint_text.text_bytes), list(hint_text.quotes)
    overlay_flags = list(hint_text.overlay_flags)
    for slot in slots:
        lines = hint_text.level_text_alternatives[slot]
        text_bytes[slot] = bytes(encode_text(lines))
        quotes[slot] = Quote(quote_id=slot, text="|".join(lines))
        overlay_flags[slot] = False
    new_addresses = _text_addresses(text_bytes)
    pointers = tuple(new_addresses[original_slot_of[pointer]] if pointer in original_slot_of else pointer
                     for pointer in hint_text.pointers)
    return replace(hint_text, pointers=pointers, text_bytes=tuple(text_bytes), quotes=quotes,
                   overlay_flags=tuple(overlay_flags))


def _text_addresses(text_bytes: Sequence[bytes]) -> list[int]:
    """Each slot's own text's CPU address, as encode_hint_texts lays them out."""
    return [cpu_address_in_bank1(offset)
            for offset in place_hint_texts([len(body) for body in text_bytes], CONSTERNATION_HINT_SLOTS)]


def _original_slot_of(text_bytes: Sequence[bytes]) -> dict[int, int]:
    """The slot whose own text lies at each address (a pointer that is none, the toll's, is absent)."""
    return {address: slot for slot, address in enumerate(_text_addresses(text_bytes))}


def _hint_shops(gw: GameWorld) -> list[HintShop]:
    """The two hint shops, in shop order."""
    shops = (gw.overworld.get_cave(destination, HintShop)
             for destination in (Destination.HINT_SHOP_1, Destination.HINT_SHOP_2))
    return [shop for shop in shops if shop is not None]


def hint_shop_prices(gw: GameWorld) -> list[int]:
    """Each hint-shop offer's price as the shops hold it, in shop order."""
    return [hint.price for shop in _hint_shops(gw) for hint in shop.hints]


def draw_hint_shop_prices(gw: GameWorld, rng: Rng) -> list[int]:
    """HT-SEL-02: each hint-shop offer's price, drawn uniformly from 10..60, in shop order."""
    hint_prices: list[int] = []
    for shop in _hint_shops(gw):
        for hint in shop.hints:
            hint.price = HINT_PRICE_LOW + rng.below(HINT_PRICE_CHOICES)
            hint_prices.append(hint.price)
    return hint_prices


def write_level_location_texts(gw: GameWorld, slot_texts: list[list[str] | None],
                               sentences: list[str | None], level_slots: list[int | None] | None = None) -> None:
    """HT-HINT-01's level-location entries, in ZORA's wording (no draws): entry N names player
    level N and the region of its door, the door of the data level shown as N (SH-NUM-03; for a
    second-quest level in a pair, its partner's door)."""
    for player_level, slot in enumerate(LEVEL_LOCATION_SLOTS, start=1):
        screen = _door_screen(gw, level_shown_as(gw.levels, player_level).level_num)
        assert screen is not None, f"player level {player_level} has no door screen"
        sentence = level_location_sentence(player_level, region_of_screen(screen))
        sentences[slot] = sentence
        slot_texts[slot] = hint_lines(sentence)
        if level_slots is not None:
            level_slots[slot] = player_level


def write_person_name_texts(gw: GameWorld, slot_texts: list[list[str] | None],
                            names: ItemNames = VANILLA_NAMES) -> None:
    """HT-HINT-01's person-name entries (no draws): the three (giver, target)
    pairs read the appearances FP-PERSON-01 drew
    (zora/generate/steps/person_appearances.py)."""
    pair10, pair11, pair12 = ((person_appearance(gw, giver), person_appearance(gw, target))
                              for giver, target in NAME_PAIR_TYPES)
    slot_texts[SHOW_SLOT] = [f"SHOW {person_name(*pair10)}", "SOMETHING"]
    # entry 11: the lowest-numbered screen with code 19 (the magical-sword
    # cave) and its hidden flag clear
    meet_screen = next((screen_info.screen_num for screen_info in gw.overworld.screens
                        if screen_info.destination == Destination.MAGICAL_SWORD_CAVE
                        and not _hidden_flag(screen_info)), None)
    meet_region = region_of_screen(meet_screen) if meet_screen is not None else 0
    meet_lines = [f"MEET {person_name(*pair11)}", region_phrase(meet_region)]
    magical_sword_cave = gw.overworld.get_cave(Destination.MAGICAL_SWORD_CAVE, ItemCave)
    if magical_sword_cave is not None:
        meet_lines.append(MEET_HEARTS_TEXT.format(hearts=magical_sword_cave.heart_requirement))
    slot_texts[MEET_SLOT] = meet_lines

    white_sword_cave = gw.overworld.get_cave(Destination.WHITE_SWORD_CAVE, ItemCave)
    white_sword_screen = _white_sword_screen(gw)
    white_sword_region = region_of_screen(white_sword_screen) if white_sword_screen is not None else 0
    # the same form speaks of the giver itself: "I HAVE", not "ME HAS"
    holder_text = "I HAVE" if name_form(*pair12) == SAME_FORM else f"{person_name(*pair12)} HAS"
    if white_sword_cave is not None:
        code = white_sword_cave.item & ITEM_CODE_MASK
        slot_texts[HOLDER_SLOT] = holder_hearts_lines(holder_text, names.phrase(code), names.label(code),
                                                      white_sword_region, white_sword_cave.heart_requirement)
    else:
        slot_texts[HOLDER_SLOT] = holder_lines(holder_text, "THE ITEM", region_phrase(white_sword_region))


# Owner request (beta 7): the hints that lead to the two sword caves say how many heart containers
# each cave asks for, so the two can be told apart. The caves' own texts already say it.
MEET_HEARTS_TEXT = "WITH {hearts} HEARTS"
HOLDER_HEARTS_TEXT = "FOR {hearts} HEARTS"
HOLDER_HEARTS_SHORT_TEXT = ", {hearts} HEARTS"      # the last resort: no "FOR"
# The longest region phrases in fewer letters, for a holder text that does not fit three lines.
SHORT_REGION_PHRASES: dict[int, str] = {1: "ON DEATH MOUNTAIN", 8: "IN A FOREST", 9: "IN THE LOST HILLS"}


def holder_lines(holder_text: str, item_phrase: str, place: str) -> list[str]:
    """The white-sword cave's holder text without a heart count: one line, else the holder, then
    the item and the place on one or two lines."""
    line = f"{holder_text} {item_phrase} {place}"
    if len(line) <= LINE_WIDTH:
        return [line]
    second_line = f"{item_phrase} {place}"
    return [holder_text, second_line] if len(second_line) <= LINE_WIDTH else [holder_text, item_phrase, place]


def holder_hearts_lines(holder_text: str, item_phrase: str, item_label: str, region: int, hearts: int) -> list[str]:
    """The white-sword cave's holder text with its heart count, wrapped: "THE ELDER HAS THE LADDER
    BY THE COAST FOR 5 HEARTS". When that needs more than three lines: the shorter region phrase,
    then the item without its article, then ", 5 HEARTS" for "FOR 5 HEARTS"; never reached with
    the white-sword cave's counts (4 to 6), the count is left out as the very last resort."""
    place = region_phrase(region)
    short_place = SHORT_REGION_PHRASES.get(region, place)
    count, short_count = HOLDER_HEARTS_TEXT.format(hearts=hearts), HOLDER_HEARTS_SHORT_TEXT.format(hearts=hearts)
    for text in (f"{holder_text} {item_phrase} {place} {count}",
                 f"{holder_text} {item_phrase} {short_place} {count}",
                 f"{holder_text} {item_label} {short_place} {count}",
                 f"{holder_text} {item_label} {short_place}{short_count}"):
        lines = textwrap.wrap(text, LINE_WIDTH, break_on_hyphens=False)
        if len(lines) <= MAX_LINES:
            return lines
    return holder_lines(holder_text, item_phrase, place)


def level9_trio_texts(gw: GameWorld, item_shuffle_result: ItemShuffleResult,
                      names: ItemNames = VANILLA_NAMES) -> list[list[str]]:
    """The level-9 trio's four candidate texts (no draws): the silver arrows,
    Ganon, Zelda and the compass's guardian, in that order. With Progressive
    Items on (PI-TEXT-01) the first points at a level-9 place holding an
    arrow-line item and names the line."""
    level9 = gw.levels[8]

    def level9_room_where(predicate: Callable[[Room], bool]) -> Room | None:
        for room in level9.rooms:
            if predicate(room):
                return room
        return None

    if names.progressive_items:
        silver_text = _arrow_upgrade_text(gw, item_shuffle_result, level9_room_where)
    else:
        silver_text = _silver_arrows_text(gw, item_shuffle_result, level9_room_where)

    ganon_room = level9_room_where(lambda room: room.enemy == Enemy.THE_BEAST)
    ganon_quadrant = _quadrant(gw, ganon_room.room_num) if ganon_room else "UNKNOWN"
    ganon_text = ["GANON IS IN THE", ganon_quadrant]

    zelda_room = level9_room_where(lambda room: room.enemy == Enemy.THE_KIDNAPPED)
    zelda_quadrant = _quadrant(gw, zelda_room.room_num) if zelda_room else "UNKNOWN"
    zelda_text = ["ZELDA IS IN THE", zelda_quadrant]

    compass_room = level9_room_where(
        lambda room: room.item == Item.COMPASS and room.room_action != RoomAction.LAST_BOSS
    )
    if compass_room is not None:
        # the list id includes $40 for D's bit 7, so mixed lists ($62+) resolve
        list_id = compass_room.monster_list | (MONSTER_BIT_LIST if compass_room.has_monster_bit else 0)
        family = compass_family_name(list_id, gw)
        line = f"THE COMPASS IS GUARDED BY {family}"
        compass_text = [line] if len(line) <= LINE_WIDTH else ["THE COMPASS IS GUARDED", f"BY {family}"]
    else:
        compass_text = ["THE COMPASS HAS", "NO GUARDIAN"]
    return [silver_text, ganon_text, zelda_text, compass_text]


RoomFinder = Callable[[Callable[[Room], bool]], Room | None]


def _silver_arrows_text(gw: GameWorld, item_shuffle_result: ItemShuffleResult,
                        level9_room_where: RoomFinder) -> list[str]:
    """HT-HINT-01's silver-arrow text: their quadrant when they are in level 9."""
    silver = next((place for place in item_shuffle_result.tracked if place.item == Item.SILVER_ARROWS), None)
    if silver is not None and silver.level == 9:
        room = level9_room_where(
            lambda room: (room.item if room.item is not None else Item.NOTHING) == Item.SILVER_ARROWS
        )
        quadrant = _quadrant(gw, room.room_num) if room else "UNKNOWN"
        line = f"SILVER ARROWS ARE IN THE {quadrant}"
        silver_text = [line] if len(line) <= LINE_WIDTH else ["SILVER ARROWS ARE", f"IN THE {quadrant}"]
    else:
        silver_text = ["SILVER ARROWS", "LIE ELSEWHERE"]
    return silver_text


def _arrow_upgrade_text(gw: GameWorld, item_shuffle_result: ItemShuffleResult,
                        level9_room_where: RoomFinder) -> list[str]:
    """PI-TEXT-01: the silver-arrow text names the arrow line and points at a level-9 place
    holding an arrow-line item (the first room in room order), if one is there."""
    if any(place.item in ARROW_LINE and place.level == 9 for place in item_shuffle_result.tracked):
        room = level9_room_where(lambda room: room.item is not None and room.item & ITEM_CODE_MASK in ARROW_LINE)
        quadrant = _quadrant(gw, room.room_num) if room else "UNKNOWN"
        return textwrap.wrap(f"AN ARROW UPGRADE IS IN THE {quadrant}", LINE_WIDTH)
    return ["ARROW UPGRADES", "LIE ELSEWHERE"]


def route_pool_candidates(gw: GameWorld, rng: Rng, book_needed: bool = False) -> dict[int, list[list[str]]]:
    """The pool's candidate lists (place_pool's draws); heart-count quotes follow the sword
    caves' requirements. Each sword cave's own slot draws only from the quotes about its heart
    count (sword_cave_heart_quotes; owner decision, 2026-10-17): the quotes place_pool routed
    there otherwise are not shown. A slot still makes one pick, but a shorter list changes how
    many words Rng.below takes (rejection sampling; none for a single candidate), so the later
    slots' picks change with it.
    With book_needed (B48) slot 0 draws from the lines in which the speaker cannot be understood."""
    white_sword_cave = gw.overworld.get_cave(Destination.WHITE_SWORD_CAVE, ItemCave)
    magical_sword_cave = gw.overworld.get_cave(Destination.MAGICAL_SWORD_CAVE, ItemCave)
    white_hearts = white_sword_cave.heart_requirement if white_sword_cave is not None else 0
    magical_hearts = magical_sword_cave.heart_requirement if magical_sword_cave is not None else 0
    pool_candidates = place_pool(rng, white_hearts, magical_hearts, book_needed)
    for cave, slot in ((white_sword_cave, WHITE_SWORD_TEXT_SLOT), (magical_sword_cave, MAGICAL_SWORD_TEXT_SLOT)):
        if cave is not None:
            pool_candidates[slot] = sword_cave_heart_quotes(slot, cave.heart_requirement)
    return pool_candidates


def select_final_texts(slot_texts: list[list[str] | None], pool_candidates: dict[int, list[list[str]]],
                       rng: IntRng, every_helpful_hint: bool = False) -> tuple[list[list[str]], list[bool]]:
    """Each slot's final text and whether the helpful overlay won: a coin when
    the slot has a helpful text, else (or on tails) a pool pick. HT-HINT-04: with
    every_helpful_hint the helpful text always wins, with no draw."""
    final_texts: list[list[str]] = []
    overlay_flags: list[bool] = []
    for slot in range(SLOT_COUNT):
        helpful_text = slot_texts[slot]
        pool = pool_candidates[slot]
        use_helpful = helpful_text is not None and (every_helpful_hint or rng.below(2) == 0)
        overlay_flags.append(use_helpful)
        if use_helpful:
            assert helpful_text is not None
            text = helpful_text
        elif pool:
            text = pool[rng.below(len(pool))]
        elif slot in UNSHOWN_SLOTS:
            text = [""]
        else:
            # No silent fallback: place_pool gives every shown slot a candidate.
            raise RuntimeError(f"HT-TEXT-02: slot {slot} has no pool candidates")
        final_texts.append(text)
    return final_texts, overlay_flags


def encode_hint_texts(final_texts: list[list[str]],
                      item_shuffle_result: ItemShuffleResult) -> tuple[list[list[int]], list[int]]:
    """Encode the texts and build their CPU pointers: the texts go to the
    extended bank in slot order, then the overflow region
    (rom_layout.place_hint_texts).

    HT-TEXT-02: the final pointers of slots 27 and 34 are replaced by other
    passes, so their drawn texts are never shown; the rebuild MAY skip them.
    They are written as empty texts, leaving the bank's room to the shown
    ones (HT-TEXT-03). The pointer exchange (HT-TEXT-04) is
    shuffle_dungeon_text (B19), which the flow runs on this pass's result."""
    encoded = [encode_text([""] if slot in UNSHOWN_SLOTS else text) for slot, text in enumerate(final_texts)]
    offsets = place_hint_texts([len(e) for e in encoded], CONSTERNATION_HINT_SLOTS)
    pointers = [cpu_address_in_bank1(offset) for offset in offsets]
    # Slot 27 is the toll text; the pointer is patched by B1 after this pass.
    # Without a toll (B22 and B23 off, FL-OFF-04) the slot keeps its own text.
    if item_shuffle_result.toll is not None:
        pointers[TOLL_SLOT] = TOLL_TEXT_POINTER[0] | (TOLL_TEXT_POINTER[1] << 8)
    return encoded, pointers
