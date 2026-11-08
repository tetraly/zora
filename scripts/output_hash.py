"""ZORA output hashes: did a change alter generated ROMs? (measurement only)

    python3 scripts/output_hash.py [--seeds N] [--code DIR] [--json OUT]
    python3 scripts/output_hash.py --matrix [--matrix-seeds N] [--matrix-jobs N] [--code DIR] [--json OUT]
    python3 scripts/output_hash.py --compare BASE.json HEAD.json

Generates seeds 0..N-1 with the post-shapes passes on and off, serializes each
onto the PRG0 base ROM and prints one combined SHA-1 per mode; --json writes
the per-seed hashes. --matrix hashes the ROM matrix instead: every flag case of
tests/archipelago_cases.py and zora.flags.presets, and matrix_jobs()'s own cases, seeds
1-4 (--matrix-seeds N: seeds 1-N; the quick check hashes 2, the batch run all 4), with each ROM's seed
document and spoiler log; a case needing a ZORA flag the hashed revision
lacks is recorded as not in that revision, and --compare lists it as new rather than different. --code DIR imports `zora` from another revision's files
(scripts/compare_revision.py exports them), so that revision is hashed with this
same script and, for the matrix, this checkout's cases; the run stops if `zora`
would come from anywhere else. --compare lists the seeds or matrix entries whose
output differs, with the matrix's count of differing ROMs, seed documents and spoiler logs, and exits 1
if any does.
"""
import argparse
import hashlib
import json
import multiprocessing
import os
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
BASE_ROM = REPO / "Legend of Zelda, The (USA).nes"
MODES = {"b1_on": True, "b1_off": False}
MATRIX = "matrix"
MATRIX_SEED_COUNT = 4         # seeds 1-4 of each case: the batch run's and --full-matrix's; the quick check's 2
# A matrix entry's hashed fields, as the comparison names them
FIELD_NAMES = {"rom": "ROMs", "document": "seed documents", "log": "spoiler logs"}
CODE_DIR_SETTING = "ZORA_CODE_DIR"

# Workers re-import this module, so the code location travels in the
# environment rather than in argv.
sys.path.insert(0, os.environ.get(CODE_DIR_SETTING, str(REPO)))


class WrongCode(RuntimeError):
    """A package came from somewhere other than the --code folder."""


def check_code_dir(*modules: Any) -> None:
    """With --code, each module must come from that folder: the folder is only put first on
    the path, so a folder without the package would silently hash this checkout instead."""
    code = os.environ.get(CODE_DIR_SETTING)
    if not code:
        return
    for module in modules:
        if not Path(module.__file__).resolve().is_relative_to(Path(code).resolve()):
            raise WrongCode(f"{module.__name__} was imported from {module.__file__}, not from {code}")


def code_dir_problem(code: Path) -> str | None:
    if not (code / "zora" / "__init__.py").is_file():
        return f"{code} holds no zora package to hash"
    return None


def _has_flag_generation() -> bool:
    """Whether the checkout being hashed generates from flag strings."""
    import importlib.util
    return importlib.util.find_spec("zora.generate") is not None


def seed_hash(args: tuple[int, bool]) -> str:
    """SHA-1 of one seed's finished ROM."""
    seed, post_shapes = args
    import zora
    check_code_dir(zora)
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


# (case, flag string, ZORA flag string, seed, the ZORA field it needs: "" for none). A revision whose
# ZoraFlags lacks that field records NOT_IN_REVISION for each hash, and the comparison lists the entry
# as new, not as a difference
MatrixJob = tuple[str, str, str, int, str]
NOT_IN_REVISION = "not in this revision"


def matrix_jobs(seed_count: int = MATRIX_SEED_COUNT) -> list[MatrixJob]:
    """(case, flag string, ZORA flag string, seed, needed field) for every matrix ROM, seeds 1 to SEED_COUNT
    of each case, from this checkout's cases: a revision hashed with --code gets the same inputs."""
    from dataclasses import replace

    from tests.archipelago_cases import FLAG_CASES
    from tests.test_coop_reserved import z1r_with
    from zora.flags import zora_flags
    from zora.flags.fields import ThreeState
    from zora.flags.presets import MVP_BASELINE, MVP_BASELINE_LEVEL_ENCODING_OFF, ZORA_PRESETS
    # Matrix-only cases: settings no flag case or preset turns on, so the release tripwires cover them
    cases = {**FLAG_CASES, **ZORA_PRESETS, "MVP baseline (encoded)": (MVP_BASELINE, ""),
             "baseline, ZORA 1.2": (MVP_BASELINE_LEVEL_ENCODING_OFF, "1.2"),
             "change secret spots": (z1r_with(toggles={"B05": ThreeState.ON}), ""),
             "remove maps, all maps and all compasses": (
                 z1r_with(toggles=dict.fromkeys(("B92", "B93", "B94"), ThreeState.ON)), ""),
             "mirror overworld": (z1r_with(toggles={"B06": ThreeState.ON}), ""),
             # Harder Bosses and Harder Ganon (ZORA version 14), each at Level 3
             "harder bosses": (MVP_BASELINE_LEVEL_ENCODING_OFF, zora_flags.encode(
                 zora_flags.ZoraFlags(harder_bosses=zora_flags.HarderLevel.LEVEL_3))),
             "harder ganon": (MVP_BASELINE_LEVEL_ENCODING_OFF, zora_flags.encode(
                 zora_flags.ZoraFlags(harder_ganon=zora_flags.HarderLevel.LEVEL_3))),
             # The pacing settings and Recorder Warping (with the recorder warping to unbeaten dungeons)
             # (ZORA version 15)
             "offense pacing earlier": (MVP_BASELINE_LEVEL_ENCODING_OFF, zora_flags.encode(
                 zora_flags.ZoraFlags(offense_pacing=zora_flags.Pacing.EARLIER))),
             "defense pacing later": (MVP_BASELINE_LEVEL_ENCODING_OFF, zora_flags.encode(
                 zora_flags.ZoraFlags(defense_pacing=zora_flags.Pacing.LATER))),
             "recorder warping": (z1r_with(toggles={"B07": ThreeState.ON}), zora_flags.encode(
                 zora_flags.ZoraFlags(recorder_warping=True)))}
    # Universal Drops v2.0 (ZORA version 19): on the baseline (Shuffle Dungeon Drops, B15, on there); with
    # Shuffle Minor Dungeon Drops (B17) and Remove Most Open Stairs (B30), which move items or change
    # layouts after the shape stage; with Add L4 Sword and Highlight No-Drop Rooms, which take its drop squares
    v2 = zora_flags.ZoraFlags(universal_drops_v2=ThreeState.ON)
    new_cases = {
        "universal drops v2.0": (MVP_BASELINE_LEVEL_ENCODING_OFF, v2),
        "universal drops v2.0, B17 and B30": (z1r_with(toggles={"B17": ThreeState.ON, "B30": ThreeState.ON}),
                                              v2),
        "universal drops v2.0, L4 sword and highlight": (MVP_BASELINE_LEVEL_ENCODING_OFF, replace(
            v2, add_l4_sword=ThreeState.ON, progressive_items=True, highlight_no_drop_rooms=ThreeState.ON))}
    seeds = range(1, seed_count + 1)
    jobs = [(name, flags, extras, seed, "") for name, (flags, extras) in cases.items() for seed in seeds]
    return jobs + [(name, flags, zora_flags.encode(chosen), seed, "universal_drops_v2")
                   for name, (flags, chosen) in new_cases.items() for seed in seeds]


def _outcome(make: Any) -> str:
    """SHA-1 of what make() returns; a refusal is part of the output, so it is recorded too."""
    try:
        data = make()
    except Exception as error:      # every refusal is an outcome to compare
        return f"{type(error).__name__}: {error}"
    return hashlib.sha1(data if isinstance(data, bytes) else data.encode()).hexdigest()


def matrix_hash(job: MatrixJob) -> tuple[str, dict[str, str]]:
    """One matrix ROM's hashes: the ROM, its seed document and its spoiler log."""
    name, flags, zora_flags, seed, needs = job
    import zora
    check_code_dir(zora)
    if needs and not _has_zora_field(needs):
        return f"{name} / seed {seed}", dict.fromkeys(FIELD_NAMES, NOT_IN_REVISION)
    from zora.generate.pipeline import generate_rom
    from zora.rom.base_rom import remember_repo_base_rom

    base = remember_repo_base_rom()
    rom = b""

    def make_rom() -> bytes:
        nonlocal rom
        rom = generate_rom(flags, seed, base, zora_flag_string=zora_flags).rom
        return rom

    def document() -> Any:
        import zora_export
        check_code_dir(zora_export)
        from zora_export.seed_document import seed_document_for
        return seed_document_for(rom, flags, seed, zora_flags)

    def log() -> str:
        from zora_export.spoiler_log import spoiler_log
        return spoiler_log(document())

    out = {"rom": _outcome(make_rom)}
    out["document"] = _outcome(lambda: json.dumps(document(), sort_keys=True)) if rom else "no ROM"
    out["log"] = _outcome(log) if rom else "no ROM"
    return f"{name} / seed {seed}", out


def _has_zora_field(name: str) -> bool:
    """Whether the revision being hashed has this ZORA flag."""
    import dataclasses
    from zora.flags.zora_flags import ZoraFlags
    return name in {field.name for field in dataclasses.fields(ZoraFlags)}


def new_entries(base: dict[str, Any], head: dict[str, Any]) -> list[str]:
    """Matrix entries the base revision could not make (a flag it lacks) and this one makes."""
    missing = dict.fromkeys(FIELD_NAMES, NOT_IN_REVISION)
    return [entry for entry, theirs in head.items() if base[entry] == missing and theirs != missing]


def combined(hashes: list[str]) -> str:
    return hashlib.sha1("".join(hashes).encode()).hexdigest()


def field_differences(base: dict[str, Any], head: dict[str, Any]) -> dict[str, int]:
    """How many matrix entries differ in each hashed field: the ROM, the seed document, the spoiler log.
    An entry stored as one hash (an older run) counts as its ROM."""
    counts = dict.fromkeys(FIELD_NAMES, 0)
    new = set(new_entries(base, head))
    for entry, theirs in head.items():
        if entry in new:
            continue
        ours = base[entry]
        if not (isinstance(ours, dict) and isinstance(theirs, dict)):
            counts["rom"] += ours != theirs
            continue
        for field in FIELD_NAMES:
            counts[field] += ours.get(field) != theirs.get(field)
    return counts


def compare(base_path: Path, head_path: Path) -> int:
    """Exit status 1 if any seed or matrix entry differs, 2 if the two files cover different
    seeds or entries (nothing to compare is not "identical")."""
    base, head = json.loads(base_path.read_text()), json.loads(head_path.read_text())
    if base.keys() != head.keys() or not head:
        print(f"output_hash: {base_path} and {head_path} hold different runs: {sorted(base)} vs {sorted(head)}")
        return 2
    changed = False
    for mode in head:
        if len(base[mode]) != len(head[mode]) or (mode == MATRIX and base[mode].keys() != head[mode].keys()):
            print(f"output_hash: {mode}: the two files cover different seeds or entries")
            return 2
        entries = base[mode].keys() if mode == MATRIX else range(len(head[mode]))
        new = new_entries(base[mode], head[mode]) if mode == MATRIX else []
        if new:
            print(f"{mode}: {len(new)} new, not in the base revision (not compared): {new[:20]}")
        differing = [entry for entry in entries if base[mode][entry] != head[mode][entry] and entry not in new]
        if differing:
            changed = True
            fields = ""
            if mode == MATRIX:
                counts = field_differences(base[mode], head[mode])
                fields = f" ({', '.join(f'{FIELD_NAMES[field]} {count}' for field, count in counts.items())})"
            print(f"{mode}: {len(differing)} of {len(head[mode]) - len(new)} differ{fields}: {differing[:20]}")
        else:
            print(f"{mode}: identical ({len(head[mode]) - len(new)})")
    return 1 if changed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--code", type=Path, help="import zora from this checkout")
    ap.add_argument("--json", type=Path, help="write per-seed hashes here")
    ap.add_argument("--compare", type=Path, nargs=2, metavar=("BASE", "HEAD"))
    ap.add_argument("--matrix", action="store_true", help="hash the ROM matrix instead of the seeds")
    ap.add_argument("--matrix-jobs", type=int, help="only the first N matrix ROMs")
    ap.add_argument("--matrix-seeds", type=int, default=MATRIX_SEED_COUNT, choices=range(1, MATRIX_SEED_COUNT + 1),
                    help=f"seeds 1-N of each matrix case (default {MATRIX_SEED_COUNT})")
    ap.add_argument("--workers", type=int, help="processes (default one per core)")
    args = ap.parse_args()
    if args.compare:
        return compare(*args.compare)
    # The matrix's cases are this checkout's, read before --code puts another revision first; and
    # progress (zora_measure/progress.py), imported here, in this process only, never in a worker
    jobs = matrix_jobs(args.matrix_seeds)[:args.matrix_jobs] if args.matrix else []
    from zora_measure.progress import track
    if args.code:
        if problem := code_dir_problem(args.code):
            print(f"output_hash: {problem}", file=sys.stderr)
            return 2
        os.environ[CODE_DIR_SETTING] = str(args.code.resolve())
        sys.path.insert(0, os.environ[CODE_DIR_SETTING])
    result: dict[str, Any] = {}
    # spawn: workers import zora afresh, from the --code folder, never this process's copy
    with multiprocessing.get_context("spawn").Pool(args.workers) as pool:
        if args.matrix:
            result[MATRIX] = dict(track(pool.imap(matrix_hash, jobs), "output_hash: the ROM matrix",
                                        total=len(jobs), unit="ROMs"))
            entries = [json.dumps(result[MATRIX][entry], sort_keys=True) for entry in sorted(result[MATRIX])]
            print(f"{MATRIX}: {len(jobs)} ROMs, combined sha1 {combined(entries)}")
        else:
            for mode, post_shapes in MODES.items():
                result[mode] = list(track(pool.imap(seed_hash, [(seed, post_shapes) for seed in range(args.seeds)]),
                                          f"output_hash: {mode}", total=args.seeds, unit="seeds"))
                print(f"{mode}: {args.seeds} seeds, combined sha1 {combined(result[mode])}")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
