"""scripts/build_site.py: the private build's packed module behaves as the
private module, carries none of its readable strings, and the build only
writes into a git-ignored folder. No wheel is built here (see
docs/site-build.md for the full build and its checks)."""
import importlib.util
import json
import random
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

from zora.rom import level_encoding
from zora.version import PLAYER_VERSION

REPO = Path(__file__).resolve().parent.parent


def _build_site() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_site", REPO / "scripts" / "build_site.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_site = _build_site()
needs_private = pytest.mark.skipif(not level_encoding.is_available() or not build_site.PRIVATE_PACKAGE.is_dir(),
                                   reason="the private level-encoding module is not installed")


@pytest.fixture(scope="module")
def minified() -> str:
    pytest.importorskip("python_minifier")
    return str(build_site.minified_source())


@needs_private
def test_packed_module_matches_the_private_module(minified: str) -> None:
    name = "packed_for_test.encoder"
    exec(build_site.loader_code(build_site.pack(minified), name), {})
    try:
        packed = sys.modules[name]
        private = level_encoding.require_available()
        rom = bytes(random.Random(7).randrange(256) for _ in range(131088))
        for seed, settings in ((1, b"8hq4"), (2**63, "flags".encode())):
            encoded = packed.apply(rom, seed, settings)
            assert encoded == private.apply(rom, seed, settings)
            assert packed.decode_level_data(encoded, seed, settings) == private.decode_level_data(
                encoded, seed, settings)
        assert packed.ALLOWED_RANGES == private.ALLOWED_RANGES
    finally:
        for module in [m for m in sys.modules if m == "packed_for_test" or m.startswith("packed_for_test.")]:
            del sys.modules[module]


@needs_private
def test_packed_blob_has_no_private_strings(minified: str) -> None:
    blob = build_site.loader_code(build_site.pack(minified))
    strings = build_site.private_strings()
    assert any("level encoding" in text for text in strings)       # the check sees the key's domain
    # The module's import path is public (zora/rom/level_encoding.py), as in the real build.
    public = {"interface": (REPO / "zora" / "rom" / "level_encoding.py").read_text()}
    _, hits = build_site.grep_check({"worker": blob}, public, strings)
    assert hits == []
    # The control: the merged source, unpacked, is caught.
    _, hits = build_site.grep_check({"leak": build_site.merged_source()}, {}, strings)
    assert len(hits) > 50


@needs_private
def test_minified_source_drops_docstrings_and_comments(minified: str) -> None:
    for path in build_site.PRIVATE_PACKAGE.glob("*.py"):
        for line in build_site._comment_lines(path.read_text()):
            if len(line) >= build_site.MIN_STRING_LENGTH:
                assert line not in minified
    assert '"""' not in minified


def test_with_private_but_no_checkout_fails_clearly(tmp_path: Path) -> None:
    with pytest.raises(build_site.BuildError, match="needs the owner's private checkout"):
        build_site.require_private(tmp_path / "level_encoding")


@pytest.mark.parametrize("out", ["web/out", "docs", ".", "../elsewhere"])
def test_output_must_be_an_ignored_folder_in_the_repo(out: str) -> None:
    with pytest.raises(build_site.BuildError):
        build_site.check_output_folder(REPO / out)


def test_default_outputs_are_ignored() -> None:
    for out in (build_site.DEFAULT_PUBLIC_OUT, build_site.DEFAULT_PRIVATE_OUT):
        assert build_site.check_output_folder(out) == out


def test_worker_has_the_glue_anchor_once() -> None:
    assert (REPO / "web" / build_site.WORKER).read_text().count(build_site.GLUE_ANCHOR) == 1


# --- the single-file beta -----------------------------------------------------

def _fake_site(root: Path, worker: str = "const GLUE = `\n`;\n") -> Path:
    """A staged site in miniature: the real index.html and fonts.css, stub
    scripts and stylesheets, a font and a one-member wheel."""
    import zipfile
    (root / "fonts").mkdir()
    (root / "dist").mkdir()
    (root / "index.html").write_text((REPO / "web" / "index.html").read_text())
    (root / "fonts.css").write_text((REPO / "web" / "fonts.css").read_text())
    for name in ("style.css", "style-extras.css", "zora.css"):
        (root / name).write_text(f"/* {name} */ body {{ color: black; }}\n")
    for name in ("widgets.js", "zora-web.js"):
        (root / name).write_text(f"// {name}\n")
    (root / build_site.WORKER).write_text(worker)
    for path in (REPO / "web" / "fonts").glob("*.woff2"):
        (root / "fonts" / path.name).write_bytes(b"woff2 " + path.name.encode())
    (root / build_site.FONT_LICENSE).write_text("SIL OPEN FONT LICENSE Version 1.1\n")
    (root / build_site.FLAG_TABS).write_text((REPO / "web" / build_site.FLAG_TABS).read_text())
    with zipfile.ZipFile(root / build_site.WHEEL_PATH, "w") as wheel:
        wheel.writestr("zora/__init__.py", "MARKER = 'in the wheel'\n")
    return root


def test_single_file_inlines_everything(tmp_path: Path) -> None:
    page = build_site.single_file_html(_fake_site(tmp_path), "beta test")
    assert "<link" not in page and '<script src=' not in page
    assert "fonts/" not in page.replace(build_site.FONT_LICENSE, "")
    assert page.count("data:font/woff2;base64,") == 3
    assert "/* zora.css */" in page and "// zora-web.js" in page
    assert "SIL OPEN FONT LICENSE" in page
    assert '{"label": "beta test"}' in page
    # web/flag-tabs.json, so the tabs work opened from disk
    tabs = re.search(f'<script type="application/json" id="{build_site.EMBEDDED_FLAG_TABS_ID}">([^<]*)</script>', page)
    assert tabs and json.loads(tabs.group(1)) == json.loads((REPO / "web" / build_site.FLAG_TABS).read_text())
    # The embedded elements come before the scripts that read them.
    assert page.index(build_site.EMBEDDED_WHEEL_ID) < page.index("// zora-web.js")
    texts = build_site.single_file_texts("beta.html", page)
    assert "in the wheel" in texts["beta.html!zora/__init__.py"]


def test_single_file_refuses_an_end_tag_inside_a_script(tmp_path: Path) -> None:
    site = _fake_site(tmp_path, worker="const x = '</script>';\n")
    with pytest.raises(build_site.BuildError, match="cannot be inlined"):
        build_site.single_file_html(site, "beta test")


def test_page_reads_the_embedded_ids() -> None:
    page_script = (REPO / "web" / "zora-web.js").read_text()
    for element_id in (build_site.EMBEDDED_INFO_ID, build_site.EMBEDDED_WORKER_ID, build_site.EMBEDDED_WHEEL_ID,
                       build_site.EMBEDDED_FLAG_TABS_ID):
        assert f'"{element_id}"' in page_script


def test_beta_output_is_ignored() -> None:
    assert build_site.check_output_folder(build_site.BETA_OUT) == build_site.BETA_OUT


def test_version_label_names_the_version_and_commit() -> None:
    label, slug = build_site.version_label()
    commit = build_site._git("rev-parse", "--short", "HEAD")
    assert label.startswith(f"v{PLAYER_VERSION} 20") and commit in label
    assert slug.startswith(f"{PLAYER_VERSION.replace(' ', '-')}-20") and f"-{commit}" in slug and " " not in slug


# --- the robots tag --------------------------------------------------------------

def test_noindex_is_opt_in(tmp_path: Path) -> None:
    """The robots tag only with --noindex (no published page uses it since 2026-10-07; publish_site.sh builds without it), the single file included."""
    source = (REPO / "web" / "index.html").read_text()
    plain = build_site.marked_page(source)
    assert plain == source
    hidden = build_site.marked_page(source, noindex=True)
    assert "<head>\n" + build_site.ROBOTS_NOINDEX in hidden
    site = _fake_site(tmp_path)
    (site / "index.html").write_text(hidden)
    page = build_site.single_file_html(site, "beta test")
    assert page.count(build_site.ROBOTS_NOINDEX) == 1
    with pytest.raises(build_site.BuildError, match="doctype"):
        build_site.marked_page("<html></html>")
