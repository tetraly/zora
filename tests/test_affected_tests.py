"""scripts/affected_tests.py (AGENTS.md "Verification"): the tests a change most likely affects, by
direct import or by a named path, with the ones reached only through imports left to the full tier
(slow tests) or to the batch run, and the quick check's capped selection (`verify.sh`, --quick)."""
import ast
import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "affected_tests.py"


def _helper() -> ModuleType:
    spec = importlib.util.spec_from_file_location("affected_tests", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["affected_tests"] = module            # its dataclass looks its module up
    spec.loader.exec_module(module)
    return module


helper = _helper()

MARKS = """
import pytest

@pytest.mark.slow                    # a comment after the mark
def test_marked(): ...

def test_fast(): ...

@pytest.mark.parametrize("seed", [1, 2])
@pytest.mark.slow
def test_swept(seed): ...

@pytest.mark.slow
class TestGroup:
    def test_inside(self): ...
"""


def test_it_finds_slow_marks_on_functions_classes_and_modules() -> None:
    assert helper.slow_tests(ast.parse(MARKS)) == ["test_marked", "test_swept", "TestGroup::test_inside"]
    assert helper.marked_tests(ast.parse(MARKS), slow=False) == ["test_fast"]
    whole = "import pytest\npytestmark = [pytest.mark.slow]\ndef test_one(): ...\ndef helper(): ...\n"
    assert helper.slow_tests(ast.parse(whole)) == ["test_one"]


def test_relative_imports_resolve_inside_zora() -> None:
    modules = helper.repo_modules()
    imports = helper.imported_modules(REPO / "zora" / "generate" / "steps" / "hint_text.py", modules)
    assert imports and all(name.startswith("zora") for name in imports)
    assert "zora.generate" in imports                      # the packages an import runs count too


def report(*paths: str) -> str:
    return subprocess.run([sys.executable, str(SCRIPT), *paths], capture_output=True, text=True, check=True,
                          cwd=REPO).stdout


def test_a_module_selects_its_direct_importers_and_leaves_the_rest_to_the_full_tier() -> None:
    out = report("zora/generate/steps/hint_text.py")
    direct, _, rest = out.partition("Reached only through imports")
    assert "tests/test_hint_text_rom.py (imports zora/generate/steps/hint_text.py)" in direct
    assert "python3 -m pytest -q -m slow -n auto " in direct
    assert "tests/test_flag_invariants.py" in rest and "tests/test_flag_invariants.py" not in direct


def test_files_that_are_not_python_count_as_their_readers_or_named_paths() -> None:
    assert "(read by zora/generate/steps/hint_text.py)" in report("zora/generate/steps/hint_pool.txt")
    assert "tests/test_cross_version.py (names scripts/output_hash.py)" in report("scripts/output_hash.py")
    assert "tests/test_stats_screen_play.py (names asm/fp-stats-01/" in report("asm/fp-stats-01/new.s")


def test_the_test_wide_setup_selects_every_slow_test() -> None:
    out = report("tests/conftest.py")
    assert "(test-wide setup: tests/conftest.py)" in out and "Reached only through imports" not in out
    assert out.count("(test-wide setup)") == len(helper.test_files(helper.repo_modules(), slow=True))
    assert report("--fast", "--ids", "tests/conftest.py") == "tests\n"


def test_the_fast_selection_is_by_file_for_verify_precheck() -> None:
    """The quick check (verify.sh) runs these files with -m "not slow and not full_tier"."""
    selected = report("--fast", "--ids", "scripts/guide_page.py").split()
    assert "tests/test_guide_page.py" in selected and all("::" not in name for name in selected)
    out = report("--fast", "zora/generate/steps/hint_text.py")
    assert "Fast tests most likely affected:" in out and "tests/test_hint_pool.py (imports" in out
    assert report("--ids", "AGENTS.md") == ""                           # nothing selected, nothing printed


def _record(seconds: dict[str, float], heavy: tuple[str, ...] = ()) -> dict[str, list[object]]:
    return {test: [value, test in heavy] for test, value in seconds.items()}


def test_the_quick_selection_stays_within_its_cap() -> None:
    """The quick check's selection (verify.sh): changed test files first, then importers; a file over
    the cap is left to the batch run, and a smaller one after it may still fit."""
    changed = ["tests/test_progress.py", "zora_measure/progress.py"]
    every = helper.quick_select(changed, {}, budget=10_000.0)
    paths = [path for path, _ in every.chosen]
    assert paths[0] == "tests/test_progress.py" and "tests/test_suite_lock.py" not in paths[:1]
    assert len(paths) > 2 and not every.left
    # The changed file costs 500 recorded seconds: over a 60-second cap, so it is left out
    record = _record({"tests/test_progress.py::test_one": 500.0, "tests/test_progress.py::test_two": 0.5})
    capped = helper.quick_select(changed, record, budget=60.0)
    assert ("tests/test_progress.py", 500.5) in capped.left
    assert capped.seconds <= 60.0 and capped.chosen
    assert {path for path, _ in capped.chosen} | {path for path, _ in capped.left} == set(paths)


def test_heavy_tests_do_not_count_toward_the_cap() -> None:
    """The quick check runs only fast tests: a slow or full_tier test's time is not its cost."""
    record = _record({"tests/test_progress.py::test_slow": 900.0, "tests/test_progress.py::test_fast": 2.0},
                     heavy=("tests/test_progress.py::test_slow",))
    quick = helper.quick_select(["tests/test_progress.py"], record, budget=5.0)
    assert quick.chosen == [("tests/test_progress.py", 2.0)]


def test_a_test_wide_change_does_not_select_every_test_in_the_quick_check() -> None:
    quick = helper.quick_select(["tests/conftest.py"], {}, budget=10_000.0)
    assert quick.chosen == [] and quick.test_wide == ["tests/conftest.py"]


def test_a_clean_copy_selects_by_its_added_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZORA_COPY_ADDED", "scripts/verify.sh:tests/test_progress.py")
    assert helper.changed_files(None) == ["scripts/verify.sh", "tests/test_progress.py"]
