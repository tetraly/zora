"""A library song that ends on a halt (Cxx) does not loop: lozft's bhop stops its rows for good and can leave a
note held until the song changes (ISUMatt's level 9, Rex's list's "Tecmo Super Bowl - Unknown Song";
docs/reports/bug-isumatt-1221053620.md). On Quantam's advice (2026-10-30) ZORA leaves its bytes alone: Random
never draws such a song (randomize.drawable_songs, importer.song_loops), and a playlist that names one is
warned about, since the player probably picked it by mistake."""
import pytest

from scripts.music_assets import assets_available, pinned_assets
from zora.rom.music.ftm import FtmModule
from zora.rom.music.importer import CHANNELS, _ModuleInfo, song_loops
from zora.rom.music.library import ORIGINAL_SONGS, Song, library_songs
from zora.rom.music.playlist import Playlist, resolve_playlist
from zora.rom.music.randomize import drawable_songs

pytestmark = pytest.mark.skipif(not assets_available(), reason="needs the music clone (scripts/music_assets.py)")

# The standard library's one song that halts (a static scan of its 116 songs, 2026-10-30)
HALTING = "Dragon Fighter - 11 Ending"
PLACED_AT = 0xA000


def songs() -> list[Song]:
    return library_songs(pinned_assets().library, safe_only=False)


def halting_song() -> Song:
    return next(song for song in songs() if song.title == HALTING)


def test_only_one_standard_song_halts() -> None:
    assert [song.title for song in songs() if not song_loops(song)] == [HALTING]
    assert all(song_loops(song) for song in ORIGINAL_SONGS)


def test_random_never_draws_a_song_that_halts() -> None:
    for safe_only in (True, False):
        pool = drawable_songs(songs(), safe_only)
        assert HALTING not in [song.title for song in pool]
        assert all(song_loops(song) for song in pool)


def test_a_placed_module_keeps_its_halt() -> None:
    """ZORA no longer rewrites a halt: the song is placed as its module holds it."""
    song = halting_song()
    assert song.module is not None
    placed = _ModuleInfo(song.module.data, song.module.address, [song]).placed_data(PLACED_AT)
    assert FtmModule(placed, PLACED_AT, CHANNELS).halts(song.number)


def test_a_playlist_naming_a_song_that_halts_is_warned_about() -> None:
    fixed, warnings = resolve_playlist(Playlist({"level9": HALTING}), songs(), safe_only=False)
    assert [song.title for song in fixed.values()] == [HALTING]
    assert [warning for warning in warnings if "doesn't loop" in warning] == [
        f"Level 9: {HALTING} doesn't loop: it stops when it ends and can leave a note held until the music "
        "changes. Did you mean another track?"]
