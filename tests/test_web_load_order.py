"""web/zora-web.js and web/widgets.js read no top-level constant before its definition while they load.

A top-level `const`, `let` or `class` is in its temporal dead zone until its line runs, so a statement
that runs at load (a call, or a constant's initializer) and reaches such a name defined further down,
directly or through the functions it calls, throws a ReferenceError and stops the page (beta 11:
`const playerSettings = loadPlayerSettings()` read CHARACTER_COLORS_SET, TUNIC_SLOTS and
LINK_COLOR_SLOTS, defined later, and the page never got past "Loading Python..."; from dd2d7e7).

A static check, since the page's top level needs a browser: it splits each script into its top-level
statements, follows the calls of each one that runs at load into the bodies of the top-level functions
it names (and of constants holding a function), and lists every name it reaches that is defined below
the statement. It over-approximates (a callback that only runs later counts as running now), so a hit
it reports in error goes in DEFERRED with the reason."""
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = ("web/zora-web.js", "web/widgets.js")
# (script, statement's first name, name reached) pairs that only run after load, each with its reason
DEFERRED: dict[tuple[str, str, str], str] = {}

DECLARATION = re.compile(r"^(?:export\s+)?(?:(async\s+)?function\*?\s+(?P<function>\w+)|class\s+(?P<class>\w+)"
                         r"|(?:const|let|var)\s+(?P<binding>\w+|[{[][^=]*))")
FUNCTION_VALUE = re.compile(r"^\s*(?:async\s+)?(?:function\b|\([^)]*\)\s*=>|\w+\s*=>)")
STRING_OR_COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/|\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'|`(?:\\.|[^`\\])*`",
                               re.DOTALL)
# A name, not a property (`.name`); a spread (`...name`) is a name
IDENTIFIER = re.compile(r"(?<![\w$])(?:(?<=\.\.\.)|(?<!\.))([A-Za-z_$][\w$]*)")
# An assignment of a function (`worker.onmessage = (event) => {`): its body runs when called
ASSIGNED_FUNCTION = re.compile(r"^[\w$.\[\]]+\s*=\s*(?:async\s+)?(?:function\b|\([^)]*\)\s*=>|\w+\s*=>)")
# Names a body declares for itself, shadowing a top-level one: bindings, destructurings, a function's
# parameters, an arrow's, a catch's
LOCAL_NAME = re.compile(r"\b(?:const|let|var)\s+(\w+)|\b(?:const|let|var)\s*([{[][^=;]*?[}\]])\s*(?:=|of\b|in\b)"
                        r"|\bfunction\*?\s*\w*\s*\(([^)]*)\)|\(([^()]*)\)\s*=>|\b(\w+)\s*=>|\bcatch\s*\((\w+)\)")


@dataclass
class Statement:
    line: int               # 1-based line of its start
    text: str               # strings and comments blanked
    kind: str               # "function", "class", "binding" or "code"
    names: tuple[str, ...]  # what it defines
    deferred: bool          # a function, or a binding whose value is a function: its body runs when called


def blank(source: str) -> str:
    """The source with strings and comments emptied (line breaks kept, so line numbers hold)."""
    return STRING_OR_COMMENT.sub(lambda match: re.sub(r"[^\n]", " ", match[0])
                                 if match[0].startswith(("//", "/*")) else '""', source)


def statements(source: str) -> list[Statement]:
    """Each top-level statement: it starts on a line at column 0 that does not close an earlier one."""
    lines = blank(source).split("\n")
    starts = [index for index, line in enumerate(lines)
              if line[:1].strip() and not line.startswith(("}", ")", "]"))]
    found = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        text = "\n".join(lines[start:end])
        match = DECLARATION.match(text)
        if match and match["function"]:
            found.append(Statement(start + 1, text, "function", (match["function"],), True))
        elif match and match["class"]:
            found.append(Statement(start + 1, text, "class", (match["class"],), True))
        elif match and match["binding"]:
            names = tuple(IDENTIFIER.findall(match["binding"]))
            value = text.split("=", 1)[1] if "=" in text else ""
            found.append(Statement(start + 1, text, "binding", names, bool(FUNCTION_VALUE.match(value))))
        else:
            found.append(Statement(start + 1, text, "code", (), bool(ASSIGNED_FUNCTION.match(text))))
    return found


def references(body: str) -> list[str]:
    """The names a body uses, less those it declares for itself."""
    local = {name for match in LOCAL_NAME.finditer(body) for group in match.groups() if group
             for name in IDENTIFIER.findall(group)}
    return [name for name in IDENTIFIER.findall(body) if name not in local]


def used_before_definition(source: str) -> list[tuple[int, str, str, int]]:
    """(statement line, statement's first name or text, name reached, its definition line) for every
    top-level name a statement running at load reaches before its definition."""
    found = statements(source)
    defined_at = {name: statement.line for statement in found for name in statement.names}
    callable_body = {name: statement.text for statement in found if statement.deferred for name in statement.names}
    hoisted = {name for statement in found if statement.kind == "function" for name in statement.names}
    hits: list[tuple[int, str, str, int]] = []
    for statement in found:
        if statement.deferred:
            continue
        # A binding's own names are defined by it; its initializer runs now.
        text = statement.text
        if statement.kind == "binding" and "=" in text:
            text = text.split("=", 1)[1]
        reached, queue = set(), references(text)
        while queue:
            name = queue.pop()
            if name in reached or name not in defined_at:
                continue
            reached.add(name)
            if name in callable_body:
                queue.extend(references(callable_body[name]))
        label = statement.names[0] if statement.names else statement.text.split("\n")[0].strip()[:60]
        # A function declaration is hoisted: callable before its line.
        hits.extend((statement.line, label, name, defined_at[name]) for name in sorted(reached)
                    if name not in hoisted and defined_at[name] > statement.line)
    return hits


@pytest.mark.parametrize("script", SCRIPTS)
def test_no_top_level_name_is_read_before_its_definition(script: str) -> None:
    hits = [f"line {line} ({label}) reaches {name}, defined on line {defined}"
            for line, label, name, defined in used_before_definition((REPO / script).read_text())
            if (script, label, name) not in DEFERRED]
    assert hits == [], "\n".join(hits)


def test_the_check_finds_the_beta_11_load_failure() -> None:
    """The check flags the shape that broke the page: a constant read by a function the load calls."""
    source = "\n".join([
        "function defaults() {",
        "  return { colors: LATER };",
        "}",
        "const settings = defaults();",
        'const LATER = "set";',
        'document.addEventListener("click", () => defaults());',
    ])
    assert [(name, defined) for _line, _label, name, defined in used_before_definition(source)] == [("LATER", 5)]
