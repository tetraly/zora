"""item_short_names.csv: every ZORA item has a row, so a renamed item fails here until its row
is updated (the HUD would otherwise show the new name in full, with no short form)."""
import csv
import unittest

from ..hud_names import HUD_NAMES_FILE, load_hud_names
from ..zora.model.item_names import ITEM_NAMES


def csv_items() -> set[str]:
    with HUD_NAMES_FILE.open(encoding="utf-8", newline="") as file:
        lines = [line for line in file.read().splitlines() if not line.startswith("#")]
    return {row["item"] for row in csv.DictReader(lines)}


class HudNamesTest(unittest.TestCase):
    def test_every_zora_item_has_a_row(self):
        missing = sorted(set(ITEM_NAMES.values()) - csv_items())
        self.assertEqual(missing, [], "add a row to item_short_names.csv for: " + ", ".join(missing))

    def test_version_line_is_a_number(self):
        version, _, _ = load_hud_names()
        self.assertGreaterEqual(version, 1)

    def test_names_fit_their_lengths(self):
        _, short, tiny = load_hud_names()
        for item, name in tiny.items():
            self.assertLessEqual(len(name), len(short.get(item, item)), item)
