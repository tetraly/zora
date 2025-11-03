"""
Flags system with multi-value support and improved readability.

Key features:
- Inline value definitions for better readability
- Support for boolean, enum, integer, and string flags
- Flags can be excluded from file string (cosmetic flags)
- Type validation
- Backward compatible with existing boolean flags
"""

from enum import Enum, IntEnum
from typing import Any, Dict, List, Optional
from dataclasses import dataclass


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
    COSMETIC = 9  # New: Flags that don't affect seed generation/file string

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
        affects_file_string: bool = None
    ):
        self.key = key
        self.display_name = display_name
        self.help_text = help_text
        self.category = category
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
        default: bool = False,
        affects_file_string: bool = None
    ):
        super().__init__(key, display_name, help_text, category, affects_file_string)
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
        default: str = None,
        affects_file_string: bool = None
    ):
        super().__init__(key, display_name, help_text, category, affects_file_string)
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
        min_value: int = None,
        max_value: int = None,
        affects_file_string: bool = None
    ):
        super().__init__(key, display_name, help_text, category, affects_file_string)
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


# ============================================================================
# FLAG REGISTRY
# ============================================================================

class FlagRegistry:
    """Central registry of all flag definitions."""

    # Item Shuffle Flags
    SHUFFLE_WOOD_SWORD_CAVE_ITEM = BooleanFlag(
        'shuffle_wood_sword_cave_item',
        'Shuffle Wood Sword Cave item',
        'Adds the Wood Sword Cave Item to the item shuffle pool. May or may not make the seed unbeatable. Recommended for advanced players only.',
        FlagCategory.ITEM_SHUFFLE
    )

    SHUFFLE_WHITE_SWORD_CAVE_ITEM = BooleanFlag(
        'shuffle_white_sword_cave_item',
        'Shuffle White Sword Cave item',
        'Adds the White Sword Cave item to the item shuffle pool',
        FlagCategory.ITEM_SHUFFLE
    )

    SHUFFLE_MAGICAL_SWORD_CAVE_ITEM = BooleanFlag(
        'shuffle_magical_sword_cave_item',
        'Shuffle Magical Sword Cave item',
        'Adds the Magical Sword to the item shuffle pool. Important Note: If the Magical Sword is shuffled into a room that normally has a standing floor item, it will become a drop item. You will need to defeat all enemies in the room for the Magical Sword to appear.',
        FlagCategory.ITEM_SHUFFLE
    )

    SHUFFLE_LETTER_CAVE_ITEM = BooleanFlag(
        'shuffle_letter_cave_item',
        'Shuffle Letter Cave Item',
        'Adds the Letter Cave Item to the item shuffle.',
        FlagCategory.ITEM_SHUFFLE
    )

    SHUFFLE_ARMOS_ITEM = BooleanFlag(
        'shuffle_armos_item',
        'Shuffle the Armos Item',
        'Adds the Armos item (the Power Bracelet in a vanilla seed) to the item shuffle pool.',
        FlagCategory.ITEM_SHUFFLE
    )

    SHUFFLE_COAST_ITEM = BooleanFlag(
        'shuffle_coast_item',
        'Shuffle the Coast Item',
        'Adds the coast item (a Heart Container in vanilla) to the item shuffle pool.',
        FlagCategory.ITEM_SHUFFLE
    )

    SHUFFLE_SHOP_ARROWS = BooleanFlag(
        'shuffle_shop_arrows',
        'Shuffle Shop Arrows',
        'Adds the wood arrows from the shop to the item shuffle pool.',
        FlagCategory.ITEM_SHUFFLE
    )

    SHUFFLE_SHOP_CANDLE = BooleanFlag(
        'shuffle_shop_candle',
        'Shuffle Shop Candle',
        'Adds the blue candle from the shop to the item shuffle pool.',
        FlagCategory.ITEM_SHUFFLE
    )

    SHUFFLE_SHOP_RING = BooleanFlag(
        'shuffle_shop_ring',
        'Shuffle Shop Ring',
        'Adds the blue ring from the shop to the item shuffle pool. The shop location price will be changed to 150 ± 25 rupees.',
        FlagCategory.ITEM_SHUFFLE
    )

    SHUFFLE_SHOP_BOOK = BooleanFlag(
        'shuffle_shop_book',
        'Shuffle Shop Book',
        'Adds the book from the shop (if one is present) to the item shuffle pool.',
        FlagCategory.ITEM_SHUFFLE
    )

    SHUFFLE_SHOP_BAIT = BooleanFlag(
        'shuffle_shop_bait',
        'Shuffle Shop Bait',
        'Adds one bait from the shops to the item shuffle pool. The other bait location will be replaced with a mystery item.',
        FlagCategory.ITEM_SHUFFLE
    )

    SHUFFLE_POTION_SHOP_ITEMS = BooleanFlag(
        'shuffle_potion_shop_items',
        'Shuffle Potion Shop Items',
        'Adds the potions in the potion shop to the item shuffle pool. Known issue: Red potions in dungeons will be downgraded to blue potions.',
        FlagCategory.ITEM_SHUFFLE
    )

    SHUFFLE_MINOR_DUNGEON_ITEMS = BooleanFlag(
        'shuffle_minor_dungeon_items',
        'Shuffle Minor Dungeon Items',
        'Adds minor items (five rupees, bombs, keys, maps, and compasses) to the item shuffle pool. Primarily designed for use with vanilla ROMs, not Zelda Randomizer ROMs.',
        FlagCategory.LEGACY
    )

    # Overworld Randomization
    SHUFFLE_CAVES = BooleanFlag(
        'shuffle_caves',
        'Shuffle Caves',
        'Shuffles where caves, shops, levels, etc. are on the overworld for 1st quest screens. This flag does not currently shuffle the location of "any road" warp caves. Can be combined with "Shuffle Caves (2nd Quest)" for mixed quest mode.',
        FlagCategory.OVERWORLD_RANDOMIZATION
    )

    SHUFFLE_CAVES_SECOND_QUEST = BooleanFlag(
        'shuffle_caves_second_quest',
        'Shuffle Caves (2nd Quest)',
        'Shuffles where caves, shops, levels, etc. are on the overworld for 2nd quest screens. If both 1st and 2nd quest shuffle flags are enabled, uses mixed quest mode (shuffles all screens from both quests). If only this flag is enabled, shuffles 2nd quest screens only and flips quest bits so they appear in the randomized game.',
        FlagCategory.OVERWORLD_RANDOMIZATION
    )

    PIN_WOOD_SWORD_CAVE = BooleanFlag(
        'pin_wood_sword_cave',
        'Pin Wood Sword Cave to Vanilla Screen',
        'Forces the Wood Sword Cave to remain at its vanilla screen location (0x77). Requires "Shuffle Caves" to be enabled.',
        FlagCategory.OVERWORLD_RANDOMIZATION
    )

    RESTRICT_LEVELS_TO_VANILLA_SCREENS = BooleanFlag(
        'restrict_levels_to_vanilla_screens',
        'Restrict Levels to Vanilla Screens',
        'Levels 1-9 can only shuffle among their 9 vanilla screen locations (they won\'t move to shop/cave locations). Requires "Shuffle Caves" to be enabled.',
        FlagCategory.OVERWORLD_RANDOMIZATION
    )

    RESTRICT_LEVELS_TO_EXPANDED_SCREENS = BooleanFlag(
        'restrict_levels_to_expanded_screens',
        'Restrict Levels to Expanded Screen Pool',
        'Levels 1-9 shuffle among 15 specific screens (the 9 vanilla locations plus 6 additional screens). Requires "Shuffle Caves" to be enabled. Mutually exclusive with "Restrict Levels to Vanilla Screens".',
        FlagCategory.OVERWORLD_RANDOMIZATION
    )

    EXTRA_RAFT_BLOCKS = BooleanFlag(
        'extra_raft_blocks',
        'Extra Raft Blocks',
        'Converts the Westlake Mall and Casino Corner regions into raft-blocked areas, requiring the raft to access additional screens.',
        FlagCategory.OVERWORLD_RANDOMIZATION
    )

    EXTRA_POWER_BRACELET_BLOCKS = BooleanFlag(
        'extra_power_bracelet_blocks',
        'Extra Power Bracelet Blocks',
        'Adds new power bracelet blocks in West Death Mountain. Intended for use with vanilla any road locations.',
        FlagCategory.OVERWORLD_RANDOMIZATION
    )

    RANDOMIZE_LOST_HILLS = BooleanFlag(
        'randomize_lost_hills',
        'Randomize Lost Hills',
        'Randomizes the Lost Hills direction sequence and adds a hint NPC in the game.',
        FlagCategory.OVERWORLD_RANDOMIZATION
    )

    RANDOMIZE_DEAD_WOODS = BooleanFlag(
        'randomize_dead_woods',
        'Randomize Dead Woods',
        'Randomizes the Dead Woods direction sequence and adds a hint NPC in the game.',
        FlagCategory.OVERWORLD_RANDOMIZATION
    )

    RANDOMIZE_HEART_CONTAINER_REQUIREMENTS = BooleanFlag(
        'randomize_heart_container_requirements',
        'Randomize Heart Container Requirements',
        'Randomizes the heart container requirements for the White Sword cave (4-6 hearts) and Magical Sword cave (10-12 hearts). NPCs will provide hints about the requirements.',
        FlagCategory.OVERWORLD_RANDOMIZATION
    )

    DONT_GUARANTEE_STARTING_SWORD_OR_WAND = BooleanFlag(
        'dont_guarantee_starting_sword_or_wand',
        'Don\'t Guarantee Starting Sword or Wand',
        'By default, either the wood sword cave or letter cave is guaranteed to be accessible from an open screen (no special items required) and contains a sword or wand. Enable this flag to remove that guarantee. You may need to find additional progression items and/or dive dungeons weaponless to get a weapon and complete the seed.',
        FlagCategory.OVERWORLD_RANDOMIZATION
    )

    # Logic & Difficulty
    AVOID_REQUIRED_HARD_COMBAT = BooleanFlag(
        'avoid_required_hard_combat',
        'Avoid Requiring "Hard" Combat',
        'The logic will not require killing any Blue Darknuts, Blue Wizzrobes, Gleeoks, or Patras to progress without making at least one sword upgrade and at least one ring available in logic. Now supports both vanilla and Zelda Randomizer ROMs by reading mixed enemy group data directly from the ROM.',
        FlagCategory.LOGIC_AND_DIFFICULTY
    )

    FORCE_ARROW_TO_LEVEL_NINE = BooleanFlag(
        'force_arrow_to_level_nine',
        'Force an arrow to be in level 9',
        'Require that an arrow be in level 9. Warning: seeds with two items forced to level nine may take a long time to generate. Seeds with three items forced to level nine will be impossible to generate.',
        FlagCategory.LOGIC_AND_DIFFICULTY
    )

    FORCE_RING_TO_LEVEL_NINE = BooleanFlag(
        'force_ring_to_level_nine',
        'Force a ring to be in level 9',
        'Require that a ring be in level 9. Warning: seeds with two items forced to level nine may take a long time to generate. Seeds with three items forced to level nine will be impossible to generate.',
        FlagCategory.LOGIC_AND_DIFFICULTY
    )

    FORCE_WAND_TO_LEVEL_NINE = BooleanFlag(
        'force_wand_to_level_nine',
        'Force a wand to be in level 9',
        'Require that a wand be in level 9. Warning: seeds with two items forced to level nine may take a long time to generate. Seeds with three items forced to level nine will be impossible to generate.',
        FlagCategory.LOGIC_AND_DIFFICULTY
    )

    FORCE_HEART_CONTAINER_TO_LEVEL_NINE = BooleanFlag(
        'force_heart_container_to_level_nine',
        'Force a heart container to be in level 9',
        'Require that at least one heart container be in level 9. Warning: seeds with two items forced to level nine may take a long time to generate. Seeds with three items forced to level nine will be impossible to generate.',
        FlagCategory.LOGIC_AND_DIFFICULTY
    )

    FORCE_TWO_HEART_CONTAINERS_TO_LEVEL_NINE = BooleanFlag(
        'force_two_heart_containers_to_level_nine',
        'Force two heart containers to be in level 9',
        'WARNING: THIS FLAG DOES NOT CURRENTLY WORK AND WILL BE FIXED IN A FUTURE UPDATE. DO NOT USE.',
        FlagCategory.HIDDEN
    )

    FORCE_HEART_CONTAINER_TO_ARMOS = BooleanFlag(
        'force_heart_container_to_armos',
        'Force heart container to Armos',
        'Require that the Armos item be a heart container. Only works when "Shuffle the Armos Item" is enabled.',
        FlagCategory.LOGIC_AND_DIFFICULTY
    )

    FORCE_HEART_CONTAINER_TO_COAST = BooleanFlag(
        'force_heart_container_to_coast',
        'Force heart container to Coast',
        'Require that the Coast item be a heart container. Only works when "Shuffle the Coast Item" is enabled.',
        FlagCategory.LOGIC_AND_DIFFICULTY
    )

    ALLOW_IMPORTANT_ITEMS_IN_LEVEL_NINE = BooleanFlag(
        'allow_important_items_in_level_nine',
        'Allow Important Items in Level 9',
        'Allows "important" items (bow, ladder, power bracelet, raft, recorder) to be placed in level 9. By default, these items are restricted from level 9.',
        FlagCategory.LOGIC_AND_DIFFICULTY
    )

    INCREASED_BAIT_BLOCKS = BooleanFlag(
        'increased_bait_blocks',
        'Increased Bait Blocks',
        'Modifies dungeon walls to make the hungry goriya block access to a separate region of each level. Best-effort - not guaranteed for all level layouts.',
        FlagCategory.LOGIC_AND_DIFFICULTY
    )

    INCREASED_STANDING_ITEMS = BooleanFlag(
        'increased_standing_items',
        'Increased Standing Items',
        'All floor items (room items) will be visible from the start. There will not be any drop items that only appear after killing all enemies in the room. Incompatible with "Increased Drop Items in Non-Push Block Rooms".',
        FlagCategory.LOGIC_AND_DIFFICULTY
    )

    REDUCED_PUSH_BLOCKS = BooleanFlag(
        'reduced_push_blocks',
        'Reduced Push Blocks',
        'Rooms that normally require killing all enemies and pushing blocks to open shutter doors will only require killing all enemies. Incompatible with "Increased Drop Items in Push Block Rooms".',
        FlagCategory.HIDDEN
    )

    INCREASED_DROP_ITEMS_IN_PUSH_BLOCK_ROOMS = BooleanFlag(
        'increased_drop_items_in_push_block_rooms',
        'Increased Drop Items in Push Block Rooms',
        'Some types of rooms with standing items (ones that would normally have push blocks) will have drop items instead. The item will appear after killing all enemies. Incompatible with "Reduced Push Blocks".',
        FlagCategory.HIDDEN
    )

    INCREASED_DROP_ITEMS_IN_NON_PUSH_BLOCK_ROOMS = BooleanFlag(
        'increased_drop_items_in_non_push_block_rooms',
        'Increased Drop Items in Non-Push Block Rooms',
        'Other types of rooms with standing items (ones that would normally NOT have push blocks) will have drop items instead. The item will appear after killing all enemies. Incompatible with "Increased Standing Items".',
        FlagCategory.HIDDEN
    )

    # Item Changes
    PROGRESSIVE_ITEMS = BooleanFlag(
        'progressive_items',
        'Progressive Items',
        'Makes swords, candles, arrows, and rings progressive. Lower-tier items replace higher-tier items in the pool, and collecting multiple copies upgrades them to the next tier. Note: Does not affect boomerangs.',
        FlagCategory.ITEM_CHANGES
    )

    ADD_L4_SWORD = BooleanFlag(
        'add_l4_sword',
        'Add L4 Sword',
        'Adds an additional sword upgrade guarded by the level 9 triforce checker. Note that with a L4 sword, melee attacks will do L4 damage but beams do L3 damage.',
        FlagCategory.ITEM_CHANGES
    )

    MAGICAL_BOOMERANG_DOES_ONE_HP_DAMAGE = BooleanFlag(
        'magical_boomerang_does_one_hp_damage',
        'Magical Boomerang Does 1 HP Damage',
        'Changes the magical boomerang to deal 1 HP of damage (equivalent to the wood sword) to enemies. Note that a boomerang may damage an enemy multiple times in one shot.',
        FlagCategory.ITEM_CHANGES
    )

    MAGICAL_BOOMERANG_DOES_HALF_HP_DAMAGE = BooleanFlag(
        'magical_boomerang_does_half_hp_damage',
        'Magical Boomerang Does Half HP Damage',
        'Changes the magical boomerang to deal half HP of damage to enemies instead of its normal behavior.',
        FlagCategory.HIDDEN
    )

    # Quality of Life
    SELECT_SWAP = BooleanFlag(
        'select_swap',
        'Enable Item Swap with Select',
        'Pressing select will cycle through your B button inventory instead of pausing the game.',
        FlagCategory.QUALITY_OF_LIFE
    )

    RANDOMIZE_LEVEL_TEXT = BooleanFlag(
        'randomize_level_text',
        'Randomize Level Text',
        'Chooses a random value (either literally or figuratively) for the "level-#" text displayed in dungeons.',
        FlagCategory.QUALITY_OF_LIFE
    )

    SPEED_UP_TEXT = BooleanFlag(
        'speed_up_text',
        'Speed Up Text',
        'Increases the scrolling speed of text displayed in caves and dungeons.',
        FlagCategory.QUALITY_OF_LIFE
    )

    SPEED_UP_DUNGEON_TRANSITIONS = BooleanFlag(
        'speed_up_dungeon_transitions',
        'Speed Up Dungeon Transitions',
        'Speeds up dungeon room transitions to be as fast as overworld screen transitions',
        FlagCategory.QUALITY_OF_LIFE
    )

    COMMUNITY_HINTS = BooleanFlag(
        'community_hints',
        'Community Hints',
        'Uses community hints for non-hint NPCs. If disabled, blank hints will be used instead. This setting overrides any hint setting set in Zelda Randomizer base ROMs.',
        FlagCategory.QUALITY_OF_LIFE
    )

    FAST_FILL = BooleanFlag(
        'fast_fill',
        'Fast Fill',
        'Fill hearts faster from fairy and potions (patch courtesy of snarfblam)',
        FlagCategory.QUALITY_OF_LIFE
    )

    FLUTE_KILLS_POLS_VOICE = BooleanFlag(
        'flute_kills_pols_voice',
        'Flute Kills Dungeon Pols Voice',
        'Play the flute to kill all Pols Voice in dungeons. Does not work on the overworld. (patch courtesy of Stratoform)',
        FlagCategory.QUALITY_OF_LIFE
    )

    LOW_HEARTS_SOUND = BooleanFlag(
        'low_hearts_sound',
        'Softer Low Hearts Sound',
        'Change the low hearts sound to a softer heartbeat sound (patch courtesy of gzip)',
        FlagCategory.QUALITY_OF_LIFE
    )

    FOUR_POTION_INVENTORY = BooleanFlag(
        'four_potion_inventory',
        'Four Potion Inventory',
        'Increases potion inventory from 2 to 4 blue potions.',
        FlagCategory.QUALITY_OF_LIFE
    )

    AUTO_SHOW_LETTER = BooleanFlag(
        'auto_show_letter',
        'Auto Show Letter',
        'Automatically shows the letter to NPCs without equipping and using it.',
        FlagCategory.QUALITY_OF_LIFE
    )

    # Hidden/Test flags
    EXAMPLE_HIDDEN_FLAG = BooleanFlag(
        'example_hidden_flag',
        'Example Hidden Flag',
        'This is an example hidden flag that will not appear in the UI but can still be used programmatically.',
        FlagCategory.HIDDEN
    )

    @classmethod
    def get_all_flags(cls) -> Dict[str, FlagDefinition]:
        """Get all flag definitions as a dictionary."""
        flags = {}
        for attr_name in dir(cls):
            attr = getattr(cls, attr_name)
            if isinstance(attr, FlagDefinition):
                flags[attr.key] = attr
        return flags

    @classmethod
    def get_flags_by_category(cls) -> Dict[FlagCategory, List[FlagDefinition]]:
        """Get flags organized by category."""
        by_category = {}
        for flag in cls.get_all_flags().values():
            if flag.category not in by_category:
                by_category[flag.category] = []
            by_category[flag.category].append(flag)
        return by_category


# ============================================================================
# FLAGS CLASS
# ============================================================================

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
