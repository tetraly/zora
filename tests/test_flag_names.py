"""docs/flag-names.csv (the owner's names for the flag fields) and its
import into zora/flags/names.json (scripts/flag_names.py)."""
import csv
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from zora.flags import form as flag_form
from zora.flags.fields import OptionField
from zora.rom import level_encoding

REPO = Path(__file__).resolve().parent.parent


def _flag_names() -> ModuleType:
    spec = importlib.util.spec_from_file_location("flag_names", REPO / "scripts" / "flag_names.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


flag_names = _flag_names()
ALL_IDS = [field.id for field in flag_form.ALL_FIELDS]


def test_every_field_has_one_row_and_the_csv_parses() -> None:
    raw = flag_names.CSV_PATH.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")                  # UTF-8 mark, for Excel
    rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
    assert tuple(rows[0]) == flag_names.COLUMNS
    assert sorted(row["field_id"] for row in rows) == sorted(ALL_IDS)
    for row in rows:
        assert row["what_it_does"] and row["spec_label"] and row["supported"]
        field = flag_form.FIELDS_BY_ID[row["field_id"]]
        if isinstance(field, OptionField):
            assert len(row["values"].split(flag_names.VALUE_SEPARATOR)) == field.count
    assert flag_names.owner_names(flag_names.read_rows()) is not None


def test_spec_columns_match_the_code() -> None:
    """Generating again would change nothing but the owner's columns, which it keeps."""
    current = flag_names.read_rows()
    for row, expected in zip(current, flag_names.spec_rows(), strict=True):
        for column in flag_names.COLUMNS:
            if column not in flag_names.KEPT_COLUMNS:
                assert row[column] == expected[column], (row["field_id"], column)


def test_the_imported_names_are_up_to_date() -> None:
    """zora/flags/names.json is what importing docs/flag-names.csv gives."""
    names = flag_names.owner_names(flag_names.read_rows())
    assert flag_names.JSON_PATH.read_text(encoding="utf-8") == flag_names.json_text(names)


def _write(path: Path, rows: list[dict[str, str]], delimiter: str = ",", encoding: str = "utf-8-sig") -> Path:
    with path.open("w", encoding=encoding, newline="") as out:
        writer = csv.DictWriter(out, fieldnames=flag_names.COLUMNS, delimiter=delimiter)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _named(**changes: tuple[str, str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = flag_names.spec_rows()
    for row in rows:
        if row["field_id"] in changes:
            row["owner_name"], row["owner_value_names"] = changes[row["field_id"]]
    return rows


def test_import_reads_what_a_spreadsheet_saves(tmp_path: Path) -> None:
    rows = _named(C03=("Hints", "Vanilla | | Community | Lies | Mixed | None | Random"),
                  B49=("Book is the map", ""))
    for delimiter, encoding in ((",", "utf-8-sig"), (";", "utf-8"), ("\t", "cp1252")):
        names = flag_names.owner_names(flag_names.read_rows(_write(tmp_path / "x.csv", rows, delimiter, encoding)))
        assert names == {"C03": {"name": "Hints", "values": ["Vanilla", "", "Community", "Lies", "Mixed", "None",
                                                             "Random"]},
                         "B49": {"name": "Book is the map"}}


@pytest.mark.parametrize("changes, message", [
    ({"B82": ("Secret mode", "")}, "keeps its fixed label"),
    ({"C03": ("", "A | B")}, "has 7 values"),
    ({"B49": ("", "On | Off")}, "only for option fields"),
])
def test_import_refuses_a_bad_edit(tmp_path: Path, changes: dict[str, tuple[str, str]], message: str) -> None:
    path = _write(tmp_path / "x.csv", _named(**changes))
    with pytest.raises(flag_names.NamesError, match=message):
        flag_names.owner_names(flag_names.read_rows(path))


def test_import_refuses_a_missing_or_doubled_field(tmp_path: Path) -> None:
    rows = flag_names.spec_rows()
    with pytest.raises(flag_names.NamesError, match="no row for C05"):
        flag_names.owner_names(flag_names.read_rows(_write(tmp_path / "x.csv",
                                                           [r for r in rows if r["field_id"] != "C05"])))
    with pytest.raises(flag_names.NamesError, match="listed twice"):
        flag_names.owner_names(flag_names.read_rows(_write(tmp_path / "y.csv", rows + rows[:1])))


def test_page_uses_owner_names_and_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    names = {"C03": {"name": "Hints", "values": ["Vanilla", "", "Community", "Lies", "Mixed", "None", "Random"]}}
    monkeypatch.setattr(flag_form, "owner_names", lambda: json.loads(json.dumps(names)))
    fields = {field["id"]: field for field in flag_form.metadata()["fields"]}
    hints = fields["C03"]
    assert (hints["label"], hints["specLabel"]) == ("Hints", "Hint style")
    assert [value["label"] for value in hints["values"]][:2] == ["Vanilla", "Helpful"]   # empty part: spec label
    assert fields["C02"]["label"] == fields["C02"]["specLabel"] == "Dungeon layout source"
    assert fields["B82"]["label"] == level_encoding.LABEL
