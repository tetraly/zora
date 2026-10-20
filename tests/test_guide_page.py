"""The Archipelago guide page (scripts/guide_page.py; docs/site-build.md "The Archipelago guide"):
docs/archipelago-guide.md rendered at build time into archipelago-guide.html beside the generator,
staged by web/stage.sh, written as one file by scripts/build_site.py --single-file and published by
scripts/publish_site.sh; the generator's multiworld steps link it, single-player mode shows neither
link. The renderer is tested on a stub (the guide's text is its author's and changes)."""
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parent.parent
GUIDE = REPO / "docs" / "archipelago-guide.md"
PAGE = (REPO / "web" / "index.html").read_text()
PAGE_SCRIPT = (REPO / "web" / "zora-web.js").read_text()

STUB = """# Playing ZORA in Archipelago

A short stub of the guide.

## 1. What you need

- **Archipelago 0.6.8**, from its
  [releases page](https://github.com/ArchipelagoMW/Archipelago/releases).
- **Your own ROM.** Either US release works:
  - the first release (PRG0);
  - the second release (PRG1).

  Other versions aren't recognized.

## 2. Install the ZORA world

1. Open the **Archipelago Launcher**.
2. Click **Install APWorld** and choose `zora.apworld`.

| File | What it is |
|---|---|
| `<your name>.yaml` | Your settings. |

### Good to know

**The client says "No handler was found
for this game".**
An *answer*, with <b>no</b> raw HTML.
"""


def _script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module                          # its dataclasses look their module up
    spec.loader.exec_module(module)
    return module


guide_page = _script("guide_page")


# --- the renderer -------------------------------------------------------------------------------

def test_the_stub_renders_every_construct_the_guide_uses() -> None:
    guide = guide_page.render(STUB)
    assert guide.title == "Playing ZORA in Archipelago"
    body = guide.body
    assert '<h2 id="1-what-you-need">1. What you need</h2>' in body
    assert '<h3 id="good-to-know">Good to know</h3>' in body
    assert ('<li><strong>Archipelago 0.6.8</strong>, from its <a href="https://github.com/ArchipelagoMW/'
            'Archipelago/releases">releases page</a>.</li>') in body
    # a nested list and a continuation paragraph stay inside their item
    assert re.search(r"<li><strong>Your own ROM\.</strong> Either US release works:<ul>\n<li>the first release "
                     r"\(PRG0\);</li>\n<li>the second release \(PRG1\)\.</li>\n</ul>\n<p>Other versions aren't "
                     r"recognized\.</p>\n</li>", body)
    assert "<ol>\n<li>Open the <strong>Archipelago Launcher</strong>.</li>" in body
    assert "<td><code>&lt;your name&gt;.yaml</code></td><td>Your settings.</td>" in body
    # a bold question over two lines, then its answer on the next
    assert ('<p><strong>The client says "No handler was found for this game".</strong><br>\n'
            "An <em>answer</em>, with &lt;b&gt;no&lt;/b&gt; raw HTML.</p>") in body
    assert [(heading.level, heading.anchor) for heading in guide.headings] == [
        (2, "1-what-you-need"), (2, "2-install-the-zora-world"), (3, "good-to-know")]


@pytest.mark.parametrize("source, problem", [
    ("No title\n", "must start with its title"),
    ("# One\n\n# Two\n", "more than one"),
    ("# Title\n\n[click](javascript:alert(1))\n", "only http"),
])
def test_the_renderer_refuses(source: str, problem: str) -> None:
    with pytest.raises(guide_page.GuideError, match=problem):
        guide_page.render(source)


def test_the_page_is_the_sites() -> None:
    """The site's stylesheets and theme toggle, its title, Contents from the "## " headings, and a
    way back to the generator."""
    page = guide_page.page(STUB)
    assert page.startswith("<!doctype html>\n")
    assert '<link rel="stylesheet" href="fonts.css">' in page and '<link rel="stylesheet" href="zora.css">' in page
    assert '<script src="widgets.js"></script>' in page and "initThemeToggle();" in page
    assert "<title>Playing ZORA in Archipelago | ZORA</title>" in page
    assert '<li><a href="#1-what-you-need">1. What you need</a></li>' in page
    assert 'href="#good-to-know"' not in page                       # Contents lists "## " only
    assert page.count('href="./"') == 3                             # wordmark, nav, "Back to ZORA"


@pytest.mark.skipif(not GUIDE.exists(), reason="docs/archipelago-guide.md is not here yet")
def test_the_real_guide_renders_and_its_contents_resolve() -> None:
    page = guide_page.page(GUIDE.read_text())
    ids = set(re.findall(r'id="([^"]+)"', page))
    targets = re.findall(r'href="#([^"]+)"', page)
    assert targets and set(targets) <= ids


# --- the site -----------------------------------------------------------------------------------

def test_the_site_stages_the_guide() -> None:
    stage = (REPO / "web" / "stage.sh").read_text()
    assert 'python3 scripts/guide_page.py docs/archipelago-guide.md "$out/archipelago-guide.html"' in stage


# a release leaves out release/ and publish_site.sh (release/allowlist.txt)
RELEASE_ONLY = (REPO / "release" / "allowlist.txt", REPO / "scripts" / "publish_site.sh",
                REPO / "scripts" / "gh_pages_commit.sh")


@pytest.mark.skipif(not all(path.exists() for path in RELEASE_ONLY), reason="no release list or publish script here")
def test_the_release_ships_and_the_site_publishes_the_guide() -> None:
    allowlist = (REPO / "release" / "allowlist.txt").read_text().splitlines()
    assert "docs/archipelago-guide.md" in allowlist and "scripts/guide_page.py" in allowlist
    publish = (REPO / "scripts" / "publish_site.sh").read_text()
    assert "docs/archipelago-guide.md" in publish.split("dirty=")[1].splitlines()[0]
    commit_step = (REPO / "scripts" / "gh_pages_commit.sh").read_text()
    assert '--cacheinfo "100644,$guide_blob,archipelago-guide.html"' in commit_step


def test_the_single_file_guide_inlines_its_styles(tmp_path: Path) -> None:
    build_site = _script("build_site")
    for name in ("fonts.css", "zora.css", "widgets.js"):
        shutil.copyfile(REPO / "web" / name, tmp_path / name)
    (tmp_path / "fonts").mkdir()
    for path in (REPO / "web" / "fonts").glob("*.woff2"):
        (tmp_path / "fonts" / path.name).write_bytes(b"woff2 " + path.name.encode())
    (tmp_path / build_site.FONT_LICENSE).write_text("SIL OPEN FONT LICENSE Version 1.1\n")
    (tmp_path / build_site.GUIDE_PAGE).write_text(guide_page.page(STUB))
    page = build_site.single_file_guide(tmp_path)
    assert "<link" not in page and "<script src=" not in page
    assert page.count("data:font/woff2;base64,") == 3 and "SIL OPEN FONT LICENSE" in page
    assert ".guide-body" in page and "function initThemeToggle" in page
    (tmp_path / build_site.GUIDE_PAGE).write_text(guide_page.page(STUB).replace('href="./"', 'href="index.html"'))
    with pytest.raises(build_site.BuildError, match="local references"):
        build_site.single_file_guide(tmp_path)


# --- the generator's links ----------------------------------------------------------------------

WIDGETS_SCRIPT = (REPO / "web" / "widgets.js").read_text()


def _guide_links(protocol: str, channel: str = "regular") -> dict[str, str]:
    """showWorldLinks run on a stubbed page of CHANNEL: where each guide link points (on the test
    channel, the zora.apworld and notes links too)."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    names = "SITE_URL|CHANNEL_URL|GUIDE_PAGE|TEST_CHANNEL_ASSETS|besideThisPage|ARCHIPELAGO_GUIDE_URL"
    constants = "\n".join(line for line in PAGE_SCRIPT.splitlines() if re.match(rf"const ({names}) =", line))
    channels = "\n".join(line for line in WIDGETS_SCRIPT.splitlines()
                          if re.match(r"const (REGULAR_CHANNEL|TEST_CHANNEL) =", line))
    functions = [re.search(rf"^function {name}\(.*?^}}\n", PAGE_SCRIPT, re.MULTILINE | re.DOTALL)
                 for name in ("element", "showWorldLinks")]
    assert all(functions) and constants.count("const ") == 6 and channels.count("const ") == 2
    prelude = (f"const location = {{ protocol: {json.dumps(protocol)} }};\n{channels}\n"
               f"const PAGE_CHANNEL = {json.dumps(channel)};")
    harness = """
const metadata = null;
const nodes = {};
const $ = (id) => (nodes[id] ||= { replaceChildren(...children) { this.children = children; } });
const document = { createElement: (tag) => ({ tag, append() {} }) };
showWorldLinks();
const world = nodes["apworld-link"] ? nodes["apworld-link"].children.filter((child) => child.href).map((a) => a.href) : [];
console.log(JSON.stringify({ world: nodes["guide-link"].children[0].href, export: nodes["export-guide-link"].href,
                             ...(world.length ? { apworld: world } : {}) }));
"""
    source = "\n".join([prelude, constants, *(match.group(0) for match in functions if match), harness])
    shown: dict[str, str] = json.loads(subprocess.run([node, "-e", source], capture_output=True, text=True,
                                                      check=True).stdout)
    return shown


def test_both_multiworld_steps_link_the_guide() -> None:
    assert _guide_links("https:") == {"world": "archipelago-guide.html", "export": "archipelago-guide.html"}
    # A single file opened from disk has no guide beside it: the site's
    site_guide = "https://zora.gg/archipelago-guide.html"
    assert _guide_links("file:") == {"world": site_guide, "export": site_guide}


def test_the_test_channel_links_its_own_guide_world_and_notes() -> None:
    """docs/releasing.md "Channels": beside the page under /test/ (no GitHub release before promotion);
    opened from disk, the test channel's on the site."""
    assert _guide_links("https:", "test") == {"world": "archipelago-guide.html", "export": "archipelago-guide.html",
                                              "apworld": ["zora.apworld", "zora-apworld-notes.txt"]}
    test_site = "https://zora.gg/test/"
    assert _guide_links("file:", "test") == {
        "world": test_site + "archipelago-guide.html", "export": test_site + "archipelago-guide.html",
        "apworld": [test_site + "zora.apworld", test_site + "zora-apworld-notes.txt"]}


def test_the_links_sit_in_the_multiworld_steps_only() -> None:
    """The world step's "Setup guide" row and the export card's "Next:" line; single-player mode
    hides both steps (setMode), so it is unchanged."""
    world_step = PAGE[PAGE.index('id="step-apworld"'):PAGE.index('id="step-rom"')]
    assert '<dd id="guide-link">' in world_step
    export_card = PAGE[PAGE.index('id="export-result"'):PAGE.index("</main>")]
    assert re.search(r'<p class="guide-next" id="export-guide">Next: see the <a id="export-guide-link"[^>]*>Archipelago'
                     r"\s+guide</a> for how to generate and join a game\.</p>", export_card)
    assert PAGE.count("guide-link") == 2 and PAGE.count("export-guide") == 2
    assert '$("step-apworld").hidden = !multiworld;' in PAGE_SCRIPT
    assert '$("export-result").hidden = !multiworld' in PAGE_SCRIPT
