"""SH-MAP-01 drawing commands: records plus one terminator, laid over the
level's previous command block."""
from zora.generate.shapes.minimap import (
    COMMAND_BLOCK_SIZE, COMMANDS_END, command_block, drawn_commands, synthesize_minimap,
)


def test_commands_end_with_one_terminator() -> None:
    cells = {0x70, 0x71, 0x60}
    _, commands, _, _ = synthesize_minimap(cells)
    assert commands[-1] == COMMANDS_END
    assert drawn_commands(commands) == commands


def test_block_keeps_previous_bytes_past_the_terminator() -> None:
    _, commands, _, _ = synthesize_minimap({0x70, 0x71})
    previous = bytes(range(COMMAND_BLOCK_SIZE))
    block = command_block(commands, previous)
    assert len(block) == COMMAND_BLOCK_SIZE
    assert block[:len(commands)] == commands
    assert block[len(commands):] == previous[len(commands):]
    # the engine reads only through the terminator
    assert drawn_commands(block) == commands
