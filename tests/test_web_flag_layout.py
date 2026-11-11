"""The flag layout of issue #15 (web/flag-tabs.json, web/zora-web.js): Overworld Quest, Dungeon Quest and
Hint Type above the tabs; every other Z1R setting on one tab, in one column and row, as the original
program places it; every ZORA extra in one group of the ZORA tab. The layout is the page's only: no flag
string, shared link or settings file reads it, so moving a setting changes none of them."""
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from zora_web import api

REPO = Path(__file__).resolve().parent.parent
PAGE_SCRIPT = (REPO / "web" / "zora-web.js").read_text()
FLAG_TABS = json.loads((REPO / "web" / "flag-tabs.json").read_text())
METADATA = api.flag_form.metadata()


def page_constant(name: str) -> str:
    match = re.search(rf"^const {name} = .*?;$", PAGE_SCRIPT, re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group(0)


def page_function(name: str) -> str:
    match = re.search(rf"^(?:async )?function {name}\(.*?^}}\n", PAGE_SCRIPT, re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group(0)


def node_value(*constants: str) -> Any:
    """The page's constants, evaluated in Node; the last one's value."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    source = "\n".join([*map(page_constant, constants), f"console.log(JSON.stringify({constants[-1]}));"])
    return json.loads(subprocess.run([node], input=source, capture_output=True, text=True, check=True).stdout)


def test_every_z1r_setting_has_one_place() -> None:
    tabs = [*node_value("START_TAB", "ADVANCED_TAB", "FLAG_TABS"), node_value("TOP_SECTION")]
    places: dict[tuple[str, int, int], str] = {}
    for field in METADATA["fields"]:
        entry = FLAG_TABS[field["id"]]
        assert entry["tab"] in tabs, field["id"]
        place = (entry["tab"], entry["column"], entry["row"])
        assert place not in places, (field["id"], places.get(place))
        places[place] = field["id"]
    assert set(FLAG_TABS) == {field["id"] for field in METADATA["fields"]}
    # Each tab's columns run from 1, each column's rows from 1, with no gaps
    for tab in tabs:
        columns = sorted({column for (name, column, _row) in places if name == tab})
        assert columns == list(range(1, len(columns) + 1)), tab
        for column in columns:
            rows = sorted(row for (name, col, row) in places if (name, col) == (tab, column))
            assert rows == list(range(1, len(rows) + 1)), (tab, column)


def test_advanced_follows_zora_extras() -> None:
    assert node_value("ADVANCED_TAB", "AFTER_ZORA_TABS") == ["Advanced"]


def test_the_quests_and_hint_type_sit_above_the_tabs() -> None:
    top = node_value("TOP_SECTION")
    above = sorted((entry["row"], field) for field, entry in FLAG_TABS.items() if entry["tab"] == top)
    assert [field for _row, field in above] == ["C01", "C02", "C03"]


def test_every_zora_extra_is_in_one_group() -> None:
    groups = node_value("ZORA_GROUPS")
    named = [name for _heading, columns in groups for column in columns for name in column]
    assert len(named) == len(set(named))
    # A field placed on a flag tab (flagTab: Wizzrobes Shoot Wallmasters on Advanced) is in no group
    shown = {field["name"] for field in METADATA["zora"]["fields"] if not field.get("hidden") and not field.get("flagTab")}
    assert set(named) == shown


def test_no_flag_string_link_or_settings_file_reads_the_layout() -> None:
    """Python makes the flag strings without the page's file, and the page's link and settings file
    never name a tab, a column or a row."""
    for package in ("zora", "zora_web", "zora_export"):
        for path in (REPO / package).rglob("*.py"):
            assert "flag-tabs" not in path.read_text(), path
    for name in ("linkSearch", "linkSettings", "pageSettings", "applyPageSettings", "controlValues", "zoraValues"):
        body = page_function(name)
        for word in ("flagTabs", "flagTabsMap", "placeOf", "ZORA_GROUPS", "TOP_SECTION", "FLAG_TABS"):
            assert word not in body, (name, word)
