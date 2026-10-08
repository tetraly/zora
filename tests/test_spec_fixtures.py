"""The spec fixtures still match docs/spec/ (skipped when docs/spec/ is absent).

tests/flags_spec_fixture.py holds the tables of docs/spec/flags-behavior.md that
tests/test_flags.py and tests/test_flag_alternatives.py check against, so the
suite runs without docs/spec/. When the spec is present, this test extracts
the tables again and compares; on a mismatch, regenerate the fixture with
`python3 tests/flags_spec_tables.py` after reviewing the spec change.
"""
import pytest

from tests import flags_spec_tables


@pytest.mark.skipif(not flags_spec_tables.SPEC_PATH.exists(), reason="docs/spec/ not present")
def test_flags_fixture_matches_the_spec() -> None:
    expected = flags_spec_tables.render(flags_spec_tables.extract(flags_spec_tables.SPEC_PATH.read_text()))
    assert flags_spec_tables.FIXTURE_PATH.read_text() == expected
