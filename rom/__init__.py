"""ROM data access module.

This module provides a clean API for reading and modifying ROM game data.
External code should use RomState for all ROM operations.

Public API:
    RomState - Main class for querying/modifying ROM data
    RomData - Data container (for advanced usage)
    TestRomBuilder - Builder for creating test scenarios
    load_from_file, load_from_bytes, load_from_test_data - Loading functions

Internal (not exported):
    Room, Cave - Implementation details, use RomState methods instead

Example:
    from rom import RomState, TestRomBuilder

    # Load from file
    state = RomState.from_rom_file("game.nes")

    # Load from test data
    state = RomState.from_test_data()

    # Build custom test scenario
    state = (TestRomBuilder.from_test_data()
        .with_room_item(3, 0x0F, Item.TRIFORCE)
        .build_state())
"""

from .rom_state import RomState
from .rom_data import RomData, load_from_file, load_from_bytes, load_from_test_data
from .test_rom_builder import TestRomBuilder
from .rom_config import RomLayout, RomRegion, NES_HEADER_SIZE

__all__ = [
    # Main API
    'RomState',
    'RomData',
    'TestRomBuilder',
    # Loading functions
    'load_from_file',
    'load_from_bytes',
    'load_from_test_data',
    # Configuration (for advanced usage)
    'RomLayout',
    'RomRegion',
    'NES_HEADER_SIZE',
]
