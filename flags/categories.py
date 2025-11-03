"""Flag categories for organizing flags in the UI."""

from enum import IntEnum


class FlagCategory(IntEnum):
    """Categories for organizing flags in the UI."""
    ITEM_SHUFFLE = 1
    ITEM_CHANGES = 2
    OVERWORLD_RANDOMIZATION = 3
    LOGIC_AND_DIFFICULTY = 4
    QUALITY_OF_LIFE = 5
    EXPERIMENTAL = 6
    LEGACY = 7
    HIDDEN = 8
    COSMETIC = 9  # Flags that don't affect seed generation/file string

    @property
    def display_name(self) -> str:
        """Get user-friendly display name for the category."""
        names = {
            FlagCategory.ITEM_SHUFFLE: "Item Shuffle",
            FlagCategory.ITEM_CHANGES: "Item Changes",
            FlagCategory.OVERWORLD_RANDOMIZATION: "Overworld Randomization",
            FlagCategory.LOGIC_AND_DIFFICULTY: "Logic & Difficulty",
            FlagCategory.QUALITY_OF_LIFE: "Quality of Life / Other",
            FlagCategory.EXPERIMENTAL: "Experimental (WARNING: Not thoroughly tested, may cause unexpected behavior or crashes)",
            FlagCategory.LEGACY: "Legacy Flags from Tetra's Item Randomizer (intended for vanilla ROMs only)",
            FlagCategory.HIDDEN: "Hidden",
            FlagCategory.COSMETIC: "Cosmetic (doesn't affect seed generation)",
        }
        return names.get(self, "Unknown")

    @property
    def affects_file_string(self) -> bool:
        """Whether flags in this category affect the file string."""
        # COSMETIC flags don't affect gameplay/generation, so exclude from file string
        return self != FlagCategory.COSMETIC
