"""Post-shapes batch B4: the enemy group pass and the boss group pass
(docs/spec/post-shapes-b4.md @ a123227), with the sprite-bank repack that
runs inside them (post-shapes-b5.md PS-SPR).

Pipeline position: after B2's per-level monster re-deal and before B3's
room exchange (and so before the late gate).
  PS-EGRP-01/02  fifteen enemies dealt into groups 0-3 (group g = enemy
                 bank tier g; 3 = the overworld), partners follow
  PS-SPR-03      their tiles packed into the banks, frame bytes renumbered
  PS-EGRP-03     every ordinary room's monster redrawn from its group
  PS-EGRP-04     the mixed monster lists redrawn the same way
  PS-EGRP-05     overworld screens redrawn from the overworld group
  PS-EGRP-06     the hungry goriya's sprite tile
  PS-BGRP-01/02  bosses dealt into pattern blocks 0-3 (3 = common)
  PS-SPR-02      their tiles packed, frame bytes and operands renumbered
  PS-BGRP-03     every boss room's boss redrawn from its block

Room changes go straight into the pass's staged blocks. Everything outside the
room blocks (tiles, frame bytes, mixed lists, overworld screens, operand
bytes) is STAGED in a GroupShuffleResult and written into the GameWorld only when
the generation pass ships (generation_pass.py), so a restarted generation reads the
base ROM's sprites again.

The overworld half (PS-EGRP-05) reads the staged overworld model after
B8's monster re-deal (PS-OWM), and Zol's hit points as B8's pass left them.
Omitted: the quest-2 room blocks. The spec walks all four room blocks, and
a rebuild MAY skip the two quest-2 ones (post-shapes-b4.md, S6): nothing
reads them under the primary preset, which locks quest 2 out. ZORA ships
quest 1 only (as the late gate's tail does), so the two quest-2 blocks keep
their bytes. This shifts only the random stream (late-gate A24) and the
quest-2 room bytes, which a whole-ROM comparison shows.
"""
from dataclasses import dataclass, field

from ...model.game_world import GameWorld
from ...model.rooms import EnemySpec
from .group_banks import Staged
from .randomize_boss_groups import GLEEOK_HEAP_OFFSET, BossDeal
from .shuffle_enemy_groups import OBJECT_TYPE_OPERAND, EnemyDeal

# --- the passes ------------------------------------------------------------------

@dataclass
class GroupShuffleResult:
    """The two group passes' results; a pass turned off (B42, B40;
    FL-OFF-04) leaves its part empty and stages nothing."""
    staged: Staged = field(default_factory=Staged)
    enemy_deal: EnemyDeal | None = None          # Shuffle Enemy Groups (B42)
    boss_deal: BossDeal | None = None            # Randomize Boss Groups (B40)
    goriya_tile: int | None = None
    rooms_redrawn: int = 0
    bosses_redrawn: int = 0


def apply_groups(gw: GameWorld, state: GroupShuffleResult) -> None:
    """Write the staged results into the GameWorld (ship.py, when the attempt ships)."""
    staged, enemies = state.staged, gw.enemies
    for block, offset, data in staged.tiles:
        gw.sprites.write_tile(block, offset, data)
    for offset, value in sorted(staged.frames.items()):
        enemies.set_frame_bytes(offset, [value])
    if staged.aquamentus_tiles is not None:
        enemies.aquamentus_tile_layout_table = staged.aquamentus_tiles
        enemies.aquamentus_sprite_ptr = staged.aquamentus_open_mouth
    if staged.gleeok_body_tiles is not None:
        enemies.gleeok_body_tiles = staged.gleeok_body_tiles
        enemies.gleeok_head_sprite_ptr_a = staged.gleeok_neck
        enemies.gleeok_head_sprite_ptr_b = staged.gleeok_head
        enemies.gleeok_head_sprite_ptr_c = staged.frames[GLEEOK_HEAP_OFFSET]
    if staged.mixed_lists is not None:
        enemies.mixed_enemy_data = staged.mixed_lists
    for screen in gw.overworld.screens:
        if screen.screen_num in staged.overworld_monsters:
            screen.enemy_spec = EnemySpec(enemy=staged.overworld_monsters[screen.screen_num])
    if staged.item_carrier_operands is not None:
        gw.item_carrier_operands = staged.item_carrier_operands
    if state.enemy_deal is not None:
        # PS-EGRP-05 and PS-EGRP-06's fixed writes: the enemy group pass's
        gw.overworld_wizzrobe_patch = staged.red_wizzrobe_overworld
        gw.object_type_operand_873d = OBJECT_TYPE_OPERAND
