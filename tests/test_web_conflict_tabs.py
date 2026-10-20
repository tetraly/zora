"""The page's conflict tabs (web/zora-web.js; owner request, 2026-10-17): when settings conflict, every
tab holding one of the conflicting settings turns red, beside the red note at each setting, so the
player can find both halves; the mark goes once the conflict is resolved. Run in Node on the page's own
functions."""
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
PAGE_SCRIPT = (REPO / "web" / "zora-web.js").read_text()
PAGE_STYLE = (REPO / "web" / "zora.css").read_text()
CONSTANTS = ("ZORA_TAB", "CONFLICT_TAB_NOTE")

# A fake of the few page pieces the functions touch: the setting maps and the tab buttons.
FAKE_PAGE = """
const zoraControls = new Map([["swordHearts", {}], ["extraCandles", {}]]);
const controls = new Map([["progressiveItems", { tab: "Items" }], ["whiteSwordHearts", { tab: "Items" }],
                          ["levelNine", { tab: "Dungeons" }]]);
const tabButtons = ["Overworld", "Dungeons", "Items", "ZORA extras"].map((name) => ({
  id: `tab-${slug(name)}`, title: "", marks: new Set(),
  classList: { toggle(mark, on) { on ? this.owner.marks.add(mark) : this.owner.marks.delete(mark); } },
}));
for (const tab of tabButtons) tab.classList.owner = tab;
const $ = (id) => ({ querySelectorAll: () => tabButtons });
const marked = () => tabButtons.filter((tab) => tab.marks.has("tab--conflict")).map((tab) => [tab.id, tab.title]);
"""


def page_function(name: str) -> str:
    match = re.search(rf"^(?:async )?function {name}\(.*?^}}\n", PAGE_SCRIPT, re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group(0)


def run(script: str) -> Any:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    constants = [line for line in PAGE_SCRIPT.splitlines() if re.match(rf"const ({'|'.join(CONSTANTS)}) = ", line)]
    assert len(constants) == len(CONSTANTS)
    functions = map(page_function, ("slug", "conflictTabs", "markConflictTabs"))
    source = "\n".join([*constants, *functions, FAKE_PAGE, script])
    return json.loads(subprocess.run([node, "-e", source], capture_output=True, text=True, check=True).stdout)


def test_each_tab_holding_a_conflicting_setting_is_marked_and_cleared() -> None:
    answers = run("""
const conflicts = [{ message: "m1", fields: ["swordHearts", "whiteSwordHearts"] },
                   { message: "m2", fields: ["progressiveItems", "extraCandles"] }];
const tabs = conflictTabs(conflicts);
markConflictTabs(tabs);
const during = marked();
markConflictTabs(conflictTabs([{ message: "m3", fields: ["levelNine", "unknownSetting"] }]));
const other = marked();
markConflictTabs(conflictTabs([]));
console.log(JSON.stringify({ tabs, during, other, after: marked() }));
""")
    note = re.search(r'const CONFLICT_TAB_NOTE = "(.*)";', PAGE_SCRIPT)
    assert note
    assert sorted(answers["tabs"]) == ["Items", "ZORA extras"]      # each tab once
    assert answers["during"] == [["tab-items", note.group(1)], ["tab-zora-extras", note.group(1)]]
    assert answers["other"] == [["tab-dungeons", note.group(1)]]     # a setting no tab shows marks none
    assert answers["after"] == []


def test_the_page_marks_tabs_with_every_conflict_and_styles_the_mark_red() -> None:
    show = page_function("showZoraState")
    assert show.index("markConflictTabs([])") < show.index("if (!zora.ok) return;")    # a bad string clears it
    assert "markConflictTabs(conflictTabs(zora.conflicts))" in show
    assert re.search(r"\.tab--conflict \{[^}]*var\(--error\)", PAGE_STYLE)
