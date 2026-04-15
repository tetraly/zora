#!/usr/bin/env python3
"""
Validate flags.yaml and optionally regenerate flags_generated.py.

Usage:
    python flags/validate_flags.py           # validate only
    python flags/validate_flags.py --generate # validate and regenerate
"""
import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any, cast

import yaml

FLAGS_YAML = Path(__file__).parent / "flags.yaml"
FLAGS_GENERATED = Path(__file__).parent / "flags_generated.py"

VALID_TYPES = {"bool", "tristate", "item", "enum", "color"}
TRISTATE_VALUES = {"off", "on", "random"}
TRISTATE_BITS = 2
ITEM_BITS = 5
BOOL_BITS = 1
COLOR_BITS = 6

BASE64_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@abcdefghijklmnopqrstuvwxyz"


# =============================================================================
# LOADING AND VALIDATION
# =============================================================================

def load_and_validate(path: Path) -> dict[str, Any]:
    """Load flags.yaml and validate its structure. Raises on error."""
    with open(path) as f:
        schema = yaml.safe_load(f)
    _validate_schema(schema)
    return cast(dict[str, Any], schema)


def _validate_schema(schema: dict[str, Any]) -> None:
    if "version" not in schema:
        raise ValueError("flags.yaml missing 'version' field")

    _validate_meta(schema)
    item_enum = _validate_item_enum(schema)
    item_ids = {entry["id"] for entry in item_enum}

    flags = schema.get("flags", [])
    seen_ids: set[str] = set()
    seen_offsets: list[tuple[int, int, str]] = []       # main string: (offset, end, flag_id)
    seen_cosmetic_offsets: list[tuple[int, int, str]] = []  # cosmetic string: (offset, end, flag_id)
    seen_orders_by_group: dict[str, set[int]] = {}

    for flag in flags:
        _validate_flag(
            flag, seen_ids, seen_orders_by_group,
            seen_offsets if (flag.get("enabled", True) and not flag.get("cosmetic", False)) else [],
            seen_cosmetic_offsets if (flag.get("enabled", True) and flag.get("cosmetic", False)) else [],
            item_ids,
        )

    _validate_total_bits(schema, seen_offsets)
    _validate_cosmetic_total_bits(schema, seen_cosmetic_offsets)

    flag_ids = {f["id"] for f in flags}
    item_flag_ids = {f["id"] for f in flags if f["type"] == "item"}

    _validate_depends_on(flags, flag_ids)
    _validate_pool_contributions(schema, item_ids)

    for constraint in schema.get("constraints", []):
        _validate_constraint(constraint, flag_ids, item_flag_ids, item_ids)


def _validate_meta(schema: dict[str, Any]) -> None:
    meta = schema.get("meta")
    if meta is None:
        raise ValueError("flags.yaml missing 'meta' section")
    for field in ("format_version", "encoding", "bit_order", "total_bits", "string_length"):
        if field not in meta:
            raise ValueError(f"meta section missing required field '{field}'")
    if meta["encoding"] not in ("base62", "base64url"):
        raise ValueError(f"Unsupported encoding '{meta['encoding']}'; only 'base62' or 'base64url' is supported")
    if meta["total_bits"] % 6 != 0:
        raise ValueError(
            f"meta.total_bits ({meta['total_bits']}) must be divisible by 6 for clean base64url encoding"
        )
    expected_length = meta["total_bits"] // 6
    if meta["string_length"] != expected_length:
        raise ValueError(
            f"meta.string_length ({meta['string_length']}) does not match "
            f"total_bits / 6 = {expected_length}"
        )

    cosmetic_meta = schema.get("cosmetic_meta")
    if cosmetic_meta is None:
        raise ValueError("flags.yaml missing 'cosmetic_meta' section")
    for field in ("encoding", "bit_order", "total_bits", "string_length"):
        if field not in cosmetic_meta:
            raise ValueError(f"cosmetic_meta section missing required field '{field}'")
    if cosmetic_meta["total_bits"] % 6 != 0:
        raise ValueError(
            f"cosmetic_meta.total_bits ({cosmetic_meta['total_bits']}) must be divisible by 6"
        )
    expected_cosmetic_length = cosmetic_meta["total_bits"] // 6
    if cosmetic_meta["string_length"] != expected_cosmetic_length:
        raise ValueError(
            f"cosmetic_meta.string_length ({cosmetic_meta['string_length']}) does not match "
            f"total_bits / 6 = {expected_cosmetic_length}"
        )


def _validate_item_enum(schema: dict[str, Any]) -> list[dict[str, Any]]:
    item_enum = schema.get("item_enum")
    if item_enum is None:
        raise ValueError("flags.yaml missing 'item_enum' section")
    seen_indices: set[int] = set()
    seen_ids: set[str] = set()
    for entry in item_enum:
        for field in ("id", "index", "label"):
            if field not in entry:
                raise ValueError(f"item_enum entry missing field '{field}': {entry}")
        idx = entry["index"]
        eid = entry["id"]
        if idx in seen_indices:
            raise ValueError(f"item_enum: duplicate index {idx}")
        if eid in seen_ids:
            raise ValueError(f"item_enum: duplicate id '{eid}'")
        seen_indices.add(idx)
        seen_ids.add(eid)
        max_item_value = (1 << ITEM_BITS) - 1
        if not (0 <= idx <= max_item_value):
            raise ValueError(
                f"item_enum: index {idx} for '{eid}' is out of range "
                f"(must be 0-{max_item_value} for {ITEM_BITS}-bit item fields)"
            )
    return cast(list[dict[str, Any]], item_enum)


def _validate_flag(
    flag: dict[str, Any],
    seen_ids: set[str],
    seen_orders_by_group: dict[str, set[int]],
    seen_offsets: list[tuple[int, int, str]],
    seen_cosmetic_offsets: list[tuple[int, int, str]],
    item_ids: set[str],
) -> None:
    is_cosmetic = flag.get("cosmetic", False)
    offset_field = "cosmetic_bit_offset" if is_cosmetic else "bit_offset"
    required = ["id", "type", "bits", offset_field, "label", "description",
                "group", "display_order", "default", "enabled"]
    for field_name in required:
        if field_name not in flag:
            raise ValueError(f"Flag missing required field '{field_name}': {flag}")

    fid = flag["id"]
    if fid in seen_ids:
        raise ValueError(f"Duplicate flag id: {fid}")
    seen_ids.add(fid)

    if not fid.isidentifier():
        raise ValueError(f"Flag id '{fid}' is not a valid Python identifier")

    ftype = flag["type"]
    if ftype not in VALID_TYPES:
        raise ValueError(f"Flag {fid}: unknown type '{ftype}' (expected: {VALID_TYPES})")

    bits = flag["bits"]
    if not isinstance(bits, int) or bits < 1:
        raise ValueError(f"Flag {fid}: bits must be a positive integer")

    bit_offset = flag[offset_field]
    if not isinstance(bit_offset, int) or bit_offset < 0:
        raise ValueError(f"Flag {fid}: {offset_field} must be a non-negative integer")

    # Check for bit range overlaps in whichever layout this flag belongs to
    flag_end = bit_offset + bits
    offsets_list = seen_cosmetic_offsets if is_cosmetic else seen_offsets
    for existing_offset, existing_end, existing_id in offsets_list:
        if not (flag_end <= existing_offset or bit_offset >= existing_end):
            raise ValueError(
                f"Flag {fid} ({offset_field} {bit_offset}-{flag_end - 1}) overlaps with "
                f"flag {existing_id} ({offset_field} {existing_offset}-{existing_end - 1})"
            )
    offsets_list.append((bit_offset, flag_end, fid))

    # Type-specific validation
    if ftype == "bool":
        if bits != BOOL_BITS:
            raise ValueError(f"Flag {fid}: bool type must have bits={BOOL_BITS}")
        if not isinstance(flag["default"], bool):
            raise ValueError(f"Flag {fid}: bool default must be true or false")

    elif ftype == "tristate":
        if bits != TRISTATE_BITS:
            raise ValueError(f"Flag {fid}: tristate type must have bits={TRISTATE_BITS}")
        if flag["default"] not in TRISTATE_VALUES:
            raise ValueError(
                f"Flag {fid}: tristate default must be one of {TRISTATE_VALUES}"
            )

    elif ftype == "item":
        if bits != ITEM_BITS:
            raise ValueError(f"Flag {fid}: item type must have bits={ITEM_BITS}")
        if flag["default"] not in ("random", "not_shuffled"):
            raise ValueError(f"Flag {fid}: item type default must be 'random' or 'not_shuffled'")

    elif ftype == "color":
        if bits != COLOR_BITS:
            raise ValueError(f"Flag {fid}: color type must have bits={COLOR_BITS}")
        if not flag.get("cosmetic", False):
            raise ValueError(f"Flag {fid}: color type must be a cosmetic flag")
        if not isinstance(flag["default"], int) or flag["default"] != 0:
            raise ValueError(f"Flag {fid}: color type default must be 0 (vanilla)")

    elif ftype == "enum":
        if "values" not in flag:
            raise ValueError(f"Flag {fid}: enum type requires a 'values' list")
        values = flag["values"]
        if not isinstance(values, list) or len(values) < 2:
            raise ValueError(f"Flag {fid}: enum 'values' must be a list of at least 2 entries")
        if len(values) > (1 << bits):
            raise ValueError(
                f"Flag {fid}: enum has {len(values)} values but bits={bits} only allows {1 << bits}"
            )
        value_ids = set()
        for i, entry in enumerate(values):
            if "id" not in entry or "label" not in entry:
                raise ValueError(f"Flag {fid}: enum values[{i}] missing 'id' or 'label'")
            if entry["id"] in value_ids:
                raise ValueError(f"Flag {fid}: duplicate enum value id '{entry['id']}'")
            value_ids.add(entry["id"])
        if flag["default"] not in value_ids:
            raise ValueError(
                f"Flag {fid}: enum default '{flag['default']}' not in values {list(value_ids)}"
            )

    # display_order uniqueness per group (hidden/disabled flags are exempt)
    if flag.get("enabled", True):
        group = flag["group"]
        order = flag["display_order"]
        seen_orders_by_group.setdefault(group, set())
        if order in seen_orders_by_group[group]:
            raise ValueError(
                f"Flag {fid}: duplicate display_order {order} within group '{group}'"
            )
        seen_orders_by_group[group].add(order)


def _validate_total_bits(schema: dict[str, Any], seen_offsets: list[tuple[int, int, str]]) -> None:
    total_bits = schema["meta"]["total_bits"]
    for offset, end, fid in seen_offsets:
        if end > total_bits:
            raise ValueError(
                f"Flag {fid} ends at bit {end - 1}, which exceeds "
                f"meta.total_bits ({total_bits})"
            )


def _validate_cosmetic_total_bits(schema: dict[str, Any], seen_cosmetic_offsets: list[tuple[int, int, str]]) -> None:
    total_bits = schema["cosmetic_meta"]["total_bits"]
    for offset, end, fid in seen_cosmetic_offsets:
        if end > total_bits:
            raise ValueError(
                f"Cosmetic flag {fid} ends at bit {end - 1}, which exceeds "
                f"cosmetic_meta.total_bits ({total_bits})"
            )


def _validate_depends_on(flags: list[dict[str, Any]], flag_ids: set[str]) -> None:
    """Validate depends_on references and detect circular dependency chains."""
    # Check all depends_on targets exist
    for flag in flags:
        dep = flag.get("depends_on")
        if dep is not None and dep not in flag_ids:
            raise ValueError(
                f"Flag '{flag['id']}': depends_on '{dep}' references unknown flag"
            )

    # Detect cycles via DFS
    dependents: dict[str, list[str]] = {}
    for flag in flags:
        dep = flag.get("depends_on")
        if dep:
            dependents.setdefault(dep, []).append(flag["id"])

    def _has_cycle(node: str, visiting: set[str], visited: set[str]) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for child in dependents.get(node, []):
            if _has_cycle(child, visiting, visited):
                return True
        visiting.discard(node)
        visited.add(node)
        return False

    visited: set[str] = set()
    for flag in flags:
        if _has_cycle(flag["id"], set(), visited):
            raise ValueError(
                f"Circular dependency detected involving flag '{flag['id']}'"
            )


def _validate_pool_contributions(schema: dict[str, Any], item_ids: set[str]) -> None:
    """Validate that pool_contributions in the schema reference known item IDs."""
    contributions = schema.get("pool_contributions", {})
    for flag_id, items in contributions.items():
        for item_id in items:
            if item_id not in item_ids:
                raise ValueError(
                    f"pool_contributions['{flag_id}']: unknown item id '{item_id}'"
                )


def _validate_constraint(
    constraint: dict[str, Any],
    flag_ids: set[str],
    item_flag_ids: set[str],
    item_ids: set[str],
) -> None:
    cid = constraint.get("id", "<unknown>")

    when_clauses = constraint.get("when", [])
    then_clauses = constraint.get("then", [])

    if not when_clauses:
        raise ValueError(f"Constraint '{cid}': missing or empty 'when' clause")
    if not then_clauses:
        raise ValueError(f"Constraint '{cid}': missing or empty 'then' clause")

    for condition in when_clauses:
        if "flag" not in condition:
            raise ValueError(f"Constraint '{cid}': 'when' entry missing 'flag' field: {condition}")
        if condition["flag"] not in flag_ids:
            raise ValueError(f"Constraint '{cid}': unknown flag '{condition['flag']}'")
        if "equals" not in condition and "not_equals" not in condition:
            raise ValueError(
                f"Constraint '{cid}': 'when' entry must have 'equals' or 'not_equals': {condition}"
            )

    for action in then_clauses:
        if "flag" in action and action["flag"] not in flag_ids:
            raise ValueError(f"Constraint '{cid}': unknown flag '{action['flag']}'")
        rule = action.get("rule")
        if rule == "no_duplicate":
            if "among" not in action:
                raise ValueError(
                    f"Constraint '{cid}': no_duplicate rule missing required 'among' field"
                )
            for ref in action["among"]:
                if ref not in flag_ids:
                    raise ValueError(
                        f"Constraint '{cid}': no_duplicate references unknown flag '{ref}'"
                    )
        elif rule == "item_in_pool":
            if "flag" not in action:
                raise ValueError(
                    f"Constraint '{cid}': item_in_pool rule missing required 'flag' field"
                )
        elif rule == "heart_container_pool_check":
            pass  # no extra fields required; evaluated entirely at runtime
        elif rule is None and "must_be_one_of" in action:
            if "flag" not in action:
                raise ValueError(
                    f"Constraint '{cid}': must_be_one_of missing required 'flag' field"
                )
            if not isinstance(action["must_be_one_of"], list):
                raise ValueError(
                    f"Constraint '{cid}': must_be_one_of must be a list"
                )
        elif rule is not None:
            raise ValueError(
                f"Constraint '{cid}': unknown rule '{rule}'"
            )


# =============================================================================
# CODE GENERATION
# =============================================================================

def compute_schema_hash(path: Path) -> str:
    """Hash the parsed, normalized content of flags.yaml.

    Uses yaml.dump with stable settings so cosmetic edits (whitespace,
    comments, key ordering) don't invalidate the hash — only structural
    changes to flag definitions do.
    """
    with open(path) as f:
        schema = yaml.safe_load(f)
    normalized = yaml.dump(schema, sort_keys=True, default_flow_style=False)
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _dq(s: str) -> str:
    """Return a Python string literal for s, preferring double quotes.

    Uses single outer quotes when the string contains a double quote but no
    single quote, to avoid backslash escaping (satisfies ruff Q003).
    """
    ctrl_escaped = s.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    has_dq = '"' in ctrl_escaped
    has_sq = "'" in ctrl_escaped
    if has_dq and not has_sq:
        return f"'{ctrl_escaped}'"
    # Default: double-quote, escaping any " inside.
    return f'"{ctrl_escaped.replace(chr(34), chr(92) + chr(34))}"'


def _dq_repr(v: Any) -> str:
    """Like repr(), but always uses double quotes for string values and string keys in dicts/lists."""
    if isinstance(v, str):
        return _dq(v)
    if isinstance(v, bool):
        return repr(v)
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, tuple):
        inner = ", ".join(_dq_repr(x) for x in v)
        return f"({inner},)" if len(v) == 1 else f"({inner})"
    if isinstance(v, list):
        inner = ", ".join(_dq_repr(x) for x in v)
        return f"[{inner}]"
    if isinstance(v, dict):
        pairs = ", ".join(f"{_dq(str(k))}: {_dq_repr(val)}" for k, val in v.items())
        return "{" + pairs + "}"
    return repr(v)


def _emit_flag_def_value(indent: str, k: str, v: Any, line_limit: int = 120) -> list[str]:
    """Emit a single key-value pair inside a _FLAG_DEFS entry, wrapping long strings."""
    prefix = f"{indent}{_dq(k)}: "
    if isinstance(v, str):
        full_line = f"{prefix}{_dq(v)},"
        if len(full_line) <= line_limit:
            return [full_line]
        # Wrap: emit as a parenthesised multi-line string using implicit concatenation.
        # Split on spaces, rebuilding chunks that fit within the limit.
        max_chunk = line_limit - len(indent) - 4 - 2  # 4 = continuation indent, 2 = surrounding quotes
        words = v.split(" ")
        chunks: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}" if current else word
            if len(candidate) > max_chunk and current:
                chunks.append(current)
                current = word
            else:
                current = candidate
        if current:
            chunks.append(current)
        result = [f"{prefix}("]
        for chunk in chunks:
            result.append(f"{indent}    {_dq(chunk)}")
        result.append(f"{indent}),")
        return result
    if isinstance(v, list) and v and isinstance(v[0], dict):
        # Emit list of dicts one entry per line
        result = [f"{prefix}["]
        for entry in v:
            result.append(f"{indent}    {_dq_repr(entry)},")
        result.append(f"{indent}],")
        return result
    full_line = f"{prefix}{_dq_repr(v)},"
    if len(full_line) <= line_limit:
        return [full_line]
    # Fallback: repr on its own line
    result = [f"{indent}{_dq(k)}: ("]
    result.append(f"{indent}    {_dq_repr(v)}")
    result.append(f"{indent}),")
    return result


def generate_flags_module(schema: dict[str, Any], schema_hash: str) -> str:
    """Generate the complete flags_generated.py module content."""
    version = schema["version"]
    meta = schema["meta"]
    cosmetic_meta = schema["cosmetic_meta"]
    flags = schema["flags"]
    item_enum = schema["item_enum"]

    main_flags = [f for f in flags if not f.get("cosmetic", False)]
    cosmetic_flags = [f for f in flags if f.get("cosmetic", False)]

    lines = [
        "# AUTO-GENERATED by flags/validate_flags.py",
        "# DO NOT EDIT MANUALLY",
        "# To regenerate: python flags/validate_flags.py --generate",
        f"# Schema version: {version}",
        "# Generated from: flags/flags.yaml",
        "",
        "from __future__ import annotations",
        "from dataclasses import dataclass, field",
        "from enum import IntEnum",
        "from typing import Any",
        "from zora.rng import Rng",
        "",
        "",
        "# ===========================================================================",
        "# TRISTATE ENUM",
        "# ===========================================================================",
        "",
        "class Tristate(IntEnum):",
        '    """Tri-state flag value: off, on, or random."""',
        "    OFF = 0",
        "    ON = 1",
        "    RANDOM = 2",
        "",
        "",
        "# ===========================================================================",
        "# ITEM ENUM",
        "# ===========================================================================",
        "",
        "class Item(IntEnum):",
        '    """Canonical item identifiers for item-type flag fields."""',
    ]

    sorted_items = sorted(item_enum, key=lambda e: e["index"])
    for entry in sorted_items:
        comment = "  # reserved" if entry.get("reserved") else ""
        lines.append(f"    {entry['id'].upper()} = {entry['index']}{comment}")

    lines += [
        "",
        "",
        "ITEM_LABELS: dict[Item, str] = {",
    ]
    for entry in sorted_items:
        lines.append(f"    Item.{entry['id'].upper()}: {_dq(entry['label'])},")
    lines += [
        "}",
        "",
        "",
    ]

    # Generate an IntEnum class for each enum-type flag
    enum_flags = [f for f in flags if f.get("type") == "enum" and f.get("enabled", True)]
    for flag in enum_flags:
        fid = flag["id"]
        class_name = "".join(w.capitalize() for w in fid.split("_"))
        lines += [
            "# ===========================================================================",
            f"# {class_name.upper()} ENUM  (flag: {fid})",
            "# ===========================================================================",
            "",
            f"class {class_name}(IntEnum):",
            f'    """Values for the {fid} flag."""',
        ]
        for i, entry in enumerate(flag["values"]):
            lines.append(f"    {entry['id'].upper()} = {i}")
        lines += ["", ""]

    lines += [
        "# ===========================================================================",
        "# FLAGS DATACLASS",
        "# ===========================================================================",
        "",
        "@dataclass",
        "class Flags:",
        '    """Randomizer configuration flags (excludes cosmetic flags).',
        "",
        "    Auto-generated from flags/flags.yaml. Do not edit manually.",
        "    Run `python flags/validate_flags.py --generate` to regenerate.",
        '    """',
        "",
    ]

    # Group enabled non-cosmetic flags by group, sorted by display_order
    groups: dict[str, list[dict[str, Any]]] = {}
    for flag in main_flags:
        if not flag.get("enabled", True):
            continue
        group = flag["group"]
        groups.setdefault(group, [])
        groups[group].append(flag)

    for group_name, group_flags in groups.items():
        lines.append(f"    # {group_name}")
        for flag in sorted(group_flags, key=lambda f: f["display_order"]):
            fid = flag["id"]
            ftype = flag["type"]
            default = flag["default"]

            if ftype == "bool":
                py_default = "True" if default else "False"
                lines.append(f"    {fid}: bool = {py_default}")
            elif ftype == "tristate":
                tristate_map = {"off": "Tristate.OFF", "on": "Tristate.ON", "random": "Tristate.RANDOM"}
                py_default = tristate_map[str(default)]
                lines.append(f"    {fid}: Tristate = {py_default}")
            elif ftype == "item":
                item_default = flag.get("default", "random")
                item_default_const = item_default.upper()
                lines.append(f"    {fid}: Item = Item.{item_default_const}")
            elif ftype == "enum":
                class_name = "".join(w.capitalize() for w in fid.split("_"))
                default_const = flag["default"].upper()
                lines.append(f"    {fid}: {class_name} = {class_name}.{default_const}")
        lines.append("")

    lines += [
        "    # Schema metadata — used for sync checking, not a flag",
        f"    _schema_version: int = field(default={version}, init=False, repr=False, compare=False)",
        f"    _schema_hash: str = field(default={_dq(schema_hash)}, init=False, repr=False, compare=False)",
        "",
        "",
    ]

    # CosmeticFlags dataclass
    lines += [
        "# ===========================================================================",
        "# COSMETIC FLAGS DATACLASS",
        "# ===========================================================================",
        "",
        "@dataclass",
        "class CosmeticFlags:",
        '    """Cosmetic-only flags encoded in a separate string from Flags.',
        "",
        "    These do not affect item placement, seed generation, or the hash code.",
        "    Players can share the same seed + flag_string with different cosmetic",
        "    settings and get the same logical game.",
        "",
        "    Auto-generated from flags/flags.yaml. Do not edit manually.",
        "    Run `python flags/validate_flags.py --generate` to regenerate.",
        '    """',
        "",
    ]
    for flag in sorted(cosmetic_flags, key=lambda f: f["cosmetic_bit_offset"]):
        if not flag.get("enabled", True):
            continue
        fid = flag["id"]
        ftype = flag["type"]
        default = flag["default"]
        if ftype == "tristate":
            tristate_map = {"off": "Tristate.OFF", "on": "Tristate.ON", "random": "Tristate.RANDOM"}
            py_default = tristate_map[str(default)]
            lines.append(f"    {fid}: Tristate = {py_default}")
        elif ftype == "enum":
            class_name = "".join(w.capitalize() for w in fid.split("_"))
            default_const = flag["default"].upper()
            lines.append(f"    {fid}: {class_name} = {class_name}.{default_const}")
        elif ftype == "color":
            lines.append(f"    {fid}: int = {int(default)}")
        elif ftype == "bool":
            py_default = "True" if default else "False"
            lines.append(f"    {fid}: bool = {py_default}")
    lines += ["", ""]

    # Encoding constants
    lines += [
        "# ===========================================================================",
        "# ENCODING CONSTANTS",
        "# ===========================================================================",
        "",
        f"BASE64_ALPHABET = {_dq(BASE64_ALPHABET)}",
        f"FLAG_STRING_LENGTH = {meta['string_length']}",
        f"TOTAL_BITS = {meta['total_bits']}",
        f"COSMETIC_FLAG_STRING_LENGTH = {cosmetic_meta['string_length']}",
        f"COSMETIC_TOTAL_BITS = {cosmetic_meta['total_bits']}",
        "",
        "# (flag_id, bit_offset, bit_width) — used by encoder/decoder",
        "_FLAG_LAYOUT: list[tuple[str, int, int]] = [",
    ]
    for flag in sorted(main_flags, key=lambda f: f["bit_offset"]):
        if not flag.get("enabled", True):
            continue
        lines.append(f"    ({_dq(flag['id'])}, {flag['bit_offset']}, {flag['bits']}),")
    lines += [
        "]",
        "",
        "# (flag_id, cosmetic_bit_offset, bit_width) — used by cosmetic encoder/decoder",
        "_COSMETIC_FLAG_LAYOUT: list[tuple[str, int, int]] = [",
    ]
    for flag in sorted(cosmetic_flags, key=lambda f: f["cosmetic_bit_offset"]):
        if not flag.get("enabled", True):
            continue
        lines.append(f"    ({_dq(flag['id'])}, {flag['cosmetic_bit_offset']}, {flag['bits']}),")
    lines += [
        "]",
        "",
        "",
    ]

    # Encoder
    lines += [
        "# ===========================================================================",
        "# ENCODER / DECODER",
        "# ===========================================================================",
        "",
        "def encode_flags(flags: Flags) -> str:",
        '    """Encode a Flags instance to a base62 flag string."""',
        "    bitfield = 0",
        "    for fid, offset, width in _FLAG_LAYOUT:",
        "        value = int(getattr(flags, fid, 0))",
        "        mask = (1 << width) - 1",
        "        bitfield |= (value & mask) << offset",
        "    chars = []",
        "    remaining = bitfield",
        "    for _ in range(FLAG_STRING_LENGTH):",
        "        chars.append(BASE64_ALPHABET[remaining & 0x3F])",
        "        remaining >>= 6",
        '    return "".join(chars)',
        "",
        "",
        "def decode_flags(flag_string: str) -> Flags:",
        '    """Decode a base62 flag string into a Flags instance.',
        "",
        "    Short strings are right-padded with '0' for backwards compatibility.",
        "    Unrecognised characters raise ValueError.",
        '    """',
        "    # Validate characters",
        "    for ch in flag_string:",
        "        if ch not in BASE64_ALPHABET:",
        '            raise ValueError(f"Invalid character {ch!r} in flag string")',
        "    # Pad for backwards compatibility",
        '    flag_string = flag_string.ljust(FLAG_STRING_LENGTH, "A")',
        "    if len(flag_string) > FLAG_STRING_LENGTH:",
        "        raise ValueError(",
        '            f"Flag string length {len(flag_string)} exceeds maximum {FLAG_STRING_LENGTH}"',
        "        )",
        "    bitfield = 0",
        "    for i, ch in enumerate(flag_string):",
        "        bitfield |= BASE64_ALPHABET.index(ch) << (i * 6)",
        "    kwargs: dict[str, Any] = {}",
        "    for fid, offset, width in _FLAG_LAYOUT:",
        "        flag_def = _FLAG_DEFS[fid]",
        '        if not flag_def.get("enabled", True):',
        "            continue  # disabled flags are not fields on the Flags dataclass",
        "        mask = (1 << width) - 1",
        "        raw = (bitfield >> offset) & mask",
        "        # Map raw int to appropriate type",
        '        if flag_def["type"] == "tristate":',
        "            kwargs[fid] = Tristate(min(raw, 2))  # clamp; 3 is invalid → OFF",
        '        elif flag_def["type"] == "item":',
        '            max_item = max(e["index"] for e in _ITEM_ENUM)',
        "            kwargs[fid] = Item(raw) if raw <= max_item else Item.RANDOM",
        '        elif flag_def["type"] == "enum":',
        "            from importlib import import_module as _im",
        "            _mod = _im(__name__)",
        '            _cls_name = "".join(w.capitalize() for w in fid.split("_"))',
        "            _cls = getattr(_mod, _cls_name)",
        '            max_val = len(flag_def["values"]) - 1',
        "            kwargs[fid] = _cls(min(raw, max_val))",
        "        else:",
        "            kwargs[fid] = bool(raw)",
        "    return Flags(**kwargs)",
        "",
        "",
        "def encode_cosmetic_flags(flags: CosmeticFlags) -> str:",
        '    """Encode a CosmeticFlags instance to a cosmetic flag string."""',
        "    bitfield = 0",
        "    for fid, offset, width in _COSMETIC_FLAG_LAYOUT:",
        "        value = int(getattr(flags, fid, 0))",
        "        mask = (1 << width) - 1",
        "        bitfield |= (value & mask) << offset",
        "    chars = []",
        "    remaining = bitfield",
        "    for _ in range(COSMETIC_FLAG_STRING_LENGTH):",
        "        chars.append(BASE64_ALPHABET[remaining & 0x3F])",
        "        remaining >>= 6",
        '    return "".join(chars)',
        "",
        "",
        "def decode_cosmetic_flags(flag_string: str) -> CosmeticFlags:",
        '    """Decode a cosmetic flag string into a CosmeticFlags instance.',
        "",
        "    Short strings are right-padded with 'A' (vanilla defaults).",
        "    Unrecognised characters raise ValueError.",
        '    """',
        "    for ch in flag_string:",
        "        if ch not in BASE64_ALPHABET:",
        '            raise ValueError(f"Invalid character {ch!r} in cosmetic flag string")',
        '    flag_string = flag_string.ljust(COSMETIC_FLAG_STRING_LENGTH, "A")',
        "    if len(flag_string) > COSMETIC_FLAG_STRING_LENGTH:",
        "        raise ValueError(",
        '            f"Cosmetic flag string length {len(flag_string)} exceeds maximum {COSMETIC_FLAG_STRING_LENGTH}"',
        "        )",
        "    bitfield = 0",
        "    for i, ch in enumerate(flag_string):",
        "        bitfield |= BASE64_ALPHABET.index(ch) << (i * 6)",
        "    kwargs: dict[str, Any] = {}",
        "    for fid, offset, width in _COSMETIC_FLAG_LAYOUT:",
        "        flag_def = _FLAG_DEFS[fid]",
        '        if not flag_def.get("enabled", True):',
        "            continue",
        "        mask = (1 << width) - 1",
        "        raw = (bitfield >> offset) & mask",
        '        if flag_def["type"] == "tristate":',
        "            kwargs[fid] = Tristate(min(raw, 2))",
        '        elif flag_def["type"] == "enum":',
        "            from importlib import import_module as _im",
        "            _mod = _im(__name__)",
        '            _cls_name = "".join(w.capitalize() for w in fid.split("_"))',
        "            _cls = getattr(_mod, _cls_name)",
        '            max_val = len(flag_def["values"]) - 1',
        "            kwargs[fid] = _cls(min(raw, max_val))",
        '        elif flag_def["type"] == "color":',
        "            kwargs[fid] = min(raw, (1 << width) - 1)",
        "        else:",
        "            kwargs[fid] = bool(raw)",
        "    return CosmeticFlags(**kwargs)",
        "",
        "",
    ]

    # Static metadata dict for runtime use
    lines += [
        "# ===========================================================================",
        "# RUNTIME METADATA",
        "# ===========================================================================",
        "",
        "# Full flag definitions for runtime introspection (e.g. UI generation)",
        "# enum-type flags have 'index' injected into each value entry at generation time.",
        "_FLAG_DEFS: dict[str, dict[str, Any]] = {",
    ]
    for flag in flags:
        lines.append(f"    {_dq(flag['id'])}: {{")
        for k, v in flag.items():
            if k == "values" and flag.get("type") == "enum":
                # Inject positional index into each enum value
                indexed = [{**entry, "index": i} for i, entry in enumerate(v)]
                lines.extend(_emit_flag_def_value("        ", k, indexed))
            else:
                lines.extend(_emit_flag_def_value("        ", k, v))
        lines.append("    },")
    lines += [
        "}",
        "",
        "_ITEM_ENUM: list[dict[str, Any]] = [",
    ]
    for entry in sorted_items:
        lines.append(f"    {_dq_repr(entry)},")
    lines += [
        "]",
        "",
        "",
    ]

    # Pool computation
    lines += [
        "# ===========================================================================",
        "# ITEM POOL COMPUTATION",
        "# ===========================================================================",
        "",
        "# Maps flag id → items it adds to the pool when resolved to ON",
        "_POOL_CONTRIBUTIONS: dict[str, list[str]] = {",
        '    "shuffle_dungeon_items": [',
        '        "bow", "boomerang", "magical_boomerang", "raft", "ladder",',
        '        "recorder", "wand", "red_candle", "magical_key",',
        '        "silver_arrows", "red_ring",',
        '        # TODO: confirm "book_of_magic" item_enum id with data_model.py',
        "    ],",
        '    "shuffle_dungeon_hearts": ["heart_container"],  # adds 8',
        '    "shuffle_letter": ["letter"],',
        '    "shuffle_wood_sword": ["wood_sword"],',
        '    "shuffle_magical_sword": ["magical_sword"],',
        '    "shuffle_major_shop_items": ["wood_arrows", "blue_candle", "blue_ring", "bait"],',
        '    "shuffle_blue_potion": ["blue_potion"],',
        "}",
        "",
        "",
        "def compute_active_pool(flags: Flags) -> set[str]:",
        '    """Return the set of item ids currently in the shuffle pool.',
        "",
        "    Call this on fully-resolved flags (after resolve_random_flags).",
        "    Random tristate values are treated as OFF for pool computation.",
        '    """',
        "    pool: set[str] = set()",
        "    for flag_id, items in _POOL_CONTRIBUTIONS.items():",
        "        value = getattr(flags, flag_id, Tristate.OFF)",
        "        if value == Tristate.ON:",
        "            pool.update(items)",
        "    # The coast location contains a heart container in vanilla.",
        "    # When coast_item is shuffled (anything other than NOT_SHUFFLED),",
        "    # that heart container enters the pool regardless of shuffle_dungeon_hearts.",
        '    not_shuffled_index = next(e["index"] for e in _ITEM_ENUM if e["id"] == "not_shuffled")',
        "    if int(flags.coast_item) != not_shuffled_index:",
        '        pool.add("heart_container")',
        "    return pool",
        "",
        "",
    ]

    # Random resolution
    lines += [
        "# ===========================================================================",
        "# RANDOM FLAG RESOLUTION",
        "# ===========================================================================",
        "",
        "# Dependency graph: maps flag_id → list of flag_ids that depend on it",
        "_DEPENDENTS: dict[str, list[str]] = {",
    ]
    dependents: dict[str, list[str]] = {}
    for flag in flags:
        dep = flag.get("depends_on")
        if dep:
            dependents.setdefault(dep, []).append(flag["id"])
    for parent, children in dependents.items():
        lines.extend(_emit_flag_def_value("    ", parent, children))
    lines += [
        "}",
        "",
        "",
        "def resolve_random_flags(flags: Flags, rng: Rng) -> Flags:",
        '    """Resolve all RANDOM tristate values to ON or OFF.',
        "",
        "    Resolution is performed in dependency order: prerequisites are resolved",
        "    before dependents. If a prerequisite resolves to OFF, all dependent",
        "    flags cascade to OFF regardless of their own setting.",
        "",
        "    Args:",
        "        flags: Flags instance (may contain Tristate.RANDOM values)",
        "        rng:   random.Random instance (or compatible) for coin flips",
        "    Returns:",
        "        New Flags instance with all tristate values resolved to ON or OFF.",
        '    """',
        "    import copy",
        "    resolved = copy.copy(flags)",
        "",
        "    # Topological order: process parents before children.",
        "    # Simple approach: iterate until stable (safe for shallow graphs).",
        "    changed = True",
        "    while changed:",
        "        changed = False",
        "        for flag_id, offset, width in _FLAG_LAYOUT:",
        "            flag_def = _FLAG_DEFS[flag_id]",
        '            if flag_def["type"] != "tristate":',
        "                continue",
        '            if not flag_def.get("enabled", True):',
        "                continue  # skip disabled flags",
        "            current = getattr(resolved, flag_id)",
        "            if current != Tristate.RANDOM:",
        "                continue",
        "            # Check if this flag's prerequisite has been resolved",
        '            dep = flag_def.get("depends_on")',
        "            if dep:",
        "                dep_value = getattr(resolved, dep)",
        "                if dep_value == Tristate.OFF:",
        "                    # Cascade: prerequisite is off, force this flag off",
        "                    object.__setattr__(resolved, flag_id, Tristate.OFF)",
        "                    changed = True",
        "                    continue",
        "                if dep_value == Tristate.RANDOM:",
        "                    # Prerequisite not yet resolved; skip for now",
        "                    continue",
        "            # Resolve randomly",
        "            flipped = Tristate.ON if rng.random() < 0.5 else Tristate.OFF",
        "            object.__setattr__(resolved, flag_id, flipped)",
        "            changed = True",
        "    return resolved",
        "",
        "",
    ]

    # Schema version check
    lines += [
        "# ===========================================================================",
        "# SCHEMA VERSION CHECK",
        "# ===========================================================================",
        "",
        f"SCHEMA_VERSION = {version}",
        f"SCHEMA_HASH = {_dq(schema_hash)}",
        "",
    ]

    return "\n".join(lines)


# =============================================================================
# MAIN
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="Validate flags.yaml")
    parser.add_argument("--generate", action="store_true",
                        help="Regenerate flags_generated.py")
    args = parser.parse_args()

    try:
        schema = load_and_validate(FLAGS_YAML)
        flag_count = len(schema["flags"])
        enabled_count = sum(1 for f in schema["flags"] if f.get("enabled", True))
        constraint_count = len(schema.get("constraints", []))
        print(
            f"✓ flags.yaml is valid "
            f"({flag_count} flags, {enabled_count} enabled, "
            f"{constraint_count} constraints)"
        )
    except (ValueError, yaml.YAMLError) as e:
        print(f"✗ flags.yaml validation failed: {e}", file=sys.stderr)
        sys.exit(1)

    if args.generate:
        schema_hash = compute_schema_hash(FLAGS_YAML)
        content = generate_flags_module(schema, schema_hash)
        FLAGS_GENERATED.write_text(content)
        print(f"✓ Generated {FLAGS_GENERATED}")


if __name__ == "__main__":
    main()
