"""Game configuration types referenced by the parser/serializer.

Reconstructed: this module was imported by the serializer but missing from the
repo snapshot. Only HintMode was needed by the data layer at first;
DungeonNothingCode + GameConfig were added for the "no item" modeling
decision (serialization byte is a setting, the model keeps a meaning).

Future settings derived from the randomizer flags (per the same decision,
landing later): hint text relocation and boss sprite relocation — they belong
as fields on GameConfig once the flag surface exists.
"""
from dataclasses import dataclass, fields
from enum import Enum, IntEnum, auto
from typing import Any


def reject_blocked_options(options: Any, blocked: dict[str, str]) -> None:
    """Raise NotImplementedError for the first blocked option set away from
    its default (blocked: option name -> what it waits on)."""
    for field in fields(options):
        if field.name in blocked and getattr(options, field.name) != field.default:
            raise NotImplementedError(f"{field.name}: waits on {blocked[field.name]}")


class HintMode(Enum):
    VANILLA = auto()      # keep vanilla hint text block layout
    COMMUNITY = auto()    # extended hint bank, centered community hints
    HELPFUL = auto()      # extended hint bank, centered helpful hints
    CONSTERNATION = auto()  # generated Consternation hint text (hints-behavior.md)


class DungeonNothingCode(IntEnum):
    """Which ROM byte encodes "no item" in dungeon room item bytes.

    The model-level meaning is Item.NOTHING; this enum chooses the encoding.
    VANILLA ($03) is what the Consternation preset uses and keeps
    parse→serialize byte-identical. ZORA_REMAP ($0E) requires the matching
    assembly patch (rom_layout.ASM_NOTHING_CODE_PATCH_*; the serializer
    emits it) which moves the engine's sentinel comparison so $03 can be
    used for the magical sword inside dungeons.
    """
    VANILLA = 0x03
    ZORA_REMAP = 0x0E


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
    # The ZORA flags Progressive Items and Shop Items in the Item Pool (PI-CODE-01): they
    # choose which of fp-prog-01 / fp-prog-02 are written, and fp-prog-01's on/off byte.
    progressive_items: bool = False
    shop_items_in_pool: bool = False
    # Shuffle Blue Potion (the owner's 2.0 flags): the potion shop's middle ware sells a pool item, so
    # fp-prog-01's one-time wares are written with it on too.
    potion_shop_in_pool: bool = False
    # The owner's 2.0 flags resolved on (zora_flags.OWNER_2_0_FIELDS names): their patches are
    # written after the code patches (zora/rom/owner_patches.py).
    owner_flags: tuple[str, ...] = ()
    # ASNB's Level 9 Entrance = Level 4 sword (docs/design/asnb.md 3c): level-9-gate is written.
    level_9_entrance_sword: bool = False
    # Archipelago's ware places (External mode only; docs/archipelago.md "Interface"): (shop number
    # in code_patches.SHOPS_BY_NUMBER order, ware position) pairs sold once whatever they hold, a
    # re-buyable blue potion too, so that buying one is a location check ZORA_B1_OneTimeWares
    # records. Empty in ZORA mode, which keeps the table as the wares alone decide it.
    one_time_places: tuple[tuple[int, int], ...] = ()
    # Archipelago's slot identity record (External mode with a slot name only; zora/rom/
    # slot_identity.py): written into bank 0's free space before the seed's code hashes the ROM.
    # Empty (ZORA mode) writes nothing there.
    slot_identity: bytes = b""
    # Encode level data (FP-TOURNEY-01; zora/rom/level_encoding.py): None leaves
    # the level data plain, byte-identical to the unencoded output.
    level_encoding: LevelEncodingKey | None = None
    # Placeholder fields for the follow-ups named in the same decision —
    # both default to the vanilla/Consternation behavior:
    relocate_hint_text: bool = False       # later derived from flags
    relocate_boss_sprites: bool = False   # later derived from flags

    def __post_init__(self) -> None:
        reject_blocked_options(self, BLOCKED_CONFIG)
