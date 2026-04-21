"""
Hint randomizer: assigns hint text to GameWorld quote slots based on hint_mode.

Modes:
  VANILLA   — no-op; vanilla text preserved.
  BLANK     — all 38 quote slots set to empty text.
  COMMUNITY — 42 slots with random community quotes per slot.
  HELPFUL   — 42 slots with gameplay-aware item location hints + community filler.

Pipeline position: runs last, after assumed_fill and randomize_maze_directions.
expand_quote_slots() must be called before randomize_hints() in COMMUNITY/HELPFUL modes.
"""

import logging
from dataclasses import dataclass
from enum import IntEnum

from zora.data_model import (
    Destination,
    EntranceType,
    GameWorld,
    HintShop,
    Item,
    ItemCave,
    Overworld,
    OverworldDirection,
    OverworldItem,
    Quote,
    Shop,
    TakeAnyCave,
)
from zora.game_config import GameConfig, HintMode
from zora.rng import Rng

log = logging.getLogger(__name__)


class HintType(IntEnum):
    WOOD_SWORD_CAVE    = 0
    MAGICAL_SWORD_CAVE = 1
    ANY_ROAD           = 2
    LOST_HILLS_HINT    = 3   # hint shop slot 3 of shop 1
    MONEY_MAKING_GAME  = 4
    DOOR_REPAIR        = 5   # used for directional Lost Hills hint in community/helpful
    LETTER_CAVE        = 6
    DEAD_WOODS_HINT    = 7   # hint shop slot 2 of shop 2
    POTION_SHOP        = 8
    HINT_SHOP          = 9
    HINT_SHOP_1A       = 10
    HINT_SHOP_1B       = 11
    HINT_SHOP_2A       = 12
    HINT_SHOP_2B       = 13
    SHOP_1             = 14
    SHOP_2             = 15
    TAKE_ANY           = 16
    SECRET             = 17
    WHITE_SWORD_CAVE   = 18
    HINT_SHOP_1C       = 19  # hint shop 1, slot 3
    HINT_SHOP_2C       = 20  # hint shop 2, slot 3
    LEVEL_3            = 21
    LEVEL_4            = 22
    LEVEL_5            = 23
    LEVEL_5B           = 24
    BOMB_UPGRADE       = 25
    EXTRA_HINT         = 26
    MUGGER             = 27
    LEVEL_6            = 28
    LEVEL_6B           = 29
    LEVEL_7            = 30
    LEVEL_7B           = 31
    LEVEL_8            = 32
    LEVEL_8B           = 33
    TRIFORCE_CHECK     = 34
    LEVEL_9            = 35
    LEVEL_9B           = 36
    LEVEL_9C           = 37
    HUNGRY_ENEMY       = 38  # moved from 18
    LEVEL_1            = 39  # moved from 19
    LEVEL_2            = 40  # moved from 20


# ---------------------------------------------------------------------------
# Quote slot categorization
# ---------------------------------------------------------------------------

# Free hint slots eligible for nice-to-have helpful hints
_FREE_HINT_SLOTS: frozenset[HintType] = frozenset({
    HintType.HINT_SHOP,
    HintType.HINT_SHOP_1A,
    HintType.HINT_SHOP_1B,
    HintType.HINT_SHOP_2A,
    HintType.HINT_SHOP_2B,
    HintType.EXTRA_HINT,
    HintType.LEVEL_1,
    HintType.LEVEL_2,
    HintType.LEVEL_3,
    HintType.LEVEL_4,
    HintType.LEVEL_5,
    HintType.LEVEL_5B,
    HintType.LEVEL_6,
    HintType.LEVEL_6B,
    HintType.LEVEL_7,
    HintType.LEVEL_7B,
    HintType.LEVEL_8,
    HintType.LEVEL_8B,
    HintType.LEVEL_9,
    HintType.LEVEL_9B,
    HintType.LEVEL_9C,
})

# Paid hint shop slots
_PAID_HINT_SLOTS: frozenset[HintType] = frozenset({
    HintType.HINT_SHOP_1A,
    HintType.HINT_SHOP_1B,
    HintType.HINT_SHOP_1C,
    HintType.HINT_SHOP_2A,
    HintType.HINT_SHOP_2B,
    HintType.HINT_SHOP_2C,
})



# ---------------------------------------------------------------------------
# Community hint pools
# ---------------------------------------------------------------------------

COMMUNITY_HINTS: dict[HintType, list[str]] = {
    HintType.WOOD_SWORD_CAVE: [
        "IT'S DANGEROUS TO CODE|ALONE! TAKE THIS.",
        "THIS AIN'T|YOUR OLD MAN'S|RANDOMIZER!",
        "DID SOMEBODY SAY| ... WOOD?",
        "YAY! A POINTY STICK!",
        "GOOD LUCK! WE'RE ALL|... OOPS!|WRONG RANDOMIZER!",
        "IT'S DANGEROUS|TO GO ALONE.|SEE YA!",
        "SPEAK SOFTLY AND|CARRY A BIG STICK",
        "I'LL TAKE|\"S WORDS\"|FOR 100!",
        "FINDING THE WOOD|SWORD FILLS YOU|WITH DETERMINATION",
        "GET EQUIPPED|WITH THIS",
        "TAKE THE CANDLE|YOU COWARD!",
        "IT'S YOUR|POKEY STABBY!",
    ],
    HintType.TAKE_ANY: [
        "RED, RED, WINE",
        "AH YES, THE|TWO GENDERS ...",
        "PERRIER OR CHOCOLATES?",
        "EVERYWHERE YOU LOOK|EVERYWHERE YOU GO|THERE'S A HEART",
        "CANDYGRAM FOR LINK",
        "YOU GOTTA HAVE HEART",
        "PLEASE SELECT ITEM",
        "TAKE NEITHER ITEM.|JUST LEAVE.",
        "CAKE OR DEATH?",
        "EENIE, MEENIE,|MINEY, MO",
        "LIMIT ONE|PER CUSTOMER",
        "DA NA NA NA|NAAAAAAAAA",
    ],
    HintType.SECRET: [
        "BANANA. TAKE A BUCK!|BANANA. TAKE A BUCK!",
        "HERE'S SOME MONEY|GO SEE A STAR WAR",
        "SWEET, SWEET MONEY",
        "IF YOU GET A LOT OF|THESE, SOMETHING GOOD|IS BOUND TO HAPPEN",
        "I'D SHELL OUT|GOOD RUPEES|FOR A CONCH.",
        "THERE'S ALWAYS|MONEY IN THE|BANANA STAND",
        "TAKE YOUR BLOOD|MONEY AND GO.",
        "WE'RE IN THE MONEY|WE'RE IN THE MONEY",
        "I'M AN ATM!|AN AUTOMATED|TELLER MOBLIN",
        "CHA-CHING!",
        "CASH IT!",
        "I'M IN THE MONEY!",
        "GANON WANTS RANSOM|TAKE THIS!",
        "IF YOU PICK THIS UP|YOU'LL LOSE IT AT|THE NEXT DOOR REPAIR",
    ],
    HintType.LETTER_CAVE: [
        "THIS LETTER WILL|SELF-DESTRUCT|IN 5 SECONDS",
        "YOU'VE GOT MAIL!",
        "PLEASE ALLOW 5-7|BUSINESS DAYS|FOR DELIVERY",
        "HEY EVERYONE|I'VE GOT PAPER!",
        "FILL THIS AT|YOUR LOCAL PHARMACY",
    ],
    HintType.POTION_SHOP: [
        "TAKE TWO POTIONS|AND CALL ME|IN THE MORNING",
        "SIDE EFFECTS MAY|INCLUDE: FULL HEALTH",
        "YOUR PRESCRIPTION|IS READY",
        "INSURANCE MAY NOT|COVER THIS",
        "SHAKE WELL|BEFORE USE",
        "WOULD YOU LIKE TO|OPT INTO AUTO-REFILLS?",
        "MY POTIONS ARE TOO|STRONG FOR YOU|TRAVELER",
        "I'VE GOT A FEVER AND|THE ONLY PRESCRIPTION|IS MORE COWBELL",
        "WE ONLY SERVE|BEPIS PRODUCTS|SORRY",
        "IS PEPSI OKAY?",
    ],
    HintType.DOOR_REPAIR: [
        "PLEASE LEAVE A TIP|FOR YOUR DOOR REPAIRER",
        "THANK YOU FOR USING|CASHLESS TOLLING",
        "EZ|PASS|PAID",
        "DON'T AWOO.|350 RUPEE PENALTY.",
        "STAND CLEAR OF|THE CLOSING DOORS|PLEASE",
        "HELP TEMMIE PAY|FOR COOL LEG",
        "QUICK, PRESS UP|AND A BEFORE I|TAKE YOUR MONEY!",
        "THAT DOOR REALLY|TIED THE ROOM TOGETHER",
        "TOSS A RUPEE|TO YOUR WITCHER",
        "YOU ARE THE|WEAKEST LINK|GOODBYE!",
        "TIME BOMB SET|GET OUT FAST!",
        "DO YOU KNOW HOW MANY|DOORS I SOLD TODAY?",
        "SHOW ME THE MONEY!",
        "YOUR HEAD A SPLODE",
        "BAGU OWES ME|20 RUPEES",
        "HERE'S A RUPOOR|FOR YOUR TROUBLES",
        "THIS IS THE FEE FEE",
        "TAX FOR TRIFORCE",
        "NOW I HAVE TO GO BACK|TO HOME DEPOT",
        "DO THEY SELL DOORS|AT WAL-MART, OR|JUST WALLS?",
        "I BET YOU THOUGHT|THIS WAS GOING TO BE|A LARGE SECRET",
        "IT'S ME, HI|I'M THE PROBLEM|IT'S ME",
        "SHHH!|THIS IS A LIBRARY",
        "NOIDS NOIDS NOIDS",
        "YOU HAVE BEEN|RECRUITED BY|THE STAR LEAGUE",
        "SKIP ROOM",
        "I BET YOU WISHED|YOU HAD MORE MONEY",
        "EXCUSE ME|THIS IS A WENDY'S",
    ],
    HintType.SHOP_1: [
        "NOW OFFERING|CURBSIDE PICKUP",
        "SHOP TIL YOU DROP!",
        "FRESH IMPORTS FROM|KOHOLINT ISLAND",
        "COME BACK TOMORROW|FOR A TWO FOR ONE|SALE",
        "I'D BUY THAT|FOR A RUPEE",
        "WOAH THERE|I'VE GOT SOME NEAT|JUNK FOR SALE",
        "YOU CAN PROBABLY|FIND THIS CHEAPER|ONLINE",
        "VISIT OUR OTHER|LOCATION IN THE|WESTLAKE MALL",
        "DOWNLOAD OUR APP TO|EARN DISCOUNTS ON|FUTURE PURCHASES!",
        "I'M NOT LIKE THOSE|OTHER MERCHANTS!",
        "MATH IS HARD.|LET'S GO SHOPPING!",
        "I WASN'T EVEN SUPPOSED|TO BE HERE TODAY",
        "CAN I OFFER YOU|A NICE EGG IN|THIS TRYING TIME?",
    ],
    HintType.SHOP_2: [
        "AS SEEN ON TV",
        "USE DISCOUNT CODE|'ZORA' FOR 10 PERCENT|OFF YOUR NEXT ORDER",
        "AND IT CAN BE YOURS|IF THE PRICE IS RIGHT!",
        "SHOP LOCAL, SUPPORT|SMALL BUSINESSES",
        "HELLO TRAVELLER!|HOW CAN I HELP YOU?",
        "I HAVE GREAT DEALS|IN STORE FOR YOU",
        "THE MIDDLE ITEM IS|MY FAMILY HEIRLOOM",
        "GET IN, LOSER,|WE'RE GOING SHOPPING",
        "SIGN UP FOR THE STORE|CARD TO GET 10 PERCENT|OFF YOUR 1ST PURCHASE",
        "SEE BACK OF RECEIPT|FOR THE RETURN POLICY",
        "SHOP SMART!|SHOP S-MART!",
        "MERCHANDIZING!|WHERE THE REAL MONEY|FROM THE MOVIE IS MADE",
    ],
    HintType.ANY_ROAD: [
        "I CHALLENGE YOU TO|A STAIRING CONTEST!",
        "LUDICROUS SPEED. GO!",
        "DOOR 1, 2, OR 3?",
        "DO YOU KNOW THE WAY|TO SAN JOSE?",
        "JUST KEEP SWIMMING!",
        "YOU KNOW BAGU?|THEN I WILL HELP|YOU CROSS",
        "WELCOME TO|WARP ZONE",
        "BE CAREFUL, STAIRS|ARE ALWAYS UP TO|SOMETHING",
        "MY ADVICE? TAKE THE|ROAD LESS TRAVELLED",
        "IN CASE OF EMERGENCY|PLEASE USE STAIRWAYS",
        "WHICH WAY TO|DENVER?",
        "THIS IS A|LOST WOODS-BOUND|EXPRESS TRAIN",
    ],
    HintType.HUNGRY_ENEMY: [
        "GRUMBLE GRUMBLE ...|SERIOUSLY, YOU WERE|SUPPOSED TO BRING FOOD",
        "OM NOM NOM NOM TIME?",
        "ARE YOU GOING|TO EAT THAT?",
        "FEED ME SEYMOUR!",
        "MUMBLE MUMBLE|SOMETHING ABOUT FOOD",
        "BUT YOU'RE|STILL HUNGRY ...",
        "DO YOU HAVE|A VEGAN OPTION?",
        "ARE YOU MY UBER EATS|DELIVERY CARRIER?",
        "C IS FOR COOKIE|THAT'S GOOD ENOUGH|FOR ME",
        "I'VE HAD ONE, YES.|BUT WHAT ABOUT|SECOND BREAKFAST?",
        "IF YOU FIND|MY LUNCH,|DON'T EAT IT.",
        "IF YOU WERE A BURRITO,|WHAT KIND OF A|BURRITO WOULD YOU BE?",
        "I AM ON A SEAFOOD|DIET. EVERY TIME|I SEE FOOD, I EAT IT.",
        "THE SOUP IS|FOR MY FAMILY.",
        "I'M A VEGETARIAN.|DON'T BRING MEAT IN|HERE OR I'M LEAVING!",
        "I ONLY CAME FOR CAKE",
        "THE CAKE IS A LIE",
        "NO SOUP FOR YOU",
    ],
    HintType.BOMB_UPGRADE: [
        "BADA BING|BADA BANG|BADA BOOM",
        "HI, I'M BOMB BARKER|PLEASE HAVE YOUR PETS|SPAYED OR NEUTERED!",
        "SPLOOSH!|KABOOM!",
        "SOMEONE SET UP US|THE BOMB UPGRADE",
        "KEEP TALKING AND|NOBODY EXPLODES",
        "YEAH, YOU AND|EVERYONE ELSE WANTS|TO HOARD BOMBS",
        "COOL GUYS DON'T|LOOK AT EXPLOSIONS",
        "EXPLOSIONS!",
        "SELLS FOR 255 RUPEES|ON EBAY",
        "PLEASE DON'T JOKE|ABOUT THESE AT|AIRPORT SECURITY",
    ],
    HintType.MONEY_MAKING_GAME: [
        "WHAT HAPPENS IN VEGAS|STAYS IN VEGAS!",
        "LET'S PLAY MONEY|TAKING GAME",
        "THE HOUSE ALWAYS WINS",
        "TRENDY GAME|ONE PLAY|10 RUPEES",
        "THE CURRENT LOTTO|JACKPOT IS|255 RUPEES",
        "LET'S GET LUCKY!",
        "HAVE A RUPEE,|LEAVE A RUPEE",
        "BONUS CHANCE||PRESS 'A' BUTTON",
        "BIG BUCKS!|NO WHAMMIES!|STOP!",
    ],
    HintType.TRIFORCE_CHECK: [
        "MASK OR FACE COVERING|REQUIRED FOR ENTRY",
        "COME BACK AS|ADULT LINK",
        "YOU MUST CONSTRUCT|ADDITIONAL PYLONS",
        "QUIT WASTING|MY TIME",
        "IS THIS A|DOKI DOKI PANIC|REMAKE?",
        "ONE DOES NOT|SIMPLY WALK INTO|DEATH MOUNTAIN",
        "YOU SHALL NOT PASS!",
        "COME BACK LATER",
        "LET ME IN!",
        "NO SOUP FOR YOU!|COME BACK ONE YEAR|NEXT!",
    ],
    HintType.MUGGER: [
        "GENDER ISN'T BINARY|BUT THIS CHOICE IS",
        "I'M SORRY,|WE DON'T|TAKE DISCOVER",
        "USE E-Z PASS TO|SAVE TIME PAYING TOLLS",
        "FOR YOUR CONVENIENCE|WE ACCEPT MULTIPLE|PAYMENT METHODS",
        "GOTTA PAY TO PLAY!",
        "PLEASE INSERT COIN|TO CONTINUE",
        "I KNOW ...|I DON'T LIKE IN-APP|PURCHASES EITHER",
    ],
    HintType.HINT_SHOP: [
        "SORRY. I KNOW NOTHING",
        "I CAN SEE THE FUTURE",
        "THIS IS NOT|LEGAL ADVICE",
        "SPOILERS!",
        "TIME TO SPILL THE TEA",
        "YOU'RE GONNA NEED|A BIGGER BOAT",
    ],
    HintType.MAGICAL_SWORD_CAVE: [],   # falls through to _OTHER_POOL
    HintType.WHITE_SWORD_CAVE:   [],   # falls through to _OTHER_POOL
}

# Catch-all pool used when a slot has no dedicated pool or its pool is empty.
_OTHER_POOL: list[str] = [
    "HONK!",
    "HEJ",
    "!LFG",
    "THIS COULD|BE YOU!",
    "WELCOME TO THE|COFFEE ZONE",
    "ARE YOU IN THE|CATBIRD SEAT?",
    "MEOW MEOW MEOW MEOW",
    "HAPPY BIRTHDAY|TO YOU!",
    "READ THE|WIKI ALREADY!",
    "GO LOCAL|SPORTS TEAM!",
    "STAY AWHILE|AND LISTEN",
    "YOU TEACH ME|A SPELL",
    "BIG BUCKS|NO WHAMMYS",
    "YOU ARE THE|WEAKEST LINK",
    "LINK I AM|YOUR FATHER",
    "THERE'S NO WIFI|HERE",
    "A WILD LINK|APPEARS",
    "PRAISE THE SUN",
    "LINK.EXE HAS|STOPPED WORKING",
    "IS THIS A|PEDESTAL SEED?",
    "DOES SPEC ROCK|WEAR GLASSES?",
    "IF YOU CAN READ THIS|YOU DON'T NEED|NEW GLASSES",
    "ZZZZZZZZ ... |ZZZZZZZZ... |ARE THEY GONE YET?",
    "THIS LINE HERE|IS MOSTLY|FILLER",
    "IT'S ME, HI|I'M THE PROBLEM,|IT'S ME",
    "WHAT THE FORK|IS A CHIDI?",
]


# ---------------------------------------------------------------------------
# Heart requirement (numerical) hints for sword caves
# ---------------------------------------------------------------------------

NUMERICAL_HINTS: dict[int, list[str]] = {
    4:  [
        "FOUR SQUARE",
        "FANTASTIC FOUR",
        "SOMETHING ABOUT FOUR",
        "FOUR SWORDS ADVENTURE",
    ],
    5:  [
        "FIVE IS RIGHT OUT",
        "FIVE PIXELS|FROM THE EDGE",
        "GIVE ME FIVE",
        "HIGH FIVE",
        "TAKE FIVE",
        "HOW IT FEELS TO|CHEW FIVE GUM",
    ],
    6:  [
        "SIX SEVEN",
        "WHY WAS SIX|AFRAID OF SEVEN?",
        "SIXTH SENSE",
        "DEEP SIX",
    ],
    10: [
        "AM I A TEN OR WHAT?",
        "10TH HEART|HAS THE ITEM",
        "TENTEN",
        "HANG TEN",
        "TEN OUT OF TEN",
        "POWER OF TEN",
    ],
    11: [
        "THESE GO TO ELEVEN",
        "ELEVENSIES!",
        "OCEAN'S ELEVEN",
        "11!!!!!",
    ],
    12: [
        "THE DIRTY DOZEN",
        "A DOZEN HEARTS",
        "TWELVE LABORS",
        "TWELVE IS SO VANILLA",
    ],
}


# ---------------------------------------------------------------------------
# Direction name maps for hint text generation
# ---------------------------------------------------------------------------

_LOST_HILLS_DIR_NAMES: dict[OverworldDirection, str] = {
    OverworldDirection.UP_NORTH:   "UP",
    OverworldDirection.DOWN_SOUTH: "DOWN",
    OverworldDirection.RIGHT_EAST: "RIGHT",
}

_DEAD_WOODS_DIR_NAMES: dict[OverworldDirection, str] = {
    OverworldDirection.UP_NORTH:   "NORTH",
    OverworldDirection.DOWN_SOUTH: "SOUTH",
    OverworldDirection.LEFT_WEST:  "WEST",
}


def _lost_hills_hint_text(directions: list[OverworldDirection]) -> str:
    d = [_LOST_HILLS_DIR_NAMES[v] for v in directions]
    return f"GO {d[0]}, {d[1]},|{d[2]}, {d[3]}|THE MOUNTAIN AHEAD"


def _dead_woods_hint_text(directions: list[OverworldDirection]) -> str:
    d = [_DEAD_WOODS_DIR_NAMES[v] for v in directions]
    return f"GO {d[0]}, {d[1]},|{d[2]}, {d[3]} TO|THE FOREST OF MAZE"


# ---------------------------------------------------------------------------
# Helpful hint generation
# ---------------------------------------------------------------------------

# Items that give progression hints (go in paid hint shop slots)
HINTABLE_PROGRESSION_ITEMS: frozenset[Item] = frozenset({
    Item.RAFT,
    Item.LADDER,
    Item.RECORDER,
    Item.BOW,
    Item.POWER_BRACELET,
    Item.SILVER_ARROWS,
})

# Items that give nice-to-have hints (go in free level/hint slots)
HINTABLE_NICE_TO_HAVE_ITEMS: frozenset[Item] = frozenset({
    Item.WAND,
    Item.BOOK,
    Item.BLUE_RING,
    Item.RED_RING,
    Item.MAGICAL_BOOMERANG,
    Item.RED_CANDLE,
    Item.MAGICAL_KEY,
    Item.MAGICAL_SHIELD,
    Item.LETTER,
})

_ALL_HINTABLE_ITEMS: frozenset[Item] = HINTABLE_PROGRESSION_ITEMS | HINTABLE_NICE_TO_HAVE_ITEMS

# Entrance type → hint phrase
_ENTRANCE_PHRASES: dict[EntranceType, str] = {
    EntranceType.OPEN:                    "EXPLORE AN OPEN CAVE",
    EntranceType.BOMB:                    "EXPLODE AN ENTRANCE",
    EntranceType.CANDLE:                  "BURN A BUSH",
    EntranceType.RECORDER:                "TOOT THE TOOTER",
    EntranceType.POWER_BRACELET:          "MOVE A BOULDER",
    EntranceType.RAFT:                    "SAIL THE SEA",
    EntranceType.LADDER:                  "STEP ACROSS THE WATER",
    EntranceType.LADDER_AND_BOMB:         "STEP ACROSS THE WATER",
    EntranceType.RAFT_AND_BOMB:           "SAIL THE SEA",
    EntranceType.POWER_BRACELET_AND_BOMB: "MOVE A BOULDER",
    EntranceType.NONE:                    "EXPLORE AN OPEN CAVE",
    EntranceType.LOST_HILLS_HINT:         "HIKE THE LOST HILLS",
    EntranceType.DEAD_WOODS_HINT:         "SOLVE THE DEAD WOODS",
}

# Progressive upgrade item name substitutions (when progressive_items is on)
_PROGRESSIVE_NAME_OVERRIDES: dict[Item, str] = {
    Item.WOOD_ARROWS:  "ARROW UPGRADE",
    Item.BLUE_CANDLE:  "CANDLE UPGRADE",
    Item.BLUE_RING:    "RING UPGRADE",
    Item.WOOD_SWORD:   "SWORD UPGRADE",
}


@dataclass
class HintableLocation:
    item: Item
    entrance_type: EntranceType


def _entrance_type_for_destination(overworld: Overworld, dest: Destination) -> EntranceType:
    """Return the entrance type of the overworld screen whose destination matches dest."""
    for screen in overworld.screens:
        if screen.destination == dest:
            return screen.entrance_type
    return EntranceType.NONE


def _item_display_name(item: Item, progressive_items: bool) -> str:
    """Return the display name for an item in hint text."""
    if progressive_items and item in _PROGRESSIVE_NAME_OVERRIDES:
        return _PROGRESSIVE_NAME_OVERRIDES[item]
    return item.name.replace("_", " ")


def _build_helpful_hint_text(location: HintableLocation, progressive_items: bool) -> str:
    """Build a three-line helpful hint string for a hintable location."""
    phrase = _ENTRANCE_PHRASES.get(location.entrance_type, "EXPLORE AN OPEN CAVE")
    name = _item_display_name(location.item, progressive_items)
    return f"{phrase}|TO FIND|THE {name}"


def _scan_hintable_locations(game_world: GameWorld) -> list[HintableLocation]:
    """Scan the GameWorld for items in the hintable sets and return their locations."""
    results: list[HintableLocation] = []
    overworld = game_world.overworld

    # Dungeon rooms and staircase rooms
    for level in game_world.levels:
        dest = Destination(level.level_num)  # LEVEL_1 = 0x01, etc.
        entrance_type = _entrance_type_for_destination(overworld, dest)
        for room in level.rooms:
            if room.item in _ALL_HINTABLE_ITEMS:
                results.append(HintableLocation(item=room.item, entrance_type=entrance_type))
        for stair in level.staircase_rooms:
            if stair.item is not None and stair.item in _ALL_HINTABLE_ITEMS:
                results.append(HintableLocation(item=stair.item, entrance_type=entrance_type))

    # Overworld caves
    for cave in overworld.caves:
        if isinstance(cave, OverworldItem):
            if cave.item in _ALL_HINTABLE_ITEMS:
                entrance_type = _entrance_type_for_destination(overworld, cave.destination)
                results.append(HintableLocation(item=cave.item, entrance_type=entrance_type))
        elif isinstance(cave, ItemCave):
            if cave.item in _ALL_HINTABLE_ITEMS:
                entrance_type = _entrance_type_for_destination(overworld, cave.destination)
                results.append(HintableLocation(item=cave.item, entrance_type=entrance_type))
        elif isinstance(cave, Shop):
            for shop_item in cave.items:
                if shop_item.item in _ALL_HINTABLE_ITEMS:
                    entrance_type = _entrance_type_for_destination(overworld, cave.destination)
                    results.append(HintableLocation(item=shop_item.item, entrance_type=entrance_type))
        elif isinstance(cave, TakeAnyCave):
            for item in cave.items:
                if item in _ALL_HINTABLE_ITEMS:
                    entrance_type = _entrance_type_for_destination(overworld, cave.destination)
                    results.append(HintableLocation(item=item, entrance_type=entrance_type))

    return results


# ---------------------------------------------------------------------------
# Quote slot expansion
# ---------------------------------------------------------------------------

def expand_quote_slots(game_world: GameWorld, config: GameConfig, rng: Rng) -> None:
    """Add extra quote slots and remap cave quote_ids for Community/Helpful modes.

    Must be called before randomize_hints(). In Vanilla/Blank modes this is a
    no-op so the pipeline can always include it unconditionally.

    Slot assignments after expansion:
      18 (WHITE_SWORD_CAVE)  — White Sword cave (split from quote_id 1; magical sword keeps 1)
      10 (HINT_SHOP_1A)      — Hint Shop 1, slot 1
      11 (HINT_SHOP_1B)      — Hint Shop 1, slot 2
      19 (HINT_SHOP_1C)      — Hint Shop 1, slot 3
      12 (HINT_SHOP_2A)      — Hint Shop 2, slot 1
      13 (HINT_SHOP_2B)      — Hint Shop 2, slot 2
      20 (HINT_SHOP_2C)      — Hint Shop 2, slot 3
    """
    if config.hint_mode not in (HintMode.COMMUNITY, HintMode.HELPFUL):
        return

    # Slots that moved above the vanilla 0-37 range need new Quote objects.
    # Slots that moved into the vanilla range (WHITE_SWORD_CAVE=18, HINT_SHOP_1C=19,
    # HINT_SHOP_2C=20) reuse existing quotes — their text is overwritten by
    # randomize_hints() anyway.
    new_slots_text = {
        HintType.HUNGRY_ENEMY: "GRUMBLE,GRUMBLE...",
        HintType.LEVEL_1:      "EASTMOST PENNINSULA IS THE SECRET.",
        HintType.LEVEL_2:      "DODONGO DISLIKES SMOKE.",
    }

    # Append new Quote objects for generated ids
    existing_ids = {q.quote_id for q in game_world.quotes}
    for qid, text in new_slots_text.items():
        if qid not in existing_ids:
            game_world.quotes.append(Quote(quote_id=qid, text=text))

    # Remap White Sword cave (Magical Sword keeps HintType.MAGICAL_SWORD_CAVE)
    for cave in game_world.overworld.caves:
        if isinstance(cave, ItemCave) and cave.destination == Destination.WHITE_SWORD_CAVE:
            cave.quote_id = HintType.WHITE_SWORD_CAVE
            break

    _remap_hint_shop_all_slots(game_world, Destination.HINT_SHOP_1, [
        HintType.HINT_SHOP_1A, HintType.HINT_SHOP_1B, HintType.HINT_SHOP_1C,
    ])
    _remap_hint_shop_all_slots(game_world, Destination.HINT_SHOP_2, [
        HintType.HINT_SHOP_2A, HintType.HINT_SHOP_2B, HintType.HINT_SHOP_2C,
    ])


def _remap_hint_shop_all_slots(
    game_world: GameWorld,
    destination: Destination,
    new_quote_ids: list[int],
) -> None:
    """Remap all three hint shop slots to the given quote_ids."""
    for cave in game_world.overworld.caves:
        if isinstance(cave, HintShop) and cave.destination == destination:
            for i, new_id in enumerate(new_quote_ids):
                if i < len(cave.hints):
                    cave.hints[i].quote_id = new_id
            return


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _pool_for(hint_type: HintType) -> list[str]:
    pool = COMMUNITY_HINTS.get(hint_type, [])
    return pool if pool else _OTHER_POOL


def _sample_hint(hint_type: HintType, rng: Rng) -> str:
    return rng.choice(_pool_for(hint_type))


def _quote_by_id(game_world: GameWorld, quote_id: int) -> Quote | None:
    for q in game_world.quotes:
        if q.quote_id == quote_id:
            return q
    return None


# ---------------------------------------------------------------------------
# Mode implementations
# ---------------------------------------------------------------------------

def _apply_blank_mode(game_world: GameWorld) -> None:
    """Set all quote texts to empty (serialized as 0xFF blank)."""
    for quote in game_world.quotes:
        quote.text = ""


def _apply_special_overrides(
    game_world: GameWorld,
    config: GameConfig,
    rng: Rng,
    filled_ids: set[int],
) -> None:
    """Apply heart-requirement and directional hint overrides.

    Fills filled_ids with the quote_ids that were assigned, so the main
    sampling loop skips them.
    """
    # Heart requirement hints
    if config.randomize_white_sword_hearts:
        white_quote = _quote_by_id(game_world, HintType.WHITE_SWORD_CAVE)
        if white_quote is not None:
            heart_count = _get_white_sword_heart_requirement(game_world)
            pool = NUMERICAL_HINTS.get(heart_count, _OTHER_POOL)
            white_quote.text = rng.choice(pool)
            filled_ids.add(HintType.WHITE_SWORD_CAVE)
            log.debug("White sword heart hint (%d hearts): %r", heart_count, white_quote.text)

    if config.randomize_magical_sword_hearts:
        magical_quote = _quote_by_id(game_world, HintType.MAGICAL_SWORD_CAVE)
        if magical_quote is not None:
            heart_count = _get_magical_sword_heart_requirement(game_world)
            pool = NUMERICAL_HINTS.get(heart_count, _OTHER_POOL)
            magical_quote.text = rng.choice(pool)
            filled_ids.add(HintType.MAGICAL_SWORD_CAVE)
            log.debug("Magical sword heart hint (%d hearts): %r", heart_count, magical_quote.text)

    # Directional hints — written to the free hint cave slots (LOST_HILLS_HINT / DEAD_WOODS_HINT).
    # In community/helpful mode the hint shop slots are remapped to share these same quote_ids.
    if config.randomize_lost_hills:
        lost_quote = _quote_by_id(game_world, HintType.LOST_HILLS_HINT)
        if lost_quote is not None:
            lost_quote.text = _lost_hills_hint_text(
                game_world.overworld.lost_hills_directions
            )
            filled_ids.add(HintType.LOST_HILLS_HINT)
            log.debug("Lost Hills hint: %r", lost_quote.text)

    if config.randomize_dead_woods:
        dead_quote = _quote_by_id(game_world, HintType.DEAD_WOODS_HINT)
        if dead_quote is not None:
            dead_quote.text = _dead_woods_hint_text(
                game_world.overworld.dead_woods_directions
            )
            filled_ids.add(HintType.DEAD_WOODS_HINT)
            log.debug("Dead Woods hint: %r", dead_quote.text)


def _get_white_sword_heart_requirement(game_world: GameWorld) -> int:
    for cave in game_world.overworld.caves:
        if isinstance(cave, ItemCave) and cave.destination == Destination.WHITE_SWORD_CAVE:
            return cave.heart_requirement
    return 5  # fallback


def _get_magical_sword_heart_requirement(game_world: GameWorld) -> int:
    for cave in game_world.overworld.caves:
        if isinstance(cave, ItemCave) and cave.destination == Destination.MAGICAL_SWORD_CAVE:
            return cave.heart_requirement
    return 10  # fallback


_HINT_SHOP_PRICE_RANGE: list[int] = list(range(10, 51))


def _randomize_hint_shop_prices(game_world: GameWorld, rng: Rng) -> None:
    """Randomize hint shop prices to 10-50 rupees per slot."""
    for cave in game_world.overworld.caves:
        if isinstance(cave, HintShop):
            for hint_item in cave.hints:
                hint_item.price = rng.choice(_HINT_SHOP_PRICE_RANGE)


def _apply_community_mode(
    game_world: GameWorld,
    config: GameConfig,
    rng: Rng,
) -> None:
    """Fill all quote slots with community hints (with special overrides applied first)."""
    filled_ids: set[int] = set()
    _apply_special_overrides(game_world, config, rng, filled_ids)

    for quote in game_world.quotes:
        if quote.quote_id in filled_ids:
            continue
        hint_type = _try_hint_type(quote.quote_id)
        if hint_type is not None:
            text = _sample_hint(hint_type, rng)
            log.debug("Community hint [%d] (%s): %r", quote.quote_id, hint_type.name, text)
        else:
            text = rng.choice(_OTHER_POOL)
            log.debug("Community hint [%d] (no type): %r", quote.quote_id, text)
        quote.text = text

    _randomize_hint_shop_prices(game_world, rng)


def _apply_helpful_mode(
    game_world: GameWorld,
    config: GameConfig,
    rng: Rng,
) -> None:
    """Fill quote slots with helpful item-location hints and community filler."""
    filled_ids: set[int] = set()
    _apply_special_overrides(game_world, config, rng, filled_ids)

    # Scan for hintable item locations
    locations = _scan_hintable_locations(game_world)
    rng.shuffle(locations)

    progression = [loc for loc in locations if loc.item in HINTABLE_PROGRESSION_ITEMS]
    nice_to_have = [loc for loc in locations if loc.item in HINTABLE_NICE_TO_HAVE_ITEMS]

    # Sort paid hint shop slots in fixed order
    paid_slot_ids = [
        HintType.HINT_SHOP_1A.value,
        HintType.HINT_SHOP_1B.value,
        HintType.HINT_SHOP_1C.value,
        HintType.HINT_SHOP_2A.value,
        HintType.HINT_SHOP_2B.value,
        HintType.HINT_SHOP_2C.value,
    ]

    # Assign progression items to paid hint shop slots
    for slot_id in paid_slot_ids:
        if slot_id in filled_ids:
            continue
        quote = _quote_by_id(game_world, slot_id)
        if quote is None:
            continue
        if progression:
            loc = progression.pop(0)
            quote.text = _build_helpful_hint_text(loc, config.progressive_items)
            log.debug("Helpful paid hint [%d]: %r", slot_id, quote.text)
        else:
            try:
                hint_type = HintType(slot_id)
            except ValueError:
                hint_type = HintType.EXTRA_HINT
            quote.text = _sample_hint(hint_type, rng)
            log.debug("Helpful paid hint fallback [%d]: %r", slot_id, quote.text)
        filled_ids.add(slot_id)

    # Assign nice-to-have items to eligible free slots
    free_slot_quotes = [
        q for q in game_world.quotes
        if q.quote_id not in filled_ids
        and _try_hint_type(q.quote_id) in _FREE_HINT_SLOTS
    ]

    for quote in free_slot_quotes:
        if nice_to_have:
            loc = nice_to_have.pop(0)
            quote.text = _build_helpful_hint_text(loc, config.progressive_items)
            log.debug("Helpful free hint [%d]: %r", quote.quote_id, quote.text)
        else:
            try:
                hint_type = HintType(quote.quote_id)
            except ValueError:
                hint_type = HintType.EXTRA_HINT
            quote.text = _sample_hint(hint_type, rng)
            log.debug("Helpful free hint fallback [%d]: %r", quote.quote_id, quote.text)
        filled_ids.add(quote.quote_id)

    # Fill all remaining slots with community hints
    for quote in game_world.quotes:
        if quote.quote_id in filled_ids:
            continue
        filler_hint_type = _try_hint_type(quote.quote_id)
        if filler_hint_type is not None:
            text = _sample_hint(filler_hint_type, rng)
            log.debug("Helpful community filler [%d] (%s): %r", quote.quote_id, filler_hint_type.name, text)
        else:
            text = rng.choice(_OTHER_POOL)
            log.debug("Helpful community filler [%d] (no type): %r", quote.quote_id, text)
        quote.text = text
        filled_ids.add(quote.quote_id)

    _randomize_hint_shop_prices(game_world, rng)


def _try_hint_type(quote_id: int) -> HintType | None:
    """Return the HintType for a quote_id, or None if not found."""
    try:
        return HintType(quote_id)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def randomize_hints(game_world: GameWorld, config: GameConfig, rng: Rng) -> None:
    """Assign hint text to all Quote slots in game_world according to hint_mode.

    Mutates game_world.quotes in place. Must be called after:
      - expand_quote_slots() (adds slots 38-42)
      - randomize_maze_directions() (finalizes direction sequences)
      - assumed_fill() (finalizes item placements)

    Args:
        game_world: Parsed world; quotes list is mutated in place.
        config:     Resolved game config.
        rng:        Seeded RNG for deterministic output.
    """
    mode = config.hint_mode

    if mode == HintMode.VANILLA:
        return

    if mode == HintMode.BLANK:
        _apply_blank_mode(game_world)
        return

    if mode == HintMode.COMMUNITY:
        _apply_community_mode(game_world, config, rng)
        return

    if mode == HintMode.HELPFUL:
        _apply_helpful_mode(game_world, config, rng)
        return
