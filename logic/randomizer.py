import io
import os
import random
import logging as log
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from version import __version_rom__

from typing import List
from .data_table import DataTable
from .items.item_randomizer import ItemRandomizer
from .patch import Patch
from .rom_reader import RomReader, NES_HEADER_OFFSET, ANY_ROAD_SCREENS_ADDRESS
from .text_data_table import TextDataTable
from .hint_writer import HintWriter
from .validator import Validator
from .flags import Flags
from .bait_blocker import BaitBlocker
from .randomizer_constants import Range, Item, CaveType, RoomAction
from .location import Location

class Z1Randomizer():
#  def __init__(self) -> None:
#    self.rom: Rom
#    self.seed: int = 0
#    self.flags: Flags
#    self.settings: Settings

#  def ConfigureSettings(self, seed: int, settings: Settings) -> None:
#    self.seed = seed
#    self.settings = settings

  def __init__(self, rom_bytes: io.BytesIO, seed: int, flags: Flags) -> None:
    self.rom_reader = RomReader(rom_bytes)
    self.seed = seed
    self.flags = flags
    self.cave_destinations_randomized_in_base_seed = False

  def _ConvertTextToRomHex(self, text: str) -> str:
    """Convert ASCII text to Zelda ROM character encoding hex string.

    The Zelda ROM uses a custom character encoding for text.
    Space = 0x24, A-Z = 0x0A-0x23, 0-9 = 0x00-0x09, period = 0x2C

    Args:
        text: The ASCII text to convert

    Returns:
        Hex string suitable for patch.AddDataFromHexString()
    """
    char_map = {
        ' ': 0x24,
        '.': 0x2C,
        '0': 0x00, '1': 0x01, '2': 0x02, '3': 0x03, '4': 0x04,
        '5': 0x05, '6': 0x06, '7': 0x07, '8': 0x08, '9': 0x09,
        'A': 0x0A, 'B': 0x0B, 'C': 0x0C, 'D': 0x0D, 'E': 0x0E, 'F': 0x0F,
        'G': 0x10, 'H': 0x11, 'I': 0x12, 'J': 0x13, 'K': 0x14, 'L': 0x15,
        'M': 0x16, 'N': 0x17, 'O': 0x18, 'P': 0x19, 'Q': 0x1A, 'R': 0x1B,
        'S': 0x1C, 'T': 0x1D, 'U': 0x1E, 'V': 0x1F, 'W': 0x20, 'X': 0x21,
        'Y': 0x22, 'Z': 0x23
    }

    hex_bytes = []
    for char in text.upper():
        if char in char_map:
            hex_bytes.append(f"{char_map[char]:02X}")
        else:
            # Default to space for unsupported characters
            hex_bytes.append("24")

    return " ".join(hex_bytes)

  def _ValidateFlagCompatibility(self, data_table: DataTable) -> None:
    """Validate that the selected ZORA flags are compatible with the base ROM.

    Checks for incompatible flag combinations and raises ValueError if found:
    - Progressive Items + Extra Candles
    - Extra Power Bracelet Blocks + Randomize Any Roads

    Args:
      data_table: The DataTable instance for reading ROM data

    Raises:
      ValueError: If an incompatible flag combination is detected
    """
    # Check for incompatible flag combination: Progressive Items + Extra Candles
    if self.flags.progressive_items:

      # Need to call ResetToVanilla first to populate the caves list
      data_table.ResetToVanilla()

      # Check Wood Sword Cave (cave 0) - all 3 positions
      wood_sword_cave_items = []
      for position in [1, 2, 3]:
        cave_type = 0 + 0x10  # Cave 0 -> CaveType 0x10
        item = data_table.GetCaveItem(cave_type, position)
        wood_sword_cave_items.append((position, item))

      # Check Take Any Cave (cave 0x11/17) - all 3 positions
      take_any_cave_items = []
      for position in [1, 2, 3]:
        cave_type = 0x11 + 0x10  # Cave 0x11 -> CaveType 0x21
        item = data_table.GetCaveItem(cave_type, position)
        take_any_cave_items.append((position, item))

      # Check if any candles were found
      candle_found = False
      candle_location = None

      for position, item in wood_sword_cave_items:
        if item in [Item.BLUE_CANDLE, Item.RED_CANDLE]:
          candle_found = True
          candle_location = f"Wood Sword Cave position {position}"
          break

      if not candle_found:
        for position, item in take_any_cave_items:
          if item in [Item.BLUE_CANDLE, Item.RED_CANDLE]:
            candle_found = True
            candle_location = f"Take Any Cave position {position}"
            break

      if candle_found:
        log.debug(f"\n!!! ERROR: Candle detected in {candle_location}")
        log.debug("Progressive Items is NOT compatible with Extra Candles flag\n")
        raise ValueError(
          "Progressive Items is not compatible with the 'Add Extra Candles' flag.\n\n"
          f"Your base ROM appears to have 'Add Extra Candles' enabled (detected a candle in the {candle_location}).\n\n"
          "Please regenerate your base ROM with the 'Add Extra Candles' flag turned OFF "
          "or disable the 'Progressive Items' flag in ZORA."
        )


    # Check for incompatible flag combination: Extra Power Bracelet Blocks + Randomize Any Roads
    if self.flags.extra_power_bracelet_blocks:
      # Read the four "take any road" screen IDs from ROM
      # ROM addresses 0x19334-0x19337 (file offsets 0x19344-0x19347 with iNES header)
      # Default values: 0x1D, 0x23, 0x49, 0x79
      DEFAULT_ANY_ROAD_SCREENS = [0x1D, 0x23, 0x49, 0x79]

      any_road_screens = self.rom_reader._ReadMemory(ANY_ROAD_SCREENS_ADDRESS, 4)

      log.debug(f"Any Road screen IDs in ROM: {[hex(x) for x in any_road_screens]}")
      log.debug(f"Default values:              {[hex(x) for x in DEFAULT_ANY_ROAD_SCREENS]}")

      if any_road_screens != DEFAULT_ANY_ROAD_SCREENS:
        raise ValueError(
          "Extra Power Bracelet Blocks is not compatible with the 'Randomize Any Roads' flag.\n\n"
          "Your base ROM appears to have 'Randomize Any Roads' enabled (detected modified Any Road screen locations).\n\n"
          "Please regenerate your base ROM with the 'Randomize Any Roads' flag turned OFF "
          "or disable the 'Extra Power Bracelet Blocks' flag in ZORA."
        )

  def _ApplyRoomActionFlags(self, data_table: DataTable) -> None:
    """Apply room action flag modifications to dungeon rooms.

    These flags modify the SecretTrigger codes (RoomAction) for rooms in levels 1-9:
    - increased_standing_items: Changes code 7 -> 1 (drop items become standing items)
    - reduced_push_blocks: Changes code 4 -> 1 (push block requirement removed)
    - increased_drop_items_in_push_block_rooms: Changes code 4 -> 7 (push block rooms get drop items)
    - increased_drop_items_in_non_push_block_rooms: Changes code 1 -> 7 (other rooms get drop items)

    Note: Some flags are incompatible and one takes precedence over the other.
    The room containing TRIFORCE_OF_POWER in level 9 is excluded from all modifications.
    """
    for level_num in Range.VALID_LEVEL_NUMBERS:
      rooms = data_table.level_7_to_9_rooms if level_num >= 7 else data_table.level_1_to_6_rooms

      for room in rooms:
        # Skip the room with TRIFORCE_OF_POWER (0x0E) in level 9
        if level_num == 9 and room.GetItem() == Item.TRIFORCE_OF_POWER:
          continue

        current_action = room.GetRoomAction()

        # Apply increased_standing_items flag (takes precedence over increased_drop_items_in_non_push_block_rooms)
        # Change code 7 (drop items) -> 1 (standing items)
        if self.flags.increased_standing_items:
          if current_action == RoomAction.KillingEnemiesOpensShuttersAndDropsItem:
            room.SetRoomAction(RoomAction.KillingEnemiesOpensShutters)
            log.debug(f"Level {level_num}: Changed room action 7 -> 1 (increased_standing_items)")

        # Apply reduced_push_blocks flag (takes precedence over increased_drop_items_in_push_block_rooms)
        # Change code 4 (push block to open shutters) -> 1 (just kill enemies)
        if self.flags.reduced_push_blocks:
          if current_action == RoomAction.PushingBlockOpensShutters:
            room.SetRoomAction(RoomAction.KillingEnemiesOpensShutters)
            log.debug(f"Level {level_num}: Changed room action 4 -> 1 (reduced_push_blocks)")

        # Apply increased_drop_items_in_push_block_rooms flag (only if reduced_push_blocks is NOT enabled)
        # Change code 4 -> 7, but only if the room has an item
        if (self.flags.increased_drop_items_in_push_block_rooms and
            not self.flags.reduced_push_blocks):
          if current_action == RoomAction.PushingBlockOpensShutters:
            # Check if room has a non-NONE item (0x03 in dungeons means NO_ITEM)
            if room.GetItem() != Item.NO_ITEM:
              room.SetRoomAction(RoomAction.KillingEnemiesOpensShuttersAndDropsItem)
              log.debug(f"Level {level_num}: Changed room action 4 -> 7 (increased_drop_items_in_push_block_rooms)")

        # Apply increased_drop_items_in_non_push_block_rooms flag (only if increased_standing_items is NOT enabled)
        # Change code 1 -> 7, but only if the room has an item
        if (self.flags.increased_drop_items_in_non_push_block_rooms and
            not self.flags.increased_standing_items):
          if current_action == RoomAction.KillingEnemiesOpensShutters:
            # Check if room has a non-NONE item (0x03 in dungeons means NO_ITEM)
            if room.GetItem() != Item.NO_ITEM:
              room.SetRoomAction(RoomAction.KillingEnemiesOpensShuttersAndDropsItem)
              log.debug(f"Level {level_num}: Changed room action 1 -> 7 (increased_drop_items_in_non_push_block_rooms)")

  def GetPatch(self) -> Patch:
    data_table = DataTable(self.rom_reader)
    item_randomizer = ItemRandomizer(data_table, self.flags)

    from .overworld_randomizer import OverworldRandomizer

    # Detect if cave destinations are already randomized in the base ROM
    detection_randomizer = OverworldRandomizer(data_table, self.flags)
    if detection_randomizer.DetectPreShuffledCaves():
      self.cave_destinations_randomized_in_base_seed = True

    validator = Validator(data_table, self.flags)

    # Validate flag compatibility with base ROM
    self._ValidateFlagCompatibility(data_table)

    # Main loop: Try a seed, if it isn't valid, try another one until it is valid.
    is_valid_seed = False
    outer_counter = 0
    max_attempts = 1000
    candidate_rng = random.Random(self.seed)
    first_attempt = True
    last_overworld_randomizer = None
    lost_hills_directions = None
    dead_woods_directions = None

    while not is_valid_seed:
      outer_counter += 1
      if outer_counter > max_attempts:
        raise Exception(
          f"Gave up after trying {max_attempts} possible item shuffles. Please try again with different seed and/or flag settings."
        )

      if first_attempt:
        candidate_seed = self.seed
        first_attempt = False
      else:
        candidate_seed = candidate_rng.randint(0, 9999999999)

      self.seed = candidate_seed
      log.info(f"Attempt {outer_counter} with seed {candidate_seed}")
      random.seed(candidate_seed)

      data_table.ResetToVanilla()

      overworld_randomizer = OverworldRandomizer(data_table, self.flags)
      overworld_randomizer.cave_destinations_randomized_in_base_seed = self.cave_destinations_randomized_in_base_seed

      # Perform overworld randomization (cave shuffle, Lost Hills, Dead Woods, etc.)
      overworld_randomizer.RandomizeHeartRequirements()
      candidate_lost_hills, candidate_dead_woods = overworld_randomizer.Randomize()

      # Run the new item randomizer (handles major item shuffle and progressive items)
      if not item_randomizer.Randomize(seed=candidate_seed):
        log.info("Randomization failed for seed %d; trying a different seed", candidate_seed)
        continue

      # Apply bait blocker if flag is enabled
      if self.flags.increased_bait_blocks:
        bait_blocker = BaitBlocker(data_table)
        for level_num in Range.VALID_LEVEL_NUMBERS:
          bait_blocker.TryToMakeHungryGoriyaBlockProgress(level_num)

      # Apply room action flags if enabled
      if (self.flags.increased_standing_items or self.flags.reduced_push_blocks or
          self.flags.increased_drop_items_in_push_block_rooms or
          self.flags.increased_drop_items_in_non_push_block_rooms):
        self._ApplyRoomActionFlags(data_table)

      is_valid_seed = validator.IsSeedValid()
      if is_valid_seed:
        last_overworld_randomizer = overworld_randomizer
        lost_hills_directions = candidate_lost_hills
        dead_woods_directions = candidate_dead_woods
        log.info("Seed %d passed validation", candidate_seed)
      else:
        log.info("Seed %d failed validation; trying a different seed", candidate_seed)

    if last_overworld_randomizer is None:
      raise RuntimeError("Failed to produce a valid overworld configuration")

    patch = data_table.GetPatch()

    # Add overworld patches (Lost Hills, Dead Woods, extra blocks)
    patch += last_overworld_randomizer.GetOverworldPatches()

    # Change White Sword cave to use the hint normally reserved for the letter cave
    # Vanilla value at 0x45B4 is 0x42, changing to 0x4C
    patch.AddData(0x45B4, [0x54])

    # Note: Heart requirements are now written to the patch by data_table.GetPatch()

    if self.flags.progressive_items:
      # New progressive item code
      # Vanilla code for handling a "class 2" (ordered by grade) item starts at 0x6D04 in the ROM
      # Original .asm from https://github.com/aldonunez/zelda1-disassembly/blob/master/src/Z_01.asm
      # HandleClass2:
      #      ; Class 2. We have a type of item that is ordered by grade.
      #    ; Item value is the grade.
      #    ;
      #    ; A: item class
      #    ; X: item type
      #    ; Y: item slot
      #    ; [0A]: item value
      #    LDA $0A
      #    CMP Items, Y
      #    BCC L6D1B_Exit              ; If we have a higher grade of this kind of item, return.
      #    STA Items, Y                ; Set the new item grade.
      #    CPY #$0B                    ; Ring item slot
      #    BNE L6D1B_Exit              ; If the item is not a ring, return.
          
      # Original bytecode: A50AD957 06902099 5706C00B
      # Revised bytecode:  A50A1879 5706EA99 5706C00B
      # NEw commands:
      #   18                   CLC          ; Clear the carry bit
      #   79 57 06             ADC $0657,Y  ; Adds the picked up amount (presumably 1) to the item grade
      #   EA                   NOP
      patch.AddData(0x6D06, [0x18, 0x79, 0x57, 0x06, 0xEA])

      # Fix for Ring/tunic colors
      patch.AddData(0x6BFB, [0x20, 0xE4, 0xFF])
      patch.AddData(0x1FFF4, [0x8E, 0x02, 0x06, 0x8E, 0x72, 0x06, 0xEE, 0x4F, 0x03, 0x60])

    # Old progressive item code
    #ItemIdToDescriptor:
    #    .BYTE $14, $21, $22, $23, $01, $01, $21, $22
    #               wood, WS, mags            candles
    #    .BYTE $21, $22, $01, $01, $01, $01, $01, $15
    #.          arrows
    #    .BYTE $01, $01, $21, $22, $01, $01, $01, $01
    #                    rings
    #    .BYTE $11, $11, $10, $01, $01, $01, $01, $11
    #    .BYTE $22, $01, $10, $12

    # Individual progressive flags are temporarily disabled
    progressive_swords = False
    progressive_candles = False
    progressive_arrows = False
    progressive_rings = False

    if progressive_swords:
      patch.AddData(0x6B49, [0x11, 0x12, 0x13])  # Swords
    if progressive_candles:
      patch.AddData(0x6B4E, [0x11, 0x12])  # Candles
    if progressive_arrows:
      patch.AddData(0x6B50, [0x11, 0x12])  # Arrows
    if progressive_rings:
      patch.AddData(0x6B5A, [0x11, 0x12])  # Rings
      # Extra fix for Ring/Tunic colors
      patch.AddData(0x6BFB, [0x20, 0xE4, 0xFF])
      patch.AddData(0x1FFF4, [0x8E, 0x02, 0x06, 0x8E, 0x72, 0x06, 0xEE, 0x4F, 0x03, 0x60])
    # Note: There isn't a comparable switch here for progressive boomerangsx because the 
    # original devs added a separate magic boomerang memory value for some reason.
    
    if self.flags.magical_boomerang_does_one_hp_damage:
      patch.AddDataFromHexString(0x7478, 
          "A9 50 99 AC 00 BD B2 04 25 09 F0 04 20 C5 7D 60 AD 75 06 0A 0A 0A 0A 85 07 A9 10 95 3D EA")  
    elif self.flags.magical_boomerang_does_half_hp_damage:
      patch.AddDataFromHexString(0x7478, 
          "A9 50 99 AC 00 BD B2 04 25 09 F0 04 20 C5 7D 60 AD 75 06 0A 0A 0A EA 85 07 A9 10 95 3D EA")

    if self.flags.speed_up_dungeon_transitions:
      # For fast scrolling. Puts NOPs instead of branching based on dungeon vs. Level 0 (OW)
      for addr in [0x141F3, 0x1426B, 0x1446B, 0x14478, 0x144AD]:
        patch.AddData(addr, [0xEA, 0xEA])


    if False: # self.flags.pacifist_mode:
      patch.AddData(0x7563, [0x00])
      patch.AddData(0x757A, [0x00])
      patch.AddData(0x75A6, [0x00, 0x00])
      patch.AddData(0x75ED, [0x00])
      patch.AddData(0x75F9, [0x00])
      patch.AddData(0x14C1C, [0xEA,0xEA,0xEA,0xEA,0xEA,0xEA,0xEA,0xEA,0xEA,0xEA,0xEA,0xEA])
      patch.AddData(0x14C89, [0xA9, 0x01, 0xEA])
      patch.AddData(0x1FB68, [0x11])
      patch.AddData(0x1FB6B, [0x21, 0x11])

#       for addr in range(0x1FB5E, 0x1FB5E + 36):
#         patch.AddData(addr, 0xFF)

    if self.flags.add_l4_sword:
      # Change a BEQ (F0) (sword_level==3) to BCS (B0) (sword_level >= 3) 
      # See https://github.com/aldonunez/zelda1-disassembly/blob/master/src/Z_01.asm#L6067 
      patch.AddDataFromHexString(0x7540, "B0")

    # For Mags patch
    patch.AddData(0x1785F, [0x0E])

    # Apply hints based on community_hints flag
    hint_writer = HintWriter()

    # Set Lost Hills and Dead Woods hints if they were randomized
    if lost_hills_directions is not None:
      hint_writer.SetLostHillsHint(lost_hills_directions)

    if dead_woods_directions is not None:
      hint_writer.SetDeadWoodsHint(dead_woods_directions)

    # Set heart requirement hints
    from .rom_data_specs import RomDataType
    if self.flags.randomize_heart_container_requirements:
      hint_writer.SetWhiteSwordHeartHint(data_table.GetRomData(RomDataType.WHITE_SWORD_HEART_REQUIREMENT))

    if self.flags.shuffle_magical_sword_cave_item or self.flags.randomize_heart_container_requirements:
      hint_writer.SetMagicalSwordHeartHint(data_table.GetRomData(RomDataType.MAGICAL_SWORD_HEART_REQUIREMENT))

    if self.flags.community_hints:
      hint_writer.FillWithCommunityHints()
    else:
      hint_writer.FillWithBlankHints()

    hint_patch = hint_writer.GetPatch()
    patch += hint_patch
    
    # Apply experimental IPS patches
    if self.flags.fast_fill:
      patch.AddFromIPS(os.path.join(os.path.dirname(__file__), '..', 'ips', 'fast_fill.ips'))

    if self.flags.flute_kills_pols_voice:
      patch.AddFromIPS(os.path.join(os.path.dirname(__file__), '..', 'ips', 'flute_kills_pols.ips'))

    if self.flags.like_like_rupees:
      patch.AddFromIPS(os.path.join(os.path.dirname(__file__), '..', 'ips', 'like_like_rupees.ips'))

    if self.flags.low_hearts_sound:
      patch.AddFromIPS(os.path.join(os.path.dirname(__file__), '..', 'ips', 'low_hearts_sound.ips'))

    if self.flags.four_potion_inventory:
      patch.AddFromIPS(os.path.join(os.path.dirname(__file__), '..', 'ips', 'four_potion_inventory.ips'))

    if self.flags.auto_show_letter:
      patch.AddFromIPS(os.path.join(os.path.dirname(__file__), '..', 'ips', 'auto_show_letter.ips'))
    

    # Include everything above in the hash code.
    hash_code = patch.GetHashCode()
    patch.AddData(0xAFD4, list(hash_code))
    patch.AddData(0xA4CD, [0x4C, 0x90, 0xAF])
    """ Old patch for code to display the CODE characters
      patch.AddData(0xAFA0, [
        0xA2, 0x0A, 0xA9, 0xFF, 0x95, 0xAC, 0xCA, 0xD0, 0xFB, 0xA2, 0x04, 0xA0, 0x60, 0xBD, 0xBF,
        0xAF, 0x9D, 0x44, 0x04, 0x98, 0x69, 0x1B, 0xA8, 0x95, 0x70, 0xA9, 0x20, 0x95, 0x84, 0xA9,
        0x00, 0x95, 0xAC, 0xCA, 0xD0, 0xE9, 0x20, 0x9D, 0x97, 0xA9, 0x14, 0x85, 0x14, 0xE6, 0x13,
        0x60, 0xFF, 0xFF, 0x1E, 0x0A, 0x06, 0x01
    ])"""
    # Copied from a Zelda Randomizer 3.5.20 ROM
    patch.AddDataFromHexString(0xAFA0, "A9008D08 01A20AA9 FF95ACCA D0FBA204 A060BDC3 AF9D4404 98691BA8 "
                                 "9570A920 9584A900 95ACCAD0 E9209D97 A9148514 E61360FF")
    """ Old patch for displaying the word CODE
        patch.AddData(
        0x1A129,
        [0x0C, 0x18, 0x0D, 0x0E, 0x24, 0x24, 0x24, 0x24, 0x24, 0x24, 0x24, 0x24, 0x24, 0x24, 0x24])"""
    # Display "ZORA" instead of "CODE"
    patch.AddDataFromHexString(0x1A129, "23181B0A2424242424242424242424")

    # Replace 'PRESS START BUTTON' with '  ZORA  V{version} BETA'
    version_text = f"  ZORA  {__version_rom__}"
    version_hex = self._ConvertTextToRomHex(version_text)
    patch.AddDataFromHexString(0x1AB40, version_hex)

    if self.flags.select_swap:
      patch.AddData(0x1EC4C, [0x4C, 0xC0, 0xFF])
      patch.AddData(0x1FFD0, [
          0xA9, 0x05, 0x20, 0xAC, 0xFF, 0xAD, 0x56, 0x06, 0xC9, 0x0F, 0xD0, 0x02, 0xA9, 0x07, 0xA8,
          0xA9, 0x01, 0x20, 0xC8, 0xB7, 0x4C, 0x58, 0xEC
      ])

    if self.flags.randomize_level_text or self.flags.speed_up_text:
      random_level_text = random.choice(
          ['palace', 'house-', 'block-', 'random', 'cage_-', 'home_-', 'castle'])
      text_data_table = TextDataTable(
          "very_fast" if self.flags.speed_up_text else "normal", random_level_text
          if self.flags.randomize_level_text else "level-")
      patch += text_data_table.GetPatch()


    return patch
