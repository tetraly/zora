"""Central registry of all flag definitions."""

from typing import Dict, List

from .categories import FlagCategory
from .definitions import BooleanFlag, EnumFlag, IntegerFlag, FlagDefinition, FlagOption


class FlagRegistry:
    """Central registry of all flag definitions."""

    # Item Shuffle Flags
    SHUFFLE_WOOD_SWORD_CAVE_ITEM = BooleanFlag(
        'shuffle_wood_sword_cave_item',
        'Shuffle Wood Sword Cave item',
        'Adds the Wood Sword Cave Item to the item shuffle pool. May or may not make the seed unbeatable. Recommended for advanced players only.',
        FlagCategory.ITEM_SHUFFLE,
        subcategory='Major Item Shuffle'
    )

    SHUFFLE_WHITE_SWORD_CAVE_ITEM = BooleanFlag(
        'shuffle_white_sword_cave_item',
        'Shuffle White Sword Cave item',
        'Adds the White Sword Cave item to the item shuffle pool',
        FlagCategory.ITEM_SHUFFLE,
        subcategory='Major Item Shuffle'
    )

    SHUFFLE_MAGICAL_SWORD_CAVE_ITEM = BooleanFlag(
        'shuffle_magical_sword_cave_item',
        'Shuffle Magical Sword Cave item',
        'Adds the Magical Sword to the item shuffle pool. Important Note: If the Magical Sword is shuffled into a room that normally has a standing floor item, it will become a drop item. You will need to defeat all enemies in the room for the Magical Sword to appear.',
        FlagCategory.ITEM_SHUFFLE,
        subcategory='Major Item Shuffle'
    )

    SHUFFLE_LETTER_CAVE_ITEM = BooleanFlag(
        'shuffle_letter_cave_item',
        'Shuffle Letter Cave Item',
        'Adds the Letter Cave Item to the item shuffle.',
        FlagCategory.ITEM_SHUFFLE,
        subcategory='Major Item Shuffle'
    )

    SHUFFLE_ARMOS_ITEM = BooleanFlag(
        'shuffle_armos_item',
        'Shuffle the Armos Item',
        'Adds the Armos item (the Power Bracelet in a vanilla seed) to the item shuffle pool.',
        FlagCategory.ITEM_SHUFFLE,
        subcategory='Major Item Shuffle'
    )

    SHUFFLE_COAST_ITEM = BooleanFlag(
        'shuffle_coast_item',
        'Shuffle the Coast Item',
        'Adds the coast item (a Heart Container in vanilla) to the item shuffle pool.',
        FlagCategory.ITEM_SHUFFLE,
        subcategory='Major Item Shuffle'
    )

    SHUFFLE_SHOP_ARROWS = BooleanFlag(
        'shuffle_shop_arrows',
        'Shuffle Shop Arrows',
        'Adds the wood arrows from the shop to the item shuffle pool.',
        FlagCategory.ITEM_SHUFFLE,
        subcategory='Major Item Shuffle'
    )

    SHUFFLE_SHOP_CANDLE = BooleanFlag(
        'shuffle_shop_candle',
        'Shuffle Shop Candle',
        'Adds the blue candle from the shop to the item shuffle pool.',
        FlagCategory.ITEM_SHUFFLE,
        subcategory='Major Item Shuffle'
    )

    SHUFFLE_SHOP_RING = BooleanFlag(
        'shuffle_shop_ring',
        'Shuffle Shop Ring',
        'Adds the blue ring from the shop to the item shuffle pool. The shop location price will be changed to 150 ± 25 rupees.',
        FlagCategory.ITEM_SHUFFLE,
        subcategory='Major Item Shuffle'
    )

    SHUFFLE_SHOP_BOOK = BooleanFlag(
        'shuffle_shop_book',
        'Shuffle Shop Book',
        'Adds the book from the shop (if one is present) to the item shuffle pool.',
        FlagCategory.ITEM_SHUFFLE,
        subcategory='Major Item Shuffle'
    )

    SHUFFLE_SHOP_BAIT = BooleanFlag(
        'shuffle_shop_bait',
        'Shuffle Shop Bait',
        'Adds one bait from the shops to the item shuffle pool. The other bait location will be replaced with a mystery item.',
        FlagCategory.ITEM_SHUFFLE,
        subcategory='Major Item Shuffle'
    )

    SHUFFLE_POTION_SHOP_ITEMS = BooleanFlag(
        'shuffle_potion_shop_items',
        'Shuffle Potion Shop Items',
        'Adds the potions in the potion shop to the item shuffle pool. Known issue: Red potions in dungeons will be downgraded to blue potions.',
        FlagCategory.ITEM_SHUFFLE,
        subcategory='Major Item Shuffle'
    )

    SHUFFLE_MINOR_DUNGEON_ITEMS = BooleanFlag(
        'shuffle_minor_dungeon_items',
        'Shuffle Minor Dungeon Items',
        'Adds minor items (five rupees, bombs, keys, maps, and compasses) to the item shuffle pool. Primarily designed for use with vanilla ROMs, not Zelda Randomizer ROMs.',
        FlagCategory.LEGACY
    )

    SHUFFLE_WITHIN_LEVEL = BooleanFlag(
        'shuffle_within_level',
        'Shuffle Items Within Levels',
        'Shuffle items within each dungeon level. If unchecked, items will remain in their original positions within each level.',
        FlagCategory.ITEM_SHUFFLE,
        subcategory='Shuffle Within Dungeons',
        default=True
    )

    ITEM_STAIR_CAN_HAVE_TRIFORCE = BooleanFlag(
        'item_stair_can_have_triforce',
        'Item Staircase Can Have Triforce',
        'Allow the triforce to be placed in item staircase rooms. If unchecked, the triforce cannot appear in item staircases.',
        FlagCategory.ITEM_SHUFFLE,
        subcategory='Shuffle Within Dungeons',
        default=True
    )

    ITEM_STAIR_CAN_HAVE_MINOR_ITEM = BooleanFlag(
        'item_stair_can_have_minor_item',
        'Item Staircase Can Have Minor Items',
        'Allow minor items (bombs, keys, 5 rupees, maps, compasses) to be placed in item staircase rooms. If unchecked, minor items cannot appear in item staircases.',
        FlagCategory.ITEM_SHUFFLE,
        subcategory='Shuffle Within Dungeons',
        default=True
    )

    ITEM_STAIR_CAN_HAVE_HEART_CONTAINER = BooleanFlag(
        'item_stair_can_have_heart_container',
        'Item Staircase Can Have Heart Container',
        'Allow heart containers to be placed in item staircase rooms. If unchecked, heart containers cannot appear in item staircases.',
        FlagCategory.ITEM_SHUFFLE,
        subcategory='Shuffle Within Dungeons',
        default=True
    )

    FORCE_MAJOR_ITEM_TO_BOSS = BooleanFlag(
        'force_major_item_to_boss',
        'Force Major Item to Boss Room',
        'Require that at least one major item (non-minor item or triforce) be placed in a room with a boss enemy.',
        FlagCategory.ITEM_SHUFFLE,
        subcategory='Shuffle Within Dungeons'
    )

    FORCE_MAJOR_ITEM_TO_TRIFORCE_ROOM = BooleanFlag(
        'force_major_item_to_triforce_room',
        'Force Major Item to Triforce Room',
        'Require that at least one major item (non-minor item or triforce) be placed in the triforce room.',
        FlagCategory.ITEM_SHUFFLE,
        subcategory='Shuffle Within Dungeons'
    )

    # Overworld Randomization
    OVERWORLD_QUEST = EnumFlag(
        'overworld_quest',
        'Overworld Quest',
        'Choose which quest to use for the overworld layout.',
        FlagCategory.OVERWORLD_RANDOMIZATION,
        options=[
            FlagOption('first_quest', '1st Quest', 'Use 1st quest overworld screens'),
            FlagOption('second_quest', '2nd Quest', 'Use 2nd quest overworld screens with quest bit flipping'),
            FlagOption('mixed_1q_screens', 'Mixed w/ 1Q Screens', 'Mix 1st and 2nd quest, prioritize 1st quest screen assignments'),
            FlagOption('mixed_2q_screens', 'Mixed w/ 2Q Screens', 'Mix 1st and 2nd quest, prioritize 2nd quest screen assignments'),
        ],
        default='first_quest'
    )

    CAVE_SHUFFLE = EnumFlag(
        'cave_shuffle',
        'Cave Shuffle',
        'Choose which types of caves/shops/levels to include in the shuffle.',
        FlagCategory.OVERWORLD_RANDOMIZATION,
        options=[
            FlagOption('none', 'None', 'No cave shuffling'),
            FlagOption('levels_only', 'Levels Only', 'Shuffle only dungeon levels (1-9)'),
            FlagOption('non_levels_only', 'Non-Levels Only', 'Shuffle only caves and shops (not levels)'),
            FlagOption('all_caves', 'All Caves', 'Shuffle all caves, shops, and levels together'),
        ],
        default='none'
    )

    SHUFFLE_WOOD_SWORD_CAVE = BooleanFlag(
        'shuffle_wood_sword_cave',
        'Shuffle Wood Sword Cave',
        'Include the Wood Sword Cave in the cave shuffle. If disabled, Wood Sword Cave stays at its vanilla location.',
        FlagCategory.OVERWORLD_RANDOMIZATION
    )

    SHUFFLE_ANY_ROAD_CAVES = BooleanFlag(
        'shuffle_any_road_caves',
        'Shuffle "Take Any Road" Caves',
        'Include "Take Any Road" warp caves in the cave shuffle. These are the caves that warp you to different locations.',
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

    # Example enum flag for testing (hidden from production UI)
    EXAMPLE_ENUM_FLAG = EnumFlag(
        'example_enum_flag',
        'Example Enum Flag',
        'This is an example enum flag for testing multi-value support.',
        FlagCategory.HIDDEN,
        options=[
            FlagOption('option1', 'Option 1', 'First option'),
            FlagOption('option2', 'Option 2', 'Second option'),
            FlagOption('option3', 'Option 3', 'Third option'),
        ],
        default='option1'
    )

    # Example integer flag for testing (hidden from production UI)
    EXAMPLE_INTEGER_FLAG = IntegerFlag(
        'example_integer_flag',
        'Example Integer Flag',
        'This is an example integer flag for testing numeric input support.',
        FlagCategory.HIDDEN,
        default=100,
        min_value=1,
        max_value=1000
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

