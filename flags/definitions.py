"""Flag definition base classes for different flag types."""

from dataclasses import dataclass
from typing import Any, List, Optional

from .categories import FlagCategory


@dataclass
class FlagOption:
    """Represents a single option for an enum flag."""
    value: str
    display_name: str
    help_text: str = ""


class FlagDefinition:
    """Base class for flag definitions with inline value specifications."""

    def __init__(
        self,
        key: str,
        display_name: str,
        help_text: str,
        category: FlagCategory,
        subcategory: Optional[str] = None,
        affects_file_string: bool = None
    ):
        self.key = key
        self.display_name = display_name
        self.help_text = help_text
        self.category = category
        self.subcategory = subcategory
        # Allow override, otherwise use category default
        self._affects_file_string = affects_file_string

    @property
    def affects_file_string(self) -> bool:
        """Whether this flag should be included in the file string."""
        if self._affects_file_string is not None:
            return self._affects_file_string
        return self.category.affects_file_string

    def get_default(self) -> Any:
        """Get the default value for this flag."""
        raise NotImplementedError

    def validate(self, value: Any) -> Any:
        """Validate and convert value if needed. Returns validated value."""
        raise NotImplementedError


class BooleanFlag(FlagDefinition):
    """A simple boolean flag."""

    def __init__(
        self,
        key: str,
        display_name: str,
        help_text: str,
        category: FlagCategory,
        subcategory: Optional[str] = None,
        default: bool = False,
        affects_file_string: bool = None
    ):
        super().__init__(key, display_name, help_text, category, subcategory, affects_file_string)
        self.default = default

    def get_default(self) -> bool:
        return self.default

    def validate(self, value: Any) -> bool:
        if not isinstance(value, bool):
            raise TypeError(f"Flag '{self.key}' expects boolean, got {type(value).__name__}")
        return value


class EnumFlag(FlagDefinition):
    """A flag with multiple predefined options."""

    def __init__(
        self,
        key: str,
        display_name: str,
        help_text: str,
        category: FlagCategory,
        options: List[FlagOption],
        subcategory: Optional[str] = None,
        default: str = None,
        affects_file_string: bool = None
    ):
        super().__init__(key, display_name, help_text, category, subcategory, affects_file_string)
        self.options = options
        self.option_dict = {opt.value: opt for opt in options}
        # Default to first option if not specified
        self.default = default if default is not None else options[0].value

        if self.default not in self.option_dict:
            raise ValueError(f"Default value '{self.default}' not in options for flag '{key}'")

    def get_default(self) -> str:
        return self.default

    def validate(self, value: Any) -> str:
        # Convert to string if needed
        if not isinstance(value, str):
            value = str(value)

        if value not in self.option_dict:
            valid_options = ", ".join(self.option_dict.keys())
            raise ValueError(
                f"Flag '{self.key}' expects one of [{valid_options}], got '{value}'"
            )
        return value

    def get_option_display_name(self, value: str) -> str:
        """Get the display name for a given option value."""
        return self.option_dict.get(value, FlagOption(value, value)).display_name


class IntegerFlag(FlagDefinition):
    """A flag with an integer value and optional range constraints."""

    def __init__(
        self,
        key: str,
        display_name: str,
        help_text: str,
        category: FlagCategory,
        default: int,
        subcategory: Optional[str] = None,
        min_value: int = None,
        max_value: int = None,
        affects_file_string: bool = None
    ):
        super().__init__(key, display_name, help_text, category, subcategory, affects_file_string)
        self.default = default
        self.min_value = min_value
        self.max_value = max_value

        # Validate default is in range
        self.validate(default)

    def get_default(self) -> int:
        return self.default

    def validate(self, value: Any) -> int:
        if not isinstance(value, int):
            raise TypeError(f"Flag '{self.key}' expects integer, got {type(value).__name__}")

        if self.min_value is not None and value < self.min_value:
            raise ValueError(
                f"Flag '{self.key}' value {value} below minimum {self.min_value}"
            )
        if self.max_value is not None and value > self.max_value:
            raise ValueError(
                f"Flag '{self.key}' value {value} above maximum {self.max_value}"
            )
        return value
