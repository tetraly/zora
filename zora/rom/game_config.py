"""Game configuration types referenced by the parser/serializer.

Reconstructed: this module was imported by the serializer but missing from the
repo snapshot. Only HintMode was needed by the data layer at first;
GameConfig was added for the "no item" modeling decision: the room bytes' "no item" code is a
setting (GameConfig.dungeon_nothing_code), the model keeps a meaning; the engine byte that
compares it is the model's (GameWorld.dungeon_nothing_code, owner ruling 2026-10-13).

Future settings derived from the randomizer flags (per the same decision,
landing later): hint text relocation and boss sprite relocation — they belong
as fields on GameConfig once the flag surface exists.
"""
from dataclasses import dataclass, field, fields
from enum import Enum, auto
from typing import Any

from ..model.canonical import OMITTED_AT_DEFAULT
from ..model.enums import DungeonNothingCode
from .revision import Revision

# DungeonNothingCode, GameConfig's field type, lives in the model (GameWorld holds the engine's code)
__all__ = ["BLOCKED_CONFIG", "DungeonNothingCode", "GameConfig", "HintMode", "LevelEncodingKey",
           "reject_blocked_options"]


def reject_blocked_options(options: Any, blocked: dict[str, str]) -> None:
    """Raise NotImplementedError for the first blocked option set away from
    its default (blocked: option name -> what it waits on)."""
    for option in fields(options):
        if option.name in blocked and getattr(options, option.name) != option.default:
            raise NotImplementedError(f"{option.name}: waits on {blocked[option.name]}")


class HintMode(Enum):
    VANILLA = auto()      # keep vanilla hint text block layout
    COMMUNITY = auto()    # extended hint bank, centered community hints
    HELPFUL = auto()      # extended hint bank, centered helpful hints
    CONSTERNATION = auto()  # generated Consternation hint text (hints-behavior.md)
    NORMAL = auto()       # HT-HINT-05: PRG0's text block, with the fixed changes and the 38 pointers


@dataclass(frozen=True)
class LevelEncodingKey:
    """Encode level data (features-behavior.md FP-TOURNEY-01): the key is the
    seed and the canonical flag string, as UTF-8."""
    seed: int
    flag_string: str

    @property
    def settings_bytes(self) -> bytes:
        return self.flag_string.encode("utf-8")


# option name -> what it waits on
BLOCKED_CONFIG = {
    "relocate_hint_text": "the randomizer flag surface",
    "relocate_boss_sprites": "the randomizer flag surface",
}


@dataclass(frozen=True)
class GameConfig:
    dungeon_nothing_code: DungeonNothingCode = DungeonNothingCode.VANILLA
    hint_mode: HintMode = HintMode.VANILLA
    # B10 (features-behavior.md): the DATA items and the CODE patches
    # (zora/rom/code_patches.py). Off keeps PRG0's code and data, so base-ROM
    # round-trip tests and shape-stage tests stay stable.
    features_b10: bool = False
    # Book is an Atlas (B49; FP-BOOK-01), one of the B10 code patches: off
    # leaves that patch out (FL-OFF-05).
    book_is_an_atlas: bool = True
    # Book to Understand NPCs (B48; HT-BOOK-01): on writes ht-book-01, so a person shows text 0
    # unless Link holds the Book. Off leaves the patch out.
    book_to_understand_npcs: bool = False
    # The ZORA flags Progressive Items and Shop Items in the Item Pool (PI-CODE-01): they
    # choose which of fp-prog-01 / fp-prog-02 are written, and fp-prog-01's on/off byte.
    progressive_items: bool = False
    shop_items_in_pool: bool = False
    # Shuffle Blue Potion (the owner's 2.0 flags): the potion shop's middle ware sells a pool item, so
    # fp-prog-01's one-time wares are written with it on too.
    potion_shop_in_pool: bool = False
    # The owner's 2.0 flags resolved on (zora_flags.OWNER_2_0_FIELDS names): their patches are
    # written after the code patches (zora/rom/owner_patches.py). The ZORA 1.0 flags resolved on
    # are named here too (zora_flags.ZORA_1_0_FIELDS), never in a field of their own: the seed's
    # code hashes this configuration, so a new field would change every seed's code.
    owner_flags: tuple[str, ...] = ()

    @property
    def bait_in_pool(self) -> bool:
        """Shop Items in the Item Pool puts the bait in the pool too: bait is a count
        (zora/rom/bait_count.py)."""
        return self.shop_items_in_pool
    # ASNB's Level 9 Entrance = Level 4 sword (docs/design/asnb.md 3c): level-9-gate is written.
    level_9_entrance_sword: bool = False
    # Permanent Sword Beam (B52; FP-BEAM-01) and OHKO (B53; FP-OHKO-01): fixed code patches
    # (zora/rom/sword_and_harm.py). Omitted from the seed's code while off, so seeds without them
    # keep their codes (model/canonical.py).
    permanent_sword_beam: bool = field(default=False, metadata=OMITTED_AT_DEFAULT)
    one_hit_knock_out: bool = field(default=False, metadata=OMITTED_AT_DEFAULT)
    # Add Bridges to the River (B87; FP-BRIDGE-01) and Add Lost Woods Shortcut (B88; FP-WOODS-01):
    # fixed overworld data bytes (zora/rom/overworld_crossings.py). Omitted from the seed's code
    # while off.
    river_bridges: bool = field(default=False, metadata=OMITTED_AT_DEFAULT)
    lost_woods_shortcut: bool = field(default=False, metadata=OMITTED_AT_DEFAULT)
    # Swords (C07; FP-WOOD-02, FP-WOOD-03; zora/rom/sword_states.py): item $02 a bomb upgrade (Wood
    # Sword Only and Swordless), and Ganon harmed by the wand alone (Swordless). Omitted from the
    # seed's code while off.
    bomb_upgrade_item: bool = field(default=False, metadata=OMITTED_AT_DEFAULT)
    wand_fights_ganon: bool = field(default=False, metadata=OMITTED_AT_DEFAULT)
    # The beta 8 export's fixed patches (zora/rom/uphill_battle.py), omitted from the seed's code
    # while off: Recorder to Unbeaten Dungeons (B07, OW-WARP-02), Hide Dungeon Numbers (B24,
    # FP-LEVEL-02), Hidden Health (B55, FP-HIDE-01), the Red Bubble Curse (C19 resolved to 1 or 2,
    # FP-BUBL-01) and Replace Book Fire with Explosion's blast (B47, FP-BOOK-02).
    recorder_to_unbeaten: bool = field(default=False, metadata=OMITTED_AT_DEFAULT)
    hide_dungeon_numbers: bool = field(default=False, metadata=OMITTED_AT_DEFAULT)
    hidden_health: bool = field(default=False, metadata=OMITTED_AT_DEFAULT)
    red_bubble_curse: int = field(default=0, metadata=OMITTED_AT_DEFAULT)
    book_explosion: bool = field(default=False, metadata=OMITTED_AT_DEFAULT)
    # Make Important Items Drops (B39, PS-EDROP-01) and Randomize Item Drop Rate (B44, PS-EDROP-02):
    # the key of their own stream (pipeline.enemy_drops_key), None with both off.
    important_item_drops: bool = field(default=False, metadata=OMITTED_AT_DEFAULT)
    random_drop_rates: bool = field(default=False, metadata=OMITTED_AT_DEFAULT)
    enemy_drops_key: int | None = field(default=None, metadata=OMITTED_AT_DEFAULT)
    # The beta 9 export's fixed patches (zora/rom/small_settings.py), omitted from the seed's code
    # while off: Killable Drop Items (B56, FP-KILL-01), Hidden Numbers (B83, FP-NUM-01), Rupees
    # Affect Speed (B80, FP-RSPD-01) and Prevent Clipping (B84, FP-CLIP-01).
    killable_drop_items: bool = field(default=False, metadata=OMITTED_AT_DEFAULT)
    hidden_numbers: bool = field(default=False, metadata=OMITTED_AT_DEFAULT)
    rupees_affect_speed: bool = field(default=False, metadata=OMITTED_AT_DEFAULT)
    prevent_clipping: bool = field(default=False, metadata=OMITTED_AT_DEFAULT)
    # Change Hidden OW Tiles (B89, FP-VIS-01; zora/rom/hidden_tiles.py), and whether its step 3 runs
    # (the resolved overworld quest is the first or the second, C01 = 0 or 1)
    change_hidden_tiles: bool = field(default=False, metadata=OMITTED_AT_DEFAULT)
    plain_dead_secrets: bool = field(default=False, metadata=OMITTED_AT_DEFAULT)
    # Item and Sprite Appearance (C15 resolved to 1 or 2, FP-SPRITE-01; zora/rom/item_sprites.py) and
    # its own stream's key (pipeline.item_sprites_key); 0 and None with it at normal
    item_appearance: int = field(default=0, metadata=OMITTED_AT_DEFAULT)
    item_sprites_key: int | None = field(default=None, metadata=OMITTED_AT_DEFAULT)
    # Archipelago's ware places (External mode only; docs/archipelago.md "Interface"): (shop number
    # in code_patches.SHOPS_BY_NUMBER order, ware position) pairs sold once whatever they hold, a
    # re-buyable blue potion too, so that buying one is a location check ZORA_B1_OneTimeWares
    # records. Empty in ZORA mode, which keeps the table as the wares alone decide it.
    one_time_places: tuple[tuple[int, int], ...] = ()
    # Archipelago's slot identity record (External mode with a slot name only; zora/rom/
    # slot_identity.py): written into bank 0's free space before the seed's code hashes the ROM.
    # Empty (ZORA mode) writes nothing there.
    slot_identity: bytes = b""
    # An Archipelago game's ROM (External mode's FINISH; zora/generate/pipeline.py finish): asm/flags2's
    # ring-color, which repaints Link when the client gives a ring through RAM (owner decision
    # 2026-10-18). Off in ZORA mode, whose output stays as it is; omitted from the seed's code there.
    archipelago_rom: bool = field(default=False, metadata=OMITTED_AT_DEFAULT)
    # Other players' items look like the Archipelago logo (an Archipelago game's foreign_item_look =
    # logo; zora/rom/archipelago_logo.py): the magical shield's tiles, take and palette bytes.
    foreign_logo: bool = field(default=False, metadata=OMITTED_AT_DEFAULT)
    # The seed number the statistics screen shows (ZORA mode; code_patches.stamp_seed_number, owner
    # request 2026-10-19). Never part of the seed's code (code_patches.seed_code_items leaves it
    # out); None in External mode (an Archipelago game's number is not one its player chose).
    seed_number: int | None = field(default=None, metadata=OMITTED_AT_DEFAULT)
    # Encode level data (FP-TOURNEY-01; zora/rom/level_encoding.py): None leaves
    # the level data plain, byte-identical to the unencoded output.
    level_encoding: LevelEncodingKey | None = None
    # The player's base ROM (docs/design/prg1.md): which release, and whether its graphics are
    # modified. serialize_to_rom sets both from the ROM it is given (revision.identify_rom); only
    # the move back to the release's own layout reads them. The plan, the model and the draws
    # never do.
    revision: Revision = Revision.PRG0
    modified_graphics: bool = False
    # Placeholder fields for the follow-ups named in the same decision —
    # both default to the vanilla/Consternation behavior:
    relocate_hint_text: bool = False       # later derived from flags
    relocate_boss_sprites: bool = False   # later derived from flags

    def __post_init__(self) -> None:
        reject_blocked_options(self, BLOCKED_CONFIG)
