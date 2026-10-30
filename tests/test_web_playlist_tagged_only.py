"""The playlist editor's Only show tagged tracks (web/zora-web.js playlistChoices; TheGobOne's request,
2026-10-25): off, every area's select lists every song, the untagged ones marked; on, only the songs
tagged for the area, and the area's pinned song whatever it is, so a pin never disappears. The page's
own code, run in Node."""
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
PAGE_SCRIPT = (REPO / "web" / "zora-web.js").read_text()
TITLE_AREA = {"key": "title", "label": "Title screen", "uses": ["Title"]}
SONGS = [{"title": "Theme", "uses": ["Title"], "safe": True},
         {"title": "Field", "uses": ["Overworld"], "safe": True},
         {"title": "Loud", "uses": ["Title", "Overworld"], "safe": False}]


def choices(tagged_only: bool, pinned: str | None = None) -> list[list[Any]]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    match = re.search(r"^function playlistChoices\(.*?^}$", PAGE_SCRIPT, re.MULTILINE | re.DOTALL)
    assert match
    arguments = ", ".join(json.dumps(value) for value in (TITLE_AREA, SONGS, tagged_only, pinned))
    call = f"playlistChoices({arguments})"
    source = f"{match.group(0)}\nconsole.log(JSON.stringify({call}.map(({{ song, notes }}) => [song.title, notes])));"
    listed: list[list[Any]] = json.loads(subprocess.run([node, "-e", source], capture_output=True, text=True,
                                                             check=True).stdout)
    return listed


def test_off_every_song_is_listed_the_untagged_marked() -> None:
    assert choices(tagged_only=False) == [["Theme", []], ["Field", ["not tagged for this area"]],
                                          ["Loud", ["unsafe for streaming"]]]


def test_on_only_the_tagged_songs_and_the_pin() -> None:
    assert choices(tagged_only=True) == [["Theme", []], ["Loud", ["unsafe for streaming"]]]
    assert [title for title, _ in choices(tagged_only=True, pinned="Field")] == ["Theme", "Field", "Loud"]


def test_the_editor_has_the_checkbox_and_remembers_it() -> None:
    fill = re.search(r"^async function fillMusicPlaylistEditor\(.*?^}$", PAGE_SCRIPT, re.MULTILINE | re.DOTALL)
    assert fill and "Only show tagged tracks" in fill.group(0) and "playlistChoices(" in fill.group(0)
    assert 'const MUSIC_TAGGED_ONLY_KEY = "zora-music-playlist-tagged-only";' in PAGE_SCRIPT
