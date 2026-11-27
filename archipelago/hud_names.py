"""The HUD's item names, read from item_short_names.csv beside this file.

The file has a version line ("# version: N"), then a header row (item,short,tiny) and one row per
item: `short` is the name used when the full name does not fit the status bar, `tiny` a second,
shorter name for a SENT line with less room. An empty cell means no name at that length. Bump the
version whenever a row changes.

Read with pkgutil.get_data, as client.py reads archipelago.json: an installed .apworld is a zip,
whose files have no path open() can read.
"""
import csv
import pkgutil

HUD_NAMES_FILE = "item_short_names.csv"


def hud_names_lines() -> list[str]:
    """The file's lines, from the package (a folder or a zipped .apworld)."""
    data = pkgutil.get_data(__package__, HUD_NAMES_FILE)
    if data is None:
        raise FileNotFoundError(HUD_NAMES_FILE)
    return data.decode("utf-8").splitlines()


def load_hud_names(lines: list[str] | None = None) -> tuple[int, dict[str, str], dict[str, str]]:
    """(version, short names, tiny names), each keyed by the item's full name."""
    lines = hud_names_lines() if lines is None else lines
    head, _, number = lines[0].partition(":") if lines else ("", "", "")
    if head.strip() != "# version" or not number.strip().isdigit():
        raise ValueError(f"{HUD_NAMES_FILE}: the first line must be '# version: N'")
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
