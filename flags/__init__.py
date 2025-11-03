"""
Flags system with multi-value support and improved readability.

Key features:
- Inline value definitions for better readability
- Support for boolean, enum, integer flags
- Flags can be excluded from file string (cosmetic flags)
- Type validation
- Backward compatible with existing boolean flags
"""

from .categories import FlagCategory
from .definitions import BooleanFlag, EnumFlag, IntegerFlag, FlagDefinition, FlagOption
from .registry import FlagRegistry
from .flags import Flags, FlagsEnum

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
