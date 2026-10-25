"""The level 9 gate room's secret trigger never opens its shutters (a bypass worry, 2026-10-24).

The room above level 9's entrance ships with trigger 0 (none) or 1 (all dead) in a finished ROM
(late-gate.md VA-REJ-19). Trigger 1 is harmless in play: the game's all-dead check counts the person's
two bonfires (type $40) as living monsters, so "all dead" is never true in that room, and only the
person's own check (pieces, or the gate's item) opens the shutters. This runs both triggers in the
emulator: too few pieces leaves the person in the room with the shutters shut, the gate's requirement
opens them. Tests/test_level_9_entry_emulator.py covers the other Level 9 Entry values."""
import pytest

from tests.needs import needs_base_rom
from tests.test_level_9_entry_emulator import ALL_PIECES, admits, generated, pieces_of
from zora.flags.fields import Level9Requirement
from zora.model.enums import RoomAction
from zora.model.level_9_gate import GateKind
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom

pytestmark = needs_base_rom

SEVEN_PIECES = pieces_of(range(1, 8))
# (C08, seed, the gate room's trigger in that ROM): seeds 1 and 7 ship trigger 0, 2 and 3 trigger 1
# (Eight Pieces); Other Item's seeds 1 and 2 ship trigger 1.
CASES = [(0, 1, RoomAction.NONE), (0, 7, RoomAction.NONE), (0, 2, RoomAction.ALL_DEAD),
         (0, 3, RoomAction.ALL_DEAD), (Level9Requirement.ITEM_INSTEAD_OF_PIECES, 1, RoomAction.ALL_DEAD),
         (Level9Requirement.ITEM_INSTEAD_OF_PIECES, 2, RoomAction.ALL_DEAD)]


@pytest.mark.parametrize(("c08", "seed", "trigger"), CASES)
def test_the_gate_room_opens_only_for_the_requirement(c08: int, seed: int, trigger: RoomAction) -> None:
    rom, gate = generated(c08, seed, remember_repo_base_rom())
    level_9 = next(level for level in parse_rom(rom).levels if level.level_num == 9)
    assert level_9.block.room(level_9.entrance_room - 0x10).room_action == trigger
    if gate.kind is GateKind.ITEM:
        assert not admits(rom, ALL_PIECES)
        assert admits(rom, 0, gate)
    else:
        assert not admits(rom, 0)
        assert not admits(rom, SEVEN_PIECES)
        assert admits(rom, ALL_PIECES)
