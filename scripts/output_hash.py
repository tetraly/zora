"""ZORA output hashes: did a change alter generated ROMs? (measurement only)

    python3 scripts/output_hash.py [--seeds N] [--code DIR] [--json OUT]
    python3 scripts/output_hash.py --compare BASE.json HEAD.json

Generates seeds 0..N-1 with the post-shapes passes on and off, serializes each
onto the PRG0 base ROM and prints one combined SHA-1 per mode; --json writes
the per-seed hashes. --code DIR imports `zora` from another checkout (a git
worktree of an older revision), so scripts/verify.sh can hash that revision
with this same script. --compare lists the seeds whose output differs and
exits 1 if any does.
"""
import argparse
import hashlib
import json
import os
import sys
from multiprocessing import Pool
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BASE_ROM = REPO / "Legend of Zelda, The (USA).nes"
MODES = {"b1_on": True, "b1_off": False}

# Workers re-import this module, so the code location travels in the
# environment rather than in argv.
sys.path.insert(0, os.environ.get("ZORA_CODE_DIR", str(REPO)))


def _has_flag_generation() -> bool:
    """Whether the checkout being hashed generates from flag strings."""
    import importlib.util
    return importlib.util.find_spec("zora.generate") is not None


def seed_hash(args: tuple[int, bool]) -> str:
    """SHA-1 of one seed's finished ROM."""
    seed, post_shapes = args
    from zora.rom.base_rom import verify_base_rom
    from zora.rom.game_config import GameConfig, HintMode
    from zora.rom.parse.rom_file import load_rom, parse_rom
    from zora.rom.serialize.rom_file import serialize_to_rom
    from zora.generate.rng import Rng
    from zora.generate.generation_pass import generate_shapes
    from zora.generate.shapes.options import ShapeOptions
    base = load_rom(verify_base_rom(BASE_ROM))
    if post_shapes and _has_flag_generation():
        # The full output from the MVP baseline flag string, level encoding off
        from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
        from zora.generate.pipeline import generate_rom
        return hashlib.sha1(generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, seed, base).rom).hexdigest()
    # b1_off (the shape stage straight into the late gate) is a test mode no
    # flag string selects; revisions before zora.generate take this path too.
    world = parse_rom(base)
    generate_shapes(world, Rng(seed), ShapeOptions(), post_shapes=post_shapes,
                    feature_data=post_shapes, seed=seed)
    # Consternation hint text requires the B1 hint-assignment pass; b1_off
    # leaves hints in their vanilla state. b1_on is the full Consternation
    # output, with the B10 code patches; b1_off keeps PRG0's code.
    hint_mode = HintMode.CONSTERNATION if post_shapes else HintMode.VANILLA
    config = GameConfig(hint_mode=hint_mode, features_b10=post_shapes)
    return hashlib.sha1(serialize_to_rom(world, base, config=config)).hexdigest()


def combined(hashes: list[str]) -> str:
    return hashlib.sha1("".join(hashes).encode()).hexdigest()


def compare(base_path: Path, head_path: Path) -> int:
    base, head = json.loads(base_path.read_text()), json.loads(head_path.read_text())
    changed = False
    for mode in MODES:
        differing = [seed for seed, (a, b) in enumerate(zip(base[mode], head[mode])) if a != b]
        if differing:
            changed = True
            print(f"{mode}: {len(differing)} of {len(head[mode])} seeds differ: {differing[:20]}")
        else:
            print(f"{mode}: identical ({len(head[mode])} seeds)")
    return 1 if changed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--code", type=Path, help="import zora from this checkout")
    ap.add_argument("--json", type=Path, help="write per-seed hashes here")
    ap.add_argument("--compare", type=Path, nargs=2, metavar=("BASE", "HEAD"))
    args = ap.parse_args()
    if args.compare:
        return compare(*args.compare)
    if args.code:
        os.environ["ZORA_CODE_DIR"] = str(args.code.resolve())
        sys.path.insert(0, os.environ["ZORA_CODE_DIR"])
    result: dict[str, list[str]] = {}
    with Pool() as pool:
        for mode, post_shapes in MODES.items():
            result[mode] = pool.map(seed_hash, [(seed, post_shapes) for seed in range(args.seeds)])
            print(f"{mode}: {args.seeds} seeds, combined sha1 {combined(result[mode])}")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
