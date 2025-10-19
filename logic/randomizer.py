import io
import os
import random
import logging as log

from typing import List
from .data_table import DataTable
from .item_randomizer import ItemRandomizer
from .patch import Patch
from .rom_reader import RomReader
from .text_data_table import TextDataTable
from .hint_writer import HintWriter
from .validator import Validator
from .flags import Flags
from .bait_blocker import BaitBlocker
from .randomizer_constants import Range

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

  def GetPatch(self) -> Patch:
    random.seed(self.seed)
    data_table = DataTable(self.rom_reader)
    item_randomizer = ItemRandomizer(data_table, self.flags)
    validator = Validator(data_table, self.flags)

    # Main loop: Try a seed, if it isn't valid, try another one until it is valid.
    is_valid_seed = False

    inner_counter = 0
    outer_counter = 0
    while not is_valid_seed:
      outer_counter += 1
      seed = random.randint(0, 9999999999)
      while True:
        inner_counter += 1
        data_table.ResetToVanilla()
        item_randomizer.ReplaceProgressiveItemsWithUpgrades()
        item_randomizer.ResetState()
        item_randomizer.ReadItemsAndLocationsFromTable()
        item_randomizer.ShuffleItems()
        if item_randomizer.HasValidItemConfiguration():
          log.debug("Success after %d inner_counter iterations" % inner_counter)
          break
        if inner_counter >= 2000:
          log.debug("Gave up after %d inner_counter iterations" % inner_counter)
      
      item_randomizer.WriteItemsAndLocationsToTable()

      # Apply bait blocker if flag is enabled
      if self.flags.increased_bait_blocks:
        bait_blocker = BaitBlocker(data_table)
        for level_num in Range.VALID_LEVEL_NUMBERS:
          bait_blocker.TryToMakeHungryGoriyaBlockProgress(level_num)

      is_valid_seed = validator.IsSeedValid()
      if outer_counter >= 1000:
          raise Exception(f"Gave up after trying {outer_counter} possible item shuffles. Please try again with different seed and/or flag settings.")
      
    patch = data_table.GetPatch()

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
      #patch.AddData(0x6D06, [0x18, 0x79, 0x57, 0x06, 0xEA])

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
        
    if self.flags.progressive_swords: 
      patch.AddData(0x6B49, [0x11, 0x12, 0x13])  # Swords
    if self.flags.progressive_candles: 
      patch.AddData(0x6B4E, [0x11, 0x12])  # Candles
    if self.flags.progressive_arrows:
      patch.AddData(0x6B50, [0x11, 0x12])  # Arrows
    if self.flags.progressive_rings:
      patch.AddData(0x6B5A, [0x11, 0x12])  # Rings
      # Extra fix for Ring/Tunic colors
      patch.AddData(0x6BFB, [0x20, 0xE4, 0xFF])
      patch.AddData(0x1FFF4, [0x8E, 0x02, 0x06, 0x8E, 0x72, 0x06, 0xEE, 0x4F, 0x03, 0x60])
    # Note: There isn't a comparable switch here for progressive boomerangsx because the 
    # original devs added a separate magic boomerang memory value for some reason.
    
    if self.flags.magical_boomerang_does_one_hp_damage:
      patch.AddDataFromHexString(0x7478, 
          "A9 50 99 AC 00 BD B2 04 25 09 F0 04 20 C5 7D 60 AD 75 06 0A 0A 0A 0A 85 07 A9 10 95 3D")  
    elif self.flags.magical_boomerang_does_half_hp_damage:
      patch.AddDataFromHexString(0x7478, 
          "A9 50 99 AC 00 BD B2 04 25 09 F0 04 20 C5 7D 60 AD 75 06 0A 0A 0A EA 85 07 A9 10 95 3D")

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

    if self.flags.extra_raft_blocks:
      # Change 1: 0x154F8 (1 byte): 0x80 -> 0x0C
      patch.AddDataFromHexString(0x154F8, "0C")

      # Change 2: 0x155F7-0x155F8 (2 bytes): 0x51 0x51 -> 0x0C 0x0C
      patch.AddDataFromHexString(0x155F7, "0C 0C")

      # Change 3: 0x15613 (1 byte): 0xF2 -> 0xEB
      patch.AddDataFromHexString(0x15613, "EB")

      # Change 4: 0x15615 (1 byte): 0x02 -> 0xAF
      patch.AddDataFromHexString(0x15615, "AF")

      # Change 5: 0x15715 (1 byte): 0x00 -> 0xB6
      patch.AddDataFromHexString(0x15715, "B6")

      # Change 6: 0x15765-0x15766 (2 bytes): 0x47 0x91 -> 0x91 0x78
      patch.AddDataFromHexString(0x15765, "91 78")

      # Change 7: 0x1582F-0x15839 (11 bytes)
      # Original: 07 18 45 13 13 13 13 13 13 13 00
      # Modified: 02 08 0B 0B 0B 0B 0B 0B 0B 0B 01
      patch.AddDataFromHexString(0x1582F, "02 08 0B 0B 0B 0B 0B 0B 0B 0B 01")

      # Change 8: 0x1592F-0x15930 (2 bytes): 0x23 0x23 -> 0x17 0x17
      patch.AddDataFromHexString(0x1592F, "17 17")

      # This seems to break the caves in South Westlake and Vanilla 4.
      # patch.AddData(0x184D4, self.rom_reader.GetSouthWestlakeMallCaveType() | 0x03)

    if self.flags.extra_power_bracelet_blocks:
      patch.AddDataFromHexString(0x1554E, "38")
      patch.AddDataFromHexString(0x15554, "06E7000000")
      patch.AddDataFromHexString(0x15649, "00A9")
      patch.AddDataFromHexString(0x1564E, "B6")
      patch.AddDataFromHexString(0x1574E, "02")
      
    if self.flags.add_l4_sword:
      # Change a BEQ (F0) (sword_level==3) to BCS (B0) (sword_level >= 3) 
      # See https://github.com/aldonunez/zelda1-disassembly/blob/master/src/Z_01.asm#L6067 
      patch.AddDataFromHexString(0x7540, "B0")

    # For Mags patch
    patch.AddData(0x1785F, [0x0E])

    # Apply hints based on community_hints flag
    hint_writer = HintWriter(seed=seed)

    # Lost Hills randomization
    if self.flags.randomize_lost_hills:
      # Generate 3 random directions from {Up, Right, Down} + Up at the end
      # Up=0x08, Down=0x04, Right=0x01
      direction_options = [0x08, 0x04, 0x01]  # Up, Down, Right
      lost_hills_directions = random.choices(direction_options, k=3)
      lost_hills_directions.append(0x08)  # Always Up at the end

      # Patch the ROM at 0x6DAB-0x6DAE with the direction sequence
      patch.AddData(0x6DAB, lost_hills_directions)
      
      # Patch the overworld to annex the two screens to the right of vanilla Level 5
      patch.AddDataFromHexString(0x154D7, "01010101010101")
      patch.AddDataFromHexString(0x154F1, "09")
      patch.AddDataFromHexString(0x154F5, "06")
      patch.AddDataFromHexString(0x155DD, "02")
      patch.AddDataFromHexString(0x155F5, "51")

      # Set Lost Hills hint
      hint_writer.SetLostHillsHint(lost_hills_directions)

    # Dead Woods randomization
    if self.flags.randomize_dead_woods:
      # Generate 3 random directions from {North, West, South} + South at the end
      # North=0x08, South=0x04, West=0x02
      direction_options = [0x08, 0x02, 0x04]  # North, West, South
      dead_woods_directions = random.choices(direction_options, k=3)
      dead_woods_directions.append(0x04)  # Always South at the end

      # Patch the ROM at 0x6DA7-0x6DAA with the direction sequence
      patch.AddData(0x6DA7, dead_woods_directions)

      # Patch the overworld (single byte change at 0x15B08)
      patch.AddDataFromHexString(0x15B08, "29")

      # Set Dead Woods hint
      hint_writer.SetDeadWoodsHint(dead_woods_directions)

    if self.flags.community_hints:
      hint_writer.FillWithCommunityHints()
    else:
      hint_writer.FillWithBlankHints()

    hint_patch = hint_writer.GetPatch()
    patch += hint_patch

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

    # "Replace 'PRESS START BUTTON' with '  ZORA  V0.1 BETA'"
    patch.AddDataFromHexString(0x1AB40, "24 24 23 18 1B 0A 24 24 1F 00 2C 01 24 0B 0E 1D 0A")

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
