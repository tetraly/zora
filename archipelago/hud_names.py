"""The HUD's item names, read from item_short_names.csv beside this file.

The file has a version line ("# version: N"), then a header row (item,short,tiny) and one row per
item: `short` is the name used when the full name does not fit the status bar, `tiny` a second,
shorter name for a SENT line with less room. An empty cell means no name at that length. Bump the
version whenever a row changes.
"""
import csv
from pathlib import Path

HUD_NAMES_FILE = Path(__file__).with_name("item_short_names.csv")


def load_hud_names(path: Path = HUD_NAMES_FILE) -> tuple[int, dict[str, str], dict[str, str]]:
    """(version, short names, tiny names), each keyed by the item's full name."""
    with path.open(encoding="utf-8", newline="") as file:
        lines = file.read().splitlines()
    head, _, number = lines[0].partition(":") if lines else ("", "", "")
    if head.strip() != "# version" or not number.strip().isdigit():
        raise ValueError(f"{path.name}: the first line must be '# version: N'")
    short: dict[str, str] = {}
    tiny: dict[str, str] = {}
    rows = csv.DictReader(line for line in lines[1:] if not line.startswith("#"))
    for row in rows:
        if row["short"]:
            short[row["item"]] = row["short"]
        if row["tiny"]:
            tiny[row["item"]] = row["tiny"]
    return int(number), short, tiny


HUD_NAMES_VERSION, HUD_SHORT_NAMES, HUD_TINY_NAMES = load_hud_names()
