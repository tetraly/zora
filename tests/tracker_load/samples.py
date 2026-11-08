"""The sample seeds of the tracker load tests: Z1R flags only and ZORA flags, at each spoiler level.

Also a command that writes them for hand testing:
    python3 -m tests.tracker_load.samples OUTDIR [SEED ...]
which writes NAME.tracker.json (the ZoraTracker save), NAME.spoiler.txt (the text log) and NAME.info.json
for every family and level (the names are z1r-L1-seed1 and so on; L1 Basic, L2 Medium, L3 Full).
"""
import json
import sys
from functools import cache
from pathlib import Path
from typing import Any

from zora.flags.codec import decode, encode
from zora.flags.fields import PRINT_QUEST_INFO, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import Swordlish, ZoraFlags
from zora.flags.zora_flags import encode as encode_zora
from zora.generate.pipeline import generate_rom
from zora.rom.base_rom import remember_repo_base_rom
from zora_export.leveled_log import leveled_log
from zora_export.seed_document import seed_document_for
from zora_export.tracker_file import tracker_file

FAMILIES = ("z1r", "zora")
# level: (Print Quest Info, Detailed Spoiler Log)
LEVELS = {1: (ThreeState.ON, False), 2: (ThreeState.OFF, True), 3: (ThreeState.ON, True)}
SEEDS = (1, 2)


def flag_strings(family: str, level: int) -> tuple[str, str]:
    """(the Z1R flag string, the ZORA flag string) of a family at a spoiler level. "z1r" changes nothing in the game:
    Medium and Full need the Detailed Spoiler Log, a ZORA flag, so that one bit is the whole ZORA string."""
    print_quest_info, detailed = LEVELS[level]
    flags = encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(toggles={PRINT_QUEST_INFO.id: print_quest_info}))
    if family == "z1r":
        zora = ZoraFlags(detailed_spoiler_log=detailed)
    else:
        zora = ZoraFlags(detailed_spoiler_log=detailed, swordlish=Swordlish.ON, compass_chime=ThreeState.ON,
                         universal_drops_v2=ThreeState.ON, swap_swords_and_rings=ThreeState.ON)
    return flags, (encode_zora(zora) if detailed or family == "zora" else "")


@cache
def document(family: str, level: int, seed: int) -> dict[str, Any]:
    flags, zora = flag_strings(family, level)
    rom = generate_rom(flags, seed, remember_repo_base_rom(), zora_flag_string=zora).rom
    return seed_document_for(rom, flags, seed, zora)


def write_samples(out: Path, seeds: tuple[int, ...] = SEEDS) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for family in FAMILIES:
        for level in LEVELS:
            for seed in seeds:
                made = document(family, level, seed)
                stem = f"{family}-L{level}-seed{seed}"
                flags, zora = flag_strings(family, level)
                files = {f"{stem}.tracker.json": json.dumps(tracker_file(made), indent=1),
                         f"{stem}.spoiler.txt": leveled_log(made),
                         f"{stem}.info.json": json.dumps({"flags": flags, "zora_flags": zora, "seed": seed,
                                                          "level": level}, indent=1)}
                for name, text in files.items():
                    (out / name).write_text(text)
                    written.append(out / name)
    return written


if __name__ == "__main__":
    folder = Path(sys.argv[1])
    count = len(write_samples(folder, tuple(int(arg) for arg in sys.argv[2:]) or SEEDS))
    sys.stdout.write(f"{count} files in {folder}\n")
