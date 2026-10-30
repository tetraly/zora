"""Randomized music (docs/music.md, docs/design/music-settings.md): the library reader, the port of
Quantam's importer against his own output, lozft on finished ROMs, the settings, the local library,
playlists, the race flag Disable Custom Music, and the game in the emulator. Skipped without the
music folder (scripts/music_assets.py) or the base ROMs. The local libraries and playlists are cut
from the standard library at test time, never committed."""
import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from scripts.music_assets import assets_available, pinned_assets
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.rom.base_rom import BASE_ROM_PATH, PRG1_ROM_PATH, remember_repo_base_rom
from zora.flags import zora_flags
from zora.flags.fields import ThreeState
from zora.rom.music import json5
from zora.rom.music.importer import AREA_SONGS, MODULE_ADDRESSES, Placed, RomFull, pack_songs
from zora.rom.music.library import (DUNGEON, ENDING, LAST_DUNGEON, ORIGINAL_SONGS, OVERWORLD, TITLE, LibraryError,
                                    USES, LibraryFile, MusicError,
                                    library_songs, module_data, read_library)
from zora.rom.music.lozft import LOZFT_ROM_SIZE, LozftUnavailable, apply_bps, lozft_bytes, lozft_bytes_sha256, with_lozft
from zora.rom.music.pin import MusicAssets, MusicAssetsInvalid
from zora.rom.music.playlist import AREA_KEYS, ORIGINAL_TITLES, PlaylistError, parse_playlist
from zora.rom.music.randomize import MusicOptions, MusicSource, options_for, randomize_music
from zora_web.api import music_library_songs, music_playlist_areas
from zora.rom.player_settings import (
    Music,
    PlayerSettingError,
    PlayerSettings,
    parse_player_settings,
    player_settings_from_page,
)

if TYPE_CHECKING:
    from tests.emulator import Emulator

pytestmark = [pytest.mark.skipif(not assets_available(), reason="needs the music clone (scripts/music_assets.py)"),
              pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")]

LIBRARY_MODULES = 321
# Quantam's importer (ZeldaMusicRandomizer's MusicImporter on FtRandoLib, the pinned commits) run on
# PRG1 with the pinned lozft (his of 2026-10-22), his library and the original tracks, seeds 1 and
# 2: its choices, by song number, and the SHA-1 of the ROM it wrote. lozft alone on PRG1 (its
# BpsFile) is LOZFT_PRG1_SHA1.
LOZFT_PRG1_SHA1 = "dd5992ff3d6b72283c0041ddc908ff1eb0bd6d8a"
REFERENCE = {
    "97f3478d6e46e26601737a8330d4fc9bca67d22d": (
        "Chaos World - 21 Castle Salatis", "Tenchi o Kurau II - 15 Ending / Staff Roll",
        "Legend of Zelda - Last Dungeon", "Zeliard - World of Darkness", "Zeliard.ftm - Ice Caverns",
        "Arumana no Kiseki - Level 5 Revisited", "Dragon Fighter - 02 Don't Disturb", "Rygar - 05 Den of Sagila",
        "Rygar - 07 Lapis", "Gargoyle's Quest II - 18 Royal Chambers", "Haunted Castle - Can't Wait Until the Night"),
    "037a6d323eede64ebf6601bd08959f651588de7a": (
        "Radia Senki - 42 Ship", "Rygar - 15 The End", "Touhou 17 - The Lamentations Known Only by Jizo",
        "Touhou 17 - The Lamentations Known Only by Jizo", "Rygar - 39 Eruga's Forest", "Nether's Lament",
        "Chaos World - 07 Battle 1", "Tenchi o Kurau II - 03 Battle Theme 1", "Gargoyle's Quest II - 18 Royal Chambers",
        "Touhou Ganshoujo - Scarlet Devil Mansion Entrance", "Dragon Fighter - 05 Dragon Fighter"),
}
# The song numbers of Quantam's importer, in its order (the overworld, the ending, level 9, levels 1-8).
REFERENCE_SONG_NUMBERS = (0, 4, 5, 6, 11, 12, 13, 14, 15, 16, 17)
TITLE_SONG, ENDING_SONG = AREA_SONGS[TITLE][0], AREA_SONGS[ENDING][0]
SONG_TABLE = 0x10
FAMITRACKER_BANKS = range(0x80, 0x100)       # a FamiTracker song's table byte: its bank XOR $FF
MUSIC_SETTINGS = PlayerSettings(music=Music.RANDOM_STANDARD)
SEED = 21
STATS_BLOCK = 0x7F00                         # fp-stats-01's, in SRAM, below lozft's driver
TOTAL_SECONDS = STATS_BLOCK + 2              # 16 bits
DRIVER_SRAM = range(0x7F40, 0x7FFE)          # lozft's driver's own SRAM
BATTERY_RAM = range(0x6000, 0x8000)          # what a cartridge's battery keeps through a power-off
HEADER = 0x10
BLANK_TILES = HEADER + 0x4000 + 0x0FF9       # bank 1 $8FF9: blank tile space the patch takes zeros from
GAME_BANKS_1_TO_6 = range(HEADER + 0x4000, HEADER + 7 * 0x4000)
BASE = BASE_ROM_PATH.read_bytes() if BASE_ROM_PATH.exists() else b""


@pytest.fixture(scope="module")
def assets() -> MusicAssets:
    return pinned_assets()


@pytest.fixture(scope="module")
def music_zora_rom() -> bytes:
    return generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, remember_repo_base_rom(), MUSIC_SETTINGS).rom


def test_the_library_reads_as_ftrandolib_reads_it(assets: MusicAssets) -> None:
    every = library_songs(assets.library, safe_only=False)
    modules = {id(song.module) for song in every}
    assert len(modules) <= LIBRARY_MODULES and all(song.enabled for song in every)
    assert all(song.module and song.module.data for song in every)
    assert module_data("hex:0102") == b"\x01\x02"


def test_a_changed_asset_is_refused(assets: MusicAssets) -> None:
    with pytest.raises(MusicAssetsInvalid):
        MusicAssets(assets.library + b" ", assets.patch)


@pytest.mark.skipif(not PRG1_ROM_PATH.exists(), reason="needs the PRG1 ROM")
def test_lozft_and_the_importer_give_quantams_bytes(assets: MusicAssets) -> None:
    """The same songs in the same song numbers give the same ROM as his importer: relocation, square
    swaps, packing, the driver copies and the song table."""
    lozft = apply_bps(assets.patch, PRG1_ROM_PATH.read_bytes())
    assert hashlib.sha1(lozft).hexdigest() == LOZFT_PRG1_SHA1
    songs = library_songs(assets.library) + list(ORIGINAL_SONGS)
    by_title = {song.title: song for song in reversed(songs)}
    for expected, titles in REFERENCE.items():
        rom = bytearray(lozft)
        pack_songs(rom, [Placed(number, by_title[title])
                         for number, title in zip(REFERENCE_SONG_NUMBERS, titles, strict=True)])
        assert hashlib.sha1(rom).hexdigest() == expected


@pytest.mark.skipif(not PRG1_ROM_PATH.exists(), reason="needs the PRG1 ROM")
def test_lozft_comes_from_the_players_rom(assets: MusicAssets) -> None:
    """lozft's own bytes are the same made from PRG0 as from PRG1 (the patch's copies from elsewhere
    read PRG1's bytes from PRG0's moved code); a ROM whose blank tiles the patch takes zeros from
    are drawn on (modified graphics) is refused, and the finished ROM keeps its own bytes elsewhere."""
    made = {path.name: lozft_bytes(assets.patch, path.read_bytes()) for path in (BASE_ROM_PATH, PRG1_ROM_PATH)}
    assert len({lozft_bytes_sha256(*pair) for pair in made.values()}) == 1
    prg0 = BASE_ROM_PATH.read_bytes()
    rom = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, remember_repo_base_rom(), MUSIC_SETTINGS).rom
    out = with_lozft(rom, assets.patch, prg0)
    own = made[BASE_ROM_PATH.name][1]
    # banks 1-6 (bank 0 has the two changes after lozft: the PRG0 site and the StatsTick call)
    assert all(out[offset] == rom[offset] for offset in GAME_BANKS_1_TO_6 if not own[offset])
    drawn = bytearray(prg0)
    drawn[BLANK_TILES:BLANK_TILES + 4] = b"\x55" * 4
    with pytest.raises(LozftUnavailable, match="graphics"):
        with_lozft(rom, assets.patch, bytes(drawn))


def test_randomized_music_gives_every_area_its_own_track(music_zora_rom: bytes, assets: MusicAssets) -> None:
    first = randomize_music(music_zora_rom, BASE, assets, SEED)
    again = randomize_music(music_zora_rom, BASE, assets, SEED)
    assert first.rom == again.rom and len(first.rom) == LOZFT_ROM_SIZE
    areas = [title for area, title in first.track_list()]
    songs = sum(len(numbers) for numbers in AREA_SONGS.values())
    assert len(areas) == songs and len(set(areas)) == len(areas)    # the ending and credits drawn too
    # the standard library tags no track Title: the title screen keeps the game's own song
    assert [place.song_number for place in first.placed if place.song.is_original] == [TITLE_SONG]
    assert first.rom[SONG_TABLE + 2 * TITLE_SONG] not in FAMITRACKER_BANKS
    ending = next(place.song for place in first.placed if place.song_number == ENDING_SONG)
    assert ENDING in ending.uses and first.rom[SONG_TABLE + 2 * ENDING_SONG] in FAMITRACKER_BANKS
    other = randomize_music(music_zora_rom, BASE, assets, SEED + 1)
    assert other.rom != first.rom


def test_lozft_needs_the_music_statistics_choice(assets: MusicAssets) -> None:
    plain = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, remember_repo_base_rom()).rom
    with pytest.raises(LozftUnavailable, match="music choice"):
        with_lozft(plain, assets.patch, BASE)


def test_the_settings_read_from_the_page_and_the_command_line() -> None:
    page = player_settings_from_page({"music": "random-local", "musicStreamingSafeOnly": "off"})
    assert (page.music, page.randomize_music, page.music_streaming_safe_only) == (Music.RANDOM_LOCAL, True, False)
    assert player_settings_from_page({"music": "random-standard"}).randomize_music
    defaults = player_settings_from_page({})
    assert not defaults.randomize_music and defaults.music_streaming_safe_only
    assert not player_settings_from_page({"music": "on"}).randomize_music
    assert parse_player_settings(["music=random-standard", "music_streaming_safe_only=off"]) == \
        PlayerSettings(music=Music.RANDOM_STANDARD, music_streaming_safe_only=False)
    with pytest.raises(PlayerSettingError):
        player_settings_from_page({"music": "loud"})
    with pytest.raises(PlayerSettingError):
        player_settings_from_page({"musicStreamingSafeOnly": "maybe"})
    options = options_for(page)
    assert (options.source, options.safe_only) == (MusicSource.LOCAL, False)


def test_the_music_plays_and_the_statistics_run_in_the_emulator(music_zora_rom: bytes, assets: MusicAssets,
                                                                tmp_path: Path) -> None:
    """Play reached, the driver's SRAM busy on the overworld, the clock in the statistics block
    ticking, and the block kept through a reset and through turning the console off and on (the
    battery-backed $6000-$7FFF carried over to a console with fresh internal RAM)."""
    from tests.emulator import Emulator
    path = tmp_path / "music.nes"
    path.write_bytes(randomize_music(music_zora_rom, BASE, assets, SEED).rom)
    emulator = Emulator(path)
    emulator.new_game()
    before = [emulator[address] for address in DRIVER_SRAM]
    emulator.run(601)
    assert sum(emulator[address] != before[i] for i, address in enumerate(DRIVER_SRAM)) > 20

    def seconds(console: Emulator) -> int:
        return console[TOTAL_SECONDS] | console[TOTAL_SECONDS + 1] << 8

    played = seconds(emulator)
    assert played >= 10
    emulator.reset()
    emulator.boot_to_file_select()
    emulator.start_game()
    assert seconds(emulator) >= played
    played = seconds(emulator)
    powered_on = Emulator(path)
    for address in BATTERY_RAM:
        powered_on[address] = emulator[address]
    powered_on.boot_to_file_select()
    powered_on.start_game()
    assert seconds(powered_on) >= played


# --- The race flag: Disable Custom Music (docs/design/music-settings.md section 7) ---------------------

RACE_FLAGS = zora_flags.encode(zora_flags.ZoraFlags(disable_custom_music=True))


def test_disable_custom_music_allows_only_off_and_vanilla() -> None:
    """Older strings decode to Off; with it On, both random values are refused, and the game (the
    vanilla-music ROM) is the same seed's as without it: the flag rules only the player settings."""
    assert not zora_flags.decode("").disable_custom_music
    assert not zora_flags.decode(zora_flags.encode(zora_flags.ZoraFlags(pegasus_boots=ThreeState.ON))) \
        .disable_custom_music
    assert zora_flags.decode(RACE_FLAGS).disable_custom_music and zora_flags.game_string(zora_flags.decode(RACE_FLAGS)) == ""
    base = remember_repo_base_rom()
    for music in (Music.RANDOM_STANDARD, Music.RANDOM_LOCAL):
        with pytest.raises(PlayerSettingError, match="Disable Custom Music"):
            generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, base, PlayerSettings(music=music), RACE_FLAGS)
    for music in (Music.ON, Music.OFF):
        raced = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, base, PlayerSettings(music=music), RACE_FLAGS)
        plain = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, base, PlayerSettings(music=music))
        assert raced.rom == plain.rom and raced.zora_flag_string == RACE_FLAGS


# --- The standard library with unsafe tracks, the original tracks mixed in ----------------------------

def test_streaming_safe_only(music_zora_rom: bytes, assets: MusicAssets) -> None:
    unsafe = {song.title for song in library_songs(assets.library, safe_only=False) if not song.streaming_safe}
    safe = randomize_music(music_zora_rom, BASE, assets, SEED)
    assert not unsafe & {place.song.title for place in safe.placed}
    drawn: set[str] = set()
    for seed in range(SEED, SEED + 6):
        full = randomize_music(music_zora_rom, BASE, assets, seed, MusicOptions(safe_only=False))
        drawn |= {place.song.title for place in full.placed}
    assert drawn & unsafe


# --- The local library (docs/design/music-settings.md section 4) ---------------------------------------

def standard_entries(assets: MusicAssets) -> list[dict[str, Any]]:
    """The standard library's single modules, as parsed."""
    return list(json5.loads(assets.library.decode("utf-8-sig"))["single"])


def library_file(name: str, entries: list[dict[str, Any]]) -> LibraryFile:
    return LibraryFile(name, json.dumps({"single": entries}).encode())


def entry(entries: list[dict[str, Any]], title: str) -> dict[str, Any]:
    return next(item for item in entries if item["title"] == title)


@pytest.fixture(scope="module")
def local_library(assets: MusicAssets) -> list[LibraryFile]:
    """Two files cut from the standard library: every use covered, and one title in both."""
    entries = standard_entries(assets)
    first = [entry(entries, title) for title in ("Blue Water Blue Sky", "Castlevania 2 - Bloody Tears",
                                                 "Undertale - Megalovania Somari Style", "bossy.ftm",
                                                 "Dark Castle.ftm", "Moskau.ftm", "Nether's Lament")]
    second = [entry(entries, title) for title in ("Battlemaniacs.ftm", "Descendant of the Archangel", "bossy.ftm")]
    return [library_file("first.json5", first), library_file("second.json5", second)]


def test_a_local_library_is_merged_and_drawn_from(music_zora_rom: bytes, assets: MusicAssets,
                                                  local_library: list[LibraryFile]) -> None:
    options = MusicOptions(source=MusicSource.LOCAL)
    result = randomize_music(music_zora_rom, BASE, assets, SEED, options, local_library)
    titles = {song.title for file in local_library for song in library_songs(file.data, safe_only=False)}
    assert {place.song.title for place in result.placed} <= titles | {ORIGINAL_TITLES[TITLE]}
    assert any("bossy.ftm" in warning and "the first is used" for warning in result.warnings)
    assert result.libraries == tuple((file.name, file.library_id) for file in local_library)
    assert randomize_music(music_zora_rom, BASE, assets, SEED, options, local_library).rom == result.rom
    with pytest.raises(MusicError, match="needs a library"):
        randomize_music(music_zora_rom, BASE, assets, SEED, options, [])


def test_a_bad_local_library_is_refused_naming_the_file(music_zora_rom: bytes, assets: MusicAssets) -> None:
    good = entry(standard_entries(assets), "Moskau.ftm")
    cases = {
        "syntax.json5": (b'{ single: [ { title: "x", data: "hex:00" },, ] }', "line 1"),
        "data.json5": (json.dumps({"single": [{**good, "data": "deflate:not base64!"}]}).encode(), "cannot be read"),
        "short.json5": (json.dumps({"single": [{**good, "data": "hex:0001"}]}).encode(), "cannot be placed"),
    }
    for name, (data, message) in cases.items():
        with pytest.raises(LibraryError, match=message) as refused:
            randomize_music(music_zora_rom, BASE, assets, SEED, MusicOptions(source=MusicSource.LOCAL),
                            [LibraryFile(name, data)])
        assert name in str(refused.value)


# --- Playlists (docs/design/music-settings.md section 5) -----------------------------------------------

def test_a_playlist_pins_its_songs_and_the_rest_is_drawn(music_zora_rom: bytes, assets: MusicAssets) -> None:
    playlist = parse_playlist("""{
      version: 1,
      tracks: {
        title: "Radia Senki - 18 Elfas Castle",   // an overworld track
        level1: "original",
        level2: "Radia Senki - 18 Elfas Castle",  // again, and not tagged for a dungeon
        level3: "random",
        ending: "Radia Senki - 19 Epilogue",
      },
    }""")
    result = randomize_music(music_zora_rom, BASE, assets, SEED, MusicOptions(playlist=playlist))
    by_number = {place.song_number: place.song for place in result.placed}
    assert by_number[AREA_KEYS["title"].song_number].title == "Radia Senki - 18 Elfas Castle"
    assert by_number[AREA_KEYS["level2"].song_number] is by_number[AREA_KEYS["title"].song_number]
    assert by_number[AREA_KEYS["level1"].song_number].is_original
    assert by_number[AREA_KEYS["ending"].song_number].title == "Radia Senki - 19 Epilogue"
    assert any("Level 2" in warning and "not tagged" in warning for warning in result.warnings)
    pinned = {"Radia Senki - 18 Elfas Castle", "Radia Senki - 19 Epilogue"}
    drawn = [song.title for number, song in by_number.items()
             if number not in {AREA_KEYS[key].song_number for key in ("title", "level1", "level2", "ending")}]
    assert len(drawn) == len(set(drawn)) and not pinned & set(drawn)
    lozft = with_lozft(music_zora_rom, assets.patch, BASE)
    level1 = SONG_TABLE + 2 * AREA_KEYS["level1"].song_number
    original_dungeon = SONG_TABLE + 2 * AREA_KEYS["level1"].original_number
    assert result.rom[level1:level1 + 2] == lozft[original_dungeon:original_dungeon + 2]


def test_a_playlist_that_cannot_be_used_is_refused(music_zora_rom: bytes, assets: MusicAssets) -> None:
    unsafe = next(song.title for song in library_songs(assets.library, safe_only=False) if not song.streaming_safe)
    refusals = {
        '{ tracks: { overworld: "No Such Song" } }': "no song",
        '{ tracks: { castle: "original" } }': "no area",
        '{ version: 2, tracks: {} }': "version",
        f'{{ tracks: {{ level1: "{unsafe}" }} }}': "unsafe for streaming",
    }
    for text, message in refusals.items():
        with pytest.raises(PlaylistError, match=message):
            randomize_music(music_zora_rom, BASE, assets, SEED, MusicOptions(playlist=parse_playlist(text)))
    allowed = parse_playlist(f'{{ tracks: {{ level1: "{unsafe}" }} }}')
    result = randomize_music(music_zora_rom, BASE, assets, SEED, MusicOptions(safe_only=False, playlist=allowed))
    assert any(place.song.title == unsafe for place in result.placed)
    songs = library_songs(assets.library, safe_only=False)
    biggest = sorted({id(song.module): song for song in songs if song.module}.values(),
                     key=lambda song: -len(song.module.data) if song.module else 0)
    every_area = {key: song.title for key, song in zip(AREA_KEYS, biggest, strict=False)}
    too_big = parse_playlist(json.dumps({"tracks": every_area}))
    with pytest.raises(RomFull, match="bytes of modules"):
        randomize_music(music_zora_rom, BASE, assets, SEED, MusicOptions(safe_only=False, playlist=too_big))


def test_a_zelda_ii_library_loads_with_its_areas_translated(assets: MusicAssets) -> None:
    """A Zelda II (Z2Randomizer) library's uses become Zelda's areas (ZELDA_II_USES): towns the
    overworld, palaces, caves and encounters the dungeons, the great palace and bosses level 9, the
    credits the ending, its title screen ZORA's Title; a use neither game has (Zelda II's House,
    GameComplete and PalaceClear among them) leaves the song out with a warning."""
    good = entry(standard_entries(assets), "Moskau.ftm")
    uses = {"Town": OVERWORLD, "Palace": DUNGEON, "Cave": DUNGEON, "Encounter": DUNGEON,
            "GreatPalace": LAST_DUNGEON, "Boss": LAST_DUNGEON, "LastBoss": LAST_DUNGEON, "Credits": ENDING,
            "Title": TITLE}
    for zelda_ii, zelda in uses.items():
        [song] = library_songs(library_file("z2.json5", [{**good, "uses": [zelda_ii]}]).data, safe_only=False)
        assert song.uses == {zelda}, zelda_ii
    for other in ("House", "GameComplete", "PalaceClear", "Castle"):
        songs, warnings = read_library(library_file("z2.json5", [{**good, "uses": [other]}]).data, safe_only=False)
        assert songs == [] and warnings == [f"Moskau.ftm: left out, The Legend of Zelda has no area for {other}"]


def test_the_standard_library_reads_without_warnings(assets: MusicAssets) -> None:
    """The pinned standard library: every track's uses are Zelda's, so nothing is left out (its
    Refights uses are commented out)."""
    songs, warnings = read_library(assets.library, safe_only=False)
    assert warnings == [] and songs
    assert all(song.uses <= set(USES) for song in songs)


def test_a_use_zelda_has_no_area_for_is_left_out_with_a_warning(music_zora_rom: bytes, assets: MusicAssets,
                                                                 local_library: list[LibraryFile]) -> None:
    """A use of another game's (the player's report: a Mega Man library's Refights) never stops the
    library: a track that has a Zelda use as well keeps that one, a track with none is left out, and
    the seed is made with the warnings."""
    entries = standard_entries(assets)
    mixed = {**entry(entries, "Moskau.ftm"), "uses": ["Overworld", "Refights"]}
    other_game = {**entry(entries, "Asgore 2A03"), "uses": ["refights"]}
    songs, warnings = read_library(library_file("mixed.json5", [mixed, other_game]).data, safe_only=False)
    assert [(song.title, song.uses) for song in songs] == [("Moskau.ftm", frozenset({OVERWORLD}))]
    assert warnings == ["Moskau.ftm: The Legend of Zelda has no area for Refights; it plays as Overworld only",
                        "Asgore 2A03: left out, The Legend of Zelda has no area for refights"]
    files = [*local_library, library_file("FtSoundTrackConfiguration.json5", [mixed, other_game])]
    result = randomize_music(music_zora_rom, BASE, assets, SEED, MusicOptions(source=MusicSource.LOCAL), files)
    assert "FtSoundTrackConfiguration.json5: Asgore 2A03: left out, The Legend of Zelda has no area for refights" \
        in result.warnings
    assert all(place.song.title != "Asgore 2A03" for place in result.placed)
    listed = music_library_songs(local_libraries=[(file.name, file.data) for file in files])
    songs_listed = listed["songs"]
    assert "error" not in listed and isinstance(songs_listed, list)
    assert "Asgore 2A03" not in {song["title"] for song in songs_listed}


def test_a_library_with_no_track_to_place_is_refused_in_plain_words(music_zora_rom: bytes,
                                                                    assets: MusicAssets) -> None:
    """Files whose every track is another game's (or disabled) cannot give a seed music: refused with
    the reason, by the page's check (music_library_songs) as by generating."""
    only_other = library_file("other.json5", [{**entry(standard_entries(assets), "Asgore 2A03"), "uses": ["Refights"]}])
    with pytest.raises(MusicError, match="no track for The Legend of Zelda's areas"):
        randomize_music(music_zora_rom, BASE, assets, SEED, MusicOptions(source=MusicSource.LOCAL), [only_other])
    error = music_library_songs(local_libraries=[(only_other.name, only_other.data)])["error"]
    assert isinstance(error, str) and "no track" in error


# --- The Title tag (TheGobOne's request for beta 9) --------------------------------------------------

# lozft's driver: the address of the module it plays (its state in the stack page; found by probing
# the title screen and play, it follows the song table's module address for the song playing).
DRIVER_MODULE_ADDRESS = 0x159
DRIVER_STATE = range(0x150, 0x1BA)       # lozft's driver's variables in the stack page
NO_MODULE = 0
TITLE_SCREEN_FRAMES = 40
PLAY_FRAMES = 120
TITLE_TRACK = "Arumana no Kiseki - Level 5 Revisited"
OVERWORLD_TRACKS = ("Blue Water Blue Sky", "Moskau.ftm")


def title_library(assets: MusicAssets, title_uses: list[str] | None) -> LibraryFile:
    """Two overworld tracks and TITLE_TRACK with title_uses (None: its own, a dungeon's)."""
    entries = standard_entries(assets)
    title = entry(entries, TITLE_TRACK)
    return library_file("title.json5", [*({**entry(entries, name), "uses": [OVERWORLD]} for name in OVERWORLD_TRACKS),
                                        title if title_uses is None else {**title, "uses": title_uses}])


def placed_title(result: Any) -> Any:
    return next(place.song for place in result.placed if place.song_number == TITLE_SONG)


def test_the_loader_takes_the_title_tag(assets: MusicAssets) -> None:
    """Title is a use like the importer's (any case, no warning); a use Zelda has no area for is still
    left out with a warning."""
    for spelling in ("Title", "title", "TITLE"):
        songs, warnings = read_library(title_library(assets, [spelling, "Refights"]).data, safe_only=False)
        assert songs[-1].uses == {TITLE}
        assert warnings == [f"{TITLE_TRACK}: The Legend of Zelda has no area for Refights; it plays as Title only"]


def test_the_title_screen_draws_from_title_tracks_else_keeps_the_games_own(music_zora_rom: bytes,
                                                                           assets: MusicAssets) -> None:
    """With a Title track the title screen gets one, and no other area does; with none (every library
    made for the Zelda importer, the standard one included) it keeps the game's own title song, which
    the track list names (TheGobOne's request, 2026-10-25: no overworld track there)."""
    local = MusicOptions(source=MusicSource.LOCAL)
    for seed in range(SEED, SEED + 4):
        tagged = randomize_music(music_zora_rom, BASE, assets, seed, local, [title_library(assets, [TITLE])])
        assert placed_title(tagged).title == TITLE_TRACK
        assert all(place.song.title != TITLE_TRACK for place in tagged.placed if place.song_number != TITLE_SONG)
        both = randomize_music(music_zora_rom, BASE, assets, seed, local, [title_library(assets, [TITLE, OVERWORLD])])
        assert placed_title(both).title == TITLE_TRACK
        untagged = randomize_music(music_zora_rom, BASE, assets, seed, local, [title_library(assets, None)])
        assert placed_title(untagged).is_original
    standard = randomize_music(music_zora_rom, BASE, assets, SEED)
    assert placed_title(standard).is_original
    assert ("Title screen", ORIGINAL_TITLES[TITLE]) in standard.track_list()
    lozft = with_lozft(music_zora_rom, assets.patch, BASE)
    title_entry = SONG_TABLE + 2 * TITLE_SONG
    assert standard.rom[title_entry:title_entry + 2] == lozft[title_entry:title_entry + 2]
    only_title = randomize_music(music_zora_rom, BASE, assets, SEED, local,
                                 [library_file("only.json5", [{**entry(standard_entries(assets), TITLE_TRACK),
                                                               "uses": [TITLE]}])])
    assert [place.song.title for place in only_title.placed] == [TITLE_TRACK]     # the other areas keep the ROM's


def test_a_playlist_takes_a_title_track_for_the_title_screen(music_zora_rom: bytes, assets: MusicAssets) -> None:
    """A Title track pinned to the title screen is tagged for it; an Overworld one, or a Title track
    pinned to a level, is not (warned, and placed). The editor's title screen lists Title alone."""
    playlist = parse_playlist(f'{{ tracks: {{ title: "{TITLE_TRACK}", level1: "{TITLE_TRACK}", '
                              f'overworld: "{OVERWORLD_TRACKS[0]}" }} }}')
    result = randomize_music(music_zora_rom, BASE, assets, SEED,
                             MusicOptions(source=MusicSource.LOCAL, playlist=playlist),
                             [title_library(assets, [TITLE])])
    assert [warning for warning in result.warnings if "not tagged" in warning] == \
        [f"Level 1: {TITLE_TRACK} is not tagged for this area"]
    overworld_title = parse_playlist(f'{{ tracks: {{ title: "{OVERWORLD_TRACKS[0]}" }} }}')
    pinned = randomize_music(music_zora_rom, BASE, assets, SEED,
                             MusicOptions(source=MusicSource.LOCAL, playlist=overworld_title),
                             [title_library(assets, [TITLE])])
    assert pinned.warnings == (f"Title screen: {OVERWORLD_TRACKS[0]} is not tagged for this area",)
    assert placed_title(pinned).title == OVERWORLD_TRACKS[0]
    listed = music_playlist_areas()["areas"]
    assert isinstance(listed, list)
    areas = {area["key"]: area["uses"] for area in listed}
    assert areas["title"] == [TITLE] and areas["overworld"] == [OVERWORLD]


def playing(emulator: "Emulator") -> int:
    """The address of the module lozft's driver plays."""
    return emulator[DRIVER_MODULE_ADDRESS] | emulator[DRIVER_MODULE_ADDRESS + 1] << 8


def module_address(rom: bytes, song_number: int) -> int:
    entry_offset = MODULE_ADDRESSES + 2 * song_number
    return rom[entry_offset] | rom[entry_offset + 1] << 8


def test_the_title_screen_plays_the_title_track_in_the_emulator(music_zora_rom: bytes, assets: MusicAssets) -> None:
    """Powered on, the title screen plays song 7's module, the Title track's, and in play the driver
    moves to the overworld's module; with no Title track it plays the game's own title song (no
    module, the driver as lozft alone has it)."""
    from tests.emulator import Emulator
    local = MusicOptions(source=MusicSource.LOCAL)
    for uses in ([TITLE], None):
        result = randomize_music(music_zora_rom, BASE, assets, SEED, local, [title_library(assets, uses)])
        assert (placed_title(result).title == TITLE_TRACK) is (uses is not None)
        emulator = Emulator(result.rom)
        emulator.run(TITLE_SCREEN_FRAMES)
        if uses is None:
            alone = Emulator(bytes(with_lozft(music_zora_rom, assets.patch, BASE)))
            alone.run(TITLE_SCREEN_FRAMES)
            assert playing(emulator) == NO_MODULE
            assert [emulator[address] for address in DRIVER_STATE] == [alone[address] for address in DRIVER_STATE]
        else:
            assert playing(emulator) == module_address(result.rom, TITLE_SONG)
            assert playing(emulator) != module_address(result.rom, AREA_SONGS[OVERWORLD][0])
            emulator.new_game()
            emulator.run(PLAY_FRAMES)
            assert playing(emulator) == module_address(result.rom, AREA_SONGS[OVERWORLD][0])
