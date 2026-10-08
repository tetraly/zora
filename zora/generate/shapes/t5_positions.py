"""T5 screen positions per screen type (SH-ROOM-11), extracted from
docs/spec/shapes-behavior.md by scripts/import_t5.py.

Screen type = layout code, or layout | 0x40 for the push-block
variant. Values are packed $XY screen positions (same format as the
levels' item_position_table entries). A screen type absent from
T5_BASE holds NO items under the base list; with
universal_drops it uses T5_UNIVERSAL (which may grant positions).
"""

T5_BASE: dict[int, tuple[int, ...]] = {
    0x00: (135, 137, 153, 172),
    0x02: (135, 137, 200),
    0x03: (137, 153, 201),
    0x04: (137, 201),
    0x05: (44, 220),
    0x06: (137, 172),
    0x08: (137,),
    0x0A: (137,),
    0x0C: (136,),
    0x0D: (172, 214),
    0x0E: (137,),
    0x0F: (137,),
    0x11: (137,),
    0x12: (138, 214, 220),
    0x13: (137, 138),
    0x14: (137, 138),
    0x15: (135, 136, 138),
    0x16: (136, 137),
    0x17: (137, 138),
    0x18: (137, 138, 200),
    0x19: (137,),
    0x1B: (137,),
    0x1C: (214,),
    0x1D: (137, 138, 201),
    0x1E: (38, 214),
    0x1F: (201,),
    0x23: (137,),
    0x24: (135, 137),
    0x25: (137,),
    0x26: (137,),
    0x28: (137,),
    0x29: (137,),
    0x5A: (214,),
    0x63: (137,),
}

T5_UNIVERSAL: dict[int, tuple[int, ...]] = {
    0x00: (44, 38, 135, 136, 137, 138, 153, 172, 200, 201, 214, 220),
    0x01: (44, 38, 135, 136, 137, 138, 153, 172, 200, 214, 220),
    0x02: (44, 38, 135, 136, 137, 138, 153, 172, 200, 201, 214, 220),
    0x03: (44, 38, 135, 136, 137, 138, 153, 172, 200, 201, 214, 220),
    0x04: (44, 38, 135, 136, 137, 138, 153, 201),
    0x05: (44, 135, 136, 137, 138, 153, 172, 201, 220),
    0x06: (38, 135, 136, 137, 138, 153, 172, 200, 214),
    0x07: (44, 38, 136, 138, 172, 200, 214, 220),
    0x08: (44, 38, 136, 137, 138, 153, 172, 214, 220),
    0x0A: (44, 38, 135, 136, 137, 138, 172, 200, 201, 214, 220),
    0x0B: (44, 38, 137, 138, 153, 172, 214, 220),
    0x0C: (44, 38, 135, 136, 137, 138, 153, 172, 201, 214),
    0x0D: (44, 38, 136, 138, 153, 172, 200, 214, 220),
    0x10: (44, 38, 153, 172, 214, 220),
    0x11: (38, 135, 136, 137, 138, 153, 172, 200, 201, 220),
    0x12: (44, 38, 137, 138, 153, 214, 220),
    0x13: (44, 38, 135, 136, 137, 138, 153),
    0x14: (44, 38, 136, 137, 138, 153, 172, 214, 220),
    0x15: (44, 38, 135, 136, 138, 172, 214, 220),
    0x16: (136, 137, 138, 153, 200, 201),
    0x17: (135, 137, 138, 200, 201),
    0x18: (44, 137, 138, 153, 172, 201, 220),
    0x19: (136, 137, 138, 153, 200, 201),
    0x1A: (44, 38, 172, 200, 201, 214, 220),
    0x1B: (44, 38, 135, 136, 137, 138, 153, 201),
    0x1C: (44, 38, 136, 138, 172, 214, 220),
    0x1D: (44, 38, 135, 136, 137, 138, 153, 172, 200, 201, 214, 220),
    0x1E: (44, 38, 135, 153, 172, 200, 201, 214, 220),
    0x1F: (44, 38, 135, 136, 138, 153, 172, 200, 201, 214, 220),
    0x22: (44, 38, 135, 136, 137, 138, 153, 172, 200, 201, 214, 220),
    0x23: (44, 38, 135, 136, 137, 138, 172, 200, 201, 214, 220),
    0x24: (135, 136, 137, 138, 153, 172, 200, 201),
    0x25: (44, 38, 135, 136, 137, 138, 153, 172, 200, 201, 214, 220),
    0x26: (44, 38, 135, 136, 137, 138, 153, 172, 200, 201, 214, 220),
    0x27: (135, 136, 137, 138, 153, 172, 200, 201),
    0x28: (135, 136, 137, 138, 153, 172, 200, 201),
}


def item_slots_for(screen_type: int, level_position_table: "list[int]",
                   universal_drops: bool) -> "tuple[int, ...]":
    """Indices (0-3) of the level's standard positions this screen type allows.

    SH-ROOM-11 model: T5 lists packed $XY screen positions per screen type;
    a room may hold an item only at slot i where level_table[i] is on the
    screen type's list (base, plus universal additions when the option is
    on — a type with no base row gets ONLY the universal list then)."""
    vals = set(T5_BASE.get(screen_type, ()))
    if universal_drops:
        vals |= set(T5_UNIVERSAL.get(screen_type, ()))
    return tuple(i for i, v in enumerate(level_position_table) if v in vals)
