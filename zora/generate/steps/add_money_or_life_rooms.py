"""Add Money or Life Rooms (B22; PS-MERCH-01): life-or-money merchants added to
person rooms."""

from zora.generate.rng import IntRng
from zora.generate.shapes.world import D_KEY1, D_OPEN, D_SHUTTER, set_side, side_of
from zora.generate.steps.item_shuffle_result import ItemShuffleResult, _level_rooms
from zora.generate.steps.shuffle_bomb_upgrade_men import BOMB_UPGRADE_CODE
from zora.generate.steps.shuffle_hungry_goriya import _level9_entry_north
from zora.model.enums import Enemy, RoomAction, Side
from zora.model.levels import MERCHANT_LIST, Level
from zora.model.rooms import MONSTER_BIT_CODE, EnemyInfo, SecretInfo

# --- PS-MERCH --------------------------------------------------------------

MERCHANT_EXCHANGES = 3        # PS-MERCH-01: partial Fisher-Yates exchanges


# --- PS-MERCH --------------------------------------------------------------

def add_money_or_life_rooms(levels: list[Level], state: ItemShuffleResult, rng: IntRng) -> None:
    """PS-MERCH-01 (P13): three partial Fisher-Yates exchanges over the
    candidate list (always made), then the count 1-3; the first `count`
    dealt entries become merchants."""
    skip = _level9_entry_north(levels)
    candidates = [level_room.room for level_room in _level_rooms(levels)
             if level_room.key != skip and level_room.room.is_person
             and level_room.room.monster_list != BOMB_UPGRADE_CODE]
    candidate_count = len(candidates)
    if candidate_count < MERCHANT_EXCHANGES:
        # P23: the pass ends at the first exchange with no candidate left:
        # no merchant this generation pass, and generation continues.
        # Never reached under the primary preset (9-19 candidates).
        return
    for position in range(MERCHANT_EXCHANGES):
        other = position + rng.below(candidate_count - position)
        candidates[position], candidates[other] = candidates[other], candidates[position]
    count = 1 + rng.below(3)
    for room in candidates[:count]:
        # the monster byte is written as $11; the person flag (layout) stays
        room.enemy_info = EnemyInfo(Enemy(MONSTER_BIT_CODE | MERCHANT_LIST))
        # trigger bits 0-2; the item position is kept
        room.secret_info = SecretInfo(RoomAction.MONEY_OR_LIFE, room.item_position)
        for side in Side:
            if side_of(room, side) in (D_OPEN, D_KEY1):
                set_side(room, side, D_SHUTTER)
        state.merchants_added += 1
