#!/usr/bin/env python3
"""Command-line interface for running the Z1 randomizer."""

import argparse
import io
import sys
import os
import traceback
from pathlib import Path
import logging

# CRITICAL: Set PYTHONHASHSEED=0 for deterministic hash functions
# This ensures the same seed/flags always produce the same ROM
if os.environ.get('PYTHONHASHSEED') != '0':
    os.environ['PYTHONHASHSEED'] = '0'
    os.execv(sys.executable, [sys.executable] + sys.argv)

# Ensure project root is on the import path when executing from the CLI folder
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from logic.flags import Flags, FlagsEnum
from logic.randomizer import Z1Randomizer

# Mapping used to convert flagstring letters back into flag bits
LETTER_MAP = ['B', 'C', 'D', 'F', 'G', 'H', 'K', 'L']
VALID_LETTERS = {letter: idx for idx, letter in enumerate(LETTER_MAP)}
COMPLEX_FLAGS = {'starting_items', 'skip_items'}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Z1 randomizer and write a patched ROM.")
    parser.add_argument(
        "--seed",
        type=int,
        required=True,
        help="Seed value to use when generating the randomized ROM.")
    parser.add_argument(
        "--flagstring",
        required=True,
        help="Flagstring describing the enabled randomizer options.")
    parser.add_argument(
        "--input-file",
        required=True,
        help="Path to the base ROM (.nes) file to randomize.")
    parser.add_argument(
        "--output-dir",
        default="outputs",
        help="Directory where the randomized ROM will be written (default: outputs).")
    parser.add_argument(
        "--output-file",
        help="Optional filename or path for the randomized ROM. "
             "If relative, it is placed inside --output-dir.")
    parser.add_argument( '-log',
        '--loglevel',
        default='warning',
        help='Provide logging level. Example --loglevel debug, default=warning' )
             
    return parser


def parse_flagstring(flagstring: str) -> tuple[Flags, str]:
    normalized = flagstring.strip().upper()
    if not normalized:
        raise ValueError("Flagstring cannot be empty.")

    invalid_chars = sorted({c for c in normalized if c not in VALID_LETTERS})
    if invalid_chars:
        raise ValueError(
            f"Flagstring contains invalid characters: {', '.join(invalid_chars)}")

    binary_str = ''.join(format(VALID_LETTERS[c], '03b') for c in normalized)
    non_complex_flags = [flag for flag in FlagsEnum if flag.value not in COMPLEX_FLAGS]

    flags = Flags()
    for index, flag in enumerate(non_complex_flags):
        if index >= len(binary_str):
            break
        if binary_str[index] == '1':
            flags.set(flag.value, True)

    # Validate flag combinations
    is_valid, errors = flags.validate()
    if not is_valid:
        raise ValueError("\n".join(errors))

    return flags, normalized


def build_default_output_name(input_path: Path, seed: int, zora_flagstring: str) -> str:
    base_name_no_ext = input_path.stem
    parts = base_name_no_ext.rsplit('_', 2)
    seed_str = str(seed)

    if len(parts) == 3 and parts[1].isdigit():
        base_name = parts[0]
        zr_flags = parts[2]
        return f"{base_name}_{seed_str}_{zr_flags}_{zora_flagstring}.nes"

    return f"{base_name_no_ext}_{seed_str}_{zora_flagstring}.nes"


def resolve_output_path(
        input_path: Path,
        seed: int,
        zora_flagstring: str,
        output_dir: Path,
        output_file: str | None) -> Path:
    if output_file:
        candidate = Path(output_file)
        if candidate.is_absolute():
            return candidate
        return output_dir / candidate

    return output_dir / build_default_output_name(input_path, seed, zora_flagstring)


def run_randomizer(
        seed: int,
        flagstring: str,
        input_path: Path,
        output_dir: Path,
        output_file: str | None = None) -> Path:
    flags, normalized_flagstring = parse_flagstring(flagstring)

    try:
        rom_bytes = io.BytesIO(input_path.read_bytes())
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Input ROM not found: {input_path}") from exc

    randomizer = Z1Randomizer(rom_bytes, seed, flags)
    patch = randomizer.GetPatch()

    # Apply patch to ROM
    rom_bytes.seek(0)
    rom_data = bytearray(rom_bytes.read())

    for address in patch.GetAddresses():
        patch_data = patch.GetData(address)
        for offset, byte in enumerate(patch_data):
            rom_data[address + offset] = byte

    output_path = resolve_output_path(
        input_path=input_path,
        seed=seed,
        zora_flagstring=normalized_flagstring,
        output_dir=output_dir,
        output_file=output_file)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(bytes(rom_data))

    return output_path


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        seed = args.seed
        flagstring = args.flagstring
        input_path = Path(args.input_file)
        output_dir = Path(args.output_dir)
        output_file = args.output_file

        logging.basicConfig(level=args.loglevel.upper())

        output_path = run_randomizer(
            seed=seed,
            flagstring=flagstring,
            input_path=input_path,
            output_dir=output_dir,
            output_file=output_file)
    except (ValueError, FileNotFoundError) as exc:
        parser.error(str(exc))
    except Exception as exc:  # pragma: no cover - defensive catch-all
        print(f"Error: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1
    else:
        print(f"Randomized ROM written to {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
