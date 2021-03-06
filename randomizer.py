import os
import random

from typing import List
from data_table import DataTable
from item_randomizer import ItemRandomizer
from level_generator import LevelGenerator
from patch import Patch
from rom import Rom
from settings import Settings
from text_data_table import TextDataTable
from validator import Validator


class ZoraRandomizer():

  def __init__(self) -> None:
    self.input_filename: str = ""
    self.output_location: str = ""
    self.seed: int = 0
    self.settings: Settings

  def ConfigureSettings(self, seed: int, settings: Settings) -> None:
    self.seed = seed
    self.settings = settings

  def Settings(self, input_filename: str, output_location: str, seed: int) -> None:
    self.input_filename = input_filename
    self.output_location = output_location
    self.seed = seed
    self.settings = Settings()

  def Run(self) -> None:
    (input_path, input_full_filename) = os.path.split(self.input_filename)
    (input_filename, input_extension) = os.path.splitext(input_full_filename)
    output_filename = os.path.join(
        self.output_location or input_path,
        "%s-randomized-%d%s" % (input_filename, self.seed, input_extension or ".nes"))
    output_rom = Rom(output_filename, src=self.input_filename)
    output_rom.OpenFile(write_mode=True)

    patch = self._GetPatch()

    for address in patch.GetAddresses():
      data: List[int]
      data = patch.GetData(address)
      output_rom.WriteBytes(address, data)

  def _GetPatch(self) -> Patch:
    random.seed(self.seed)
    data_table = DataTable()
    data_table.ResetToVanilla()
    level_generator = LevelGenerator(data_table)
    level_generator.Generate()
    item_randomizer = ItemRandomizer(data_table, self.settings)
    item_randomizer.Randomize()

    validator = Validator(data_table, self.settings)
    while not validator.IsSeedValid():
      item_randomizer.Randomize()

    patch = data_table.GetPatch()
    patch.AddData(0x16fd8, [
        0xFF, 0xA5, 0xEC, 0x30, 0x0B, 0x49, 0x80, 0xCD, 0xA1, 0x6B, 0xD0, 0x09, 0xA4, 0x10, 0xF0,
        0x05, 0x85, 0xEC, 0x4C, 0x47, 0xB5, 0x4C, 0x59, 0xB5, 0xAC, 0xBB, 0x6B, 0xB9, 0xF1, 0xAF,
        0x85, 0x98, 0xB9, 0xF6, 0xAF, 0x85, 0x70, 0xB9, 0xFB, 0xAF, 0x60, 0x00, 0x04, 0x08, 0x01,
        0x02, 0x78, 0x78, 0x78, 0x00, 0xF0, 0x8D, 0x3D, 0xDD, 0x8D, 0x8D
    ])
    patch.AddData(0x17058, [0xA9, 0x78, 0x85, 0x70, 0x20, 0xE0, 0xAF, 0x85])
    patch.AddData(0x17550, [0x20, 0xC0, 0xB8, 0x4C, 0xC9, 0xAF, 0x12, 0x20])
    patch.AddData(0x178D0, [0xAD, 0x22, 0x05, 0xC9, 0x01, 0xF0, 0x03, 0x4C, 0x2F, 0x75, 0x60])
    patch.AddData(0x1934D, [0x00])
    
    # Fix for ring/tunic colors
    patch.AddData(0x6BFB, [0x20, 0xE4, 0xFF])
    patch.AddData(0x1FFF4, [0x8E, 0x02, 0x06, 0x8E, 0x72, 0x06, 0xEE, 0x4F, 0x03, 0x60])

    self._AddExtras(patch)
    return patch

  def _AddExtras(self, patch: Patch) -> None:
    if self.settings.progressive_items:
      patch.AddData(0x6B49, [0x11, 0x12, 0x13])  # Swords
      patch.AddData(0x6B4E, [0x11, 0x12])  # Candles
      patch.AddData(0x6B50, [0x11, 0x12])  # Arrows
      patch.AddData(0x6B5A, [0x11, 0x12])  # Rings

    # Change "no item" code from 0x03 (Mags) to 0x0E (Triforce of Power)
    patch.AddData(0x1785F, [0x0E])

    # Include everything above in the hash code.
    hash_code = patch.GetHashCode()
    patch.AddData(0xAFD0, hash_code)
    patch.AddData(0xA4CD, [0x4C, 0x90, 0xAF])
    patch.AddData(0xAFA0, [
        0xA2, 0x0A, 0xA9, 0xFF, 0x95, 0xAC, 0xCA, 0xD0, 0xFB, 0xA2, 0x04, 0xA0, 0x60, 0xBD, 0xBF,
        0xAF, 0x9D, 0x44, 0x04, 0x98, 0x69, 0x1B, 0xA8, 0x95, 0x70, 0xA9, 0x20, 0x95, 0x84, 0xA9,
        0x00, 0x95, 0xAC, 0xCA, 0xD0, 0xE9, 0x20, 0x9D, 0x97, 0xA9, 0x14, 0x85, 0x14, 0xE6, 0x13,
        0x60, 0xFF, 0xFF, 0x1E, 0x0A, 0x06, 0x01
    ])

    # What does this do?
    patch.AddData(
        0x1A129,
        [0x0C, 0x18, 0x0D, 0x0E, 0x24, 0x24, 0x24, 0x24, 0x24, 0x24, 0x24, 0x24, 0x24, 0x24, 0x24])

    if self.settings.select_swap:
      patch.AddData(0x1EC4C, [0x4C, 0xC0, 0xFF])
      patch.AddData(0x1FFD0, [
          0xA9, 0x05, 0x20, 0xAC, 0xFF, 0xAD, 0x56, 0x06, 0xC9, 0x0F, 0xD0, 0x02, 0xA9, 0x07, 0xA8,
          0xA9, 0x01, 0x20, 0xC8, 0xB7, 0x4C, 0x58, 0xEC
      ])

    if self.settings.randomize_level_text or self.settings.speed_up_text:
      random_level_text = random.choice(
          ['palace', 'house-', 'block-', 'random', 'cage_-', 'home_-', 'castle'])
      text_data_table = TextDataTable(
          "very_fast" if self.settings.speed_up_text else "normal",
          random_level_text if self.settings.randomize_level_text else "level-")
      patch += text_data_table.GetPatch()
