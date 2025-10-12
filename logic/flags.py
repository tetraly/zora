from enum import Enum

class FlagsEnum(Enum):
    PROGRESSIVE_ITEMS = (
        'progressive_items',
        'Progressive Items',
        'If enabled, there will be three wood swords, two wood arrows, two blue rings, and two blue candles in the item pool. Collecting multiples of each will upgrade the item.'
    )
    SHUFFLE_WOOD_SWORD_CAVE_ITEM = (
        'shuffle_wood_sword_cave_item',
        'Shuffle Wood Sword Cave item',
        'Adds the Wood Sword Cave Item to the item shuffle pool. May or may not make the seed unbeatable. Recommended for advanced players only.'
    )    
    SHUFFLE_WHITE_SWORD_CAVE_ITEM = (
        'shuffle_white_sword_cave_item',
        'Shuffle White Sword Cave item',
        'Adds the White Sword Cave item to the item shuffle pool'
    )
    SHUFFLE_MAGICAL_SWORD_CAVE_ITEM = (
        'shuffle_magical_sword_cave_item',
        'Shuffle Magical Sword Cave item',
        'Adds the Magical Sword to the item shuffle pool. Important Note: If the Magical Sword is shuffled into a room that normally has a standing floor item, it will become a drop item. You will need to defeat all enemies in the room for the Magical Sword to appear.'
    )
    SHUFFLE_LETTER_CAVE_ITEM = (
        'shuffle_letter_cave_item',
        'Shuffle Letter Cave Item',
        'Adds the Letter Cave Item to the item shuffle.'
    )
    SHUFFLE_ARMOS_ITEM = (
        'shuffle_armos_item',
        'Shuffle the Armos Item',
        'Adds the Armos item (the Power Bracelet in a vanilla seed) to the item shuffle pool.'
    )
    SHUFFLE_COAST_ITEM = (
        'shuffle_coast_item',
        'Shuffle the Coast Item',
        'Adds the coast item (a Heart Container in vanilla) to the item shuffle pool.'
    )
    SHUFFLE_SHOP_ITEMS = (
        'shuffle_shop_items',
        'Shuffle Shop Items',
        'Adds the blue candle, blue ring, wood arrows, and both baits to the item shuffle pool.'
    )
    SHUFFLE_POTION_SHOP_ITEMS = (
        'shuffle_potion_shop_items',
        'Shuffle Potion Shop Items',
        'Adds the potions in the potion shop to the item shuffle pool. Known issue: Red potions in dungeons will be downgraded to blue potions.'
    )
    SHUFFLE_MINOR_DUNGEON_ITEMS = (
        'shuffle_minor_dungeon_items',
        'Shuffle Minor Dungeon Items',
        'Adds minor items (five rupees, bombs, keys, maps, and compasses) to the item shuffle pool.'
    )
    AVOID_REQUIRED_HARD_COMBAT = (
        'avoid_required_hard_combat',
        'Avoid Requiring "Hard" Combat',
        'The logic will not require killing any Blue Darknuts, Blue Wizzrobes, Gleeoks, or Patras to progress without making at least one sword upgrade and at least one ring available in logic.'
    )
    SELECT_SWAP = (
        'select_swap',
        'Enable Item Swap with Select',
        'Pressing select will cycle through your B button inventory instead of pausing the game.'
    )
    RANDOMIZE_LEVEL_TEXT = (
        'randomize_level_text',
        'Randomize Level Text',
        'Chooses a random value (either literally or figuratively) for the "level-#" text displayed in dungeons.'
    )
    SPEED_UP_TEXT = (
        'speed_up_text',
        'Speed Up Text',
        'Increases the scrolling speed of text displayed in caves and dungeons.'
    )
    SPEED_UP_DUNGEON_TRANSITIONS = (
        'speed_up_dungeon_transitions',
        'Speed Up Dungeon Transitions',
        'Speeds up dungeon room transitions to be as fast as overworld screen transitions'
    )
    ADD_L4_SWORD = (
        'add_l4_sword',
        'Add L4 Sword',
        'Adds an additional sword upgrade to the potion shop. Note: Will only be useful with progressive items enabled.'
    )
    FORCE_ARROW_TO_LEVEL_NINE = (
        'force_arrow_to_level_nine',
        'Force an arrow to be in level 9',
        'Require that an arrow be in level 9. Warning: seeds with two items forced to level nine may take a long time to generate. Seeds with three items forced to level nine will be impossible to generate.'
    )
    FORCE_RING_TO_LEVEL_NINE = (
        'force_ring_to_level_nine',
        'Force a ring to be in level 9',
        'Require that a ring be in level 9. Warning: seeds with two items forced to level nine may take a long time to generate. Seeds with three items forced to level nine will be impossible to generate.'
    )
    FORCE_WAND_TO_LEVEL_NINE = (
        'force_wand_to_level_nine',
        'Force a wand to be in level 9',
        'Require that a wand be in level 9. Warning: seeds with two items forced to level nine may take a long time to generate. Seeds with three items forced to level nine will be impossible to generate.'
    )
    
    def __init__(self, value, display_name, help_text):
        self._value_ = value
        self.display_name = display_name
        self.help_text = help_text

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

        
