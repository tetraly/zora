"""Mirror Overworld (B06; overworld-behavior.md OW-MIR-02 and OW-MIR-03) on the model: the overworld data
the world holds, flipped left to right, so the world describes the game as played and a ROM parsed back
gives the same world (game data in the model, owner ruling 2026-10-13).

Screen s becomes m(s) = s XOR $0F (same row, column c becomes 15 - c). What the model holds moves with
it: each screen's tables by its new number (the serializer writes them by screen number), its cave-exit
column, the start screen, the Any Road screens, the secret Armos screens and columns, the whirlwind
list, the recorder's secret screens and the mazes' right and left. The rest of the flip (the layout
rows, the column heaps, the shortcut stairs' columns, PRG0's code bytes, the spawn spots and the
caption) is not in the model: the writer applies it to the image when the world is mirrored
(zora/rom/mirror_overworld.py mirror_image, from final_steps.write_code_patches).

FINISH flips a copy of the built world just before it is written (pipeline.written_world): generation,
its logic and the hint text (which states each door's region after the flip, HT-MIR-01) work on the world
left to right as PRG0's. Caves and dungeons are not flipped."""
from ...model.enums import OverworldDirection
from ...model.game_world import GameWorld
from ...rom.mirror_overworld import mirror_screen

LAST_COLUMN = 0x0F                   # a square column c becomes LAST_COLUMN - c, its low nibble XOR $0F
HIGH_NIBBLE_COLUMN = 0xF0            # a byte holding the column in bits 7-4
BYTE = 0x100
MIRRORED_DIRECTIONS = {OverworldDirection.RIGHT_EAST: OverworldDirection.LEFT_WEST,
                       OverworldDirection.LEFT_WEST: OverworldDirection.RIGHT_EAST}


def mirror_overworld(world: GameWorld) -> None:
    """OW-MIR-02 step 1 and OW-MIR-03 on the world's overworld, in place, once; the world then says so
    (GameWorld.overworld_mirrored)."""
    assert not world.overworld_mirrored, "the overworld is flipped once"
    overworld = world.overworld
    for screen in overworld.screens:
        screen.screen_num = mirror_screen(screen.screen_num)
        screen.exit_x_position ^= LAST_COLUMN
    # in screen order again: the list is indexed by screen number (mixed_overworld_quest and others)
    overworld.screens[:] = sorted(overworld.screens, key=lambda screen: screen.screen_num)
    overworld.start_screen = mirror_screen(overworld.start_screen)
    overworld.any_road_screens = [mirror_screen(screen) for screen in overworld.any_road_screens]
    overworld.armos_screen_ids = [mirror_screen(screen) for screen in overworld.armos_screen_ids]
    overworld.armos_positions = [position ^ HIGH_NIBBLE_COLUMN for position in overworld.armos_positions]
    # the recorder's whirlwind arrives on the screen right of the listed one: OW-WARP-01's rule on the
    # flipped door ($80, a placeholder, becomes $8F like any other screen number)
    overworld.recorder_warp_destinations = [(mirror_screen((screen + 1) % BYTE) - 1) % BYTE
                                            for screen in overworld.recorder_warp_destinations]
    overworld.recorder_secret_screens = [mirror_screen(screen) for screen in overworld.recorder_secret_screens]
    overworld.dead_woods_directions = [MIRRORED_DIRECTIONS.get(step, step) for step in overworld.dead_woods_directions]
    overworld.lost_hills_directions = [MIRRORED_DIRECTIONS.get(step, step) for step in overworld.lost_hills_directions]
    world.overworld_mirrored = True
