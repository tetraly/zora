"""The overworld monsters', hit points' and level 9 records' figures
(post-shapes-b8.md)."""

import statistics
from typing import Any

from zora.model.enums import Enemy
from zora.model.game_world import GameWorld
from zora.model.levels import GANON_LIST, ZELDA_LIST
from zora_measure.checkpoints.groups_and_palettes import _vanilla
from zora_measure.checkpoints.summaries import LEVELS_7_9, Summary

# --- B8: overworld monsters, hit points, level 9's records (post-shapes-b8.md) ---

SPEC_B8 = "post-shapes-b8.md @ c2d0322"
OWM_SCREEN_11 = 11
GLEEOK_HEAD_VALUES = (4, 5, 6, 7, 8)
HP_WALK = 2                           # PS-HP: a nibble moves at most two


def _ow_pair(gw: GameWorld, screen: int) -> tuple[int, bool]:
    """(whole table-C byte, table-D bit 7) of an overworld screen."""
    s = gw.overworld.screens[screen]
    code = s.enemy_spec.enemy.value
    return (gw.overworld.qty_table.index(s.enemy_quantity) << 6) | (code & 0x3F), code >= 0x40


def owm_non_candidates_kept(gw: GameWorld) -> bool:
    """PS-OWM-01/03: screens that are not candidates keep PRG0's pair,
    apart from 119 and the start screen S (OW-START-01's exchange)."""
    from zora.generate.steps.shuffle_overworld_monsters import EXCLUDED_MONSTER_BYTES
    from zora.generate.steps.shuffle_start_screen import PRG0_START_SCREEN
    base = _vanilla()
    exchanged = {PRG0_START_SCREEN, gw.overworld.start_screen}
    return all(_ow_pair(gw, s) == _ow_pair(base, s) for s in range(128)
               if _ow_pair(base, s)[0] in EXCLUDED_MONSTER_BYTES and s not in exchanged)


def owm_screens(gw: GameWorld) -> dict[str, bool]:
    from zora.generate.steps.shuffle_start_screen import PRG0_START_SCREEN as OLD_START
    base = _vanilla()
    return {"11 keeps $10": _ow_pair(gw, OWM_SCREEN_11) == _ow_pair(base, OWM_SCREEN_11),
            "119 byte differs": _ow_pair(gw, OLD_START)[0] != _ow_pair(base, OLD_START)[0],
            "119 flag differs": _ow_pair(gw, OLD_START)[1] != _ow_pair(base, OLD_START)[1]}


def start_screen_takes_119s_pair(gw: GameWorld) -> tuple[int, int]:
    """PS-OWM-03: with S not 119, S holds PRG0's 119 pair (byte $00, bit 7
    clear); (hits, cases)."""
    from zora.generate.steps.shuffle_start_screen import PRG0_START_SCREEN as OLD_START
    start = gw.overworld.start_screen
    if start == OLD_START:
        return 0, 0
    return int(_ow_pair(gw, start) == _ow_pair(_vanilla(), OLD_START)), 1


def screen_119_layout_kept(gw: GameWorld) -> bool:
    """PS-OWM-03: the other seven bits of 119's LevelBlockAttrsD byte (the
    screen layout) keep PRG0's value."""
    from zora.generate.steps.shuffle_start_screen import PRG0_START_SCREEN as OLD_START
    return gw.overworld.screens[OLD_START].screen_code == _vanilla().overworld.screens[OLD_START].screen_code


def owm_no_barred_placement(gw: GameWorld) -> bool:
    """PS-OWM-02 on the finished overworld (lists read from PRG0's)."""
    from zora.generate.steps.shuffle_overworld_monsters import MonsterPair, _is_barred
    base = _vanilla()
    return not any(_is_barred(base, MonsterPair(s.enemy_spec, s.enemy_quantity), s.screen_num)
                   for s in gw.overworld.screens)


def _hp_offsets(gw: GameWorld, object_types: range) -> list[int]:
    """Each object type's hit-point value minus PRG0's."""
    base = _vanilla().enemies.hp
    return [gw.enemies.hp[Enemy(t)] - base[Enemy(t)] for t in object_types]


def enemy_hp_walk(gw: GameWorld) -> dict[str, Any]:
    """PS-HP-01: object types $00-$31 and the rope within PRG0's value +-2."""
    from zora.generate.steps.change_enemy_hp import ENEMY_HP_TYPES
    moves = _hp_offsets(gw, ENEMY_HP_TYPES)
    rope = gw.enemies.rope_hp or (0, 0)
    return {"within 2": all(abs(m) <= HP_WALK for m in moves)
            and all(abs(v - b) <= HP_WALK for v, b in zip(rope, (1, 4), strict=True)),
            "mean move": statistics.mean(moves), "unchanged": sum(m == 0 for m in moves) / len(moves)}


HP_WALK_SUMMARY = Summary(
    lambda values: (f"{sum(v['within 2'] for v in values)}/{len(values)}; mean move "
                    f"{statistics.mean(v['mean move'] for v in values):+.3f}; unchanged "
                    f"{statistics.mean(v['unchanged'] for v in values):.3f}"),
    lambda value: {"within 2": float(value["within 2"]), "mean move": float(value["mean move"]),
                   "unchanged": float(value["unchanged"])}
)


def boss_hp_walk(gw: GameWorld) -> dict[str, bool]:
    """PS-HP-02: object types $32-$49 within PRG0's value +-2; the four
    mirrors equal their type's value; the head in 4..8."""
    from zora.generate.steps.change_enemy_hp import BOSS_HP_TYPES, BOSS_MIRRORS
    enemies = gw.enemies
    return {"within 2": all(abs(m) <= HP_WALK for m in _hp_offsets(gw, BOSS_HP_TYPES)),
            "mirrors": all(getattr(enemies, name) == enemies.hp[enemy]
                           for enemy, name in BOSS_MIRRORS.items()),
            "head 4-8": enemies.gleeok_head_hp in GLEEOK_HEAD_VALUES}


def gleeok_head_hp(gw: GameWorld) -> int:
    return gw.enemies.gleeok_head_hp


def level9_records_match(gw: GameWorld) -> dict[str, bool]:
    """PS-L9REC-01: one $37 room and one $3E room in level 9's block, and
    the records name them; level 9's boss record off vanilla; levels 1-8's
    boss records vanilla."""
    rooms = gw.blocks[LEVELS_7_9].rooms
    zelda = [r.room_num for r in rooms if r.monster_list | (r.count_index << 6) == ZELDA_LIST]
    ganon = [r.room_num for r in rooms if r.monster_list | (r.count_index << 6) == GANON_LIST]
    level9 = gw.levels[8]
    vanilla = _vanilla().levels
    return {"records": zelda == [level9.triforce_room_ptr] and ganon == [level9.boss_room],
            "L9 boss record changed": level9.boss_room != vanilla[8].boss_room,
            "L1-8 boss records vanilla": all(level.boss_room == old.boss_room
                                             for level, old in zip(gw.levels[:8], vanilla[:8], strict=True))}


def wizzrobe_overworld_patch(gw: GameWorld) -> bool:
    return gw.overworld_wizzrobe_patch
