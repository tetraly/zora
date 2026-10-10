"""ZORA: open-source The Legend of Zelda (NES) randomizer.

  zora.model     the game model (rooms, levels, overworld, sprites, GameWorld)
  zora.rom       the data layer: the only code that reads or writes ROM bytes
  zora.flags     flag strings, their fields, dependencies, support and form
  zora.generate  generation: the pipeline, the shape stage, the steps named
                 after their flags, the late gate and the acceptance check

This package is generation only: it is what Archipelago ships (copied in as
worlds.zora.zora, possibly from a zip). It imports itself relatively and never
imports its sibling packages, which ship with the page and the release only:
  zora_measure   checks, statistics and the spec's checkpoints
  zora_export    the seed document and the spoiler log
  zora_web       the web page's stable interface (zora_web.api)
scripts/check_imports.py (run by scripts/verify.sh) enforces both rules;
docs/packaging.md "Packages".
"""
