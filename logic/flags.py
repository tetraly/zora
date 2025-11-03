"""
Backward compatibility shim for logic.flags module.
The actual implementation has been moved to /flags/ package at the root level.
This file re-exports everything to maintain backward compatibility.
"""

# Re-export everything from the flags package (now at root level)
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flags import (
    FlagCategory,
    BooleanFlag,
    EnumFlag,
    IntegerFlag,
    FlagDefinition,
    FlagOption,
    FlagRegistry,
    Flags,
    FlagsEnum,
)

__all__ = [
    'FlagCategory',
    'BooleanFlag',
    'EnumFlag',
    'IntegerFlag',
    'FlagDefinition',
    'FlagOption',
    'FlagRegistry',
    'Flags',
    'FlagsEnum',
]
