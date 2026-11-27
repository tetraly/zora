"""FP-PERSON-01: each cave person object type takes one of four
appearances (features-behavior.md B10b).

This pass owns the appearance draws. HT-HINT-01's three name pairs read
the result (zora/generate/steps/hint_text.py) instead of drawing their own.
"""
from ...model.game_world import GameWorld
from ..rng import IntRng

FIRST_NPC_ENTRY = 0x54               # object type of EnemyData.overworld_npc_pointers[0]
CAVE_PERSON_TYPES = range(0x6B, 0x7C)   # the 17 cave person object types
FIRST_APPEARANCE = 0x58              # ObjAnimations $58-$5B: the two elders, merchant, Moblin
APPEARANCE_COUNT = 4
APPEARANCE_FRAME_LENGTH = 1          # a person's one tile; the game draws both halves from it


def draw_person_appearances(gw: GameWorld, rng: IntRng) -> None:
    """FP-PERSON-01: one independent uniform draw per cave person type,
    in type order.

    Each type takes its appearance's frame list with the pointer. ObjAnimFrameHeap holds one list
    per pointer, written from the first type that names it, so a type keeping its old list (the
    elder's [$98] for most) overwrote the merchant's $9C and the Moblin's $F8: both are drawn as two
    unmirrored tiles, so either showed the elder's half beside $9A (2.0.2 test report, seed 123)."""
    enemies = gw.enemies
    appearance_frames = {appearance: enemies.frame_bytes(appearance, APPEARANCE_FRAME_LENGTH)
                         for appearance in range(FIRST_APPEARANCE, FIRST_APPEARANCE + APPEARANCE_COUNT)}
    for object_type in CAVE_PERSON_TYPES:
        appearance = FIRST_APPEARANCE + rng.below(APPEARANCE_COUNT)
        enemies.overworld_npc_pointers[object_type - FIRST_NPC_ENTRY] = appearance
        enemies.overworld_npc_frames[object_type - FIRST_NPC_ENTRY] = list(appearance_frames[appearance])


def person_appearance(gw: GameWorld, object_type: int) -> int:
    return gw.enemies.overworld_npc_pointers[object_type - FIRST_NPC_ENTRY]
