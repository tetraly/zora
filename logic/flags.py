from enum import Enum, IntEnum


class FlagCategory(IntEnum):
    """Categories for organizing flags in the UI."""
    ITEM_SHUFFLE = 1
    ITEM_CHANGES = 2
    OVERWORLD_RANDOMIZATION = 3
    LOGIC_AND_DIFFICULTY = 4
    QUALITY_OF_LIFE = 5
    EXPERIMENTAL = 6
    LEGACY = 7

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
            FlagCategory.LEGACY: "Legacy Flags (Designed for vanilla ROMs, not Zelda Randomizer ROMs)",
        }
        return names.get(self, "Unknown")


class FlagsEnum(Enum):
    SHUFFLE_WOOD_SWORD_CAVE_ITEM = (
        'shuffle_wood_sword_cave_item',
        'Shuffle Wood Sword Cave item',
        'Adds the Wood Sword Cave Item to the item shuffle pool. May or may not make the seed unbeatable. Recommended for advanced players only.',
        FlagCategory.ITEM_SHUFFLE
    )
    SHUFFLE_WHITE_SWORD_CAVE_ITEM = (
        'shuffle_white_sword_cave_item',
        'Shuffle White Sword Cave item',
        'Adds the White Sword Cave item to the item shuffle pool',
        FlagCategory.ITEM_SHUFFLE
    )
    SHUFFLE_MAGICAL_SWORD_CAVE_ITEM = (
        'shuffle_magical_sword_cave_item',
        'Shuffle Magical Sword Cave item',
        'Adds the Magical Sword to the item shuffle pool. Important Note: If the Magical Sword is shuffled into a room that normally has a standing floor item, it will become a drop item. You will need to defeat all enemies in the room for the Magical Sword to appear.',
        FlagCategory.ITEM_SHUFFLE
    )
    SHUFFLE_LETTER_CAVE_ITEM = (
        'shuffle_letter_cave_item',
        'Shuffle Letter Cave Item',
        'Adds the Letter Cave Item to the item shuffle.',
        FlagCategory.ITEM_SHUFFLE
    )
    SHUFFLE_ARMOS_ITEM = (
        'shuffle_armos_item',
        'Shuffle the Armos Item',
        'Adds the Armos item (the Power Bracelet in a vanilla seed) to the item shuffle pool.',
        FlagCategory.ITEM_SHUFFLE
    )
    SHUFFLE_COAST_ITEM = (
        'shuffle_coast_item',
        'Shuffle the Coast Item',
        'Adds the coast item (a Heart Container in vanilla) to the item shuffle pool.',
        FlagCategory.ITEM_SHUFFLE
    )
    SHUFFLE_SHOP_ARROWS = (
        'shuffle_shop_arrows',
        'Shuffle Shop Arrows',
        'Adds the wood arrows from the shop to the item shuffle pool.',
        FlagCategory.ITEM_SHUFFLE
    )
    SHUFFLE_SHOP_CANDLE = (
        'shuffle_shop_candle',
        'Shuffle Shop Candle',
        'Adds the blue candle from the shop to the item shuffle pool.',
        FlagCategory.ITEM_SHUFFLE
    )
    SHUFFLE_SHOP_RING = (
        'shuffle_shop_ring',
        'Shuffle Shop Ring',
        'Adds the blue ring from the shop to the item shuffle pool. The shop location price will be changed to 150 ± 25 rupees.',
        FlagCategory.ITEM_SHUFFLE
    )
    SHUFFLE_SHOP_BOOK = (
        'shuffle_shop_book',
        'Shuffle Shop Book',
        'Adds the book from the shop (if one is present) to the item shuffle pool.',
        FlagCategory.ITEM_SHUFFLE
    )
    SHUFFLE_SHOP_BAIT = (
        'shuffle_shop_bait',
        'Shuffle Shop Bait',
        'Adds one bait from the shops to the item shuffle pool. The other bait location will be replaced with a mystery item.',
        FlagCategory.ITEM_SHUFFLE
    )
    SHUFFLE_POTION_SHOP_ITEMS = (
        'shuffle_potion_shop_items',
        'Shuffle Potion Shop Items',
        'Adds the potions in the potion shop to the item shuffle pool. Known issue: Red potions in dungeons will be downgraded to blue potions.',
        FlagCategory.ITEM_SHUFFLE
    )
    SHUFFLE_MINOR_DUNGEON_ITEMS = (
        'shuffle_minor_dungeon_items',
        'Shuffle Minor Dungeon Items',
        'Adds minor items (five rupees, bombs, keys, maps, and compasses) to the item shuffle pool. Primarily designed for use with vanilla ROMs, not Zelda Randomizer ROMs.',
        FlagCategory.LEGACY
    )
    AVOID_REQUIRED_HARD_COMBAT = (
        'avoid_required_hard_combat',
        'Avoid Requiring "Hard" Combat',
        'The logic will not require killing any Blue Darknuts, Blue Wizzrobes, Gleeoks, or Patras to progress without making at least one sword upgrade and at least one ring available in logic. Primarily designed for use with vanilla ROMs, not Zelda Randomizer ROMs.',
        FlagCategory.LEGACY
    )
    SELECT_SWAP = (
        'select_swap',
        'Enable Item Swap with Select',
        'Pressing select will cycle through your B button inventory instead of pausing the game.',
        FlagCategory.QUALITY_OF_LIFE
    )
    RANDOMIZE_LEVEL_TEXT = (
        'randomize_level_text',
        'Randomize Level Text',
        'Chooses a random value (either literally or figuratively) for the "level-#" text displayed in dungeons.',
        FlagCategory.QUALITY_OF_LIFE
    )
    SPEED_UP_TEXT = (
        'speed_up_text',
        'Speed Up Text',
        'Increases the scrolling speed of text displayed in caves and dungeons.',
        FlagCategory.QUALITY_OF_LIFE
    )
    SPEED_UP_DUNGEON_TRANSITIONS = (
        'speed_up_dungeon_transitions',
        'Speed Up Dungeon Transitions',
        'Speeds up dungeon room transitions to be as fast as overworld screen transitions',
        FlagCategory.QUALITY_OF_LIFE
    )
    FORCE_ARROW_TO_LEVEL_NINE = (
        'force_arrow_to_level_nine',
        'Force an arrow to be in level 9',
        'Require that an arrow be in level 9. Warning: seeds with two items forced to level nine may take a long time to generate. Seeds with three items forced to level nine will be impossible to generate.',
        FlagCategory.LOGIC_AND_DIFFICULTY
    )
    FORCE_RING_TO_LEVEL_NINE = (
        'force_ring_to_level_nine',
        'Force a ring to be in level 9',
        'Require that a ring be in level 9. Warning: seeds with two items forced to level nine may take a long time to generate. Seeds with three items forced to level nine will be impossible to generate.',
        FlagCategory.LOGIC_AND_DIFFICULTY
    )
    FORCE_WAND_TO_LEVEL_NINE = (
        'force_wand_to_level_nine',
        'Force a wand to be in level 9',
        'Require that a wand be in level 9. Warning: seeds with two items forced to level nine may take a long time to generate. Seeds with three items forced to level nine will be impossible to generate.',
        FlagCategory.LOGIC_AND_DIFFICULTY
    )
    FORCE_HEART_CONTAINER_TO_LEVEL_NINE = (
        'force_heart_container_to_level_nine',
        'Force a heart container to be in level 9',
        'Require that at least one heart container be in level 9. Warning: seeds with two items forced to level nine may take a long time to generate. Seeds with three items forced to level nine will be impossible to generate.',
        FlagCategory.LOGIC_AND_DIFFICULTY
    )
    FORCE_TWO_HEART_CONTAINERS_TO_LEVEL_NINE = (
        'force_two_heart_containers_to_level_nine',
        'Force two heart containers to be in level 9',
        'WARNING: THIS FLAG DOES NOT CURRENTLY WORK AND WILL BE FIXED IN A FUTURE UPDATE. DO NOT USE.',
        FlagCategory.EXPERIMENTAL
    )
    FORCE_HEART_CONTAINER_TO_ARMOS = (
        'force_heart_container_to_armos',
        'Force heart container to Armos',
        'Require that the Armos item be a heart container. Only works when "Shuffle the Armos Item" is enabled.',
        FlagCategory.LOGIC_AND_DIFFICULTY
    )
    FORCE_HEART_CONTAINER_TO_COAST = (
        'force_heart_container_to_coast',
        'Force heart container to Coast',
        'Require that the Coast item be a heart container. Only works when "Shuffle the Coast Item" is enabled.',
        FlagCategory.LOGIC_AND_DIFFICULTY
    )
    EXTRA_RAFT_BLOCKS = (
        'extra_raft_blocks',
        'Extra Raft Blocks',
        'Converts the Westlake Mall and Casino Corner regions into raft-blocked areas, requiring the raft to access additional screens.',
        FlagCategory.OVERWORLD_RANDOMIZATION
    )
    EXTRA_POWER_BRACELET_BLOCKS = (
        'extra_power_bracelet_blocks',
        'Extra Power Bracelet Blocks',
        'Adds new power bracelet blocks in West Death Mountain. Intended for use with vanilla any road locations.',
        FlagCategory.OVERWORLD_RANDOMIZATION
    )
    NO_IMPORTANT_ITEMS_IN_LEVEL_NINE = (
        'no_important_items_in_level_nine',
        'No Important Items in Level 9',
        'Prevents important items (raft, power bracelet, recorder, bow, ladder) from being placed in level 9. This setting overrides the corresponding Zelda Randomizer flag setting.',
        FlagCategory.LOGIC_AND_DIFFICULTY
    )
    PROGRESSIVE_ITEMS = (
        'progressive_items',
        'Progressive Items',
        'Makes swords, candles, arrows, and rings progressive. Lower-tier items replace higher-tier items in the pool, and collecting multiple copies upgrades them to the next tier.',
        FlagCategory.ITEM_CHANGES
    )
    # PROGRESSIVE_ARROWS = (
    #     'progressive_arrows',
    #     'Progressive Arrows',
    #     'Replaces Silver Arrows with Wood Arrows in the item pool. Collecting multiple wood arrows will upgrade your arrows.'
    # )
    # PROGRESSIVE_CANDLES = (
    #     'progressive_candles',
    #     'Progressive Candles',
    #     'Replaces Red Candles with Blue Candles in the item pool. Collecting multiple blue candles will upgrade your candle.'
    # )
    # PROGRESSIVE_RINGS = (
    #     'progressive_rings',
    #     'Progressive Rings',
    #     'Replaces Red Rings with Blue Rings in the item pool. Collecting multiple blue rings will upgrade your ring.'
    # )
    # PROGRESSIVE_SWORDS = (
    #     'progressive_swords',
    #     'Progressive Swords',
    #     'Replaces White and Magical Swords with Wood Swords in the item pool. Collecting multiple wood swords will upgrade your sword to the next level.'
    # )
    ADD_L4_SWORD = (
        'add_l4_sword',
        'Add L4 Sword',
        'Adds an additional sword upgrade guarded by the level 9 triforce checker. Note that with a L4 sword, melee attacks will do L4 damage but beams do L3 damage.',
        FlagCategory.ITEM_CHANGES
    )
    # PROGRESSIVE_BOOMERANGS = (
    #     'progressive_boomerangs',
    #     'Progressive Boomerangs',
    #     'Replaces Magical Boomerangs with Wood Boomerangs in the item pool. Collecting multiple wood boomerangs will upgrade your boomerang.'
    # )
    MAGICAL_BOOMERANG_DOES_ONE_HP_DAMAGE = (
        'magical_boomerang_does_one_hp_damage',
        'Magical Boomerang Does 1 HP Damage',
        'Changes the magical boomerang to deal 1 HP of damage (equivalent to the wood sword) to enemies. Note that a boomerang may damage an enemy multiple times in one shot.',
        FlagCategory.ITEM_CHANGES
    )
    MAGICAL_BOOMERANG_DOES_HALF_HP_DAMAGE = (
        'magical_boomerang_does_half_hp_damage',
        'Magical Boomerang Does Half HP Damage',
        'Changes the magical boomerang to deal half HP of damage to enemies instead of its normal behavior.',
        FlagCategory.ITEM_CHANGES
    )
    INCREASED_BAIT_BLOCKS = (
        'increased_bait_blocks',
        'Increased Bait Blocks',
        'Modifies dungeon walls to make the hungry goriya block access to a separate region of each level. Best-effort - not guaranteed for all level layouts.',
        FlagCategory.LOGIC_AND_DIFFICULTY
    )
    COMMUNITY_HINTS = (
        'community_hints',
        'Community Hints',
        'Uses community hints from NextGen and Zelda 2 randomizers for NPC text. If disabled, blank hints will be used instead. This setting overrides any hint setting set in Zelda Randomizer base ROMs.',
        FlagCategory.QUALITY_OF_LIFE
    )
    RANDOMIZE_LOST_HILLS = (
        'randomize_lost_hills',
        'Randomize Lost Hills',
        'Randomizes the Lost Hills direction sequence and adds a hint NPC in the game.',
        FlagCategory.OVERWORLD_RANDOMIZATION
    )
    RANDOMIZE_DEAD_WOODS = (
        'randomize_dead_woods',
        'Randomize Dead Woods',
        'Randomizes the Dead Woods direction sequence and adds a hint NPC in the game.',
        FlagCategory.OVERWORLD_RANDOMIZATION
    )
    RANDOMIZE_HEART_CONTAINER_REQUIREMENTS = (
        'randomize_heart_container_requirements',
        'Randomize Heart Container Requirements',
        'Randomizes the heart container requirements for the White Sword cave (4-6 hearts) and Magical Sword cave (10-12 hearts). NPCs will provide hints about the requirements.',
        FlagCategory.OVERWORLD_RANDOMIZATION
    )
    RANDOMIZE_OVERWORLD_CAVE_DESTINATIONS = (
        'randomize_overworld_cave_destinations',
        'Randomize Overworld Cave Destinations',
        'Shuffles the destinations of all overworld caves (dungeons, item caves, and shops).',
        FlagCategory.OVERWORLD_RANDOMIZATION
    )
    DONT_GUARANTEE_STARTING_SWORD_OR_WAND = (
        'dont_guarantee_starting_sword_or_wand',
        'Don\'t Guarantee Starting Sword or Wand',
        'By default, either the wood sword cave or letter cave is guaranteed to be accessible from an open screen (no special items required) and contains a sword or wand. Enable this flag to remove that guarantee. You may need to find additional progression items and/or dive dungeons weaponless to get a weapon and complete the seed.',
        FlagCategory.OVERWORLD_RANDOMIZATION
    )
    FAST_FILL = (
        'fast_fill',
        'Fast Fill',
        'Fill hearts faster from fairy and potions (patch courtesy of snarfblam)',
        FlagCategory.EXPERIMENTAL
    )
    FLUTE_KILLS_POLS_VOICE = (
        'flute_kills_pols_voice',
        'Flute Kills Pols Voice',
        'Play the flute to kill all Pols Voice (patch courtesy of Stratoform)',
        FlagCategory.EXPERIMENTAL
    )
    LIKE_LIKE_RUPEES = (
        'like_like_rupees',
        'Like Likes Eat Rupees',
        'Like-Likes eat rupees instead of the Magical Shield (patch courtesy of gzip)',
        FlagCategory.EXPERIMENTAL
    )
    LOW_HEARTS_SOUND = (
        'low_hearts_sound',
        'Softer Low Hearts Sound',
        'Change the low hearts sound to a softer heartbeat sound (patch courtesy of gzip)',
        FlagCategory.EXPERIMENTAL
    )
    FOUR_POTION_INVENTORY = (
        'four_potion_inventory',
        'Four Potion Inventory',
        'Increases potion inventory from 2 to 4 blue potions.',
        FlagCategory.EXPERIMENTAL
    )
    AUTO_SHOW_LETTER = (
        'auto_show_letter',
        'Auto Show Letter',
        'Automatically shows the letter to NPCs without equipping and using it.',
        FlagCategory.EXPERIMENTAL
    )
    INCREASED_STANDING_ITEMS = (
        'increased_standing_items',
        'Increased Standing Items',
        'All floor items (room items) will be visible from the start. There will not be any drop items that only appear after killing all enemies in the room. Incompatible with "Increased Drop Items in Non-Push Block Rooms".',
        FlagCategory.EXPERIMENTAL
    )
    REDUCED_PUSH_BLOCKS = (
        'reduced_push_blocks',
        'Reduced Push Blocks',
        'Rooms that normally require killing all enemies and pushing blocks to open shutter doors will only require killing all enemies. Incompatible with "Increased Drop Items in Push Block Rooms".',
        FlagCategory.EXPERIMENTAL
    )
    INCREASED_DROP_ITEMS_IN_PUSH_BLOCK_ROOMS = (
        'increased_drop_items_in_push_block_rooms',
        'Increased Drop Items in Push Block Rooms',
        'Some types of rooms with standing items (ones that would normally have push blocks) will have drop items instead. The item will appear after killing all enemies. Incompatible with "Reduced Push Blocks".',
        FlagCategory.EXPERIMENTAL
    )
    INCREASED_DROP_ITEMS_IN_NON_PUSH_BLOCK_ROOMS = (
        'increased_drop_items_in_non_push_block_rooms',
        'Increased Drop Items in Non-Push Block Rooms',
        'Other types of rooms with standing items (ones that would normally NOT have push blocks) will have drop items instead. The item will appear after killing all enemies. Incompatible with "Increased Standing Items".',
        FlagCategory.EXPERIMENTAL
    )

    def __init__(self, value, display_name, help_text, category):
        self._value_ = value
        self.display_name = display_name
        self.help_text = help_text
        self.category = category

    @classmethod
    def get_flag_list(cls):
        return [(flag.value.lower(), flag.display_name, flag.help_text) for flag in cls]


class Flags:
    def __init__(self):
        # Initialize all flags as False (boolean values)
        self.flags = {flag.value: False for flag in FlagsEnum}

    def __getattr__(self, flag_value):
        # Return the boolean value, defaulting to False if not found
        return self.flags.get(flag_value, False)

    def get(self, flag_value):
        return self.flags.get(flag_value, False)

    def set(self, flag_value, state: bool):
        if flag_value in self.flags:
            self.flags[flag_value] = state
        else:
            raise KeyError(f"Flag '{flag_value}' not found.")

        
