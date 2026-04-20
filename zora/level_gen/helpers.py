"""Boss room safety checks for new-level generation.

Pure validation functions that determine whether a room's screen type
is compatible with specific boss types.  Used by PlaceBosses and
NewLevelRooms to avoid placing bosses in rooms where they would break.

Ported line-by-line from HelperMethods.cs.
Cross-referenced against Module.cs:
  safeForGleeok  — Module.cs:33065
  safeForGohma   — Module.cs:31807
  safeForDodongo — Module.cs:31839
All three match the .cs decompilation exactly.
"""


def safe_for_gleeok(screen_type: int, boss_id: int) -> bool:
    loc = screen_type & 0x7F
    if loc == 18 or loc == 11 or loc == 36 or loc == 35 or loc == 20 \
            or loc == 9 or loc == 15 or loc == 14:
        return False

    if boss_id % 64 == 5:
        if loc == 19 or loc == 22 or loc == 24 or loc == 25 \
                or loc == 18 or loc == 11 or loc == 20 or loc == 21 \
                or loc == 23:
            return False

    return (loc & 0x40) == 0


def safe_for_gohma(screen_type: int) -> bool:
    loc = screen_type & 0x3F
    return loc != 11 and loc != 18 and loc != 14 and loc != 15


def safe_for_dodongo(screen_type: int) -> bool:
    loc = screen_type & 0x3F
    return loc != 11 and loc != 18 and loc != 14 and loc != 15 and loc != 9
