"""The Archipelago guide as a page of ZORA's site (docs/site-build.md, "The Archipelago guide"):
docs/archipelago-guide.md rendered to HTML at build time, so editing that one file updates the page.

    python3 scripts/guide_page.py SOURCE.md OUT.html

web/stage.sh writes it as archipelago-guide.html beside index.html, with the site's stylesheets
and its light/dark toggle; scripts/build_site.py --single-file also writes it as one file
(styles and fonts inlined) for scripts/publish_site.sh. The page links back to the generator
("./"); the generator's multiworld steps link here (web/zora-web.js ARCHIPELAGO_GUIDE_URL).

The renderer takes the Markdown the guide uses, no more (no dependency, so the release tree builds
the site as it is): one "# " title, "## " and "### " headings (each with an anchor from its text;
the "## " ones also listed under Contents), paragraphs, "- " and "1. " lists nested by indent with
continuation paragraphs (a paragraph whose first line is all bold breaks the line after it, for
the troubleshooting's questions), "| " tables, `code`, **bold**, *italic* and [links](url). Raw HTML in the
source is escaped, never passed through. Anything else is a plain paragraph.
"""
from __future__ import annotations

import html
import re
import sys
from dataclasses import dataclass
from pathlib import Path

PAGE_NAME = "archipelago-guide.html"
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
LIST_ITEM = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.*)$")
TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
CODE_SPAN = re.compile(r"`([^`]+)`")
LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
BOLD = re.compile(r"\*\*(.+?)\*\*")
BOLD_LINE = re.compile(r"^\*\*[^*]+\*\*$")
ITALIC = re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])")
SAFE_URL = re.compile(r"^(https?://|#|\./|[\w.-]+\.html\b)")
PLACEHOLDER = "\x00{}\x00"


class GuideError(ValueError):
    pass


# --- inline ------------------------------------------------------------------------------------

def inline(text: str) -> str:
    """One run of text: escaped, then code spans (kept verbatim), links, bold and italic."""
    spans: list[str] = []

    def keep(markup: str) -> str:
        spans.append(markup)
        return PLACEHOLDER.format(len(spans) - 1)

    text = CODE_SPAN.sub(lambda match: keep(f"<code>{html.escape(match[1], quote=False)}</code>"), text)
    text = html.escape(text, quote=False)

    def link(match: re.Match[str]) -> str:
        url = html.unescape(match[2])
        if not SAFE_URL.match(url):
            raise GuideError(f"a link to {url!r}: only http(s), anchors and pages beside this one")
        return f'<a href="{html.escape(url)}">{match[1]}</a>'

    text = LINK.sub(link, text)
    text = BOLD.sub(r"<strong>\1</strong>", text)
    text = ITALIC.sub(r"<em>\1</em>", text)
    return re.sub("\x00(\\d+)\x00", lambda match: spans[int(match[1])], text)


def anchor(heading: str, taken: set[str]) -> str:
    """GitHub's anchor for a heading ("1. What you need" -> "1-what-you-need"), numbered if taken."""
    plain = re.sub(r"[`*_]", "", LINK.sub(r"\1", heading)).lower()
    base = re.sub(r"[^\w\- ]", "", plain).strip().replace(" ", "-")
    name, number = base, 1
    while name in taken:
        name, number = f"{base}-{number}", number + 1
    taken.add(name)
    return name


# --- blocks ------------------------------------------------------------------------------------

@dataclass
class Heading:
    level: int
    text: str
    anchor: str


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def is_block_start(line: str) -> bool:
    return bool(HEADING.match(line) or LIST_ITEM.match(line) or line.lstrip().startswith("|"))


def table(lines: list[str]) -> str:
    def cells(row: str) -> list[str]:
        return [cell.strip() for cell in row.strip().strip("|").split("|")]
    head, body = cells(lines[0]), [cells(row) for row in lines[2:]]
    rows = "".join("<tr>" + "".join(f"<td>{inline(cell)}</td>" for cell in row) + "</tr>\n" for row in body)
    return ('<div class="guide-table"><table>\n<thead><tr>' + "".join(f"<th>{inline(cell)}</th>" for cell in head)
            + f"</tr></thead>\n<tbody>\n{rows}</tbody>\n</table></div>\n")


def list_block(lines: list[str], headings: list[Heading], taken: set[str]) -> str:
    """A list: items at the first line's indent, each item's own lines (nested lists and
    continuation paragraphs, indented under it) rendered as blocks of their own."""
    first = LIST_ITEM.match(lines[0])
    assert first
    base, ordered = len(first[1]), first[2][0].isdigit()
    items: list[list[str]] = []
    for line in lines:
        match = LIST_ITEM.match(line)
        if match and len(match[1]) == base:
            items.append([match[3]])
        else:
            items[-1].append(line[base + 2:] if indent_of(line) >= base + 2 else line.strip())
    rendered = []
    for item in items:
        while item and not item[-1].strip():
            item.pop()
        if all(line.strip() and not is_block_start(line) for line in item[1:]):
            rendered.append(f"<li>{inline(' '.join(line.strip() for line in item))}</li>")
        else:
            rendered.append(f"<li>{blocks(item, headings, taken, tight=True)}</li>")
    tag = "ol" if ordered else "ul"
    return f"<{tag}>\n" + "\n".join(rendered) + f"\n</{tag}>\n"


def blocks(lines: list[str], headings: list[Heading], taken: set[str], tight: bool = False) -> str:
    """Block-level Markdown to HTML. TIGHT: a list item's first paragraph is not wrapped in <p>."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if heading := HEADING.match(line):
            level, text = len(heading[1]), heading[2]
            name = anchor(text, taken)
            headings.append(Heading(level, text, name))
            out.append(f'<h{level} id="{name}">{inline(text)}</h{level}>\n')
            i += 1
            continue
        if line.lstrip().startswith("|") and i + 1 < len(lines) and TABLE_SEPARATOR.match(lines[i + 1]):
            end = i + 2
            while end < len(lines) and lines[end].lstrip().startswith("|"):
                end += 1
            out.append(table(lines[i:end]))
            i = end
            continue
        if item := LIST_ITEM.match(line):
            base = len(item[1])
            end = i + 1
            while end < len(lines):
                following = lines[end]
                if following.strip():
                    nested = LIST_ITEM.match(following)
                    if indent_of(following) <= base and not (nested and len(nested[1]) == base):
                        if not lines[end - 1].strip() or is_block_start(following):
                            break
                    end += 1
                    continue
                after = next((later for later in lines[end:] if later.strip()), "")
                again = LIST_ITEM.match(after)
                if not after or (indent_of(after) <= base and not (again and len(again[1]) == base)):
                    break
                end += 1
            out.append(list_block(lines[i:end], headings, taken))
            i = end
            continue
        end = i + 1
        while end < len(lines) and lines[end].strip() and not is_block_start(lines[end]):
            end += 1
        parts = [part.strip() for part in lines[i:end]]
        # A question in bold on its own line(s), its answer below (the guide's troubleshooting)
        question = next((count for count in range(1, len(parts))
                         if BOLD_LINE.match(" ".join(parts[:count]))), None)
        if question:
            text = f"{inline(' '.join(parts[:question]))}<br>\n{inline(' '.join(parts[question:]))}"
        else:
            text = inline(" ".join(parts))
        out.append(text if tight and not out else f"<p>{text}</p>\n")
        i = end
    return "".join(out)


@dataclass
class Guide:
    title: str
    body: str
    headings: list[Heading]


def render(markdown: str) -> Guide:
    """The guide's title (its one "# " line, first) and body."""
    lines = markdown.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    title = HEADING.match(lines[0]) if lines else None
    if not title or len(title[1]) != 1:
        raise GuideError("the guide must start with its title, one '# ' line")
    if any((match := HEADING.match(line)) and len(match[1]) == 1 for line in lines[1:]):
        raise GuideError("the guide has more than one '# ' title")
    headings: list[Heading] = []
    return Guide(title[2], blocks(lines[1:], headings, set()), headings)


# --- the page ----------------------------------------------------------------------------------

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} | ZORA</title>
<link rel="stylesheet" href="fonts.css">
<link rel="stylesheet" href="zora.css">
</head>
<body>

<header class="masthead">
  <div class="masthead-bar">
    <a class="wordmark wordmark-link" href="./">ZORA</a>
    <nav class="masthead-nav">
      <a href="./">Generate a game</a>
      <button id="dark-mode-btn" class="theme-btn" type="button"></button>
    </nav>
  </div>
  <div class="masthead-hero">
    <h1>{title}</h1>
  </div>
  <svg class="waves" viewBox="0 0 1440 120" preserveAspectRatio="none" aria-hidden="true">
    <path class="wave wave-1" d="M0 60 C 240 20, 480 100, 720 60 S 1200 20, 1440 56 L1440 120 L0 120 Z"></path>
    <path class="wave wave-2" d="M0 84 C 260 52, 520 116, 780 84 S 1240 56, 1440 80 L1440 120 L0 120 Z"></path>
    <path class="wave wave-3" d="M0 104 C 300 84, 600 124, 900 102 S 1300 90, 1440 100 L1440 120 L0 120 Z"></path>
  </svg>
</header>

<main class="guide">
<nav class="guide-contents" aria-labelledby="guide-contents-title">
<h2 id="guide-contents-title">Contents</h2>
<ol>
{contents}
</ol>
</nav>
<article class="guide-body">
{body}</article>
<p class="guide-back"><a href="./">Back to ZORA</a></p>
</main>

<script src="widgets.js"></script>
<script>initThemeToggle();</script>
</body>
</html>
"""


def page(markdown: str) -> str:
    guide = render(markdown)
    contents = "\n".join(f'<li><a href="#{heading.anchor}">{inline(heading.text)}</a></li>'
                         for heading in guide.headings if heading.level == 2)
    return PAGE.format(title=inline(guide.title), contents=contents, body=guide.body)


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    source, out = Path(sys.argv[1]), Path(sys.argv[2])
    try:
        out.write_text(page(source.read_text()))
    except (OSError, GuideError) as problem:
        print(f"guide_page: {source}: {problem}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
