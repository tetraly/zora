"""GameWorld: the whole game as the generator sees it."""

from dataclasses import dataclass, field

from .enums import VANILLA_PERSON_INITS, UnderworldPersonInit
from .levels import Level, LevelBlock
from .overworld import Overworld, Quote
from .rooms import LifeOrMoneyToll
from .sprites import EnemyData, SpriteData


@dataclass
class GameWorld:
    overworld: Overworld
    levels: list[Level]      # exactly 9, index 0 = Level 1
    quotes: list[Quote]      # exactly 38
    sprites: SpriteData
    enemies: EnemyData
    levels_2q: list[Level] = field(default_factory=list)  # exactly 9, index 0 = 2Q Level 1; read-only, never serialised
    # The two quest-1 room blocks (0 = levels 1-6, 1 = levels 7-9) and the
    # quest-2 pair; every level's rooms live here.
    blocks: list[LevelBlock] = field(default_factory=list)
    blocks_2q: list[LevelBlock] = field(default_factory=list)
    # Verbatim quotes_data block (pointer table + text) as parsed. Lets VANILLA
    # hint mode round-trip byte-identically without depending on the
    # decode/re-encode character table being lossless.
    quotes_raw: bytes = b""
    # PS-MERCH-04's toll; None is the vanilla merchant ("50 rupees or a
    # heart container").
    life_or_money_toll: LifeOrMoneyToll | None = None
    # PS-BOMB-03: the two levels whose persons take the bomb-upgrade path;
    # None is the vanilla code (levels 5 and 7, behind a branch).
    bomb_upgrade_levels: tuple[int, int] | None = None
    # PS-HINT-06: levels 1-8's person init routine (jump-table low bytes).
    person_inits: tuple[UnderworldPersonInit, ...] = VANILLA_PERSON_INITS
    # Hint-text pass output (hints-behavior.md).  VANILLA serialization ignores
    # these and passthroughs quotes_raw; CONSTERNATION serialization writes the
    # generated 45-slot pointer table and selector tables.
    hint_pointers: tuple[int, ...] | None = None
    hint_text_bytes: tuple[bytes, ...] | None = None
    white_sword_text_selector: int | None = None
    hint_shop_offer_selectors: tuple[int, ...] | None = None
    underworld_text_selectors_a: bytes | None = None
    underworld_text_selectors_b: bytes | None = None
    hint_overlay_flags: tuple[bool, ...] = ()
    # PS-EGRP-05: the three item-carrier CMP operands at 0x1E70F/13/17
    # (vanilla Like Like $17, Stalfos $2A, Gibdo $30; $FF when that enemy
    # is in the overworld group). Purpose not established (K-B4-02).
    item_carrier_operands: tuple[int, int, int] = (0x17, 0x2A, 0x30)
    # PS-EGRP-06's fixed operand at 0x0474D (CPU $873D bank 1, a CPY #
    # operand; vanilla $7B, written $7E). Purpose not established.
    object_type_operand_873d: int = 0x7B
    # PS-EGRP-05's red-Wizzrobe overworld patch: four fixed byte runs
    # (rom_layout.OVERWORLD_WIZZROBE_PATCH), written when True.
    overworld_wizzrobe_patch: bool = False
    # The starting-hearts byte (read only): the life toll's cost derives
    # from it.
    starting_hearts: int = 0xFF
    # FP-START-01: the Items block each starting-state routine sets
    # (new file; second-quest switch), read from the ROM; None if unrecognized
    starting_items_new_file: bytes | None = None
    starting_items_second_quest: bytes | None = None
    # FP-START-01 and FL-ALT-02: the heart containers a new save file (and the second-quest
    # switch) starts with, and how many of them are full (HeartValues; PRG0: 3 and 3)
    new_file_heart_containers: int = 3
    new_file_full_hearts: int = 3
    # FP-START-01: the hearts a Continue restores (operand at 0x14B83)
    continue_hearts_operand: int = 0x02
    # FP-RESET-01, FP-TEXT-01, FP-BEEP-01, FP-FIX-01, FP-Q2R-01, FP-LEVEL-01
    reset_controller1: int = 0xFB
    text_speed_value: int = 0x06
    low_health_beep_value: int = 0x40
    dmc_level_value: int = 0x7F
    q2_room_trigger_value: int = 0x06
    level_dash_tile: int = 0x62

    # B10 DATA-item state (docs/spec/features-behavior.md).
    # Credits text pointers for lines 12-15 (CPU addresses in bank 2).
    credits_pointers: tuple[int, int, int, int] = (0xAD33, 0xAD4D, 0xAD59, 0xAD72)
    # The record line 15 addresses (length, first column, tiles), as read from a ROM; measured
    # only (FP-LOCK-02's Check), never written: the serializer writes the pointers.
    credits_line_15_record: bytes = b""
    # Title-screen seed number (right-aligned in the first replaced row).
    title_seed_number: int = 0
    # Title-screen version line (ZORA-authored; empty means leave PRG0 row blank).
    title_version_line: str = ""
    # Level-9 entrance refusal text (ZORA-authored; must state eight).
    level9_refusal_text: str = ""
    # FP-PERSON-01: the 17 cave-person animation bytes for object types $6B-$7B.
    cave_person_animations: tuple[int, ...] = ()
