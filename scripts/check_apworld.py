"""The release check for zora.apworld: a fresh Archipelago with only the built .apworld installed.

    python3 scripts/check_apworld.py [--rev REV | --uncommitted-world | --apworld PATH]
                                     [--players N] [--seed S] [--skip-newest] [--archipelago-repo URL]

1. Build zora.apworld (scripts/build_apworld.py; or check the one given with --apworld) and run
   the release's text checks on every file in it (scripts/make_release.py's: no mentions, no
   personal paths, no original-game bytes or text, against PRG0 and PRG1).
2. For each Archipelago: the required one (REQUIRED_ARCHIPELAGO, 0.6.8; must pass), then as warnings
   only, so a new Archipelago never blocks a ZORA release, the coming one (UPCOMING_ARCHIPELAGO,
   0.6.9) and any newer release (--skip-newest checks the required one only):
   - its source, fetched fresh into temp/archipelago-check/ (git archive of the exact commit), in a
     virtual environment with its own requirements (ModuleUpdate.py) and pytest;
   - the .apworld in custom_worlds/, host.yaml naming the PRG0 base ROM;
   - generate a multiworld: ZORA players whose YAMLs the web page's multiworld mode exports
     (zora_web.multiworld.export_yaml: the page's defaults, then random offered settings and
     player settings), and a ChecksFinder player;
   - build every ZORA patch into a ROM as a player's machine does (Patch.create_rom_file) from
     the PRG0 ROM, the PRG1 ROM and PRG0 with modified graphics (the organizer generated on
     PRG0): each ROM must carry its slot's identity and its own release's layout;
   - the world's own tests (its test/ folder, inside the .apworld) and Archipelago's general
     tests scoped to ZORA (AP_TEST_WORLDS=zora).
Exit status 1 if anything required fails. The first run downloads Archipelago and installs its
requirements (several minutes); later runs reuse the download and the environment.

Progress: the run is a job (zora_measure/progress.py) that reports its step once a minute.
"""
from __future__ import annotations

import argparse
import io
import os
import random
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import build_apworld  # noqa: E402 - the scripts folder above
import make_release  # type: ignore[import-not-found, unused-ignore]  # noqa: E402 - puts REPO on the path; a release leaves it out
from zora import archipelago as zora_ap  # noqa: E402
from zora.flags import form as flag_form  # noqa: E402
from zora.rom.base_rom import BASE_ROM_PATH, PRG1_ROM_PATH, verify_base_rom, verify_prg1_rom  # noqa: E402
from zora.rom.revision import GRAPHICS_BLOCKS, NES_HEADER_SIZE, Revision, identify_rom, layout_of  # noqa: E402
from zora.rom.slot_identity import MAX_NAME_LENGTH as SLOT_NAME_LENGTH  # noqa: E402
from zora.rom.slot_identity import SLOT_IDENTITY_ADDRESS, SLOT_IDENTITY_SIZE  # noqa: E402
from zora_measure.progress import Job, note_step  # noqa: E402
from zora_web import multiworld  # noqa: E402

WORK = REPO / "temp" / "archipelago-check"
ARCHIPELAGO_REPO = "https://github.com/ArchipelagoMW/Archipelago.git"


@dataclass(frozen=True)
class Archipelago:
    label: str
    ref: str            # a tag or a commit
    required: bool


# Owner ruling (2026-10-13): 0.6.8, the release players have, is required; 0.6.9 is a warning until it is
# released. On 2026-10-13 0.6.9 has no release tag: UPCOMING_ARCHIPELAGO is the commit that set its
# version to 0.6.9 and the one after it (the main branch then). Once 0.6.9 is released, the owner
# decides whether it becomes the required one.
REQUIRED_ARCHIPELAGO = Archipelago("0.6.8", "0.6.8", required=True)
UPCOMING_ARCHIPELAGO = Archipelago("0.6.9 (not yet released)", "9b64e832874a50d5d14d5bc599d356d2c5194d7a",
                                   required=False)
RELEASE_TAG = re.compile(r"^refs/tags/(\d+)\.(\d+)\.(\d+)$")
OTHER_GAME = ("Finder", "ChecksFinder")
TEST_REQUIREMENTS = ("pytest", "pytest-subtests", "pytest-xdist")
TEST_WORKERS = 2                        # beside another session's suite, as AGENTS.md allows without the lock
COMMAND_TIMEOUT = 1800                  # seconds: the first requirements install is the longest step
DEFAULT_PLAYERS = 6                     # ZORA players: the page's defaults and 5 random settings
DEFAULT_SEED = 13


@dataclass
class Result:
    name: str
    passed: bool
    detail: list[str] = field(default_factory=list)


_JOB: list[Job] = []


def progress(message: str) -> None:
    print(f"  ... {message}", flush=True)
    if _JOB:
        note_step(message, _JOB[0].id)


def run(command: list[str | Path], cwd: Path, env: dict[str, str] | None = None,
        timeout: int = COMMAND_TIMEOUT) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(part) for part in command], cwd=cwd, capture_output=True, text=True, check=False,
                          stdin=subprocess.DEVNULL, timeout=timeout, env={**os.environ, **(env or {})})


def tail(done: subprocess.CompletedProcess[str], lines: int = 15) -> list[str]:
    return (done.stdout + done.stderr).strip().splitlines()[-lines:]


# --- 1. the release's text checks on the .apworld --------------------------------------------

def repository_path(name: str) -> str:
    """A file's path in this repository from its path in the .apworld (build_apworld.apworld_path's
    inverse), so release/'s reviewed lists, which name repository paths, apply."""
    inside = name.removeprefix(f"{build_apworld.WORLD_FOLDER}/")
    if inside.startswith(f"{build_apworld.PACKAGE}/") or inside == build_apworld.LICENSE:
        return inside
    return f"{build_apworld.WORLD_SOURCE}/{inside}"


def apworld_texts(apworld: Path) -> list[tuple[str, str]]:
    """(repository path, text) for each text file in the .apworld."""
    texts = []
    with zipfile.ZipFile(apworld) as archive:
        for name in sorted(archive.namelist()):
            try:
                texts.append((repository_path(name), archive.read(name).decode("utf-8")))
            except UnicodeDecodeError:
                continue
    return texts


def text_checks(apworld: Path) -> list[Result]:
    texts = apworld_texts(apworld)
    with zipfile.ZipFile(apworld) as archive:
        names = archive.namelist()
    checks = [make_release.check_mentions(texts), make_release.check_personal_paths(texts)]
    for release, rom in make_release.release_roms().items():
        checks += [make_release.check_game_bytes(texts, rom, release),
                   make_release.check_game_text(texts, rom, release)]
    results = [Result(f"{apworld.name}: {check.name}", check.passed, check.hits) for check in checks]
    shipped_privately = [name for name in names if "/private/" in f"/{name}" or name.endswith(".nes")]
    results.append(Result(f"{apworld.name}: no private module and no ROM", not shipped_privately, shipped_privately))
    return results


# --- 2. a fresh Archipelago --------------------------------------------------------------------

def newest_release(repo: str) -> Archipelago:
    """The newest X.Y.Z release tag, as a warning."""
    listed = subprocess.run(["git", "ls-remote", "--tags", repo], capture_output=True, text=True, check=True).stdout
    versions = [tuple(int(part) for part in match.groups()) for line in listed.splitlines()
                if (match := RELEASE_TAG.match(line.split("\t")[-1]))]
    newest = ".".join(map(str, max(versions)))
    return Archipelago(f"{newest} (newest release)", newest, required=False)


def fetch(target: Archipelago, repo: str) -> tuple[Path, str]:
    """A fresh source tree of TARGET (temp/archipelago-check/<ref>/tree) and its commit."""
    git_dir = WORK / "archipelago.git"
    if not git_dir.exists():
        subprocess.run(["git", "init", "-q", "--bare", str(git_dir)], check=True)
    ref = target.ref if re.fullmatch(r"[0-9a-f]{40}", target.ref) else f"refs/tags/{target.ref}"
    subprocess.run(["git", "--git-dir", str(git_dir), "fetch", "-q", "--depth", "1", repo, ref], check=True,
                   capture_output=True)
    commit = subprocess.run(["git", "--git-dir", str(git_dir), "rev-parse", "FETCH_HEAD^{commit}"],
                            capture_output=True, text=True, check=True).stdout.strip()
    tree = WORK / target.ref / "tree"
    shutil.rmtree(tree, ignore_errors=True)
    tree.mkdir(parents=True)
    archive = subprocess.run(["git", "--git-dir", str(git_dir), "archive", "--format=tar", commit],
                             capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(tree, filter="data")
    return tree, commit


def environment(target: Archipelago, tree: Path) -> Path:
    """TARGET's virtual environment (kept between runs) with its requirements and pytest; its python."""
    venv = WORK / target.ref / "venv"
    python = venv / "bin" / "python"
    if not python.exists():
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    commands: list[list[str | Path]] = [[python, "ModuleUpdate.py", "--yes"],
                                        [python, "-m", "pip", "install", "-q", *TEST_REQUIREMENTS]]
    for command in commands:
        done = run(command, tree)
        if done.returncode != 0:
            raise RuntimeError(f"{' '.join(map(str, command))} failed:\n" + "\n".join(tail(done)))
    return python


def host_yaml(tree: Path, rom: Path) -> None:
    (tree / "host.yaml").write_text(f'zora_options:\n  rom_file: "{rom}"\nbizhawkclient_options:\n'
                                    '  rom_start: false\n')


# --- the players: the web page's exports -------------------------------------------------------

def random_page_values(rng: random.Random) -> dict[str, int]:
    """One offered value for each option, as Archipelago's option keys take them."""
    return {spec.key: rng.choice([value for value, _key in spec.value_keys]) for spec in zora_ap.option_fields()}


def random_settings(rng: random.Random) -> dict[str, object]:
    """One value for each player setting, in the page's form."""
    settings: dict[str, object] = {}
    for spec in zora_ap.player_setting_fields():
        values: list[str | int] = (list(spec.colors) if spec.kind == zora_ap.COLOR
                                   else [value for value, _label in spec.choices])
        settings[spec.key] = rng.choice(values)
    return settings


def exported_players(count: int, seed: int) -> list[tuple[str, str]]:
    """(file name, YAML) for COUNT ZORA players, as the web page exports them: the page's default
    flag string and settings first, then random offered settings the page accepts (a combination
    ZORA refuses, OptionsConflict, is drawn again, as the page would refuse its export)."""
    rng = random.Random(seed)
    default_flags = flag_form.metadata()["defaultFlags"]
    exports = [multiworld.export_yaml("ZORA1", default_flags, "", {})]
    while len(exports) < count:
        try:
            flag_string, zora_flag_string = zora_ap.flag_strings(random_page_values(rng))
            exports.append(multiworld.export_yaml(f"ZORA{len(exports) + 1}", flag_string, zora_flag_string,
                                                  random_settings(rng)))
        except (zora_ap.OptionsConflict, multiworld.ExportRefused):
            continue
    return [(export["fileName"], export["yaml"]) for export in exports]


def other_game_yaml() -> str:
    name, game = OTHER_GAME
    return f"name: {name}\ngame: {game}\n{game}: {{}}\n"


# --- generate, bake, test ------------------------------------------------------------------------

def generate(python: Path, tree: Path, players: list[tuple[str, str]], seed: int) -> tuple[Result, list[Path]]:
    folder, output = tree / "Players", tree / "output"
    shutil.rmtree(folder, ignore_errors=True)
    shutil.rmtree(output, ignore_errors=True)
    folder.mkdir()
    for file_name, text in players:
        (folder / file_name).write_text(text)
    (folder / "other-game.yaml").write_text(other_game_yaml())
    done = run([python, "Generate.py", "--player_files_path", folder, "--outputpath", output, "--seed", str(seed)],
               tree)
    zips = sorted(output.glob("*.zip"))
    if done.returncode != 0 or len(zips) != 1:
        return Result(f"generates {len(players)} exported ZORA YAMLs + {OTHER_GAME[1]}", False, tail(done)), []
    unpacked = output / "unpacked"
    with zipfile.ZipFile(zips[0]) as archive:
        archive.extractall(unpacked)
    patches = sorted(unpacked.glob("*.apzora"))
    passed = len(patches) == len(players)
    return (Result(f"generates {len(players)} exported ZORA YAMLs + {OTHER_GAME[1]} ({zips[0].name}): "
                   f"{len(patches)} .apzora", passed, [] if passed else tail(done)), patches)


def modified_graphics_rom() -> Path:
    """PRG0 with one tile of its first graphics block changed: identify_rom's 'modified graphics'."""
    data = bytearray(verify_base_rom().read_bytes())
    _name, offset, _length = GRAPHICS_BLOCKS[0]
    data[NES_HEADER_SIZE + offset:NES_HEADER_SIZE + offset + 16] = bytes(range(16))
    path = WORK / "Legend of Zelda, The (USA) (modified graphics).nes"
    path.write_bytes(bytes(data))
    identified = identify_rom(bytes(data))
    assert identified.revision is Revision.PRG0 and identified.modified_graphics
    return path


def slot_name(rom: bytes) -> str | None:
    """The slot name a ROM's identity record holds, read where the client reads it."""
    identity = zora_ap.rom_identity(rom[:SLOT_IDENTITY_ADDRESS + SLOT_IDENTITY_SIZE])
    return None if identity is None else identity.ap_name.decode(errors="replace")


BAKE = ("import sys, Patch\n"
        "for path in sys.argv[1:]:\n"
        "    meta, target = Patch.create_rom_file(path)\n"
        "    print(meta['player'], target)\n")


def expected_slot_name(player: int, seed_name: str) -> str:
    """The name the world writes into a slot's ROM (ZoraWorld.ap_name), which its client logs in with."""
    return f"ZORA{player}_{seed_name}".encode()[:SLOT_NAME_LENGTH].decode()


def bake(python: Path, tree: Path, patches: list[Path], label: str, rom: Path, revision: Revision) -> Result:
    """Every patch built into a ROM from ROM, as each player's machine does; each must carry its
    slot's login name and have ROM's release's layout."""
    host_yaml(tree, rom)
    done = run([python, "-c", BAKE, *patches], tree)
    problems = [] if done.returncode == 0 else tail(done)
    for line in done.stdout.splitlines():
        player, _space, target = line.partition(" ")
        baked = Path(target).read_bytes()
        expected = expected_slot_name(int(player), Path(target).name.split("_")[1])
        if slot_name(baked) != expected:
            problems.append(f"{Path(target).name}: slot identity {slot_name(baked)!r}, expected {expected!r}")
        if layout_of(baked) is not revision:
            problems.append(f"{Path(target).name}: layout {layout_of(baked)}, expected {revision.value}'s")
        Path(target).unlink()
    if done.returncode == 0 and len(done.stdout.splitlines()) != len(patches):
        problems.append(f"{len(done.stdout.splitlines())} of {len(patches)} patches built")
    return Result(f"builds all {len(patches)} patches from {label}", not problems, problems)


def world_tests(python: Path, tree: Path, apworld: Path) -> Result:
    with zipfile.ZipFile(apworld) as archive:
        modules = sorted(name.removesuffix(".py").replace("/", ".") for name in archive.namelist()
                         if re.fullmatch(r"zora/test/test_\w+\.py", name))
    done = run([python, "-m", "unittest", *(f"worlds.{module}" for module in modules)], tree,
               env={"AP_TEST_WORLDS": "zora"})
    summary = [line for line in (done.stdout + done.stderr).splitlines() if re.match(r"^(Ran|OK|FAILED)", line)]
    return Result(f"the world's tests ({', '.join(module.rsplit('.', 1)[1] for module in modules)}): "
                  + " ".join(summary), done.returncode == 0, [] if done.returncode == 0 else tail(done, 40))


def general_tests(python: Path, tree: Path) -> Result:
    done = run([python, "-m", "pytest", "test/general", "-q", "-n", str(TEST_WORKERS), "-p", "no:cacheprovider"], tree,
               env={"AP_TEST_WORLDS": "zora"})
    summary = (done.stdout.strip().splitlines() or ["(no output)"])[-1]
    return Result(f"Archipelago's general tests, scoped to ZORA: {summary}", done.returncode == 0,
                  [] if done.returncode == 0 else tail(done, 40))


def check_archipelago(target: Archipelago, apworld: Path, repo: str, players: list[tuple[str, str]],
                      seed: int) -> list[Result]:
    progress(f"Archipelago {target.label}: fetching {target.ref[:12]}...")
    tree, commit = fetch(target, repo)
    progress(f"Archipelago {target.label}: its requirements and pytest (the first time takes several minutes)...")
    python = environment(target, tree)
    (tree / "custom_worlds").mkdir(exist_ok=True)
    shutil.copyfile(apworld, tree / "custom_worlds" / "zora.apworld")
    host_yaml(tree, verify_base_rom())
    version = run([python, "-c", "import Utils; print(Utils.__version__)"], tree).stdout.strip()
    results = [Result(f"Archipelago {version} from {commit[:9]}, with only {apworld.name} added", True)]
    progress(f"Archipelago {target.label}: generating...")
    generated, patches = generate(python, tree, players, seed)
    results.append(generated)
    if patches:
        roms = (("the PRG0 ROM", verify_base_rom(), Revision.PRG0),
                ("the PRG1 ROM", verify_prg1_rom(), Revision.PRG1),
                ("PRG0 with modified graphics", modified_graphics_rom(), Revision.PRG0))
        for label, rom, revision in roms:
            progress(f"Archipelago {target.label}: building the patches from {label}...")
            results.append(bake(python, tree, patches, label, rom, revision))
    host_yaml(tree, verify_base_rom())
    progress(f"Archipelago {target.label}: the world's tests...")
    results.append(world_tests(python, tree, apworld))
    progress(f"Archipelago {target.label}: Archipelago's general tests...")
    results.append(general_tests(python, tree))
    return results


def report(heading: str, results: list[Result], required: bool) -> bool:
    print(f"== {heading}")
    for result in results:
        mark = "PASS" if result.passed else ("FAIL" if required else "WARN")
        print(f"[{mark}] {result.name}")
        for line in result.detail:
            print(f"      {line}")
    return all(result.passed for result in results)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rev", default="HEAD", help="build from this commit (default HEAD)")
    parser.add_argument("--uncommitted-world", action="store_true",
                        help="build with archipelago/ from the working tree")
    parser.add_argument("--apworld", type=Path, help="check this .apworld instead of building one")
    parser.add_argument("--players", type=int, default=DEFAULT_PLAYERS,
                        help=f"ZORA players (default {DEFAULT_PLAYERS})")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="the players' settings and Archipelago's seed")
    parser.add_argument("--skip-newest", action="store_true", help="check the required Archipelago only")
    parser.add_argument("--archipelago-repo", default=ARCHIPELAGO_REPO, help="where to fetch Archipelago from")
    args = parser.parse_args()
    for rom in (BASE_ROM_PATH, PRG1_ROM_PATH):
        if not rom.exists():
            print(f"check_apworld: {rom.name} is missing: the check builds patches from both releases", file=sys.stderr)
            return 1
    _JOB.append(Job("check_apworld.py", stream=sys.stdout).start())
    ok = False
    try:
        ok = check(args)
    finally:
        _JOB.pop().finish(ok=ok)
    return 0 if ok else 1


def check(args: argparse.Namespace) -> bool:
    WORK.mkdir(parents=True, exist_ok=True)
    if args.apworld:
        apworld = args.apworld.resolve()
    else:
        progress("building zora.apworld...")
        built = build_apworld.build(args.rev, args.uncommitted_world, WORK / "zora.apworld")
        for key, value in built.items():
            print(f"build_apworld: {key}: {value}")
        apworld = WORK / "zora.apworld"
    progress("the release's text checks on the .apworld...")
    passed = report("zora.apworld", text_checks(apworld), required=True)
    players = exported_players(args.players, args.seed)
    targets = [REQUIRED_ARCHIPELAGO]
    if not args.skip_newest:
        targets.append(UPCOMING_ARCHIPELAGO)
        newest = newest_release(args.archipelago_repo)
        if newest.ref != REQUIRED_ARCHIPELAGO.ref:
            targets.append(newest)
    warnings = False
    for target in targets:
        try:
            results = check_archipelago(target, apworld, args.archipelago_repo, players, args.seed)
        except (RuntimeError, subprocess.SubprocessError) as failed:
            results = [Result(f"Archipelago {target.label}: could not be set up", False, str(failed).splitlines())]
        heading = f"Archipelago {target.label}" + ("" if target.required else " (a warning only)")
        target_passed = report(heading, results, target.required)
        if target.required:
            passed &= target_passed
        else:
            warnings |= not target_passed
    print(f"check_apworld: {'PASSED' if passed else 'FAILED'}"
          + (" (with warnings for a newer Archipelago)" if warnings and passed else ""))
    return passed


if __name__ == "__main__":
    sys.exit(main())
