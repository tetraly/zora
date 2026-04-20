"""Diff tool for comparing Python and C# pipeline snapshots.

Compares snapshot files in snapshots_py/ vs snapshots_cs/ byte-by-byte.
Reports the first divergent byte in each file, or confirms a match.
"""

from __future__ import annotations

import os
import sys

SCRIPT_DIR = os.path.dirname(__file__)
PY_DIR = os.path.join(SCRIPT_DIR, "snapshots_py")
CS_DIR = os.path.join(SCRIPT_DIR, "snapshots_cs")


def compare_file(name: str) -> bool:
    py_path = os.path.join(PY_DIR, name)
    cs_path = os.path.join(CS_DIR, name)

    if not os.path.exists(py_path):
        print(f"  MISSING (py): {name}")
        return False
    if not os.path.exists(cs_path):
        print(f"  MISSING (cs): {name}")
        return False

    py_data = open(py_path, "rb").read()
    cs_data = open(cs_path, "rb").read()

    if len(py_data) != len(cs_data):
        print(f"  SIZE MISMATCH: {name} — py={len(py_data)} cs={len(cs_data)}")
        return False

    mismatches = []
    for i in range(len(py_data)):
        if py_data[i] != cs_data[i]:
            mismatches.append(i)

    if not mismatches:
        print(f"  MATCH: {name} ({len(py_data)} bytes)")
        return True

    print(f"  MISMATCH: {name} — {len(mismatches)} bytes differ")
    for offset in mismatches[:10]:
        print(f"    offset 0x{offset:04X}: py=0x{py_data[offset]:02X} cs=0x{cs_data[offset]:02X}")
    if len(mismatches) > 10:
        print(f"    ... and {len(mismatches) - 10} more")
    return False


def main() -> None:
    if not os.path.isdir(PY_DIR):
        print(f"Python snapshots not found at {PY_DIR}")
        print("Run: python3 -m new_level.test_pipeline")
        sys.exit(1)
    if not os.path.isdir(CS_DIR):
        print(f"C# snapshots not found at {CS_DIR}")
        print("Run the C# test harness first (see TestPipeline.cs)")
        sys.exit(1)

    py_files = sorted(f for f in os.listdir(PY_DIR) if f.endswith(".hex"))
    cs_files = sorted(f for f in os.listdir(CS_DIR) if f.endswith(".hex"))

    all_files = sorted(set(py_files) | set(cs_files))
    if not all_files:
        print("No snapshot files found.")
        sys.exit(1)

    total = 0
    matched = 0

    # Group by step for readability
    groups = {}
    for name in all_files:
        parts = name.split("_", 2)
        prefix = parts[0]  # "snapshot" or "grid"
        groups.setdefault(prefix, []).append(name)

    for prefix in sorted(groups.keys()):
        print(f"\n=== {prefix} files ===")
        for name in sorted(groups[prefix]):
            total += 1
            if compare_file(name):
                matched += 1

    print(f"\n{'='*50}")
    print(f"Results: {matched}/{total} files match")
    if matched == total:
        print("ALL SNAPSHOTS MATCH — port is correct!")
    else:
        print(f"{total - matched} file(s) differ — check the first divergent step")

    sys.exit(0 if matched == total else 1)


if __name__ == "__main__":
    main()
