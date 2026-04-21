"""
Spoiler log generation for ZORA.

Reads the randomized GameWorld and produces:
  1. A human-readable plain-text log (build_spoiler_log)
  2. A structured JSON-serializable dict for the interactive viewer (build_spoiler_data)
"""
from __future__ import annotations

from typing import Any

import base64

from zora.data_model import (
    BossSpriteSet,
    CaveDefinition,
    Destination,
    DoorRepairCave,
    Enemy,
    EnemySpriteSet,
    GameWorld,
    HintCave,
    HintShop,
    Item,
    ItemCave,
    Level,
    MoneyMakingGameCave,
    OverworldItem,
    Quote,
    Room,
    RoomType,
    SecretCave,
    Shop,
    StaircaseRoom,
    TakeAnyCave,
)
from zora.game_config import GameConfig, HintMode
from zora.hint_randomizer import HintType
from zora.game_validator import DungeonLocation, Location
from zora.item_randomizer import collect_item_locations

_DESTINATION_LABELS: dict[Destination, str] = {
    Destination.WOOD_SWORD_CAVE:    "Wood Sword Cave",
    Destination.WHITE_SWORD_CAVE:   "White Sword Cave",
    Destination.MAGICAL_SWORD_CAVE: "Magical Sword Cave",
    Destination.LETTER_CAVE:        "Letter Cave",
    Destination.ARMOS_ITEM:         "Armos Item",
    Destination.COAST_ITEM:         "Coast Item",
    Destination.SHOP_1:             "Shop 1",
    Destination.SHOP_2:             "Shop 2",
    Destination.SHOP_3:             "Shop 3",
    Destination.SHOP_4:             "Shop 4",
    Destination.POTION_SHOP:        "Potion Shop",
    Destination.TAKE_ANY:           "Take Any Cave",
    Destination.ANY_ROAD:           "Any Road",
    Destination.LOST_HILLS_HINT:    "Lost Hills Hint",
    Destination.MONEY_MAKING_GAME:  "Money Making Game",
    Destination.DOOR_REPAIR:        "Door Repair",
    Destination.DEAD_WOODS_HINT:    "Dead Woods Hint",
    Destination.HINT_SHOP_1:        "Hint Shop 1",
    Destination.HINT_SHOP_2:        "Hint Shop 2",
    Destination.MEDIUM_SECRET:      "Medium Secret",
    Destination.LARGE_SECRET:       "Large Secret",
    Destination.SMALL_SECRET:       "Small Secret",
}


def _item_label(item: Item) -> str:
    return item.name.replace("_", " ").title()


def _dest_label(dest: Destination) -> str:
    return _DESTINATION_LABELS.get(dest, dest.name.replace("_", " ").title())


def _hint_type_label(quote_id: int) -> str | None:
    """Return the HintType name for a quote_id, or None if not a valid HintType."""
    try:
        return HintType(quote_id).name
    except ValueError:
        return None


def _location_label(loc: Location) -> str:
    if isinstance(loc, DungeonLocation):
        return f"Level {loc.level_num} Room {loc.room_num:#04x}"
    base = _dest_label(loc.destination)
    if loc.position > 0:
        return f"{base} (slot {loc.position + 1})"
    return base


def _item_at_location(game_world: GameWorld, loc: Location) -> Item | None:
    if isinstance(loc, DungeonLocation):
        level = game_world.levels[loc.level_num - 1]
        for room in level.rooms:
            if room.room_num == loc.room_num:
                return room.item
        for sr in level.staircase_rooms:
            if sr.room_num == loc.room_num:
                return sr.item
        return None

    ow = game_world.overworld
    cave_by_dest = {c.destination: c for c in ow.caves}
    c = cave_by_dest.get(loc.destination)
    if c is None:
        return None
    if isinstance(c, ItemCave):
        return c.item
    if isinstance(c, OverworldItem):
        return c.item
    if isinstance(c, Shop):
        if loc.position < len(c.items):
            return c.items[loc.position].item
    return None


def _cave_lines(cave: CaveDefinition) -> list[str]:
    """Return a multi-line description of a cave's current state."""
    label = _dest_label(cave.destination)

    if isinstance(cave, OverworldItem):
        return [f"  {label}: {_item_label(cave.item)}"]

    if isinstance(cave, ItemCave):
        parts = [f"  {label}: {_item_label(cave.item)}  (quote {cave.quote_id})"]
        if cave.heart_requirement:
            parts[0] += f"  [{cave.heart_requirement} hearts required]"
        return parts

    if isinstance(cave, Shop):
        header = f"  {label}  (quote {cave.quote_id}"
        if cave.letter_requirement:
            header += ", letter required"
        header += ")"
        item_lines = [
            f"    slot {i + 1}: {_item_label(si.item)}  @ {si.price} rupees"
            for i, si in enumerate(cave.items)
        ]
        return [header] + item_lines

    if isinstance(cave, HintShop):
        header = f"  {label}  (entry quote {cave.quote_id})"
        hint_lines = [
            f"    slot {i + 1}: hint quote {hi.quote_id}  @ {hi.price} rupees"
            for i, hi in enumerate(cave.hints)
        ]
        return [header] + hint_lines

    if isinstance(cave, TakeAnyCave):
        items_str = ", ".join(_item_label(it) for it in cave.items)
        return [f"  {label}: [{items_str}]  (quote {cave.quote_id})"]

    if isinstance(cave, SecretCave):
        sign = "+" if cave.rupee_value >= 0 else ""
        return [f"  {label}: {sign}{cave.rupee_value} rupees  (quote {cave.quote_id})"]

    if isinstance(cave, DoorRepairCave):
        return [f"  {label}: costs {cave.cost} rupees  (quote {cave.quote_id})"]

    if isinstance(cave, HintCave):
        return [f"  {label}  (quote {cave.quote_id})"]

    if isinstance(cave, MoneyMakingGameCave):
        return [
            f"  {label}  (quote {cave.quote_id})",
            f"    bets: {cave.bet_low} / {cave.bet_mid} / {cave.bet_high}",
            f"    outcomes: +{cave.win_small} / +{cave.win_large} / "
            f"{cave.lose_small} / {cave.lose_small_2} / {cave.lose_large}",
        ]

    # Fallback for any future cave type
    return [f"  {label}: {cave!r}"]


def build_spoiler_log(
    game_world: GameWorld,
    config: GameConfig,
    seed: int,
    flag_string: str,
) -> str:
    """Return a plain-text spoiler log for this seed."""
    lines: list[str] = [
        "ZORA — Zelda One Randomizer App",
        f"Seed:  {seed}",
        f"Flags: {flag_string}",
        "",
    ]

    # --- Item placements ---
    locations = collect_item_locations(game_world, config)

    def _sort_key(loc: Location) -> tuple[int, int, int]:
        if isinstance(loc, DungeonLocation):
            return (0, loc.level_num, loc.room_num)
        return (1, loc.destination.value, loc.position)

    locations.sort(key=_sort_key)

    lines.append("=== Item Placements ===")
    lines.append("")
    for loc in locations:
        item = _item_at_location(game_world, loc)
        item_str = _item_label(item) if item is not None else "(unknown)"
        loc_str = _location_label(loc)
        lines.append(f"  {loc_str:<36} {item_str}")
    lines.append("")

    # --- Caves and shops ---
    lines.append("=== Caves & Shops ===")
    lines.append("")
    for cave in game_world.overworld.caves:
        lines.extend(_cave_lines(cave))
    lines.append("")

    # --- Quotes ---
    lines.append("=== Quotes ===")
    lines.append("")
    sorted_quotes: list[Quote] = sorted(game_world.quotes, key=lambda q: q.quote_id)
    show_hint_type = config.hint_mode != HintMode.VANILLA
    for q in sorted_quotes:
        text_repr = q.text.replace("|", " / ") if q.text else "(blank)"
        hint_name = _hint_type_label(q.quote_id) if show_hint_type else None
        if hint_name:
            lines.append(f"  [{q.quote_id:>2}] ({hint_name}) {text_repr}")
        else:
            lines.append(f"  [{q.quote_id:>2}] {text_repr}")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# NES color palette lookup (64 entries, from flags.yaml nes_color_palette)
# ---------------------------------------------------------------------------

_NES_PALETTE: dict[int, str] = {
    0x00: "#626262", 0x01: "#012090", 0x02: "#240BA0", 0x03: "#470090",
    0x04: "#600062", 0x05: "#6A0024", 0x06: "#601100", 0x07: "#472300",
    0x08: "#243400", 0x09: "#014000", 0x0A: "#004300", 0x0B: "#003A1E",
    0x0C: "#002C52", 0x0D: "#000000", 0x0E: "#000000", 0x0F: "#000000",
    0x10: "#ABABAB", 0x11: "#1F56E1", 0x12: "#4B38F6", 0x13: "#7524DA",
    0x14: "#9518A7", 0x15: "#9E1C5C", 0x16: "#932F12", 0x17: "#784600",
    0x18: "#505900", 0x19: "#2B6800", 0x1A: "#116C00", 0x1B: "#066341",
    0x1C: "#0E5282", 0x1D: "#000000", 0x1E: "#000000", 0x1F: "#000000",
    0x20: "#FFFFFF", 0x21: "#65AAFE", 0x22: "#8C8FFE", 0x23: "#B478FE",
    0x24: "#D26DFE", 0x25: "#DA6FAF", 0x26: "#D18064", 0x27: "#BA932A",
    0x28: "#97A400", 0x29: "#74B10A", 0x2A: "#5AB533", 0x2B: "#4DAD70",
    0x2C: "#53A0AB", 0x2D: "#3C3C3C", 0x2E: "#000000", 0x2F: "#000000",
    0x30: "#FFFFFF", 0x31: "#BEDAFE", 0x32: "#CCCEFE", 0x33: "#DDC4FE",
    0x34: "#EABEFE", 0x35: "#EEBFDD", 0x36: "#E9C6BA", 0x37: "#DFCE9F",
    0x38: "#D0D68E", 0x39: "#C2DA8E", 0x3A: "#B7DBA0", 0x3B: "#B1D8BA",
    0x3C: "#B4D2D8", 0x3D: "#A0A0A0", 0x3E: "#000000", 0x3F: "#000000",
}


def _nes_color_hex(index: int) -> str:
    """Look up CSS hex color for a NES palette index (0x00-0x3F)."""
    return _NES_PALETTE.get(index & 0x3F, "#000000")


def _level_palette_hex(level: Level) -> tuple[str, str]:
    """Extract the bright and dark floor colors from a level's palette.

    Returns (bright_hex, dark_hex) CSS color strings.
    The bright color is group 2 byte 3 (the brightest BG accent).
    The dark color is group 2 byte 1 (the mid-tone accent).
    """
    data = level.palette_raw[3:3 + 32]  # 8 groups x 4 bytes
    bright_index = data[2 * 4 + 3]  # group 2, byte 3
    dark_index = data[2 * 4 + 1]    # group 2, byte 1
    return _nes_color_hex(bright_index), _nes_color_hex(dark_index)


_NO_ITEM_VALUES: frozenset[Item] = frozenset({
    Item.NOTHING, Item.OVERWORLD_NO_ITEM,
})


def _item_name_or_none(item: Item | None) -> str | None:
    """Return display name for an item, or None for nothing/no-item."""
    if item is None or item in _NO_ITEM_VALUES:
        return None
    return item.name


def _room_dict(
    room: Room,
    level: Level,
    room_to_staircase: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    """Serialize a Room to a JSON-friendly dict."""
    sc_info = room_to_staircase.get(room.room_num)
    return {
        "room_num": room.room_num,
        "row": room.room_num >> 4,
        "col": room.room_num & 0x0F,
        "room_type": room.room_type.name,
        "walls": {
            "north": room.walls.north.name,
            "east": room.walls.east.name,
            "south": room.walls.south.name,
            "west": room.walls.west.name,
        },
        "enemy": room.enemy_spec.enemy.name,
        "enemy_quantity": room.enemy_quantity,
        "item": _item_name_or_none(room.item),
        "room_action": room.room_action.name,
        "is_dark": room.is_dark,
        "movable_block": room.movable_block,
        "is_entrance": room.room_num == level.entrance_room,
        "is_boss": room.room_num == level.boss_room,
        "staircase_index": sc_info["staircase_index"] if sc_info else None,
        "staircase_type": sc_info["staircase_type"] if sc_info else None,
        "staircase_label": sc_info["staircase_label"] if sc_info else None,
        "staircase_item": sc_info["staircase_item"] if sc_info else None,
    }


def _staircase_dict(sr: StaircaseRoom, index: int) -> dict[str, Any]:
    """Serialize a StaircaseRoom to a JSON-friendly dict."""
    return {
        "room_num": sr.room_num,
        "room_type": sr.room_type.name,
        "item": _item_name_or_none(sr.item),
        "staircase_index": index,
    }


def _cave_dict(cave: CaveDefinition) -> dict[str, Any]:
    """Serialize a CaveDefinition to a JSON-friendly dict."""
    dest = _dest_label(cave.destination)
    base: dict[str, Any] = {
        "destination": cave.destination.name,
        "destination_label": dest,
    }

    if isinstance(cave, OverworldItem):
        base["type"] = "OverworldItem"
        base["item"] = _item_label(cave.item)
        return base

    if isinstance(cave, ItemCave):
        base["type"] = "ItemCave"
        base["item"] = _item_label(cave.item)
        base["quote_id"] = cave.quote_id
        base["heart_requirement"] = cave.heart_requirement
        return base

    if isinstance(cave, Shop):
        base["type"] = "Shop"
        base["quote_id"] = cave.quote_id
        base["letter_requirement"] = cave.letter_requirement
        base["items"] = [
            {"item": _item_label(si.item), "price": si.price}
            for si in cave.items
        ]
        return base

    if isinstance(cave, HintShop):
        base["type"] = "HintShop"
        base["quote_id"] = cave.quote_id
        base["hints"] = [
            {"quote_id": hi.quote_id, "price": hi.price}
            for hi in cave.hints
        ]
        return base

    if isinstance(cave, TakeAnyCave):
        base["type"] = "TakeAnyCave"
        base["quote_id"] = cave.quote_id
        base["items"] = [_item_label(it) for it in cave.items]
        return base

    if isinstance(cave, SecretCave):
        base["type"] = "SecretCave"
        base["quote_id"] = cave.quote_id
        base["rupee_value"] = cave.rupee_value
        return base

    if isinstance(cave, DoorRepairCave):
        base["type"] = "DoorRepairCave"
        base["quote_id"] = cave.quote_id
        base["cost"] = cave.cost
        return base

    if isinstance(cave, HintCave):
        base["type"] = "HintCave"
        base["quote_id"] = cave.quote_id
        return base

    if isinstance(cave, MoneyMakingGameCave):
        base["type"] = "MoneyMakingGameCave"
        base["quote_id"] = cave.quote_id
        base["bet_low"] = cave.bet_low
        base["bet_mid"] = cave.bet_mid
        base["bet_high"] = cave.bet_high
        base["win_small"] = cave.win_small
        base["win_large"] = cave.win_large
        base["lose_small"] = cave.lose_small
        base["lose_small_2"] = cave.lose_small_2
        base["lose_large"] = cave.lose_large
        return base

    # Fallback
    base["type"] = type(cave).__name__
    return base


_ENEMY_SET_ATTR: dict[EnemySpriteSet, str] = {
    EnemySpriteSet.A:  "enemy_set_a",
    EnemySpriteSet.B:  "enemy_set_b",
    EnemySpriteSet.C:  "enemy_set_c",
    EnemySpriteSet.OW: "ow_sprites",
}

_BOSS_SET_ATTR: dict[BossSpriteSet, str] = {
    BossSpriteSet.A: "boss_set_a",
    BossSpriteSet.B: "boss_set_b",
    BossSpriteSet.C: "boss_set_c",
}

_VANILLA_ENEMY_GROUPS: dict[EnemySpriteSet, list[Enemy]] = {
    EnemySpriteSet.A: [
        Enemy.RED_GORIYA, Enemy.BLUE_GORIYA,
        Enemy.WALLMASTER, Enemy.ROPE, Enemy.STALFOS,
    ],
    EnemySpriteSet.B: [
        Enemy.RED_DARKNUT, Enemy.BLUE_DARKNUT,
        Enemy.POLS_VOICE, Enemy.GIBDO,
    ],
    EnemySpriteSet.C: [
        Enemy.VIRE, Enemy.LIKE_LIKE,
        Enemy.RED_WIZZROBE, Enemy.BLUE_WIZZROBE,
        Enemy.RED_LANMOLA, Enemy.BLUE_LANMOLA,
    ],
    EnemySpriteSet.OW: [
        Enemy.BLUE_LYNEL, Enemy.RED_LYNEL,
        Enemy.BLUE_MOBLIN, Enemy.RED_MOBLIN,
        Enemy.BLUE_TEKTITE, Enemy.RED_TEKTITE,
    ],
}

_MIXED_GROUP_SPRITE_SET: dict[int, EnemySpriteSet] = {
    0x6D: EnemySpriteSet.B,
    0x6E: EnemySpriteSet.A,
    0x6F: EnemySpriteSet.B,
    0x70: EnemySpriteSet.B,
    0x71: EnemySpriteSet.C,
    0x72: EnemySpriteSet.C,
    0x73: EnemySpriteSet.C,
    0x74: EnemySpriteSet.B,
    0x75: EnemySpriteSet.A,
    0x76: EnemySpriteSet.C,
    0x77: EnemySpriteSet.C,
    0x78: EnemySpriteSet.B,
    0x79: EnemySpriteSet.A,
    0x7A: EnemySpriteSet.A,
    0x7B: EnemySpriteSet.C,
    0x7C: EnemySpriteSet.C,
}


def _enemy_name(enemy: Enemy) -> str:
    return enemy.name.replace("_", " ").title()


_FRAME_TILE_WIDTH: dict[Enemy, int] = {
    Enemy.ZOL:           2,
    Enemy.POLS_VOICE:    2,
    Enemy.WALLMASTER:    2,
    Enemy.VIRE:          2,
    Enemy.LIKE_LIKE:     2,
    Enemy.BLUE_TEKTITE:  2,
    Enemy.RED_TEKTITE:   2,
    Enemy.RED_LANMOLA:   2,
    Enemy.BLUE_LANMOLA:  2,
}


def _frame_width(enemy: Enemy, col: int, sorted_unique: list[int]) -> int:
    """Return tile width for a specific frame of an enemy."""
    default = _FRAME_TILE_WIDTH.get(enemy, 4)
    idx = sorted_unique.index(col) if col in sorted_unique else -1
    if idx < 0:
        return default
    if idx + 1 < len(sorted_unique):
        gap = sorted_unique[idx + 1] - col
        if gap in (2, 4):
            return gap
    if idx > 0:
        prev_gap = col - sorted_unique[idx - 1]
        if prev_gap in (2, 4):
            return prev_gap
    return default


def _build_enemy_spoiler_data(game_world: GameWorld) -> dict[str, Any]:
    """Build the enemies section of spoiler data."""
    enemies = game_world.enemies
    sprites = game_world.sprites

    # --- Enemy sprite sets ---
    dungeon_common = bytes(sprites.dungeon_common)
    common_tiles = len(dungeon_common) // 16

    enemy_sets: list[dict[str, Any]] = []
    for sprite_set in (EnemySpriteSet.A, EnemySpriteSet.B, EnemySpriteSet.C, EnemySpriteSet.OW):
        attr = _ENEMY_SET_ATTR[sprite_set]
        bank_bytes = bytes(getattr(sprites, attr))

        if sprite_set == EnemySpriteSet.OW:
            col_start = 156
            frames_bank = bank_bytes
        else:
            col_start = 158 - common_tiles
            frames_bank = dungeon_common + bank_bytes

        members = enemies.cave_groups.get(sprite_set) or _VANILLA_ENEMY_GROUPS.get(sprite_set, [])
        member_names = [_enemy_name(e) for e in members]

        levels_using: list[int | str] = []
        for level in game_world.levels:
            if level.enemy_sprite_set == sprite_set:
                levels_using.append(level.level_num)
        if sprite_set == EnemySpriteSet.OW:
            levels_using.append("OW")

        tile_frame_data: list[dict[str, Any]] = []
        for e in members:
            frames = enemies.tile_frames.get(e, [])
            sorted_unique = sorted(set(frames))
            seen: set[int] = set()
            deduped: list[dict[str, int]] = []
            for col in frames:
                if col not in seen:
                    seen.add(col)
                    deduped.append({"col": col, "width": _frame_width(e, col, sorted_unique)})
            tile_frame_data.append({
                "enemy": _enemy_name(e),
                "frames": deduped,
            })

        mixed_in_set: list[dict[str, Any]] = []
        for code, owner_set in sorted(_MIXED_GROUP_SPRITE_SET.items()):
            if owner_set == sprite_set:
                group_members = enemies.mixed_groups.get(code, [])
                mixed_in_set.append({
                    "group_code": code,
                    "group_num": code - 0x62 + 1,
                    "members": [_enemy_name(e) for e in group_members],
                })

        enemy_sets.append({
            "set": sprite_set.name,
            "bank_b64": base64.b64encode(bank_bytes).decode("ascii"),
            "frames_bank_b64": base64.b64encode(frames_bank).decode("ascii"),
            "col_start": col_start,
            "enemies": member_names,
            "tile_frames": tile_frame_data,
            "levels": levels_using,
            "mixed_groups": mixed_in_set,
        })

    # --- Boss sprite sets ---
    boss_sets: list[dict[str, Any]] = []
    for boss_set in (BossSpriteSet.A, BossSpriteSet.B, BossSpriteSet.C):
        attr = _BOSS_SET_ATTR[boss_set]
        bank_bytes = bytes(getattr(sprites, attr))

        levels_using: list[int] = []
        for level in game_world.levels:
            if level.boss_sprite_set == boss_set:
                levels_using.append(level.level_num)

        boss_sets.append({
            "set": boss_set.name,
            "bank_b64": base64.b64encode(bank_bytes).decode("ascii"),
            "levels": levels_using,
        })

    expansion_b64 = base64.b64encode(
        bytes(sprites.boss_set_expansion),
    ).decode("ascii")

    return {
        "enemy_sets": enemy_sets,
        "boss_sets": boss_sets,
        "boss_expansion_b64": expansion_b64,
    }


def build_spoiler_data(
    game_world: GameWorld,
    config: GameConfig,
    seed: int,
    flag_string: str,
) -> dict[str, Any]:
    """Return a structured, JSON-serializable dict for the interactive spoiler viewer.

    This function takes a GameWorld (the same model produced by parse_game_world),
    making it reusable for any source that produces a GameWorld — including a future
    ROM upload/parse feature.
    """
    # --- Levels ---
    levels_data: list[dict[str, Any]] = []
    for level in game_world.levels:
        palette_hex, palette_hex_dark = _level_palette_hex(level)
        # Build mapping from regular room_num -> staircase info.
        # Transport staircases link two rooms; item staircases link one.
        room_to_staircase: dict[int, dict[str, Any]] = {}
        transport_counter = 0
        transport_letters = "ABCDEFGH"
        for idx, sr in enumerate(level.staircase_rooms):
            sc_index = idx + 1
            if sr.room_type == RoomType.TRANSPORT_STAIRCASE:
                letter = transport_letters[transport_counter] if transport_counter < len(transport_letters) else str(transport_counter + 1)
                transport_counter += 1
                if sr.left_exit is not None:
                    room_to_staircase[sr.left_exit] = {
                        "staircase_index": sc_index,
                        "staircase_type": "transport",
                        "staircase_label": f"Transport {letter}",
                        "staircase_item": None,
                    }
                if sr.right_exit is not None:
                    room_to_staircase[sr.right_exit] = {
                        "staircase_index": sc_index,
                        "staircase_type": "transport",
                        "staircase_label": f"Transport {letter}",
                        "staircase_item": None,
                    }
            elif sr.room_type == RoomType.ITEM_STAIRCASE:
                item_name = _item_name_or_none(sr.item)
                if sr.return_dest is not None:
                    room_to_staircase[sr.return_dest] = {
                        "staircase_index": sc_index,
                        "staircase_type": "item",
                        "staircase_label": f"{item_name} (staircase)" if item_name else "Item Staircase",
                        "staircase_item": item_name,
                    }
        rooms = [_room_dict(r, level, room_to_staircase) for r in level.rooms]
        staircases = [
            _staircase_dict(sr, idx + 1)
            for idx, sr in enumerate(level.staircase_rooms)
        ]
        levels_data.append({
            "level_num": level.level_num,
            "entrance_room": level.entrance_room,
            "boss_room": level.boss_room,
            "palette_hex": palette_hex,
            "palette_hex_dark": palette_hex_dark,
            "rooms": rooms,
            "staircase_rooms": staircases,
        })

    # --- Overworld ---
    ow = game_world.overworld
    screens_data = [
        {
            "screen_num": s.screen_num,
            "row": s.screen_num >> 4,
            "col": s.screen_num & 0x0F,
            "destination": s.destination.name,
            "entrance_type": s.entrance_type.name,
            "enemy": s.enemy_spec.enemy.name,
            "enemy_quantity": s.enemy_quantity,
            "quest_visibility": s.quest_visibility.name,
        }
        for s in ow.screens
    ]

    overworld_data: dict[str, Any] = {
        "start_screen": ow.start_screen,
        "any_road_screens": ow.any_road_screens,
        "recorder_warp_destinations": ow.recorder_warp_destinations,
        "lost_hills_directions": [d.name for d in ow.lost_hills_directions],
        "dead_woods_directions": [d.name for d in ow.dead_woods_directions],
        "screens": screens_data,
    }

    # --- Caves ---
    caves_data = [_cave_dict(c) for c in ow.caves]

    # --- Quotes ---
    show_hint_type = config.hint_mode != HintMode.VANILLA
    quotes_data: list[dict[str, Any]] = []
    for q in sorted(game_world.quotes, key=lambda q: q.quote_id):
        entry: dict[str, Any] = {"quote_id": q.quote_id, "text": q.text}
        if show_hint_type:
            hint_name = _hint_type_label(q.quote_id)
            if hint_name:
                entry["hint_type"] = hint_name
        quotes_data.append(entry)

    return {
        "seed": seed,
        "flag_string": flag_string,
        "levels": levels_data,
        "overworld": overworld_data,
        "caves": caves_data,
        "quotes": quotes_data,
        "enemies": _build_enemy_spoiler_data(game_world),
    }
