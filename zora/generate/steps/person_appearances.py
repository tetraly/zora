"""FP-PERSON-01: each cave person object type takes one of four
appearances (features-behavior.md B10b).

This pass owns the appearance draws. HT-HINT-01's three name pairs read
the result (zora/generate/steps/hint_text.py) instead of drawing their own.
"""
from zora.generate.rng import IntRng
from zora.model.game_world import GameWorld

FIRST_NPC_ENTRY = 0x54               # object type of EnemyData.overworld_npc_pointers[0]
CAVE_PERSON_TYPES = range(0x6B, 0x7C)   # the 17 cave person object types
FIRST_APPEARANCE = 0x58              # ObjAnimations $58-$5B: old man, old woman, merchant, Moblin
APPEARANCE_COUNT = 4


def draw_person_appearances(gw: GameWorld, rng: IntRng) -> None:
    """FP-PERSON-01: one independent uniform draw per cave person type,
    in type order."""
    for object_type in CAVE_PERSON_TYPES:
        gw.enemies.overworld_npc_pointers[object_type - FIRST_NPC_ENTRY] = (
            FIRST_APPEARANCE + rng.below(APPEARANCE_COUNT)
        )


def person_appearance(gw: GameWorld, object_type: int) -> int:
    return gw.enemies.overworld_npc_pointers[object_type - FIRST_NPC_ENTRY]
