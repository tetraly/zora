"""BUILD and FINISH (zora/generate/pipeline.py; Archipelago Phase 2, docs/archipelago.md):
generate_rom is finish(build(...)), and finishing with no assignment (ZORA mode) leaves the
built world as it was, so a build finishes to the same bytes twice. Test 1 proper is
`sh scripts/verify.sh 55c5c68` (identical output)."""
import pytest

from tests.archipelago_cases import FLAG_CASES
from zora.generate.pipeline import build, finish, generate_rom, plan
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.player_settings import DEFAULT_PLAYER_SETTINGS


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("vanilla ROM missing")
    return remember_repo_base_rom()


@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_generate_rom_is_finish_of_build(base: bytes, case: str) -> None:
    flag_string, zora_flag_string = FLAG_CASES[case]
    built = build(plan(flag_string, 4, zora_flag_string), base)
    rom = finish(built, base, None, DEFAULT_PLAYER_SETTINGS)
    assert rom == generate_rom(flag_string, 4, base, zora_flag_string=zora_flag_string).rom
    assert finish(built, base) == finish(built, base) == rom
