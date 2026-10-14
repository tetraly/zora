"""The world's tests, run by Archipelago's test runner with the world installed (the release check,
scripts/check_apworld.py, runs them against a fresh Archipelago). They need Archipelago and a
The Legend of Zelda (USA) ROM in host.yaml (zora_options rom_file), so they live here, not in
ZORA's own tests/.
"""
from test.bases import WorldTestBase


class ZoraTestBase(WorldTestBase):
    game = "ZORA"
