"""ZORA: open-source The Legend of Zelda (NES) randomizer.

  zora.model     the game model (rooms, levels, overworld, sprites, GameWorld)
  zora.rom       the data layer: the only code that reads or writes ROM bytes
  zora.flags     flag strings, their fields, dependencies, support and form
  zora.generate  generation: the pipeline, the shape stage, the steps named
                 after their flags, the late gate and the acceptance check
  zora.measure   checks, statistics and the spec's checkpoints
  zora.api       the web page's stable interface
"""
