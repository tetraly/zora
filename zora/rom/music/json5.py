"""The JSON5 the music library uses, read as JSON: `//` comments, unquoted keys and trailing commas.

Only those three extensions (the standard library uses no others). Comment markers inside strings
are kept: the modules' base64 data holds `/` characters, sometimes two in a row.
"""
import json
import re
from typing import Any

UNQUOTED_KEY = re.compile(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)")
TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def _without_comments(text: str) -> str:
    """The text with each `//` comment outside a string removed (to the end of its line)."""
    out: list[str] = []
    in_string = escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if in_string:
            out.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
            out.append(char)
        elif text.startswith("//", index):
            end = text.find("\n", index)
            index = len(text) if end < 0 else end
            continue
        else:
            out.append(char)
        index += 1
    return "".join(out)


def _outside_strings(text: str, pattern: re.Pattern[str], replacement: str) -> str:
    """pattern.sub on the parts of text outside double-quoted strings."""
    parts = re.split(r'("(?:[^"\\]|\\.)*")', text)
    return "".join(part if index % 2 else pattern.sub(replacement, part) for index, part in enumerate(parts))


def loads(text: str) -> Any:
    plain = _without_comments(text)
    plain = _outside_strings(plain, UNQUOTED_KEY, r'\1"\2"\3')
    plain = _outside_strings(plain, TRAILING_COMMA, r"\1")
    return json.loads(plain)
