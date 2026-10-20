"""GameWorld: the whole game as the generator sees it."""

from dataclasses import dataclass, field

from .canonical import OMITTED_AT_DEFAULT
from .enums import VANILLA_PERSON_INITS, DungeonNothingCode, Item, UnderworldPersonInit
from .levels import ARRIVAL_DUNGEON, ARRIVAL_OVERWORLD, Level, LevelBlock
from .overworld import Overworld, Quote
from .rooms import LifeOrMoneyToll
from .sprites import EnemyData, SpriteData

# The two sets of levels (SH-SRC-01): levels 1-6 read one room block, levels 7-9 another
SET_SLICES = (slice(0, 6), slice(6, 9))
SET_NAMES = ("1-6", "7-9")


@dataclass
class GameWorld:
    overworld: Overworld
    levels: list[Level]      # exactly 9, index 0 = Level 1
    quotes: list[Quote]      # exactly 38
    sprites: SpriteData
    enemies: EnemyData
    # PRG0's second-quest levels, exactly 9 (index 0 = 2Q Level 1), read-only: what a
    # second-quest set (C02, SH-SRC-02/03) starts from; they are never serialized.
    levels_2q: list[Level] = field(default_factory=list)
    # The two quest-1 room blocks (0 = levels 1-6, 1 = levels 7-9) and the
    # quest-2 pair; every level's rooms live here. A level reads the block its
    # Level.block is (SH-SRC-02): one of `blocks`, or one of `blocks_2q` for a
    # second-quest set. `blocks` is also what each set's first-quest slot in the ROM stores: with
    # level encoding on, a second-quest set's block is stored there too
    # (store_second_quest_sets_in_first_quest_slots).
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
    # The byte at 0x0A868 (PRG0 $FF, free space), read only and no longer used: the life toll's
    # heart count follows new_file_heart_containers (FL-ALT-07). Kept so seeds keep their codes.
    starting_hearts: int = 0xFF
    # FP-START-01: the Items block each starting-state routine sets
    # (new file; second-quest switch), read from the ROM; None if unrecognized
    starting_items_new_file: bytes | None = None
    starting_items_second_quest: bytes | None = None
    # FP-START-01 and FL-ALT-02: the heart containers a new save file (and the second-quest
    # switch) starts with, and how many of them are full (HeartValues; PRG0: 3 and 3)
    new_file_heart_containers: int = 3
    new_file_full_hearts: int = 3
    # FP-START-02 and FP-START-03: the start items a new save file (and the second-quest switch)
    # holds; none writes PRG0's starting routines, any writes fp-start-02's table
    start_items: tuple[Item, ...] = ()
    # FL-ALT-06 (C18): the Triforce pieces a new save file (and the second-quest switch) holds, one
    # bit per level 1-8 (InvTriforce); any writes fp-start-02's table. 0 leaves the seed's code as
    # it was (canonical.OMITTED_AT_DEFAULT)
    start_triforce_pieces: int = field(default=0, metadata=OMITTED_AT_DEFAULT)
    # FP-START-01: the hearts a Continue restores (operand at 0x14B83)
    continue_hearts_operand: int = 0x02
    # FL-ALT-07: FormatHeartsInTextBuf's BEQ @EmitSpace operand (0x06731), PRG0's $04 draws the meter
    # blank for HeartValues $00; one starting heart sets it to $00. Omitted from the seed's code at
    # PRG0's value (canonical.OMITTED_AT_DEFAULT)
    heart_meter_blank_branch: int = field(default=0x04, metadata=OMITTED_AT_DEFAULT)
    # FP-RESET-01, FP-TEXT-01, FP-BEEP-01, FP-FIX-01, FP-Q2R-01, FP-LEVEL-01
    reset_controller1: int = 0xFB
    text_speed_value: int = 0x06
    low_health_beep_value: int = 0x40
    dmc_level_value: int = 0x7F
    q2_room_trigger_value: int = 0x06
    # SH-SRC-05: the three quest-number branches send a first-quest save down the
    # second-quest path (ropes with $40 hit points that flash, Stalfos that shoot)
    monsters_take_second_quest_path: bool = False
    level_dash_tile: int = 0x62
    # FP-ENTR-01: the overworld's arrival code (its level information +$3D), which ZORA's code
    # patches read; None in a ROM without them (PRG0's $FF). Set with the levels' codes
    # (record_level_entry_codes).
    overworld_arrival_code: int | None = None
    # The "no item" code the engine's sentinel comparison reads (layout.ASM_NOTHING_CODE_PATCH_*):
    # ZORA_REMAP ($0E) with Randomize Magical Sword, so $03 can be the magical sword inside
    # dungeons. The room bytes are written in GameConfig.dungeon_nothing_code, which generation
    # sets this from.
    dungeon_nothing_code: DungeonNothingCode = DungeonNothingCode.VANILLA

    # B10 DATA-item state (docs/spec/features-behavior.md).
    # Credits text pointers for lines 12-15 (CPU addresses in bank 2).
    credits_pointers: tuple[int, int, int, int] = (0xAD33, 0xAD4D, 0xAD59, 0xAD72)
    # The record line 15 addresses (length, first column, tiles), as read from a ROM; measured
    # only (FP-LOCK-02's Check), never written: the serializer writes the pointers.
    credits_line_15_record: bytes = b""
    # HT-BOOK-01's Check: the three bytes of UpdatePersonState_Textbox's text-pointer load (PRG0's
    # LDA PersonTextAddrs, Y, or B48's call), as read from a ROM; measured only, never written:
    # the serializer writes the patch (GameConfig.book_to_understand_npcs).
    person_text_pointer_load: bytes = b""
    # Title-screen seed number (right-aligned in the first replaced row).
    title_seed_number: int = 0
    # Title-screen version line (ZORA-authored; empty means leave PRG0 row blank).
    title_version_line: str = ""
    # Level-9 entrance refusal text (ZORA-authored; must state eight).
    level9_refusal_text: str = ""
    # FP-PERSON-01: the 17 cave-person animation bytes for object types $6B-$7B.
    cave_person_animations: tuple[int, ...] = ()

    @property
    def uses_start_table(self) -> bool:
        """FP-START-03: fp-start-02's starting table is written, for start items or start pieces
        (FL-ALT-06); otherwise PRG0's starting routines stay."""
        return bool(self.start_items or self.start_triforce_pieces)

    @property
    def level_blocks(self) -> list[LevelBlock]:
        """The room block each set's levels read (SH-SRC-02): blocks[s], or blocks_2q[s] for a
        second-quest set (levels 1-6, then 7-9)."""
        return [self.levels[0].block, self.levels[6].block]

    def record_level_entry_codes(self) -> None:
        """FP-ENTR-01 and FP-ENTR-02: the level-information bytes ZORA's code patches read, where
        no pass set them: each level's arrival code (from below, ARRIVAL_DUNGEON) and the room a
        move leaves it by (Level.exit_room_count; the start-room swap sets both for a moved start
        room, PS-START-03), and the overworld's arrival code. Run when the rooms' owners are
        final, at the end of generation; doing it twice is doing it once."""
        for level in self.levels:
            if level.arrival_code is None:
                level.arrival_code = ARRIVAL_DUNGEON
            if level.exit_room is None:
                level.exit_room = level.exit_room_count()
        self.overworld_arrival_code = ARRIVAL_OVERWORLD

    def store_second_quest_sets_in_first_quest_slots(self) -> None:
        """Encode level data (FP-TOURNEY-01; owner decision, 2026-10-12): the encoding takes the
        second-quest blocks' ROM space for itself, so a set whose levels read their second-quest
        block has that block stored in the set's first-quest slot instead, whose own block no level
        of the set reads. The levels keep reading the same block and their level information is
        unchanged; the serializer writes the block at the first-quest slot and points the set's
        levels there ($87, $8A). Owner ruling: the changed pointer bytes are data the protection
        method needs. A world with no second-quest set is unchanged; doing it twice is doing it
        once."""
        for set_index, block in enumerate(self.blocks_2q):
            read = [level.block is block for level in self.levels[SET_SLICES[set_index]]]
            if not any(read):
                continue
            if not all(read):
                raise ValueError(f"levels {SET_NAMES[set_index]} read more than one room block")
            self.blocks[set_index] = block
