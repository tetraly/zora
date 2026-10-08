"""Build the player-setting patches (docs/player-settings-patches.md).

    python3 asm/settings/build.py build           rebuild, write asm/settings/player_settings_data.py
    python3 asm/settings/build.py check           rebuild, exit 1 if that module differs
    python3 asm/settings/build.py edit CHOICE     write the sources with CHOICE applied to temp/asm-settings/edit/src
    python3 asm/settings/build.py refresh CHOICE  check CHOICE applies and list its hook sites
    python3 asm/settings/build.py apply IN OUT [SETTING=CHOICE ...]
                                                  write IN with the chosen settings as OUT

A player setting (FP-SET-01) picks one of a few choices after generation.
Each choice that differs from ZORA's own code is a patch folder asm/settings/CHOICE/
(asm/README.md: ZORA's code only, no disassembly text), applied on top of asm/series.txt
(ZORA's code patches, the flag patches FLAG_PATCHES aside); a choice may also leave out hooks
of the series and replace a series patch's routines. The choices of one setting are
alternatives, and the choices of different settings are never applied on top of each other.
They are not in asm/series.txt, so scripts/asm_patches.py does not see them and ZORA's output
does not change.

`build` assembles PRG0 plus the series (the "ZORA build"), then each choice
on top of it, and records, per setting, the union of the bytes any choice
changes, and every choice's bytes there (the ZORA build's bytes for a
choice without a folder). Writing one choice's bytes therefore selects it
whatever choice the ROM held before, and every choice of a setting writes
the same bytes (FP-SET-01: a setting changes only its own entry's bytes).

This script imports scripts/asm_patches.py for its assembling and patch
helpers and does not change it; each build works in a scratch folder of its own
(scripts/asm_patches.py's scratch()).
"""
import argparse
import importlib.util
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

REPO = Path(__file__).resolve().parents[2]
SETTINGS_DIR = REPO / "asm" / "settings"
OUTPUT = SETTINGS_DIR / "player_settings_data.py"
# `edit` writes the sources with a choice applied here, to read; builds use scratch folders.
EDIT_TREE = REPO / "temp" / "asm-settings" / "edit"
sys.path.insert(0, str(REPO))

from zora.rom.base_rom import Original, Piece, piece_bytes  # noqa: E402


def _builder() -> ModuleType:
    """scripts/asm_patches.py, loaded read-only for its helpers."""
    spec = importlib.util.spec_from_file_location("asm_patches_tool", REPO / "scripts" / "asm_patches.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = _builder()


@dataclass(frozen=True)
class Setting:
    """A player setting: its choices (choice -> patch folder in asm/settings/, or None for
    the ZORA build as it is) and the choice every corpus ROM carries."""
    name: str
    entry: str
    choices: dict[str, str | None]
    default: str


SETTINGS = (
    # FP-HOT-01. "off" (PRG0's pause) is not built here.
    Setting("select_swap", "FP-HOT-01",
            {"toggle": None, "swap_only": "select-swap-only"}, default="toggle"),
    # FP-RESET-01. The ZORA build holds PRG0's
    # test; the serializer writes the default's operand as data today.
    Setting("death_warp", "FP-RESET-01",
            {"controller2_up_a": None,
             "controller1_up_a": "death-warp-controller1-up-a",
             "controller1_up_select": "death-warp-controller1-up-select"},
            default="controller1_up_a"),
    # FP-SET-04.
    Setting("music", "FP-SET-04", {"on": None, "off": "music-off"}, default="on"),
    # FP-FIX-02.
    Setting("reduce_flashing", "FP-FIX-02", {"off": None, "on": "reduce-flashing"}, default="off"),
)

CHOICE_FOLDERS = [folder for setting in SETTINGS for folder in setting.choices.values() if folder]

# The bytes a setting writes, per choice: (file offset, piece), a piece being ZORA's bytes or
# an Original (the original game's, read from the player's ROM; zora.rom.base_rom).
Writes = tuple[tuple[int, Piece], ...]


# --- building ---------------------------------------------------------------

# Series patches a ZORA flag leaves out of most ROMs (PI-CODE-01): the settings are built
# without them. They share no byte with the settings (tests/test_progressive_patches.py), so
# a setting's bytes are the same with or without them.
FLAG_PATCHES = ("fp-prog-01", "fp-prog-02")


def zora_tree(work: Path, choice: Any = None) -> Any:
    """The pinned sources with asm/series.txt applied (the flag patches FLAG_PATCHES aside) in
    `work`, with `choice`'s changes to the series (hooks left out, routines replaced), if any."""
    tree = tool.SourceTree(work)
    leave_out = choice.leave_out if choice is not None else frozenset()
    replaced = choice.replaced_routines if choice is not None else {}
    for name in tool.series():
        if name not in FLAG_PATCHES:
            tree.apply(tool.series_patch(name), leave_out, replaced)
    return tree


def load_choice(folder: str) -> Any:
    """asm/settings/CHOICE/ as a patch (scripts/asm_patches.py's Patch)."""
    return tool.load_patch(SETTINGS_DIR / folder)


def choice_image(folder: str) -> bytes:
    """The ZORA build with the choice applied."""
    choice = load_choice(folder)
    tree = zora_tree(tool.scratch("asm-settings-choice"), choice)
    return bytes(tree.apply(choice))


def spans(offsets: set[int]) -> list[tuple[int, int]]:
    """Runs of offsets as (first, last); changes closer than the builder's
    RUN_GAP join one run, as in zora/asm_patch_data.py."""
    runs: list[list[int]] = []
    for offset in sorted(offsets):
        if runs and offset - runs[-1][1] <= tool.RUN_GAP:
            runs[-1][1] = offset
        else:
            runs.append([offset, offset])
    return [(first, last) for first, last in runs]


def build_all() -> tuple[bytes, dict[str, dict[str, Writes]]]:
    """The ZORA build and, per setting, each choice's writes."""
    zora = bytes(zora_tree(tool.scratch("asm-settings")).image)
    original = tool.verify_base_rom().read_bytes()
    result: dict[str, dict[str, Writes]] = {}
    for setting in SETTINGS:
        images = {choice: choice_image(folder) if folder else zora
                  for choice, folder in setting.choices.items()}
        changed = {offset for image in images.values()
                   for offset in range(len(zora)) if image[offset] != zora[offset]}
        runs = spans(changed)
        result[setting.name] = {
            choice: tuple(piece for first, last in runs
                          for piece in tool.run_pieces(first, zora[first:last + 1], image[first:last + 1], original))
            for choice, image in images.items()}
    return zora, result


def render(writes: dict[str, dict[str, Writes]]) -> str:
    lines = ['"""Player-setting patches as bytes (docs/player-settings-patches.md).',
             "",
             "Generated by `python3 asm/settings/build.py build` from asm/settings/;",
             "do not edit. SETTINGS[setting][choice] is a tuple of (file offset, piece):",
             "every choice of a setting writes the same offsets, so writing a choice",
             "selects it whatever the ROM held. Apply after ZORA's code patches. A piece",
             "is ZORA's own bytes or an Original (source, length): the original game's",
             "bytes, read from the player's ROM when written (never stored here).",
             '"""',
             "from zora.rom.base_rom import Original, Piece",
             "",
             "DEFAULTS: dict[str, str] = {"]
    lines.extend(f'    "{setting.name}": "{setting.default}",  # {setting.entry}' for setting in SETTINGS)
    lines.append("}")
    lines.append("")
    lines.append("SETTINGS: dict[str, dict[str, tuple[tuple[int, Piece], ...]]] = {")
    for setting, choices in writes.items():
        lines.append(f'    "{setting}": {{')
        for choice, runs in choices.items():
            lines.append(f'        "{choice}": (')
            for offset, piece in runs:
                lines += tool.piece_lines("            ", offset, piece)
            lines.append("        ),")
        lines.append("    },")
    lines.append("}")
    return "\n".join(lines) + "\n"


def report(writes: dict[str, dict[str, Writes]]) -> None:
    for setting, choices in writes.items():
        for choice, runs in choices.items():
            print(f"{setting}={choice}: {len(runs)} pieces")
            for offset, piece in runs:
                shown = (f"original 0x{piece.source:05X} x{piece.length}" if isinstance(piece, Original)
                         else piece.hex())
                print(f"    0x{offset:05X}  {shown}")


# --- applying ---------------------------------------------------------------

def apply_settings(rom: bytes, chosen: dict[str, str],
                   settings: dict[str, dict[str, Writes]]) -> bytes:
    """`rom` (ZORA's code patches applied) with each chosen setting's bytes.
    Refuses a ROM whose bytes there match none of the setting's choices."""
    out = bytearray(rom)
    for name, choice in chosen.items():
        choices = settings[name]
        held = held_choices(bytes(out), name, settings)
        if not held:
            raise SystemExit(f"{name}: the ROM holds none of its choices' bytes")
        for offset, piece in choices[choice]:
            data = piece_bytes(piece)
            out[offset:offset + len(data)] = data
    return bytes(out)


def held_choices(rom: bytes, name: str, settings: dict[str, dict[str, Writes]]) -> list[str]:
    """The choices of setting `name` whose bytes `rom` holds."""
    return [choice for choice, runs in settings[name].items()
            if all(rom[offset:offset + len(data)] == data
                   for offset, data in ((offset, piece_bytes(piece)) for offset, piece in runs))]


def apply_ported_bytes_only(rom: bytes, settings: dict[str, dict[str, Writes]]) -> bytes:
    """`rom` with only the death-warp test's ported bytes of the controller 1
    Up and Select choice, without ZORA's precedence check in FP-HOT-01's
    item-screen code: the control for that check."""
    out = bytearray(rom)
    for offset, piece in settings["death_warp"]["controller1_up_select"]:
        if offset in DEATH_WARP_TEST:
            data = piece_bytes(piece)
            out[offset:offset + len(data)] = data
    return bytes(out)


# The ported sites (docs/player-settings-patches.md), as headered file offsets.
DEATH_WARP_TEST = range(0x140EA, 0x140F2)        # UpdateMenuActive's two-button test
PORTED_SITES = {
    "death-warp test": DEATH_WARP_TEST,
    "flash site 1": range(0x16895, 0x16897),     # level-end flash store (bank 5)
    "flash site 2": range(0x0AA2F, 0x0AA33),     # EndingFlashColors (bank 2)
    "flash site 3": range(0x06A5B, 0x06A5D),     # bomb grayscale store (bank 1)
    # PRG0's site-4 store, where ZORA's FP-FIX-02 has its JMP: site 4 is
    # applied inside ZORA's own code instead.
    "flash site 4 in PRG0": range(0x061A3, 0x061A6),
}
# Music off's routine, in bank 0's free space ($A000).
MUSIC_OFF_ROUTINE = 0x02010


def ported_sites(rom: bytes) -> dict[str, str]:
    """The bytes at each ported site, as hex."""
    return {site: rom[offsets.start:offsets.stop].hex() for site, offsets in PORTED_SITES.items()}


def music_off_space_is_blank(rom: bytes, settings: dict[str, dict[str, Writes]]) -> bool:
    """Is the free space music off's routine takes all $FF in `rom`?"""
    (piece,) = [piece for offset, piece in settings["music"]["off"] if offset == MUSIC_OFF_ROUTINE]
    data = piece_bytes(piece)
    return rom[MUSIC_OFF_ROUTINE:MUSIC_OFF_ROUTINE + len(data)] == bytes([0xFF]) * len(data)


def load_data() -> ModuleType:
    spec = importlib.util.spec_from_file_location("player_settings_data", OUTPUT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- editing ----------------------------------------------------------------

def edit(folder: str) -> None:
    """Write the sources with the choice applied to temp/asm-settings/edit/src, to read it in
    place. Edits go to asm/settings/CHOICE/, never to that folder."""
    choice = load_choice(folder)
    tree = zora_tree(tool.scratch("asm-settings-edit"), choice)
    tree.apply(choice)
    shutil.rmtree(EDIT_TREE, ignore_errors=True)
    shutil.copytree(tree.src, EDIT_TREE / "src")
    print(f"{folder} on the ZORA build: {EDIT_TREE / 'src'}")


def refresh(folder: str) -> None:
    """Check that the choice applies on the ZORA build, and list each hook's site."""
    choice = load_choice(folder)
    tree = zora_tree(tool.scratch("asm-settings-refresh"), choice)
    lines = tree.lines()
    for hook in choice.hooks:
        file, site = tool.hook_site(lines, folder, hook)
        print(f"{folder}.{hook.name}: 0x{hook.offset:05X} +{hook.length}, {file} line {site[0]}: {hook.note}")
    tree.apply(choice)
    print(f"{folder} applies")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("build", "check", "edit", "refresh", "apply"))
    parser.add_argument("args", nargs="*")
    args = parser.parse_args()
    if args.command in ("edit", "refresh"):
        if len(args.args) != 1:
            parser.error("one CHOICE name required")
        (edit if args.command == "edit" else refresh)(args.args[0])
        return 0
    if args.command == "apply":
        if len(args.args) < 2:
            parser.error("IN and OUT required")
        source, target, *pairs = args.args
        chosen = dict(pair.split("=", 1) for pair in pairs)
        data = load_data()
        rom = apply_settings(Path(source).read_bytes(), chosen, data.SETTINGS)
        Path(target).write_bytes(rom)
        print(f"wrote {target}")
        return 0
    _, writes = build_all()
    report(writes)
    text = render(writes)
    if args.command == "build":
        OUTPUT.write_text(text)
        print(f"wrote {OUTPUT.relative_to(REPO)}")
        return 0
    if not OUTPUT.exists() or OUTPUT.read_text() != text:
        print(f"{OUTPUT.relative_to(REPO)} is out of date: run `asm/settings/build.py build`")
        return 1
    print("up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
