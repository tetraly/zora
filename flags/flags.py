"""Flags class for managing flag values with validation and serialization."""

from enum import Enum
from typing import Any, Dict, Optional

from .definitions import BooleanFlag, EnumFlag, IntegerFlag, FlagDefinition
from .registry import FlagRegistry


class Flags:
    """Container for flag values with validation and serialization."""

    def __init__(self):
        # Initialize all flags with their default values
        self._definitions = FlagRegistry.get_all_flags()
        self._values: Dict[str, Any] = {
            key: defn.get_default()
            for key, defn in self._definitions.items()
        }

    def __getattr__(self, key: str) -> Any:
        """Access flags as attributes: flags.shuffle_caves"""
        if key.startswith('_'):
            # Allow normal attribute access for private attributes
            return object.__getattribute__(self, key)

        if key in self._values:
            return self._values[key]

        raise AttributeError(f"Flag '{key}' not found")

    def __setattr__(self, key: str, value: Any):
        """Set flags as attributes: flags.shuffle_caves = True"""
        if key.startswith('_'):
            # Allow normal attribute setting for private attributes
            object.__setattr__(self, key, value)
            return

        self.set(key, value)

    def get(self, key: str, default: Any = None) -> Any:
        """Get flag value with optional default."""
        return self._values.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set flag value with validation."""
        if key not in self._definitions:
            raise KeyError(f"Flag '{key}' not found.")

        definition = self._definitions[key]
        validated_value = definition.validate(value)
        self._values[key] = validated_value

    def get_definition(self, key: str) -> Optional[FlagDefinition]:
        """Get the definition for a flag."""
        return self._definitions.get(key)

    def to_dict(self, include_non_file_string: bool = True) -> Dict[str, Any]:
        """
        Export flags to dictionary.

        Args:
            include_non_file_string: If False, exclude flags that don't affect file string
        """
        result = {}
        for key, value in self._values.items():
            definition = self._definitions[key]

            # Skip flags that don't affect file string if requested
            if not include_non_file_string and not definition.affects_file_string:
                continue

            result[key] = value

        return result

    def from_dict(self, data: Dict[str, Any]) -> None:
        """Import flags from dictionary."""
        for key, value in data.items():
            try:
                self.set(key, value)
            except (KeyError, TypeError, ValueError) as e:
                # Log warning but continue
                import logging
                logging.warning(f"Failed to set flag '{key}': {e}")

    def to_file_string(self) -> str:
        """
        Generate a compact string representation for filenames.
        Only includes flags that affect the file string.
        """
        parts = []
        for key, value in sorted(self._values.items()):
            definition = self._definitions[key]

            # Skip flags that don't affect file string
            if not definition.affects_file_string:
                continue

            # Skip flags at default value to keep string compact
            if value == definition.get_default():
                continue

            # Encode flag based on type
            if isinstance(definition, BooleanFlag):
                if value:  # Only include if True
                    parts.append(key[0:3])  # Use first 3 chars as abbreviation
            elif isinstance(definition, EnumFlag):
                # Use abbreviation + value abbreviation
                parts.append(f"{key[0:3]}{value[0:3]}")
            elif isinstance(definition, IntegerFlag):
                parts.append(f"{key[0:3]}{value}")

        return "_".join(parts) if parts else "default"

    def get_all_definitions(self) -> Dict[str, FlagDefinition]:
        """Get all flag definitions."""
        return self._definitions.copy()


# Backward compatibility: Expose old FlagsEnum for UI code
class FlagsEnum(Enum):
    """Backward compatibility wrapper for existing UI code."""

    @classmethod
    def get_flag_list(cls):
        """Get flag list in old format for backward compatibility."""
        flag_list = []
        for key, defn in FlagRegistry.get_all_flags().items():
            flag_list.append((key, defn.display_name, defn.help_text))
        return flag_list

    # Also expose properties that UI code expects
    @property
    def value(self) -> str:
        """Flag key (for backward compatibility)."""
        return self.name.lower()

    @property
    def display_name(self) -> str:
        """Display name (for backward compatibility)."""
        defn = FlagRegistry.get_all_flags().get(self.value)
        return defn.display_name if defn else ""

    @property
    def help_text(self) -> str:
        """Help text (for backward compatibility)."""
        defn = FlagRegistry.get_all_flags().get(self.value)
        return defn.help_text if defn else ""

    @property
    def category(self):
        """Category (for backward compatibility)."""
        defn = FlagRegistry.get_all_flags().get(self.value)
        return defn.category if defn else None
