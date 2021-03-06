# List of option checkbox fields for dynamic page generation.
FLAGS = (
    ('progressive_items', 'Progressive swords, rings, arrows, and candles',
     'If enabled, there will be three wood swords, two wood arrows, two blue rings, and two blue candles in the item pool.  Collecting multiples of each will upgrade the item.'
    ), ('shuffle_white_sword', 'Shuffle White Sword',
        'Adds the White Sword to the item shuffle pool'),
    ('shuffle_magical_sword', 'Shuffle Magical Sword',
     'Adds the Magical Sword to the item shuffle pool.  Important Note: If the Magical Sword is shuffled into a room that normally has a standing floor item it will become a drop item, meaning that you will need to defeat all enemies in the room in order for the Magical Sword to appear.'
    ), ('shuffle_letter', 'Shuffle Letter',
        'Adds the letter for the potion shop to the item shuffle.'),
    ('shuffle_armos_item', 'Shuffle the Armos Item',
     'Adds the Power Bracelet to the item shuffle pool.'),
    ('shuffle_coast_item', 'Shuffle the Coast Item',
     'Adds the coast heart container to the item shuffle pool.'),
    ('shuffle_shop_items', 'Shuffle Shop Items',
     'Adds the blue candle, blue ring, wood arrows, and both baits to the item shuffle pool.'),
    ('shuffle_take_any_hearts_shields_and_bait',
     'Shuffle Take Any Hearts, Magical Shields, and Bait',
     'If selected, four heart containers, one magical shield, and one bait will be added to the item pool to replace the 3 magical shields, 2 baits, and take any hearts'
    ),
    ('avoid_required_hard_combat', 'Avoid Requiring "Hard" Combat',
     'The logic will not require killing any Blue Darknuts, Blue Wizzrobes, Gleeoks, or Patras to progress without making at least one sword upgrade and at least one ring available in logic.'
    ), ('select_swap', 'Enable Item Swap with Select',
        'Pressing select will cycle through your B button inventory instead of pause the game.'),
    ('randomize_level_text', 'Randomize Level Text',
     'Chooses a random value (either literally or figuratively) for the "level-#" text displayed in dungeons.'
    ), ('speed_up_text', 'Speed Up Text',
        'Increases the scrolling speed of text displayed in caves and dungeons.'))
