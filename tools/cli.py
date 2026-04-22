"""Generate a seed the same way the API route does, with debug logging."""

import argparse
import logging
import random
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flags.flags_generated import (
    CosmeticFlags,
    decode_cosmetic_flags,
    decode_flags,
    resolve_random_flags,
)
from zora.api.validation import parse_cosmetic_flag_string, parse_flag_string
from zora.generate_game import generate_game

def _timeout_handler(signum, frame):
    raise TimeoutError("Generation timed out")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a seed via the same codepath as POST /generate")
    parser.add_argument("flag_string", help="Flag string (e.g. FUBVVzzHYKi8eKKIGIABBVBAFV)")
    parser.add_argument("seed", type=int, help="Integer seed")
    parser.add_argument("--cosmetic", default="", help="Cosmetic flag string (default: empty/vanilla)")
    parser.add_argument("--rom-version", type=int, default=None, help="ROM version (default: None)")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout in seconds (default: 30)")
    parser.add_argument("--log-level", default="DEBUG", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Log level (default: DEBUG)")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(relativeCreated)8.0fms %(name)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )

    flag_string, flag_errors = parse_flag_string(args.flag_string)
    if flag_errors:
        print(f"Flag errors: {flag_errors}", file=sys.stderr)
        sys.exit(1)

    flags = decode_flags(flag_string)

    rng = random.Random(args.seed)
    resolved_flags = resolve_random_flags(flags, rng)

    cosmetic_flag_string, cosmetic_errors = parse_cosmetic_flag_string(args.cosmetic)
    if cosmetic_errors:
        print(f"Cosmetic flag errors: {cosmetic_errors}", file=sys.stderr)
        sys.exit(1)
    cosmetic_flags: CosmeticFlags = decode_cosmetic_flags(cosmetic_flag_string)

    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(args.timeout)

    t_start = time.monotonic()
    try:
        patch_bytes, hash_code, spoiler_log, spoiler_data = generate_game(
            resolved_flags, args.seed, flag_string=flag_string,
            rom_version=args.rom_version, cosmetic_flags=cosmetic_flags,
        )
        signal.alarm(0)
        elapsed = time.monotonic() - t_start
        print(f"\nSUCCESS in {elapsed:.2f}s ({len(patch_bytes)} patch bytes)")
    except TimeoutError as e:
        elapsed = time.monotonic() - t_start
        print(f"\nTIMEOUT after {elapsed:.2f}s: {e}", file=sys.stderr)
        sys.exit(2)
    except RuntimeError as e:
        signal.alarm(0)
        elapsed = time.monotonic() - t_start
        print(f"\nFAILED after {elapsed:.2f}s: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
