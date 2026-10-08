"""What the hint texts convey (hints-behavior.md HT-HINT-01/02, HT-APP-A1),
measured without reading their wording, the same way on ZORA output and on
corpus ROMs.

Each side writes its own wording, so no text is matched against words:
1. The slot each text was composed for is recovered from its pointer's rank.
   Both sides lay the bodies out in slot order, and HT-TEXT-04 exchanges
   pointers only (slots 27 and 34 point outside the block).
2. Each composed slot's possible facts are read from the ROM: the region of
   a door screen, a level-9 quadrant, the compass family, a person pair's
   name form, the requirement candidates of HT-HINT-01.
3. Across a sample of ROMs, a text conveys a fact when it recurs and (nearly)
   every occurrence comes with that fact, and a pool text (which carries no
   map information, HT-TEXT-02) would agree that often only with
   probability under CHANCE_LIMIT. A text seen once is left undecided, on
   both sides, so both samples must be the same size.

The checkpoints (zora/measure/checkpoints/) record the facts per ROM and classify
in their Summary's cross-ROM `resolve` step.
"""
import math
from collections import Counter, defaultdict
from collections.abc import Hashable
from dataclasses import dataclass

from zora.generate.steps.hint_text import (
    ARROW_LINE,
    FORMS,
    HUMAN_FORM,
    INSIDE_MEANS,
    PERSON_SPRITES,
    REQUIREMENT_SLOTS,
    SAME_FORM,
    _quadrant,
    compass_family_name,
    inside_dungeon_needs,
    item_place,
    name_form,
    region_of_screen,
    requirement_candidates,
    sword_enters,
)
from zora.model.enums import Destination, Item, QuestVisibility, RoomAction
from zora.model.game_world import GameWorld
from zora.model.levels import GANON_LIST, ZELDA_LIST
from zora.model.overworld import ItemCave
from zora.model.rooms import Room

SLOT_COUNT = 45
OUTSIDE_BLOCK = (27, 34)             # pointers replaced by later passes (HT-TEXT-02)
CHANCE_LIMIT = 1e-3
MATCH_RATE = 0.9                     # share of a text's occurrences that must carry its fact
UNIVERSAL_FREQUENCY = 0.99           # a fact this common cannot be tested by agreement
UNIVERSAL_SHARE = 0.25               # ... and its text is then the one shown this often
LOCATION_SLOTS = {1: 33, 2: 38, 3: 20, 4: 21, 5: 22, 6: 23, 7: 28, 8: 31, 9: 32}  # after HT-HINT-02
SILVER_SLOT, GANON_OR_ZELDA_SLOT, ZELDA_OR_COMPASS_SLOT = 35, 36, 37
SHOW_SLOT, MEET_SLOT, WHITE_SWORD_SLOT = 6, 7, 3
# The third requirement text moves from 38 to 12 (HT-HINT-02)
COMPOSED_REQUIREMENT_SLOTS = tuple(12 if slot == 38 else slot for slot in REQUIREMENT_SLOTS)
# HT-HINT-01's person pairs, as ObjAnimations entries (giver, target)
SHOW_PAIR, MEET_PAIR, WHITE_SWORD_PAIR = (115, 117), (116, 110), (112, 109)
FIRST_NPC_ENTRY = 0x54               # EnemyData.overworld_npc_pointers[0]'s object type
MONSTER_BIT_LIST = 0x40              # list id bit 6 = the D byte's bit 7
WHITE_SWORD_CAVE_CODE, MEET_CAVE_CODE = 18, 19
HIDDEN = (QuestVisibility.SECOND_QUEST, QuestVisibility.NEITHER_QUEST)   # F bit 7 set
# Ties between equally likely facts: a Ganon-room text shows only in slot
# 36, where the Zelda-room fact is always present too.
KIND_ORDER = ("ganon", "zelda")

Key = tuple[Hashable, ...]


@dataclass(frozen=True)
class Shown:
    """One composed slot of one ROM: the text displayed for it and every
    fact its helpful entry could convey."""
    slot: int
    text: str
    facts: frozenset[Key]


# --- reading the ROM -----------------------------------------------------------

def has_hint_text(gw: GameWorld) -> bool:
    """Whether the ROM carries the 45-slot generated text (not PRG0's)."""
    return gw.hint_pointers is not None and len(gw.hint_pointers) == SLOT_COUNT


def composed_texts(gw: GameWorld) -> dict[int, str]:
    """Composed slot -> the text displayed for it, through the pointer ranks."""
    pointers = gw.hint_pointers
    assert pointers is not None and len(pointers) == SLOT_COUNT
    inside = [slot for slot in range(SLOT_COUNT) if slot not in OUTSIDE_BLOCK]
    by_address = sorted(inside, key=lambda slot: pointers[slot])
    return {composed: gw.quotes[final].text for composed, final in zip(inside, by_address, strict=True)}


def _lowest_screen(gw: GameWorld, code: int, flag_clear: bool) -> int:
    """The lowest-numbered screen with a destination code (and, when asked,
    its hidden flag clear)."""
    return next(s.screen_num for s in gw.overworld.screens if s.destination.value == code
                and not (flag_clear and s.quest_visibility in HIDDEN))


def _pair_form(gw: GameWorld, pair: tuple[int, int]) -> str:
    sprites = gw.enemies.overworld_npc_pointers
    giver, target = (sprites[entry - FIRST_NPC_ENTRY] for entry in pair)
    return name_form(giver, target)


def _list_id(room: Room) -> int:
    """HT-HINT-01's monster list id: C's low six bits, plus $40 for D's bit 7."""
    return room.monster_list | (MONSTER_BIT_LIST if room.has_monster_bit else 0)


def location_shown(gw: GameWorld) -> list[Shown]:
    """HT-HINT-01's level-location entries: each level's door-screen region."""
    if not has_hint_text(gw):
        return []
    texts = composed_texts(gw)
    return [Shown(slot, texts[slot],
                  frozenset({("location", level, region_of_screen(_lowest_screen(gw, level, True)))}))
            for level, slot in LOCATION_SLOTS.items()]


def name_shown(gw: GameWorld) -> list[Shown]:
    """Entries 10-12: the pairs' name forms, with the meet entry's region and
    the white-sword entry's item and region."""
    if not has_hint_text(gw):
        return []
    texts = composed_texts(gw)
    cave = gw.overworld.get_cave(Destination.WHITE_SWORD_CAVE, ItemCave)
    assert cave is not None
    meet_region = region_of_screen(_lowest_screen(gw, MEET_CAVE_CODE, True))
    ws_region = region_of_screen(_lowest_screen(gw, WHITE_SWORD_CAVE_CODE, False))
    return [
        Shown(SHOW_SLOT, texts[SHOW_SLOT], frozenset({("show", _pair_form(gw, SHOW_PAIR))})),
        Shown(MEET_SLOT, texts[MEET_SLOT],
              frozenset({("meet", _pair_form(gw, MEET_PAIR), meet_region)})),
        Shown(WHITE_SWORD_SLOT, texts[WHITE_SWORD_SLOT],
              frozenset({("white sword", _pair_form(gw, WHITE_SWORD_PAIR), cave.item, ws_region)})),
    ]


def trio_shown(gw: GameWorld, progressive_items: bool = False) -> list[Shown]:
    """The level-9 trio: slot 35 the silver arrow (with Progressive Items on, the first
    level-9 room holding an arrow-line item, PI-TEXT-01); 36 the Ganon or the Zelda room;
    37 the Zelda room or the compass family."""
    if not has_hint_text(gw):
        return []
    texts = composed_texts(gw)
    rooms = gw.levels[8].rooms
    arrows = ARROW_LINE if progressive_items else frozenset({Item.SILVER_ARROWS})
    silver = next((r for r in rooms if r.item in arrows), None)
    ganon = next(r for r in rooms if _list_id(r) == GANON_LIST)
    zelda = next(r for r in rooms if _list_id(r) == ZELDA_LIST)
    compass = next((r for r in rooms if r.item == Item.COMPASS
                    and r.room_action != RoomAction.LAST_BOSS), None)
    silver_fact = ("silver", _quadrant(gw, silver.room_num) if silver else "elsewhere")
    ganon_fact = ("ganon", _quadrant(gw, ganon.room_num))
    zelda_fact = ("zelda", _quadrant(gw, zelda.room_num))
    compass_fact = ("compass", compass_family_name(_list_id(compass), gw) if compass else None)
    return [Shown(SILVER_SLOT, texts[SILVER_SLOT], frozenset({silver_fact})),
            Shown(GANON_OR_ZELDA_SLOT, texts[GANON_OR_ZELDA_SLOT], frozenset({ganon_fact, zelda_fact})),
            Shown(ZELDA_OR_COMPASS_SLOT, texts[ZELDA_OR_COMPASS_SLOT],
                  frozenset({zelda_fact, compass_fact}))]


def requirement_shown(gw: GameWorld) -> list[Shown]:
    """The ten requirement texts: each could convey any candidate of
    HT-HINT-01 rebuilt from the ROM (ZORA's reading of rules 1-5)."""
    from zora.measure.checkpoints.acceptance import TRACKED_TYPES, item_places
    if not has_hint_text(gw):
        return []
    texts = composed_texts(gw)
    places = item_places(gw)
    # the pool's types where the ROM holds them in a level (a triforce piece,
    # which the spec's boss forms name in 62 of 3,447, is in every level:
    # its facts hold in every ROM and cannot be told apart; QUESTIONS #64.8)
    level_items = [(int(item), level) for item in TRACKED_TYPES
                   for level in places.get(item, []) if level in LOCATION_SLOTS]
    facts = frozenset(("requirement", *c.key)
                      for c in requirement_candidates(gw, level_items))
    return [Shown(slot, texts[slot], facts) for slot in COMPOSED_REQUIREMENT_SLOTS]


INSIDE_DUNGEON_KEYS = ("tested", "blocked", *(form for _means, form in INSIDE_MEANS))


def inside_dungeon_outcomes(gw: GameWorld) -> Counter[str]:
    """HT-HINT-01 rule 2 on the ROM's own item records: the records with a
    dungeon (tested), those the sword alone cannot enter (blocked), and the
    ladder, recorder and bow candidates formed."""
    from zora.measure.checkpoints.acceptance import TRACKED_TYPES, item_places
    places = item_places(gw)
    outcomes: Counter[str] = Counter()
    for item in TRACKED_TYPES:
        for level in places.get(item, []):
            if level not in LOCATION_SLOTS:
                continue
            place = item_place(gw.levels, level, int(item))
            if place is None:
                continue
            outcomes["tested"] += 1
            if not sword_enters(place):
                outcomes["blocked"] += 1
                outcomes.update(inside_dungeon_needs(place, int(item)))
    return outcomes


# --- classifying across ROMs ---------------------------------------------------

def _log_binomial_tail(hits: int, n: int, p: float) -> float:
    """log P(X >= hits) for X ~ Binomial(n, p)."""
    if p >= 1.0:
        return 0.0
    if p <= 0.0:
        return 0.0 if hits == 0 else -math.inf
    terms = [math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
             + k * math.log(p) + (n - k) * math.log1p(-p) for k in range(hits, n + 1)]
    top = max(terms)
    return top + math.log(sum(math.exp(t - top) for t in terms))


def classify(roms: list[list[Shown]]) -> list[list[Key | None]]:
    """Per ROM and composed slot: the fact its text conveys, or None (a pool
    text, or a text too rare to decide).

    A text conveys a fact when at least MATCH_RATE of its occurrences come
    with it (a finished-ROM replay of the dungeon walk misses a few, the
    #63.2 seeds) and a pool text would match that often only with
    probability under CHANCE_LIMIT. A fact every ROM holds (the silver arrow
    is never in level 9, VA-REJ-08) cannot be tested that way: its text is
    the one shown in more than UNIVERSAL_SHARE of the ROMs at its slot,
    which no pool string reaches (a slot draws among several pool
    candidates, and only on the lost half of the overlay)."""
    per_slot: dict[int, Counter[Key]] = defaultdict(Counter)
    shown_per_slot: Counter[int] = Counter()
    occurrences: dict[str, list[Shown]] = defaultdict(list)
    for rom in roms:
        for shown in rom:
            per_slot[shown.slot].update(shown.facts)
            shown_per_slot[shown.slot] += 1
            occurrences[shown.text].append(shown)

    def frequency(fact: Key, shown: Shown) -> float:
        return per_slot[shown.slot][fact] / shown_per_slot[shown.slot]

    conveys: dict[str, Key] = {}
    for text, seen in occurrences.items():
        if len(seen) < 2:
            continue
        hits = Counter(fact for shown in seen for fact in shown.facts)
        best: tuple[float, int, Key] | None = None
        for fact, count in hits.items():
            if count < MATCH_RATE * len(seen):
                continue
            mean_frequency = sum(frequency(fact, shown) for shown in seen) / len(seen)
            if mean_frequency >= UNIVERSAL_FREQUENCY:
                share = len(seen) / max(shown_per_slot[shown.slot] for shown in seen)
                score = -math.inf if share > UNIVERSAL_SHARE else 0.0
            else:
                score = _log_binomial_tail(count, len(seen), mean_frequency)
            rank = KIND_ORDER.index(fact[0]) if fact[0] in KIND_ORDER else 0
            if best is None or (round(score, 9), rank) < (round(best[0], 9), best[1]):
                best = (score, rank, fact)
        if best is not None and best[0] < math.log(CHANCE_LIMIT):
            conveys[text] = best[2]
    return [[conveys.get(shown.text) for shown in rom] for rom in roms]


# --- per-ROM results of each checkpoint --------------------------------------------

def location_results(roms: list[list[Shown]]) -> list[dict[str, bool]]:
    results = []
    for rom in classify(roms):
        # a ROM without hint text has no location entries (location_shown returns [])
        shown = dict(zip(LOCATION_SLOTS, rom, strict=False))
        results.append({f"L{level}": shown.get(level) is not None for level in LOCATION_SLOTS})
    return results


NAME_FORMS = (SAME_FORM, HUMAN_FORM, *PERSON_SPRITES.values())


def name_results(roms: list[list[Shown]]) -> list[Counter[str]]:
    """Entry 10's name form when shown, and which of entries 10-12 are shown."""
    results = []
    for rom in classify(roms):
        counts: Counter[str] = Counter()
        if not rom:
            results.append(counts)
            continue
        show, meet, white_sword = rom
        if show is not None:
            counts[str(show[1])] += 1
        counts["shown 6"] += show is not None
        counts["shown 7"] += meet is not None
        counts["shown 3"] += white_sword is not None
        results.append(counts)
    return results


TRIO_PARTS = ("35 silver", "36 ganon", "36 zelda", "37 zelda", "37 compass")


def trio_results(roms: list[list[Shown]]) -> list[Counter[str]]:
    # a ROM without hint text has no trio (trio_shown returns []): strict=False
    return [Counter(f"{slot} {fact[0]}" for slot, fact in
                    zip((SILVER_SLOT, GANON_OR_ZELDA_SLOT, ZELDA_OR_COMPASS_SLOT), rom, strict=False)
                    if fact is not None)
            for rom in classify(roms)]


def requirement_results(roms: list[list[Shown]]) -> list[Counter[str]]:
    return [Counter(str(fact[1]) for fact in rom if fact is not None) for rom in classify(roms)]


# --- slot 19's white-sword item hint (HT-TEXT-02) --------------------------------------

WHITE_SWORD_TEXT_SLOT = 19
ITEM_CODE_MASK = 0x3F                # the ware's item code; its top two bits are 0 in every final (HT-TEXT-02)
# HT-TEXT-02: the white-sword cave's middle ware that adds a slot-19
# candidate, as the case it names ($09 and $0A share one string).
WHITE_SWORD_HINT_CASES: dict[int, str] = {Item.RECORDER: "recorder", Item.SILVER_ARROWS: "bow", Item.BOW: "bow",
                                           Item.RED_RING: "red ring", Item.POWER_BRACELET: "power bracelet"}


def white_sword_case(gw: GameWorld) -> str | None:
    cave = gw.overworld.get_cave(Destination.WHITE_SWORD_CAVE, ItemCave)
    assert cave is not None
    return WHITE_SWORD_HINT_CASES.get(cave.item & ITEM_CODE_MASK)


def white_sword_hint_shown(gw: GameWorld) -> list[Shown]:
    """Slot 19's displayed text, with the white-sword cave's case as its
    possible fact (none when the ware adds no candidate)."""
    if not has_hint_text(gw):
        return []
    return [Shown(WHITE_SWORD_TEXT_SLOT, composed_texts(gw)[WHITE_SWORD_TEXT_SLOT],
                  frozenset({("white sword", white_sword_case(gw))}))]


def white_sword_hint_results(roms: list[list[Shown]]) -> list[dict[str, tuple[int, int]]]:
    """Per ROM: whether slot 19 shows an item hint (a text the classifier
    finds conveying one case: it recurs with that ware and only with it),
    counted among the ROMs whose ware is a case and among the others."""
    results = []
    for rom, facts in zip(roms, classify(roms), strict=True):
        if not rom:
            results.append({"when matching": (0, 0), "otherwise": (0, 0)})
            continue
        case = next(iter(rom[0].facts))[1]
        shown = int(facts[0] is not None and facts[0][1] is not None)
        results.append({"when matching": (shown, 1), "otherwise": (0, 0)} if case is not None
                       else {"when matching": (0, 0), "otherwise": (shown, 1)})
    return results


# --- which slots show pool text (HT-TEXT-02) ---------------------------------------

GREETING, BLANK, COMPOSED, POOL_TEXT = "greeting", "blank", "composed", "pool"
TEXT_KINDS = (POOL_TEXT, COMPOSED, GREETING, BLANK)
SHOWN_SLOTS = tuple(slot for slot in range(SLOT_COUNT) if slot not in OUTSIDE_BLOCK)


@dataclass(frozen=True)
class SlotTexts:
    """One ROM's displayed text per composed slot, and its composed-slot
    records (for the classifier)."""
    texts: dict[int, str]
    composed: list[Shown]


def slot_texts(gw: GameWorld) -> SlotTexts | None:
    if not has_hint_text(gw):
        return None
    return SlotTexts(composed_texts(gw),
                     location_shown(gw) + name_shown(gw) + trio_shown(gw) + requirement_shown(gw))


def text_kind_results(roms: list[SlotTexts | None]) -> list[Counter[str]]:
    """Per ROM, each slot's text kind as "<slot> <kind>":
    - greeting: a text slot 0 shows in more than UNIVERSAL_SHARE of the
      sample (HT-TEXT-02's greeting; in another slot, the fallback of a slot
      with no candidates);
    - blank: an empty text;
    - composed: a text the classifier finds conveying its slot's fact;
    - pool: any other text.
    Wording-free, so the same on ZORA output and corpus ROMs."""
    present = [rom for rom in roms if rom is not None]
    facts = iter(classify([rom.composed for rom in present]))
    slot0 = Counter(rom.texts[0] for rom in present)
    greetings = {text for text, count in slot0.items() if count > UNIVERSAL_SHARE * len(present)}
    results = []
    for rom in roms:
        counts: Counter[str] = Counter()
        if rom is not None:
            conveyed = {shown.slot for shown, fact in zip(rom.composed, next(facts), strict=True) if fact is not None}
            for slot, text in rom.texts.items():
                kind = (GREETING if text in greetings else BLANK if not text.strip("~|")
                        else COMPOSED if slot in conveyed else POOL_TEXT)
                counts[f"{slot} {kind}"] += 1
        results.append(counts)
    return results


__all__ = [
    "FORMS",
    "NAME_FORMS",
    "TRIO_PARTS",
    "Shown",
    "classify",
    "location_results",
    "location_shown",
    "name_results",
    "name_shown",
    "requirement_results",
    "requirement_shown",
    "trio_results",
    "trio_shown",
]
