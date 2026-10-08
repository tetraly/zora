"""The owner's names for the flag fields: docs/flag-names.csv <-> zora/flags/names.json.

    python3 scripts/flag_names.py generate
        Writes docs/flag-names.csv: one row per field of zora/flags/, in
        the page's order, with the spec label, a plain sentence on what the
        field does (flags-behavior.md), its values, the MVP baseline value
        and the support-matrix status. The owner's two columns (owner_name,
        owner_value_names) are kept from the existing file, so generating
        again never loses them.
    python3 scripts/flag_names.py import
        Reads docs/flag-names.csv after the owner has edited and saved it
        (from Numbers, Excel or a text editor), checks it, and writes the
        owner's names to zora/flags/names.json, which the web page uses
        (zora/flags/form.py). Nothing else in the file is read back.

The CSV is UTF-8 with a byte-order mark, so Excel and Numbers both open it
with the right characters. The import also accepts the Windows-1252 that
older Excel versions save, and a semicolon or tab instead of the comma.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from zora.flags import form as flag_form  # noqa: E402
from zora.flags.fields import ENCODE_LEVEL_DATA, OPTION_FIELDS, TOGGLE_FIELDS
from zora.flags.support import mvp_baseline_settings, support
from zora.rom import level_encoding
from zora.flags.fields import OptionField  # noqa: E402
from zora.flags.support import Support

CSV_PATH = REPO / "docs" / "flag-names.csv"
JSON_PATH = REPO / "zora" / "flags" / "names.json"
COLUMNS = ("page_section", "field_id", "spec_label", "what_it_does", "kind", "values", "baseline_value",
           "supported", "owner_name", "owner_value_names", "community_name", "community_source", "match")
OWNER_COLUMNS = ("owner_name", "owner_value_names")
# The community's name for each field (z1r.wiki), how it was matched, and
# where: kept like the owner's columns when generating again; the import
# reads only the owner's.
COMMUNITY_COLUMNS = ("community_name", "community_source", "match")
KEPT_COLUMNS = (*OWNER_COLUMNS, *COMMUNITY_COLUMNS)
VALUE_SEPARATOR = " | "
ENCODE_SECTION, OPTION_SECTION, TOGGLE_SECTION = "Top", "Option fields", "Three-state fields"

# One plain sentence per field: what a player sees with it on versus off
# (three-state fields), or what it chooses (option fields). Built from
# flags-behavior.md FL-ENC-04, FL-ENC-05, FL-DEP-01 to FL-DEP-05 and the
# entries its support matrix cites (FL-SUP-02, FL-SUP-03).
WHAT_IT_DOES = {
    "C01": "Chooses which overworld the player explores: the first quest's, the second quest's, "
           "a mix of the two, or one picked for each seed.",
    "C02": "Chooses where the dungeon layouts come from: the first quest, the second quest, a mix, "
           "newly generated shapes, a mix with shapes, or one picked for each seed.",
    "C03": "Chooses what the people in caves and dungeons say: the original lines, helpful hints, "
           "community lines, misleading hints, a mix, nothing at all, or one picked for each seed.",
    "C04": "Chooses the screen the player starts on: the usual one, a shuffled one (easy or full "
           "shuffle), or the wooden-sword cave's screen.",
    "C05": "Chooses which entrances lead somewhere new: none, only the dungeon doors, only the other "
           "caves, all of them, or one picked for each seed.",
    "C06": "Chooses how widely items are shuffled: not at all, among dungeon items only, within each "
           "dungeon, or across dungeons, caves and the overworld together.",
    "C07": "Chooses how the wooden sword works: as usual, as the only sword, never given, no swords at "
           "all, or one picked for each seed.",
    "C08": "Chooses what opens level 9: 1 to 8 Triforce pieces, nothing (it is open), a random count in "
           "a range, specific pieces, an item instead of pieces, or one picked for each seed.",
    "C09": "Chooses how enemies' hit points change: not at all, by up to 2 or up to 4 for each kind of "
           "enemy, all to zero, or one picked for each seed.",
    "C10": "Chooses how bosses' hit points change: not at all, by up to 2 or up to 4 for each boss, all "
           "to zero, or one picked for each seed.",
    "C11": "Chooses an item that is always found at the secret Armos spot, or none.",
    "C12": "Chooses an item that is always found in the coast cave, or none; the Ladder is not allowed "
           "there.",
    "C13": "Chooses an item that is always found in the white-sword cave, or none.",
    "C14": "Chooses how dungeon rooms are shuffled: not at all, within each dungeon, between dungeons, "
           "or one picked for each seed.",
    "C15": "Chooses how items and characters look: as usual, a fun percentage, shuffled sprites, or one "
           "picked for each seed.",
    "C16": "Chooses how many hearts the player starts with: 1 to 16, or a random number from 1 to 5.",
    "C17": "Limits how many of the chosen starting items the player really gets: all of them, at most "
           "0 to 20, or a random limit from 0 to 20.",
    "C18": "Chooses how many Triforce pieces the player starts with: 0 to 8, or a random number.",
    "C19": "Chooses what a red bubble does to the player: takes the sword away as in the original game, "
           "reverses the controls, slows the player down, or one picked for each seed.",
    "C20": "Sets the fewest hearts the white-sword cave can ask for (4 to 6).",
    "C21": "Sets the most hearts the white-sword cave can ask for (4 to 6).",
    "C22": "Sets the fewest hearts the magical-sword cave can ask for (10 to 14).",
    "C23": "Sets the most hearts the magical-sword cave can ask for (10 to 14).",
    "C24": "Sets the fewest Triforce pieces level 9 can ask for when it asks for a random count or for "
           "specific pieces.",
    "C25": "Sets the most Triforce pieces level 9 can ask for when it asks for a random count or for "
           "specific pieces.",
    "C26": "Chooses an item that is always found inside level 9 (the first of two), or none.",
    "C27": "Chooses an item that is always found inside level 9 (the second of two), or none.",
    "B01": "With it on, the recorder takes the player to the dungeons' new entrances; with it off, it "
           "works as usual.",
    "B02": "With it on, the wooden-sword cave can be at any hidden cave spot; with it off, it is not "
           "moved to one.",
    "B03": "With it on, the wooden-sword cave can be hidden behind blocks; with it off, it never is.",
    "B04": "With it on, the take-any-road caves trade places; with it off, they stay where they are.",
    "B05": "With it on, the tiles that hide secret entrances move; with it off, they stay where they are.",
    "B06": "With it on, the overworld is mirrored; with it off, it is laid out as usual.",
    "B07": "With it on, the recorder takes the player to dungeons not yet beaten; with it off, it works "
           "as usual.",
    "B08": "With it on, shop wares move between shops and their prices vary; with it off, each shop "
           "sells its usual wares.",
    "B09": "With it on, shops can also sell extra candles; with it off, they don't.",
    "B10": "With it on, the number of hearts the white-sword and magical-sword caves ask for changes with "
           "each seed; with it off, they ask for the usual number.",
    "B11": "With it on, the money-making game's amounts change with each seed; with it off, they are "
           "the usual ones.",
    "B12": "With it on, the bomb-upgrade person's price and number of extra bombs change with each seed; "
           "with it off, they are the usual ones.",
    "B13": "With it on, the item under the secret Armos is shuffled with the others; with it off, it is "
           "the usual item.",
    "B14": "Changes nothing in the game: it is shown and kept in the flag string only.",
    "B15": "With it on, the items in dungeon rooms are shuffled within each level; with it off, they "
           "stay in their rooms.",
    "B16": "Changes nothing in the game: it is shown and kept in the flag string only (heart containers "
           "are shuffled by the item shuffle setting instead).",
    "B17": "With it on, bombs, rupees and keys are shuffled along with the other items; with it off, they "
           "are not.",
    "B18": "With it on, the player has to beat Ganon to finish; with it off, the game ends as usual.",
    "B19": "With it on, the hints given by people in dungeons are swapped around between them; with it "
           "off, each person keeps their hint.",
    "B20": "With it on, generated dungeons can also use second-quest rooms; with it off, they use only "
           "first-quest rooms.",
    "B21": "With it on, generated dungeons also use the second quest's mix of doors; with it off, they "
           "don't.",
    "B22": "With it on, some people in dungeon rooms become merchants who ask for life or money; with it "
           "off, they are as usual.",
    "B23": "With it on, what those merchants ask for changes with each seed; with it off, it is the usual "
           "amount.",
    "B24": "With it on, the dungeon numbers are hidden; with it off, they are shown.",
    "B25": "With it on, important items can be inside level 9; with it off, they can't.",
    "B26": "With it on, a dungeon can start in a different room; with it off, each dungeon starts in its "
           "usual room.",
    "B27": "With it on, the dungeons get different colours; with it off, they keep their usual colours.",
    "B28": "With it on, the hungry goriya that wants food can be in a different dungeon room; with it "
           "off, it stays in its usual room.",
    "B29": "With it on, the people who sell bomb upgrades in dungeons are moved around; with it off, they "
           "stay where they are.",
    "B30": "With it on, most open staircases are removed; with it off, they stay.",
    "B31": "With it on, the monsters on the overworld screens are shuffled; with it off, each screen has "
           "its usual monsters.",
    "B32": "With it on, each dungeon's monsters are shuffled between its rooms; with it off, they stay in "
           "their rooms.",
    "B33": "With it on, Ganon and Zelda are moved by those shuffles too; with it off, they stay where they "
           "are.",
    "B34": "With it on, the bosses are shuffled; with it off, each boss is in its usual place.",
    "B35": "With it on, level 9's monsters also move between levels; with it off, they stay in level 9.",
    "B36": "With it on, monsters can move from one dungeon to another; with it off, each dungeon keeps "
           "its own monsters.",
    "B37": "With it on, second-quest monsters can appear in generated dungeons; with it off, they don't.",
    "B38": "With it on, the groups that decide what enemies drop are shuffled; with it off, they are as "
           "usual.",
    "B39": "With it on, enemies can drop important items; with it off, they don't.",
    "B40": "With it on, the groups of bosses are mixed up; with it off, they are as usual.",
    "B41": "With it on, Ganon has no hit points; with it off, Ganon's hit points are as usual.",
    "B42": "With it on, the groups of enemies are shuffled; with it off, they are as usual.",
    "B43": "With it on, the overworld screens' monsters are redrawn from the overworld group; with it "
           "off, they are as usual.",
    "B44": "With it on, how often items drop is random; with it off, it is the usual rate.",
    "B45": "With it on, every enemy has the most health possible; with it off, enemy health is as usual.",
    "B46": "With it on, every boss has the most health possible; with it off, boss health is as usual.",
    "B47": "With it on, the Book of Magic turns the wand's fire into an explosion; with it off, it makes "
           "fire as usual.",
    "B48": "With it on, carrying the Book of Magic lets the player understand old men; with it off, it "
           "doesn't.",
    "B49": "With it on, holding the Book of Magic counts as having every dungeon's map; with it off, each "
           "map has to be found.",
    "B50": "With it on, the game plays in blackout mode; with it off, it doesn't.",
    "B51": "With it on, the game prints quest information; with it off, it doesn't.",
    "B52": "With it on, the sword always shoots a beam; with it off, the beam works as usual.",
    "B53": "With it on, any hit knocks the player out; with it off, damage is as usual.",
    "B54": "With it on, people's text appears faster; with it off, it appears at the usual speed.",
    "B55": "With it on, the player's health is hidden; with it off, it is shown.",
    "B56": "With it on, items that enemies drop can be destroyed; with it off, they can't.",
    "B59": "With it on, the player starts with 8 bombs; with it off, bombs have to be found.",
    "B79": "With it on, extra bosses are added; with it off, there are the usual bosses.",
    "B80": "With it on, the rupees the player carries change their speed; with it off, they don't.",
    "B81": "With it on, the game forces an overworld block for an item; with it off, it doesn't.",
    "B82": level_encoding.HELP_TEXT,
    "B83": "With it on, numbers are hidden; with it off, they are shown.",
    "B84": "With it on, the game prevents slipping through walls while the screen scrolls; with it off, "
           "it doesn't.",
    "B86": "With it on, generated dungeon shapes are not sorted by size; with it off, they are.",
    "B87": "With it on, bridges are added over the river; with it off, the river is as usual.",
    "B88": "With it on, there is a shortcut through the Lost Woods; with it off, there isn't.",
    "B89": "With it on, the hidden tiles on the overworld change; with it off, they are as usual.",
    "B90": "With it on, the bomb upgrade adds more bombs; with it off, it adds the usual number.",
    "B91": "With it on, generated dungeons can use universal drops; with it off, they don't.",
}
# The starting-item fields (FL-ENC-05 B57 to B78 and B85), whose sentences share one form.
_START_ITEMS = {
    "B57": "the Raft", "B58": "the Bow", "B60": "the Recorder", "B61": "the Bait", "B62": "the Magical Key",
    "B63": "the Letter", "B64": "the Power Bracelet", "B65": "the Ladder", "B66": "the Wand",
    "B67": "the Book of Magic", "B68": "the wooden sword", "B69": "the white sword",
    "B70": "the magical sword", "B71": "the wooden arrow", "B72": "the Silver Arrow",
    "B73": "the blue candle", "B74": "the red candle", "B75": "the blue ring", "B76": "the red ring",
    "B77": "the wooden Boomerang", "B78": "the Magical Boomerang", "B85": "the magical shield",
}
WHAT_IT_DOES |= {field_id: f"With it on, the player starts with {item} (within the limit on starting "
                           f"items); with it off, it has to be found."
                 for field_id, item in _START_ITEMS.items()}


class NamesError(ValueError):
    pass


def page_fields() -> list[tuple[str, flag_form.FieldDef]]:
    """Every field with its page section, in the page's order: Encode level
    data at the top, then the option fields tab, then the three-state tab."""
    encode = ENCODE_LEVEL_DATA
    fields: list[tuple[str, flag_form.FieldDef]] = [(ENCODE_SECTION, encode)]
    fields += [(OPTION_SECTION, field) for field in OPTION_FIELDS]
    fields += [(TOGGLE_SECTION, field) for field in TOGGLE_FIELDS if field != encode]
    return fields


def _spec_value_labels(field: flag_form.FieldDef) -> list[str]:
    return [flag_form.spec_value_label(field, value) for value in flag_form.field_values(field)]


def _supported_text(field: flag_form.FieldDef) -> str:
    labels = [flag_form.spec_value_label(field, value) for value in flag_form.supported_values(field)]
    if len(labels) == 1:
        return labels[0] + " only"
    return " or ".join(labels) + (" (both supported)" if len(labels) == 2 else " (all supported)")


def spec_rows() -> list[dict[str, str]]:
    baseline = mvp_baseline_settings()
    rows = []
    for section, field in page_fields():
        option = isinstance(field, OptionField)
        value = baseline.option(field) if option else int(baseline.toggle(field))
        assert support(baseline)[field.id] is Support.SUPPORTED
        rows.append({
            "page_section": section,
            "field_id": field.id,
            "spec_label": flag_form.spec_field_label(field),
            "what_it_does": WHAT_IT_DOES[field.id],
            "kind": "option" if option else "on/off" if field == ENCODE_LEVEL_DATA else "on/off/random",
            "values": VALUE_SEPARATOR.join(_spec_value_labels(field)) if option else "",
            "baseline_value": flag_form.spec_value_label(field, value),
            "supported": _supported_text(field),
            **dict.fromkeys(KEPT_COLUMNS, ""),
        })
    return rows


# ---------------------------------------------------------------------------
# Reading what the owner saved
# ---------------------------------------------------------------------------

def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252")          # older Excel "CSV (Comma delimited)"


def read_rows(path: Path = CSV_PATH) -> list[dict[str, str]]:
    """The CSV's rows as dictionaries, whatever delimiter the spreadsheet used."""
    text = _decode(path.read_bytes())
    header = text.splitlines()[0] if text else ""
    delimiter = max(",;\t", key=header.count)
    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter)
    missing = [column for column in ("field_id", *OWNER_COLUMNS) if column not in (reader.fieldnames or [])]
    if missing:
        raise NamesError(f"{path.name}: missing column(s) {', '.join(missing)}; the first row must be the "
                         "column names")
    return [{key: (value or "").strip() for key, value in row.items() if key} for row in reader]


def owner_names(rows: list[dict[str, str]]) -> dict[str, dict[str, object]]:
    """The owner's names by field id, checked: every field once, no unknown
    field, the right number of value names, Encode level data unnamed."""
    fields = {field.id: field for _section, field in page_fields()}
    seen: dict[str, int] = {}
    problems = []
    names: dict[str, dict[str, object]] = {}
    for number, row in enumerate(rows, start=2):
        field_id = row.get("field_id", "")
        if not field_id and not any(row.values()):
            continue                           # an empty line a spreadsheet left
        if field_id not in fields:
            problems.append(f"row {number}: unknown field_id {field_id!r}")
            continue
        if field_id in seen:
            problems.append(f"row {number}: {field_id} is listed twice (also row {seen[field_id]})")
            continue
        seen[field_id] = number
        field = fields[field_id]
        name, value_text = row.get("owner_name", ""), row.get("owner_value_names", "")
        entry: dict[str, object] = {}
        if name:
            if field == ENCODE_LEVEL_DATA:
                problems.append(f"row {number}: {field_id} keeps its fixed label "
                                f"{level_encoding.LABEL!r}; leave owner_name empty")
            else:
                entry["name"] = name
        if value_text:
            if not isinstance(field, OptionField):
                problems.append(f"row {number}: {field_id} is an on/off/random field; owner_value_names "
                                "is only for option fields")
            else:
                values = [part.strip() for part in value_text.split(VALUE_SEPARATOR.strip())]
                if len(values) != field.count:
                    problems.append(f"row {number}: {field_id} has {field.count} values but owner_value_names "
                                    f"gives {len(values)}, separated by |; leave a part empty to keep the "
                                    "spec's name for it")
                else:
                    entry["values"] = values
        if entry:
            names[field_id] = entry
    absent = [field_id for field_id in fields if field_id not in seen]
    if absent:
        problems.append(f"no row for {', '.join(absent)}")
    if problems:
        raise NamesError("docs/flag-names.csv:\n  " + "\n  ".join(problems))
    return names


# ---------------------------------------------------------------------------

def generate(path: Path = CSV_PATH) -> int:
    kept = {row["field_id"]: row for row in read_rows(path)} if path.exists() else {}
    rows = spec_rows()
    for row in rows:
        for column in KEPT_COLUMNS:
            row[column] = kept.get(row["field_id"], {}).get(column, "")
    with path.open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def json_text(names: dict[str, dict[str, object]]) -> str:
    return json.dumps(names, indent=1, ensure_ascii=False, sort_keys=True) + "\n"


def import_names(path: Path = CSV_PATH, out: Path = JSON_PATH) -> dict[str, dict[str, object]]:
    names = owner_names(read_rows(path))
    out.write_text(json_text(names), encoding="utf-8")
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("generate", "import"))
    args = parser.parse_args()
    try:
        if args.action == "generate":
            count = generate()
            print(f"{CSV_PATH.relative_to(REPO)}: {count} fields")
        else:
            names = import_names()
            values = sum(1 for entry in names.values() if "values" in entry)
            print(f"{JSON_PATH.relative_to(REPO)}: owner names for {sum('name' in e for e in names.values())} "
                  f"fields, value names for {values}")
    except NamesError as exc:
        print(f"flag_names: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
