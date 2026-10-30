"""Link sprite sets (features-behavior.md FP-LINK-01, FP-LINK-02; zora/rom/link_sprite.py): the
file format and its refusals, the page's check against Python's, and FP-LINK-02's Check: a set's
640 bytes land on Link's six groups, every other byte is the output with PRG0's Link, the seed's
code is the same, and Random picks PRG0's Link, a built-in set or the player's set by the
seed. Generation and every patch
leave the groups alone; so does randomized music (lozft)."""
import base64
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.needs import needs_base_rom
from zora.flags.form import metadata
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.rom.base_rom import PRG1_ROM_PATH, remember_repo_base_rom
from zora.rom.code_patches import seed_code
from zora.rom.link_art import LinkSpriteSet, offered_sprite_sets
from zora.rom.link_sprite import (
    LINK_TILE_GROUPS,
    SPRITE_SET_SIZE,
    TILE_SIZE,
    SpriteSet,
    SpriteSetError,
    built_in_sprite_sets,
    link_tile_offsets,
    link_tiles,
    sprite_set_file,
    sprite_set_from_file,
    sprite_set_object,
)
from zora.rom.player_settings import (
    LinkSprite,
    PlayerSettingError,
    PlayerSettings,
    apply_player_settings,
    player_settings_from_page,
    resolved_player_settings,
)

REPO = Path(__file__).resolve().parent.parent
PAGE_SCRIPT = (REPO / "web" / "zora-web.js").read_text()
CP5 = MVP_BASELINE_LEVEL_ENCODING_OFF          # the spec's CP-5 string
# FP-LINK-02's test set: 640 bytes of any content
TEST_SET = SpriteSet("Test set", "ZORA tests", "Made for this test; anyone may use it.",
                     bytes((i * 7 + 3) % 256 for i in range(SPRITE_SET_SIZE)))


# A built-in set with color 1 as art and bytes from the game (fromGame)
KRAID = built_in_sprite_sets()["zeromeaning-kraid"]


def with_set(choice: LinkSprite = LinkSprite.SET) -> PlayerSettings:
    return PlayerSettings(link_sprite=choice, sprite_set=TEST_SET)


def test_the_groups_are_fp_link_01s() -> None:
    """The six groups in the table's order: 40 tiles, 640 bytes, the spec's file offsets."""
    assert [(offset, offset + tiles * TILE_SIZE - 1) for offset, tiles in LINK_TILE_GROUPS] == [
        (0x808F, 0x824E), (0x4E44, 0x4E63), (0x4EC4, 0x4EE3), (0x85CF, 0x85EE), (0x860F, 0x864E), (0x868F, 0x86AE)]
    assert SPRITE_SET_SIZE == 640 == len(link_tile_offsets())


def test_the_file_reads_back() -> None:
    assert sprite_set_from_file(sprite_set_file(TEST_SET)) == TEST_SET
    data = json.loads(sprite_set_file(TEST_SET))
    assert data == {"format": "zora-link-sprite-set", "version": 1, "name": "Test set", "author": "ZORA tests",
                    "provenance": TEST_SET.provenance, "tiles": base64.b64encode(TEST_SET.tiles).decode()}


def set_file(**changes: object) -> str:
    return json.dumps({**sprite_set_object(TEST_SET), **changes})


REFUSED = {
    "639 bytes": set_file(tiles=base64.b64encode(bytes(639)).decode()),
    "641 bytes": set_file(tiles=base64.b64encode(bytes(641)).decode()),
    "an empty author": set_file(author=" "),
    "no name": set_file(name=""),
    "no tiles": set_file(tiles=None),
    "tiles not base64": set_file(tiles="not base64!"),
    "another format": set_file(format="something else"),
    "a later version": set_file(version=2),
    "not an object": "[]",
    "not JSON": "{",
    "color 1 neither clothing nor art": set_file(recommendedColors={"tunics": [41, 50, 22], "other": [39, 23],
                                                                    "colorOne": "skin"}),
    "fromGame not pairs": set_file(fromGame=[[0, 8, 16]]),
    "fromGame out of order": set_file(tiles=base64.b64encode(bytes(SPRITE_SET_SIZE)).decode(),
                                      fromGame=[[16, 32], [0, 8]]),
    "fromGame past the end": set_file(tiles=base64.b64encode(bytes(SPRITE_SET_SIZE)).decode(),
                                      fromGame=[[632, 648]]),
    "fromGame over art": set_file(fromGame=[[0, 8]]),         # the test set's bytes there are not zeros
}


@pytest.mark.parametrize("case", list(REFUSED))
def test_a_wrong_set_is_refused_with_a_message(case: str) -> None:
    with pytest.raises(SpriteSetError) as refused:
        sprite_set_from_file(REFUSED[case])
    assert str(refused.value)


def test_the_page_refuses_what_python_refuses() -> None:
    """The page's checkedLinkSpriteSet, run in Node on the same files, refuses each with the same
    message (but "not JSON", which the page's file reader catches before it) and keeps a good one."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    start = PAGE_SCRIPT.index("class LinkSpriteSetError")
    end = PAGE_SCRIPT.index("function loadLinkSpriteSet")
    cases = {case: text for case, text in REFUSED.items() if case != "not JSON"}
    # the palette's size and the color it never offers, which the set's colors are checked against
    script = "const NES_PALETTE = new Array(64), BLACKER_THAN_BLACK = 13;\n" + PAGE_SCRIPT[start:end] + f"""
const rule = {json.dumps(metadata()["linkSpriteSet"])};
const out = {{}};
for (const [name, text] of Object.entries({json.dumps(cases)})) {{
  try {{ checkedLinkSpriteSet(JSON.parse(text), rule); out[name] = null; }}
  catch (err) {{ out[name] = err.message; }}
}}
out.good = checkedLinkSpriteSet(JSON.parse({json.dumps(sprite_set_file(TEST_SET))}), rule);
out.kraid = checkedLinkSpriteSet(JSON.parse({json.dumps(sprite_set_file(KRAID))}), rule);
console.log(JSON.stringify(out));"""
    found = json.loads(subprocess.run([node, "-e", script], capture_output=True, text=True, check=True).stdout)
    for case, text in cases.items():
        with pytest.raises(SpriteSetError) as refused:
            sprite_set_from_file(text)
        assert found[case] == str(refused.value), case
    assert sprite_set_from_file(json.dumps(found["good"])) == TEST_SET
    assert sprite_set_from_file(json.dumps(found["kraid"])) == KRAID      # colorOne and fromGame kept


def test_the_page_sends_the_set_with_the_choice() -> None:
    page = {"linkSprite": "set", "linkSpriteSet": sprite_set_object(TEST_SET)}
    assert player_settings_from_page(page) == with_set()
    with pytest.raises(PlayerSettingError, match="needs a sprite set"):
        player_settings_from_page({"linkSprite": "set"})
    assert player_settings_from_page({"linkSprite": "random"}).link_sprite is LinkSprite.RANDOM     # the built-ins
    with pytest.raises(PlayerSettingError, match="exactly 640 bytes"):
        player_settings_from_page({**page, "linkSpriteSet": {**sprite_set_object(TEST_SET), "tiles": ""}})


def random_choices(settings: PlayerSettings) -> list[LinkSpriteSet | None]:
    """Random resolved for seeds 1 to 300 (27 choices): each seed's set, None for PRG0's Link."""
    resolved = [resolved_player_settings(settings, seed) for seed in range(1, 301)]
    assert all((choice.link_sprite is LinkSprite.LINK) == (choice.sprite_set is None) for choice in resolved)
    return [choice.sprite_set for choice in resolved]


def test_random_picks_link_a_built_in_set_or_the_players_by_the_seed() -> None:
    """FP-LINK-02's Random over seeds 1 to 300: PRG0's Link, each built-in set (built-in art included,
    link_art.offered_sprite_sets) and the player's set
    all occur, and a seed gives the same twice; without a set of the player's, Link and the built-ins."""
    built_in = list(offered_sprite_sets().values())
    chosen = random_choices(with_set(LinkSprite.RANDOM))
    assert set(map(id, chosen)) == set(map(id, [None, *built_in, TEST_SET]))
    assert chosen == random_choices(with_set(LinkSprite.RANDOM))
    without = random_choices(PlayerSettings(link_sprite=LinkSprite.RANDOM))
    assert set(map(id, without)) == set(map(id, [None, *built_in]))


def check_set_on(rom: bytes) -> None:
    """FP-LINK-02's Check on one finished ROM: the groups equal the set, every other byte the output
    with PRG0's Link, and the seed's code the same."""
    link = apply_player_settings(rom, PlayerSettings())
    styled = apply_player_settings(rom, with_set())
    assert link_tiles(styled) == TEST_SET.tiles
    groups = link_tile_offsets()
    assert all(styled[i] == link[i] for i in range(len(rom)) if i not in groups)
    assert seed_code(styled) == seed_code(link)


@needs_base_rom
@pytest.mark.parametrize("seed", [1, 2])
def test_the_set_lands_on_links_groups_and_nowhere_else(seed: int) -> None:
    check_set_on(generate_rom(CP5, seed, remember_repo_base_rom()).rom)


@pytest.mark.slow
@needs_base_rom
def test_the_spec_check_over_seeds_1_to_10() -> None:
    for seed in range(1, 11):
        check_set_on(generate_rom(CP5, seed, remember_repo_base_rom()).rom)


@pytest.mark.skipif(not PRG1_ROM_PATH.exists(), reason="needs the PRG1 ROM")
def test_a_prg1_base_takes_the_same_writes() -> None:
    base = PRG1_ROM_PATH.read_bytes()
    rom = generate_rom(CP5, 3, base).rom
    assert link_tiles(rom) == link_tiles(base)          # generation leaves them as the player's ROM has them
    check_set_on(rom)


@needs_base_rom
def test_random_writes_what_its_choice_writes() -> None:
    rom = generate_rom(CP5, 5, remember_repo_base_rom()).rom
    chosen = resolved_player_settings(with_set(LinkSprite.RANDOM), 5)
    assert apply_player_settings(rom, with_set(LinkSprite.RANDOM)) == apply_player_settings(rom, chosen)


@pytest.mark.slow
@needs_base_rom
def test_randomized_music_keeps_the_set() -> None:
    """lozft takes its bytes from the player's own ROM and keeps the finished ROM's elsewhere: the
    set's groups survive Music: Random (standard library)."""
    from scripts.music_assets import assets_available, pinned_assets
    from zora.rom.music.randomize import randomize_music
    if not assets_available():
        pytest.skip("the music assets are not here")
    from zora.rom.player_settings import Music
    base = remember_repo_base_rom()
    settings = PlayerSettings(music=Music.RANDOM_STANDARD, link_sprite=LinkSprite.SET, sprite_set=TEST_SET)
    rom = generate_rom(CP5, 21, base, settings).rom
    assert link_tiles(randomize_music(rom, base, pinned_assets(), 21).rom) == TEST_SET.tiles
