"""Enemy randomization orchestrator.

Called by generate_game as a single pipeline step. Dispatches to the
individual enemy randomization functions in the correct order, gating
each on the appropriate GameConfig flags.

Call order (matches original C# ordering):
1. shuffle_bosses — reassigns boss tiers to dungeons
2. shuffle_monsters_between_levels — moves enemies across levels
3. shuffle_monsters — shuffles enemies within each level
4. remap_overworld_monsters — shuffles overworld enemy placements
5. randomize_hp — adjusts enemy/boss HP (self-gates per branch)
6. shuffle_enemy_groups — shuffles which enemies share sprite banks
7. change_dungeon_boss_groups — redistributes bosses across sprite-set groups
"""

from __future__ import annotations

from zora.data_model import Enemy, GameWorld
from zora.dungeon.dungeon import fix_pushblock_staircase_shutters
from zora.enemy.change_dungeon_boss_groups import change_dungeon_boss_groups
from zora.enemy.change_dungeon_enemy_groups import change_dungeon_enemy_groups
from zora.enemy.hp import randomize_hp
from zora.enemy.remap_overworld_monsters import remap_overworld_monsters
from zora.enemy.shuffle_bosses import shuffle_bosses
from zora.enemy.shuffle_monsters import shuffle_monsters
from zora.enemy.shuffle_monsters_between_levels import shuffle_monsters_between_levels
from zora.game_config import GameConfig
from zora.level_gen.orchestrator import fix_npc_shutter_doors
from zora.rng import Rng


def randomize_enemies(
    game_world: GameWorld,
    config: GameConfig,
    rng: Rng,
) -> None:
    """Run all enemy randomization steps in order.

    Each sub-function either self-gates on its config flags or is gated
    here. The call order matters — sprite group changes must happen before
    individual enemy shuffling so that the shufflers operate on the
    updated enemy rosters.

    Args:
        game_world: The game state to modify in place.
        config: Resolved game configuration.
        rng: Shared RNG instance (state flows between steps).
    """

    # GLEEOK_1 is glitchy — replace any vanilla instances with GLEEOK_2.
    _replace_gleeok_1(game_world)

    if config.shuffle_bosses:
        shuffle_bosses(game_world, rng)

    if config.shuffle_monsters_between_levels:
        shuffle_monsters_between_levels(game_world, rng, config.include_level_9)

    if config.shuffle_dungeon_monsters:
        shuffle_monsters(
            game_world, rng,
            shuffle=config.shuffle_dungeon_monsters,
            shuffle_gannon=config.shuffle_ganon_zelda,
            must_beat_gannon=config.force_ganon,
        )

    if config.randomize_overworld_enemies:
        remap_overworld_monsters(game_world, rng)

    randomize_hp(game_world, config, rng)

    if config.shuffle_enemy_groups:
        change_dungeon_enemy_groups(
            game_world, rng,
            overworld=config.randomize_overworld_enemies,
            force_wizzrobes_to_9=not config.include_level_9,
        )

    if config.change_dungeon_boss_groups:
        change_dungeon_boss_groups(game_world, rng)

    for level in game_world.levels:
        fix_npc_shutter_doors(level)
        fix_pushblock_staircase_shutters(level)


def _replace_gleeok_1(game_world: GameWorld) -> None:
    """Replace all GLEEOK_1 enemy placements with GLEEOK_2.

    GLEEOK_1 is visually glitchy and should never appear in the game.
    """
    for level in game_world.levels:
        for room in level.rooms:
            if room.enemy_spec.enemy == Enemy.GLEEOK_1:
                room.enemy_spec.enemy = Enemy.GLEEOK_2
