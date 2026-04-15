"""
Verifies that flags_generated.py is in sync with flags.yaml.

If this test fails, run:
    python flags/validate_flags.py --generate
"""
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent
FLAGS_DIR = REPO_ROOT / "flags"
FLAGS_YAML = FLAGS_DIR / "flags.yaml"
FLAGS_GENERATED = FLAGS_DIR / "flags_generated.py"

# Ensure validate_flags is importable
sys.path.insert(0, str(FLAGS_DIR))


def test_flags_generated_exists():
    assert FLAGS_GENERATED.exists(), (
        "flags_generated.py does not exist. "
        "Run: python flags/validate_flags.py --generate"
    )


def test_flags_yaml_is_valid():
    from validate_flags import load_and_validate
    load_and_validate(FLAGS_YAML)  # raises on error


def test_flags_generated_in_sync():
    from validate_flags import compute_schema_hash
    current_hash = compute_schema_hash(FLAGS_YAML)
    generated_content = FLAGS_GENERATED.read_text()

    assert current_hash in generated_content, (
        "flags_generated.py is out of sync with flags.yaml.\n"
        "Run: python flags/validate_flags.py --generate"
    )


def test_flags_constraints_reference_valid_ids():
    schema = yaml.safe_load(FLAGS_YAML.read_text())
    flag_ids = {f["id"] for f in schema.get("flags", [])}

    for constraint in schema.get("constraints", []):
        cid = constraint.get("id", "<unknown>")
        for condition in constraint.get("when", []):
            assert condition["flag"] in flag_ids, (
                f"Constraint '{cid}' references unknown flag '{condition['flag']}'"
            )
        for coercion in constraint.get("then", []):
            if "flag" in coercion:
                assert coercion["flag"] in flag_ids, (
                    f"Constraint '{cid}' references unknown flag '{coercion['flag']}'"
                )
            if "among" in coercion:
                for ref in coercion["among"]:
                    assert ref in flag_ids, (
                        f"Constraint '{cid}' no_duplicate references unknown flag '{ref}'"
                    )
