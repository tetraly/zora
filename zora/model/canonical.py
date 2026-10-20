"""A model value written out in one fixed form, byte for byte: what the seed's code hashes
(FP-HASH-01; owner ruling, beta 5: the code comes from the generated game, never the ROM).

The form follows the model's own equality: a dataclass contributes the fields it compares
(`field(compare=False)` back-references are left out, as == leaves them out), so two values
that are equal always write the same bytes, and two that differ in any compared field write
different ones. Every value is tagged with its kind and length, so no two values run together.
A type the form does not know is refused (TypeError), so a new kind of model value can never be
hashed by accident (an object's id or its memory address).

A field added after seeds were published may be marked OMITTED_AT_DEFAULT: while it holds its
default it writes nothing, so every earlier seed keeps its bytes (and its code); any other value
writes the field as usual. Two equal values still write the same bytes.
"""
from dataclasses import MISSING, Field, fields, is_dataclass
from enum import Enum
from typing import Any

# field(metadata=OMITTED_AT_DEFAULT): the field writes nothing while it holds its default
OMITTED_AT_DEFAULT = {"canonical": "omitted at default"}


def canonical_bytes(value: Any, left_out: tuple[type, ...] = ()) -> bytes:
    """`value` in the fixed form; an instance of a `left_out` type writes only its type's name."""
    out: list[bytes] = []
    _write(value, left_out, out)
    return b"".join(out)


def _tagged(tag: bytes, data: bytes) -> bytes:
    return tag + len(data).to_bytes(4, "big") + data


def _write(value: Any, left_out: tuple[type, ...], out: list[bytes]) -> None:
    if value is None:
        out.append(b"N")
    elif isinstance(value, bool):                         # before int: bool is an int
        out.append(b"T" if value else b"F")
    elif isinstance(value, Enum):
        out.append(_tagged(b"E", type(value).__qualname__.encode()))
        _write(value.value, left_out, out)
    elif isinstance(value, int):
        out.append(_tagged(b"I", str(value).encode()))
    elif isinstance(value, str):
        out.append(_tagged(b"S", value.encode("utf-8")))
    elif isinstance(value, bytes | bytearray):
        out.append(_tagged(b"B", bytes(value)))
    elif isinstance(value, left_out):
        out.append(_tagged(b"X", type(value).__qualname__.encode()))
    elif is_dataclass(value) and not isinstance(value, type):
        compared = [field for field in fields(value) if field.compare and not _omitted(field, value)]
        out.append(_tagged(b"C", type(value).__qualname__.encode()) + len(compared).to_bytes(4, "big"))
        for field in compared:
            out.append(_tagged(b"K", field.name.encode()))
            _write(getattr(value, field.name), left_out, out)
    elif isinstance(value, list | tuple):                 # a NamedTuple compares as its tuple
        out.append(b"L" + len(value).to_bytes(4, "big"))
        for item in value:
            _write(item, left_out, out)
    elif isinstance(value, dict):
        items = sorted((canonical_bytes(key, left_out), canonical_bytes(item, left_out)) for key, item in value.items())
        out.append(b"D" + len(items).to_bytes(4, "big"))
        out.extend(key + item for key, item in items)
    elif isinstance(value, set | frozenset):
        members = sorted(canonical_bytes(item, left_out) for item in value)
        out.append(b"Z" + len(members).to_bytes(4, "big"))
        out.extend(members)
    else:
        raise TypeError(f"no fixed form for {type(value).__qualname__}")


def _omitted(field: Field[Any], value: Any) -> bool:
    """A field marked OMITTED_AT_DEFAULT that holds its default."""
    if field.metadata.get("canonical") != OMITTED_AT_DEFAULT["canonical"]:
        return False
    default = field.default_factory() if field.default is MISSING else field.default   # type: ignore[misc]
    return bool(getattr(value, field.name) == default)
