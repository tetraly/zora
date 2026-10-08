"""The data-layer boundary (AGENTS.md "Data layer"): only zora/rom/ reads or
writes raw ROM bytes. Everything else goes through
parse_rom -> GameWorld -> serialize_to_rom."""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The data layer: one package.
DATA_LAYER = "zora/rom/"
# Tests OF the data layer, which check bytes at fixed offsets by design.
DATA_LAYER_TESTS = {
    "tests/test_asm_patches.py", "tests/test_data_boundary.py", "tests/test_flag_alternatives.py",
    "tests/test_person_code.py",
    "tests/test_rom_layout.py", "tests/test_roundtrip.py",
    "tests/test_serializer_guards.py", "tests/test_overworld.py",
}
# The parser's raw-slice entry points.
RAW_ACCESS = re.compile(
    r"\b(RawBinFiles|load_bin_files\w*|original_bins_from_rom|parse_game_world)\b")
# Indexing anything with a literal file offset ($4000 and up).
FILE_OFFSET_INDEX = re.compile(r"\[0x[0-9A-Fa-f]{4,5}\b")


def _code_lines(path: Path) -> list[tuple[int, str]]:
    return [(n, line) for n, line in enumerate(path.read_text().splitlines(), 1)
            if not line.lstrip().startswith("#")]


def test_only_the_data_layer_reads_raw_rom_bytes() -> None:
    offenders = []
    for folder in ("zora", "scripts", "tests"):
        for path in sorted((REPO / folder).rglob("*.py")):
            rel = path.relative_to(REPO).as_posix()
            if rel.startswith(DATA_LAYER) or rel in DATA_LAYER_TESTS:
                continue
            for n, line in _code_lines(path):
                if RAW_ACCESS.search(line) or FILE_OFFSET_INDEX.search(line):
                    offenders.append(f"{rel}:{n}: {line.strip()}")
    assert not offenders, "raw ROM access outside the data layer:\n" + "\n".join(offenders)
