"""The release's Archipelago world (scripts/make_release.py, docs/releasing.md): release/allowlist.txt
ships the world (archipelago/) and its two scripts, so the commit-time scan (scripts/release_scan.py)
reads them; each release builds zora.apworld for its GitHub release, with notes naming the world's
version, ZORA's version and the source hash; the page links that asset, tagged v<ZORA_VERSION> as
every earlier release is.
"""
import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from zora.version import PLAYER_VERSION, ZORA_VERSION
from zora_web import multiworld

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
WORLD_FILES = ("archipelago/__init__.py", "archipelago/archipelago.json", "archipelago/test/test_world.py",
               "scripts/build_apworld.py", "scripts/check_apworld.py")

# a release leaves out make_release.py and the scan (release/allowlist.txt)
needs_release_scripts = pytest.mark.skipif(
    not ((SCRIPTS / "make_release.py").exists() and (SCRIPTS / "release_scan.py").exists()),
    reason="no release scripts here")


def _script(name: str) -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module                          # its dataclasses look their module up
    spec.loader.exec_module(module)
    return module


def _tracked() -> list[str]:
    return subprocess.run(["git", "-C", str(REPO), "ls-files"], capture_output=True, text=True,
                          check=True).stdout.splitlines()


@needs_release_scripts
def test_the_world_and_its_scripts_ship_and_are_scanned() -> None:
    make_release = _script("make_release")
    tracked = _tracked()
    if "archipelago/__init__.py" not in tracked:
        pytest.skip("no Archipelago world in this checkout")
    shipped = make_release.selected(tracked, make_release.read_allowlist())
    scanned = {path for path, _text in _script("release_scan").released_texts(REPO)}
    for path in WORLD_FILES:
        assert shipped.get(path) == path
        assert path in scanned, path


def test_the_page_links_its_own_versions_world() -> None:
    """The GitHub release asset of this version's tag (v2.0.0b4 for 2.0 beta 4, as published)."""
    assert multiworld.release_tag("2.0.0b4") == "v2.0.0b4"
    url = f"https://github.com/tetraly/zora/releases/download/v{ZORA_VERSION}/zora.apworld"
    assert multiworld.apworld_url() == url
    assert multiworld.metadata()["apworldUrl"] == url
    page = (REPO / "web" / "zora-web.js").read_text()
    assert "metadata.multiworld.apworldUrl" in page
    assert "const APWORLD_URL" not in page


@needs_release_scripts
def test_the_release_notes_name_the_worlds_versions_and_source_hash(tmp_path: Path,
                                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    make_release = _script("make_release")
    monkeypatch.setattr(make_release, "ASSETS", tmp_path)
    world = {"world version": "1.2.3", "ZORA version": ZORA_VERSION, "source hash": "ab" * 32, "sha256": "cd" * 32}
    notes = make_release.write_release_notes(world, "2026-10-13").read_text()
    for line in (f"- world version: {world['world version']}", f"- ZORA version: {ZORA_VERSION}",
                 f"- source hash: {world['source hash']}", f"- SHA-256 of zora.apworld: {world['sha256']}"):
        assert line in notes.splitlines()
    assert f"## {PLAYER_VERSION}" not in notes            # the version is the GitHub release's title
    assert "Unreleased" not in notes


@needs_release_scripts
def test_the_github_release_command_attaches_the_world() -> None:
    make_release = _script("make_release")
    tag = multiworld.release_tag()
    command = make_release.github_release_command(tag, make_release.ASSETS / "release-notes.md")
    assert command.startswith(f"gh release create {tag} {make_release.ASSETS / 'zora.apworld'} --repo tetraly/zora")
    assert f'--title "ZORA {PLAYER_VERSION}"' in command
    assert ("--prerelease" in command) == (PLAYER_VERSION != ZORA_VERSION)
