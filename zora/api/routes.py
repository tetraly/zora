"""ZORA API endpoint handlers. See doc/API_SPEC.md for full specification."""
from __future__ import annotations

import logging
import signal
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from flask import Blueprint, jsonify, request

from zora.api.validation import (
    CosmeticFlags,
    decode_cosmetic_flags,
    decode_flags,
    parse_cosmetic_flag_string,
    parse_flag_string,
    parse_seed,
    resolve_random_flags,
    validate_flags_static,
)
from zora.generate_game import generate_game, generate_game_from_rom
from zora.patch import encode_patch
from zora.version import __version__

# Ensure flags/ is importable (mirrors validation.py path setup)
_FLAGS_DIR = Path(__file__).parent.parent.parent / "flags"
if str(_FLAGS_DIR) not in sys.path:
    sys.path.insert(0, str(_FLAGS_DIR))

_FLAGS_YAML = _FLAGS_DIR / "flags.yaml"

log = logging.getLogger(__name__)

bp = Blueprint("api", __name__)

VERSION = __version__
SLOW_REQUEST_THRESHOLD_S = 3.0
GENERATION_TIMEOUT_S = 50


class _GenerationTimeout(Exception):
    pass


def _timeout_handler(signum: int, frame: Any) -> None:
    raise _GenerationTimeout()


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------

def _err(code: str, message: str, http_status: int, details: list[str] | None = None) -> Any:
    body: dict[str, object] = {"error": code, "message": message}
    if details is not None:
        body["details"] = details
    return jsonify(body), http_status


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@bp.get("/health")
def health() -> Any:
    return jsonify({"status": "ok", "version": VERSION})


# ---------------------------------------------------------------------------
# GET /flags
# ---------------------------------------------------------------------------

@bp.get("/flags")
def flags() -> Any:
    try:
        schema = yaml.safe_load(_FLAGS_YAML.read_text())
    except Exception:
        log.exception("Failed to load flags.yaml")
        return _err("internal_error", "Failed to load flag definitions", 500)

    meta = schema["meta"]
    all_flags = schema["flags"]
    item_enum = schema["item_enum"]

    # Only enabled flags, sorted by display_order within group
    enabled_flags = [f for f in all_flags if f.get("enabled", True)]
    enabled_flags.sort(key=lambda f: (f["group"], f["display_order"]))

    # Derive groups from flags
    seen_groups: dict[str, int] = {}
    for f in enabled_flags:
        group = f["group"]
        if group not in seen_groups:
            seen_groups[group] = f["display_order"]

    groups = [
        {"id": name, "display_order": i + 1}
        for i, name in enumerate(seen_groups)
    ]

    # Strip internal-only fields from flag defs before sending.
    # Inject positional 'index' into enum values so the frontend has a
    # guaranteed integer for every multi-value flag (item flags already have it).
    omit = {"phase"}
    clean_flags = []
    for f in enabled_flags:
        cleaned = {k: v for k, v in f.items() if k not in omit}
        if f.get("type") == "enum" and "values" in f:
            cleaned["values"] = [
                {**entry, "index": i} for i, entry in enumerate(f["values"])
            ]
        clean_flags.append(cleaned)

    cosmetic_meta = schema.get("cosmetic_meta", {})
    response = jsonify({
        "version": VERSION,
        "schema_version": meta["format_version"],
        "string_length": meta["string_length"],
        "cosmetic_string_length": cosmetic_meta.get("string_length", 0),
        "flags": clean_flags,
        "item_enum": sorted(item_enum, key=lambda e: e["index"]),
        "groups": groups,
        "constraints": schema.get("constraints", []),
        "nes_color_palette": schema.get("nes_color_palette", []),
    })
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


# ---------------------------------------------------------------------------
# POST /generate
# ---------------------------------------------------------------------------

@bp.post("/generate")
def generate() -> Any:
    t_start = time.monotonic()

    # 1. Parse request JSON
    body = request.get_json(silent=True) or {}
    raw_flag_string = body.get("flag_string")
    if raw_flag_string is None:
        return _err("invalid_flag_string", "flag_string is required", 400, details=[])

    rom_version = body.get("rom_version")
    if rom_version is not None and (not isinstance(rom_version, int) or rom_version < 0):
        return _err("invalid_rom_version", "rom_version must be a non-negative integer", 400)

    # Parse optional cosmetic flag string (defaults to vanilla when absent)
    raw_cosmetic_flag_string = body.get("cosmetic_flag_string", "")
    cosmetic_flag_string, cosmetic_errors = parse_cosmetic_flag_string(raw_cosmetic_flag_string)
    if cosmetic_errors:
        return _err("invalid_cosmetic_flag_string", cosmetic_errors[0], 400, details=[])
    cosmetic_flags: CosmeticFlags = decode_cosmetic_flags(cosmetic_flag_string)

    # 2 & 3. Validate flag string and decode
    flag_string, flag_errors = parse_flag_string(raw_flag_string)
    if flag_errors:
        return _err("invalid_flag_string", flag_errors[0], 400, details=[])

    flags = decode_flags(flag_string)

    # 4. Static validation
    static_errors = validate_flags_static(flags)
    if static_errors:
        return _err(
            "validation_failed",
            "Flag combination is not valid",
            400,
            details=static_errors,
        )

    # 5. Resolve seed
    import random as _random
    seed, seed_error = parse_seed(body.get("seed"))
    if seed_error:
        return _err("invalid_seed", seed_error, 400)
    assert seed is not None

    # 6. Resolve random flags
    rng = _random.Random(seed)
    resolved_flags = resolve_random_flags(flags, rng)

    # 7. Post-resolution validation
    post_errors = validate_flags_static(resolved_flags)
    if post_errors:
        return _err(
            "validation_failed",
            "Flag combination is not valid after resolution",
            400,
            details=post_errors,
        )

    # 8 & 9. Run randomizer and generate patch
    old_handler = signal.getsignal(signal.SIGALRM)
    try:
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(GENERATION_TIMEOUT_S)
        patch_bytes, hash_code, spoiler_log, spoiler_data = generate_game(
            resolved_flags, seed, flag_string=flag_string,
            rom_version=rom_version, cosmetic_flags=cosmetic_flags,
        )
        signal.alarm(0)
    except _GenerationTimeout:
        log.warning("Generation timed out after %ds: seed=%s flags=%s",
                    GENERATION_TIMEOUT_S, seed, flag_string)
        return _err(
            "generation_timeout",
            "Seed generation took too long. Please try a different seed.",
            503,
        )
    except RuntimeError:
        signal.alarm(0)
        log.exception("Randomizer failed for seed=%s flags=%s", seed, flag_string)
        return _err(
            "generation_failed",
            "Randomizer could not produce a valid seed within iteration limit",
            500,
        )
    finally:
        signal.signal(signal.SIGALRM, old_handler)

    elapsed = time.monotonic() - t_start
    if elapsed > SLOW_REQUEST_THRESHOLD_S:
        log.warning("Slow generation: %.2fs seed=%s flags=%s", elapsed, seed, flag_string)

    # 10. Build response
    return jsonify({
        "seed": str(seed),
        "flag_string": flag_string,
        "cosmetic_flag_string": cosmetic_flag_string,
        "rom_version": rom_version,
        "patch": encode_patch(patch_bytes),
        "patch_format": "ips",
        "hash_code": hash_code,
        "spoiler_log": spoiler_log,
        "spoiler_data": spoiler_data,
    })


# ---------------------------------------------------------------------------
# POST /generate/rerandomize
# ---------------------------------------------------------------------------

_NES_ROM_SIZE = 0x10 + 0x20000  # iNES header + 128 KB PRG

@bp.post("/generate/rerandomize")
def generate_rerandomize() -> Any:
    t_start = time.monotonic()

    # 1. Validate ROM file
    rom_file = request.files.get("rom")
    if rom_file is None:
        return _err("missing_rom", "rom file is required", 400)
    rom_bytes = rom_file.read()
    if len(rom_bytes) != _NES_ROM_SIZE:
        return _err(
            "invalid_rom",
            f"ROM must be exactly {_NES_ROM_SIZE} bytes (got {len(rom_bytes)})",
            400,
        )

    # 2. Parse flags from form fields
    raw_flag_string = request.form.get("flag_string")
    if raw_flag_string is None:
        return _err("invalid_flag_string", "flag_string is required", 400, details=[])

    rom_version_raw = request.form.get("rom_version")
    rom_version: int | None = None
    if rom_version_raw is not None:
        try:
            rom_version = int(rom_version_raw)
            if rom_version < 0:
                raise ValueError
        except ValueError:
            return _err("invalid_rom_version", "rom_version must be a non-negative integer", 400)

    # Parse optional cosmetic flag string (defaults to vanilla when absent)
    raw_cosmetic_flag_string = request.form.get("cosmetic_flag_string", "")
    cosmetic_flag_string, cosmetic_errors = parse_cosmetic_flag_string(raw_cosmetic_flag_string)
    if cosmetic_errors:
        return _err("invalid_cosmetic_flag_string", cosmetic_errors[0], 400, details=[])
    cosmetic_flags_rr: CosmeticFlags = decode_cosmetic_flags(cosmetic_flag_string)

    # 3. Validate and decode flags
    flag_string, flag_errors = parse_flag_string(raw_flag_string)
    if flag_errors:
        return _err("invalid_flag_string", flag_errors[0], 400, details=[])

    flags = decode_flags(flag_string)

    static_errors = validate_flags_static(flags)
    if static_errors:
        return _err("validation_failed", "Flag combination is not valid", 400, details=static_errors)

    # 4. Resolve seed
    import random as _random
    seed, seed_error = parse_seed(request.form.get("seed"))
    if seed_error:
        return _err("invalid_seed", seed_error, 400)
    assert seed is not None

    # 5. Resolve random flags
    rng = _random.Random(seed)
    resolved_flags = resolve_random_flags(flags, rng)

    post_errors = validate_flags_static(resolved_flags)
    if post_errors:
        return _err(
            "validation_failed",
            "Flag combination is not valid after resolution",
            400,
            details=post_errors,
        )

    # 6. Run rerandomizer (validates ROM magic internally)
    old_handler = signal.getsignal(signal.SIGALRM)
    try:
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(GENERATION_TIMEOUT_S)
        patch_bytes, hash_code, spoiler_log, spoiler_data = generate_game_from_rom(
            rom_bytes, resolved_flags, seed, flag_string=flag_string,
            rom_version=rom_version, cosmetic_flags=cosmetic_flags_rr,
        )
        signal.alarm(0)
    except _GenerationTimeout:
        log.warning("Rerandomize timed out after %ds: seed=%s flags=%s",
                    GENERATION_TIMEOUT_S, seed, flag_string)
        return _err(
            "generation_timeout",
            "Seed generation took too long. Please try a different seed.",
            503,
        )
    except ValueError as exc:
        signal.alarm(0)
        return _err("invalid_rom", str(exc), 400)
    except RuntimeError:
        signal.alarm(0)
        log.exception("Rerandomizer failed for seed=%s flags=%s", seed, flag_string)
        return _err(
            "generation_failed",
            "Randomizer could not produce a valid seed within iteration limit",
            500,
        )
    finally:
        signal.signal(signal.SIGALRM, old_handler)

    elapsed = time.monotonic() - t_start
    if elapsed > SLOW_REQUEST_THRESHOLD_S:
        log.warning("Slow rerandomize: %.2fs seed=%s flags=%s", elapsed, seed, flag_string)

    return jsonify({
        "seed": str(seed),
        "flag_string": flag_string,
        "cosmetic_flag_string": cosmetic_flag_string,
        "rom_version": rom_version,
        "patch": encode_patch(patch_bytes),
        "patch_format": "ips",
        "hash_code": hash_code,
        "spoiler_log": spoiler_log,
        "spoiler_data": spoiler_data,
    })


# ---------------------------------------------------------------------------
# POST /generate/race  (Phase 1 stub)
# ---------------------------------------------------------------------------

@bp.post("/generate/race")
def generate_race() -> Any:
    return _err("not_implemented", "Race ROM generation is not yet available", 501)
