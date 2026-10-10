"""Per-seed output hashes of seeds FIRST..END-1 in both of scripts/output_hash.py's modes, one
seed after another (no process pool: tests/test_cross_version.py runs several of these at once
beside the xdist workers), written as JSON {mode: [sha1, ...]}.

    python3 tests/cross_version_hashes.py FIRST END OUT.json

The hash of a seed is output_hash.seed_hash's, the function its own pool runs; ZORA_CODE_DIR
says which checkout's zora it imports, as for that script.
"""
import importlib.util
import json
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "output_hash", Path(__file__).resolve().parent.parent / "scripts" / "output_hash.py")
assert _spec and _spec.loader
output_hash = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(output_hash)


def main(first: int, end: int, out: Path) -> int:
    hashes = {mode: [output_hash.seed_hash((seed, post_shapes)) for seed in range(first, end)]
              for mode, post_shapes in output_hash.MODES.items()}
    out.write_text(json.dumps(hashes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(int(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3])))
