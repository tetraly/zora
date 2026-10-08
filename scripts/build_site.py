"""Build the web site into a git-ignored folder (docs/site-build.md).

    python3 scripts/build_site.py [--out DIR]
        The public site, exactly as web/stage.sh stages it (default temp/site).
    python3 scripts/build_site.py --with-private [--out DIR]
        The same plus the owner's private level-encoding module
        (private/level_encoding/, never committed here), default
        temp/site-private. Only this build should ever be published.

The private module ships in a form a casual visitor cannot read or grep:
its run-time files are merged into one module, minified with
python-minifier (docstrings, comments and type hints removed, local and
global names renamed except the three the public interface calls),
compressed and base64-encoded, and embedded in the build's own copy of the
worker, which unpacks and loads it before importing zora. This is a speed
bump, not secrecy: anyone determined can unpack it in the browser.

The build then greps every file of the site, including the members of the
wheel, for strings taken from the private source (names, string
constants, docstring and comment lines) that the public site does not
already contain, and fails on any hit.

    python3 scripts/build_site.py --single-file [--with-private]
        Also writes the staged site as ONE page, temp/beta/zora-<version>-<date>-<commit>.html
        (with -public before .html without --with-private), for testers to
        open from disk: stylesheets, scripts, fonts (data: URIs), the wheel
        and the worker inlined (docs/beta-testers.md). With --with-private the
        grep check runs on that file too, the embedded wheel's members included.

--noindex adds <meta name="robots" content="noindex"> to every page written
(off by default; scripts/publish_site.sh, the real site, leaves it off).
"""
from __future__ import annotations

import argparse
import ast
import base64
import io
import json
import re
import shutil
import subprocess
import sys
import tokenize
import zipfile
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from zora.version import PLAYER_VERSION, ZORA_VERSION  # noqa: E402

PRIVATE_PACKAGE = REPO / "private" / "level_encoding"
# The run-time part of the private package, in dependency order; the rest
# (checks, lockstep, tests) is development tooling and never ships.
RUNTIME_MODULES = ("patch.py", "encoder.py")
# The names zora/rom/level_encoding.py calls on the module; they keep their names.
INTERFACE_NAMES = ("apply", "decode_level_data", "ALLOWED_RANGES")
# The import path zora/rom/level_encoding.py loads (its PRIVATE_MODULE).
MODULE_NAME = "private.level_encoding.encoder"
WORKER = "zora-worker.js"
# The start of the Python glue in the worker; the loader goes first in it.
GLUE_ANCHOR = "const GLUE = `\n"
DEFAULT_PUBLIC_OUT = REPO / "temp" / "site"
DEFAULT_PRIVATE_OUT = REPO / "temp" / "site-private"
BETA_OUT = REPO / "temp" / "beta"
WHEEL_PATH = f"dist/zora-{ZORA_VERSION}-py3-none-any.whl"
# The ids web/zora-web.js looks for: the label, the worker's source and the
# wheel (base64).
EMBEDDED_INFO_ID = "zora-embedded"
EMBEDDED_WORKER_ID = "zora-embedded-worker"
EMBEDDED_WHEEL_ID = "zora-embedded-wheel"
# web/flag-tabs.json, which a page opened from disk cannot fetch (zora-web.js
# FLAG_TABS_EMBEDDED_ID)
EMBEDDED_FLAG_TABS_ID = "zora-embedded-flag-tabs"
FLAG_TABS = "flag-tabs.json"
STYLESHEET_TAG = re.compile(r'<link rel="stylesheet" href="([^"]+)">')
SCRIPT_TAG = re.compile(r'<script src="([^"]+)"></script>')
FONT_URL = re.compile(r"url\('(fonts/[^']+\.woff2)'\)")
FONT_LICENSE = "fonts/OFL.txt"
DOCTYPE = "<!doctype html>\n"
# --noindex (optional; scripts/publish_site.sh leaves it off): asks search engines not to list the published page.
ROBOTS_NOINDEX = '<meta name="robots" content="noindex">\n'
# Shorter strings are too generic to say anything about the private source.
MIN_STRING_LENGTH = 6

# Runs first in the worker's Python: registers the unpacked module under
# MODULE_NAME so that zora.rom.level_encoding finds it.
LOADER = """import base64 as _b, sys as _s, types as _t, zlib as _z
def _install(blob, name):
    parts = name.split(".")
    for depth in range(1, len(parts)):
        package = _t.ModuleType(".".join(parts[:depth]))
        package.__path__ = []
        _s.modules.setdefault(package.__name__, package)
    module = _t.ModuleType(name)
    _s.modules[name] = module
    exec(compile(_z.decompress(_b.b64decode(blob)).decode(), "<extras>", "exec"), module.__dict__)
_install("{blob}", "{name}")
del _install
"""


class BuildError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Output folder
# ---------------------------------------------------------------------------

def check_output_folder(out: Path) -> Path:
    """The output must be a git-ignored folder inside this repo with nothing tracked in it."""
    out = out.resolve()
    if out == REPO or REPO not in out.parents:
        raise BuildError(f"{out}: the output folder must be inside {REPO}")
    relative = out.relative_to(REPO)
    ignored = subprocess.run(["git", "-C", str(REPO), "check-ignore", "-q", f"{relative}/"]).returncode == 0
    tracked = subprocess.run(["git", "-C", str(REPO), "ls-files", str(relative)],
                             capture_output=True, text=True, check=True).stdout
    if not ignored or tracked:
        raise BuildError(f"{relative}: the output folder must be git-ignored and hold no tracked files")
    return out


def stage_public(out: Path, noindex: bool = False) -> None:
    """The public site, by web/stage.sh itself; then, with noindex, its page gets the robots tag."""
    subprocess.run(["sh", "web/stage.sh", str(out)], cwd=REPO, check=True, stdout=subprocess.DEVNULL)
    page = out / "index.html"
    page.write_text(marked_page(page.read_text(), noindex))


def marked_page(page: str, noindex: bool = False) -> str:
    """The page, with noindex the robots meta tag first in <head>."""
    if not page.startswith(DOCTYPE):
        raise BuildError(f"index.html does not start with {DOCTYPE.strip()!r}")
    if noindex:
        if "<head>\n" not in page:
            raise BuildError("index.html has no <head> for the robots tag")
        page = page.replace("<head>\n", "<head>\n" + ROBOTS_NOINDEX, 1)
    return page


# ---------------------------------------------------------------------------
# Packing the private module
# ---------------------------------------------------------------------------

def require_private(package: Path = PRIVATE_PACKAGE) -> None:
    missing = [name for name in RUNTIME_MODULES if not (package / name).is_file()]
    if missing:
        raise BuildError(f"--with-private needs the owner's private checkout: {package} lacks "
                         + ", ".join(missing))


def merged_source(package: Path = PRIVATE_PACKAGE) -> str:
    """The run-time modules as one module: their own relative imports, the
    __future__ import and __all__ dropped (comments go with the parse)."""
    body: list[ast.stmt] = []
    for name in RUNTIME_MODULES:
        for node in ast.parse((package / name).read_text()).body:
            if isinstance(node, ast.ImportFrom) and (node.level > 0 or node.module == "__future__"):
                continue
            if isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
                continue
            body.append(node)
    return ast.unparse(ast.Module(body=body, type_ignores=[]))


def minified_source(package: Path = PRIVATE_PACKAGE) -> str:
    import python_minifier
    return str(python_minifier.minify(
        merged_source(package),
        remove_literal_statements=True,          # docstrings
        rename_locals=True,
        rename_globals=True,
        preserve_globals=list(INTERFACE_NAMES),
    ))


def pack(source: str) -> str:
    return base64.b64encode(zlib.compress(source.encode(), 9)).decode("ascii")


def loader_code(blob: str, name: str = MODULE_NAME) -> str:
    code = LOADER.format(blob=blob, name=name)
    # It goes inside a JavaScript template literal.
    if any(marker in code for marker in ("`", "${", "\\")):
        raise BuildError("the loader cannot sit in the worker's template literal")
    return code


def add_private_module(out: Path) -> None:
    worker = out / WORKER
    text = worker.read_text()
    if text.count(GLUE_ANCHOR) != 1:
        raise BuildError(f"{WORKER}: the glue's start ({GLUE_ANCHOR!r}) was not found once")
    worker.write_text(text.replace(GLUE_ANCHOR, GLUE_ANCHOR + loader_code(pack(minified_source()))))


# ---------------------------------------------------------------------------
# The grep check
# ---------------------------------------------------------------------------

def _comment_lines(source: str) -> set[str]:
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    return {token.string.lstrip("#").strip() for token in tokens if token.type == tokenize.COMMENT}


def private_strings(package: Path = PRIVATE_PACKAGE) -> set[str]:
    """Distinctive strings of every Python file of the private package: the
    names it defines, its string constants, and each line of its docstrings
    and comments."""
    found: set[str] = set()
    for path in sorted(package.rglob("*.py")):
        source = path.read_text()
        found |= _comment_lines(source)
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                found.add(node.name)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                found.add(node.id)
            elif isinstance(node, ast.arg):
                found.add(node.arg)
            elif isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)):
                text = node.value.decode("latin-1") if isinstance(node.value, bytes) else node.value
                found.add(text.strip())
                found |= {line.strip() for line in text.splitlines()}
    return {text for text in found if len(text) >= MIN_STRING_LENGTH}


def site_texts(out: Path) -> dict[str, str]:
    """Every file of the site as text, the wheel's members one by one."""
    texts: dict[str, str] = {}
    for path in sorted(p for p in out.rglob("*") if p.is_file()):
        relative = str(path.relative_to(out))
        if path.suffix == ".whl":
            with zipfile.ZipFile(path) as wheel:
                for member in wheel.namelist():
                    texts[f"{relative}!{member}"] = wheel.read(member).decode("utf-8", "replace")
        else:
            texts[relative] = path.read_bytes().decode("utf-8", "replace")
    return texts


def grep_check(site: dict[str, str], public: dict[str, str], strings: set[str]) -> tuple[list[str], list[str]]:
    """The private strings the public site lacks (the ones the check can
    see), and every hit of one in the site."""
    public_text = "\n".join(public.values())
    distinctive = sorted(text for text in strings if text not in public_text)
    hits = [f"{path}: {text!r}" for text in distinctive for path, content in site.items() if text in content]
    return distinctive, hits


# ---------------------------------------------------------------------------
# The single-file beta
# ---------------------------------------------------------------------------

def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def version_label() -> tuple[str, str]:
    """The beta's label for the page and its file-name form: ZORA's version
    (zora/version.py), HEAD's commit date and short hash, marked when tracked
    files differ from HEAD. Only the page shows it; ROM output does not change."""
    date, commit = _git("log", "-1", "--format=%cs"), _git("rev-parse", "--short", "HEAD")
    modified = bool(_git("status", "--porcelain", "--untracked-files=no"))
    label = f"v{PLAYER_VERSION} {date} {commit}" + (" modified" if modified else "")
    return label, label.removeprefix("v").replace(" ", "-")


def _inline(text: str, closing: str, what: str) -> str:
    """Text for a <style> or <script> element (or a comment), which must not
    hold its own end tag; a script must not open a comment either, which
    changes how the browser finds the end tag."""
    for marker in (closing, "<!--") if closing == "</script" else (closing,):
        if marker in text.lower():
            raise BuildError(f"{what} holds {marker!r} and cannot be inlined")
    return text


def _data_uri(path: Path, media_type: str) -> str:
    return f"data:{media_type};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _stylesheet(site: Path, name: str) -> str:
    css = (site / name).read_text()
    css = FONT_URL.sub(lambda match: f"url('{_data_uri(site / match.group(1), 'font/woff2')}')", css)
    return f"<style>\n{_inline(css, '</style', name)}</style>"


def single_file_html(site: Path, label: str) -> str:
    """The staged site as one page that works opened from disk (file://):
    stylesheets, fonts and scripts inline, and the worker, the wheel and the
    flag tabs in non-running script elements that web/zora-web.js reads."""
    page = (site / "index.html").read_text()
    page, sheets = STYLESHEET_TAG.subn(lambda match: _stylesheet(site, match.group(1)), page)
    worker = _inline((site / WORKER).read_text(), "</script", WORKER)
    wheel = base64.b64encode((site / WHEEL_PATH).read_bytes()).decode("ascii")
    info = _inline(json.dumps({"label": label}), "</script", "the label")
    flag_tabs = _inline(json.dumps(json.loads((site / FLAG_TABS).read_text())), "</script", FLAG_TABS)
    embedded = (f'<script type="application/json" id="{EMBEDDED_INFO_ID}">{info}</script>\n'
                f'<script type="application/json" id="{EMBEDDED_FLAG_TABS_ID}">{flag_tabs}</script>\n'
                f'<script type="text/plain" id="{EMBEDDED_WORKER_ID}">{worker}</script>\n'
                f'<script type="text/plain" id="{EMBEDDED_WHEEL_ID}">{wheel}</script>\n')
    scripts = SCRIPT_TAG.findall(page)
    page = SCRIPT_TAG.sub(lambda match: "<script>\n" + _inline((site / match.group(1)).read_text(),
                                                                 "</script", match.group(1)) + "</script>",
                          page)
    if not sheets or not scripts:
        raise BuildError("index.html: no stylesheet or script tags to inline")
    first_script = page.index("<script>")
    page = page[:first_script] + embedded + page[first_script:]
    # The fonts' licence travels with them (SIL OFL 1.1).
    licence = _inline((site / FONT_LICENSE).read_text(), "-->", FONT_LICENSE)
    page = page.replace("<head>\n", f"<head>\n<!--\nDM Sans and DM Mono, embedded below:\n\n{licence}-->\n", 1)
    leftover = re.findall(r'(?:href|src)="(?!data:|https://)[^"]*"', page)
    if leftover:
        raise BuildError(f"index.html: local references left in the single file: {leftover}")
    return page


def embedded_wheel(page: str) -> bytes:
    match = re.search(f'<script type="text/plain" id="{EMBEDDED_WHEEL_ID}">([^<]*)</script>', page)
    if not match:
        raise BuildError("the single file carries no wheel")
    return base64.b64decode(match.group(1))


def single_file_texts(name: str, page: str) -> dict[str, str]:
    """The single file as text, and the embedded wheel's members one by one."""
    texts = {name: page}
    with zipfile.ZipFile(io.BytesIO(embedded_wheel(page))) as wheel:
        for member in wheel.namelist():
            texts[f"{name}!{member}"] = wheel.read(member).decode("utf-8", "replace")
    return texts


def build_single_file(site: Path, with_private: bool, public: dict[str, str] | None) -> Path:
    label, slug = version_label()
    out = check_output_folder(BETA_OUT)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"zora-{slug}{'' if with_private else '-public'}.html"
    page = single_file_html(site, label)
    if with_private:
        assert public is not None
        distinctive, hits = grep_check(single_file_texts(path.name, page), public, private_strings())
        print(f"grep check (single file): {len(distinctive)} distinctive strings, {len(hits)} hits")
        if hits:
            raise BuildError("private strings in the single file (not written):\n  " + "\n  ".join(hits[:40]))
    path.write_text(page)
    print(f"single file {path.relative_to(REPO)} ({path.stat().st_size:,} bytes), {label}")
    return path


# ---------------------------------------------------------------------------

def build(out: Path, with_private: bool, single_file: bool = False, noindex: bool = False) -> None:
    if with_private:
        require_private()
    out = check_output_folder(out)
    stage_public(out, noindex)
    if not with_private:
        print(f"public site in {out.relative_to(REPO)}")
        if single_file:
            build_single_file(out, with_private, None)
        return
    public = site_texts(out)
    add_private_module(out)
    distinctive, hits = grep_check(site_texts(out), public, private_strings())
    print(f"grep check: {len(distinctive)} distinctive strings from the private source "
          f"(of {len(private_strings())}; the rest also occur in the public site), {len(hits)} hits")
    if hits:
        shutil.rmtree(out)
        raise BuildError("private strings in the built site (output removed):\n  " + "\n  ".join(hits[:40]))
    print(f"private site in {out.relative_to(REPO)}")
    if single_file:
        build_single_file(out, with_private, public)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--with-private", action="store_true",
                        help="include the private level-encoding module (packed)")
    parser.add_argument("--single-file", action="store_true",
                        help="also write the site as one page in temp/beta, for testers to open from disk")
    parser.add_argument("--out", type=Path, help="output folder (git-ignored; default temp/site or temp/site-private)")
    parser.add_argument("--noindex", action="store_true",
                        help='add <meta name="robots" content="noindex"> to the pages written (for publishing)')
    args = parser.parse_args()
    out = args.out or (DEFAULT_PRIVATE_OUT if args.with_private else DEFAULT_PUBLIC_OUT)
    try:
        build(out, args.with_private, args.single_file, args.noindex)
    except BuildError as exc:
        print(f"build_site: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
