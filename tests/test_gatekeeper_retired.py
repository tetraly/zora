"""Gatekeeper Bosses (ZORA flag version 12; beta 9 and 10) is retired (2026-10-29; docs/reports/gatekeeper-lessons.md):
its slot stays in the ZORA flag string (zora_flags.RETIRED_FIELDS), so a string with it at Anywhere, Late or Early
still decodes, means the same settings as with it off, and builds without gatekeepers; Archipelago accepts the
option in a YAML, any of its old values, and ignores it (archipelago.RETIRED_ZORA_FLAGS)."""
import pytest

from tests.needs import needs_base_rom
from zora import archipelago
from zora.flags import zora_flags, zora_form
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.rom.base_rom import remember_repo_base_rom

GATEKEEPER = "gatekeeper_bosses"
GATEKEEPER_VERSION = 12
ANYWHERE, LATE, EARLY = 1, 2, 3
# ISUMatt's beta 10 ZORA flags (Gatekeeper Bosses: Anywhere) and the same flags with it off
ISUMATT_ZORA, ISUMATT_ZORA_OFF = "12.2820FQxB", "10.Jpeob2c"


def with_gatekeeper(value: int) -> str:
    """A version-12 string whose only set field is Gatekeeper Bosses at VALUE (encode can no longer write one)."""
    number = 0
    for field in reversed([field for field in zora_flags.FIELDS if field.version <= GATEKEEPER_VERSION]):
        number = number * field.slots + (value if field.name == GATEKEEPER else 0)
    return f"{GATEKEEPER_VERSION}{zora_flags.VERSION_SEPARATOR}{zora_flags._format_payload(number)}"


def test_the_field_is_retired_and_keeps_its_slot() -> None:
    assert GATEKEEPER in zora_flags.RETIRED_FIELDS
    field = next(field for field in zora_flags.FIELDS if field.name == GATEKEEPER)
    assert field.slots == zora_flags.GATEKEEPER_BOSSES_SLOTS
    assert not hasattr(zora_flags.DEFAULT, GATEKEEPER)
    assert GATEKEEPER not in {field["name"] for field in zora_form.FIELDS}


@pytest.mark.parametrize("value", [ANYWHERE, LATE, EARLY])
def test_a_string_with_it_on_means_the_settings_without_it(value: int) -> None:
    assert zora_flags.decode(with_gatekeeper(value)) == zora_flags.DEFAULT
    assert zora_flags.canonicalize(with_gatekeeper(value)) == ""


def test_the_reported_strings_keep_their_other_settings() -> None:
    assert zora_flags.decode(ISUMATT_ZORA) == zora_flags.decode(ISUMATT_ZORA_OFF)
    assert zora_flags.canonicalize(ISUMATT_ZORA) == ISUMATT_ZORA_OFF


@needs_base_rom
@pytest.mark.parametrize("value", [ANYWHERE, EARLY])
def test_a_string_with_it_on_builds_the_rom_without_it(value: int) -> None:
    base = remember_repo_base_rom()
    assert (generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, base, zora_flag_string=with_gatekeeper(value)).rom
            == generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, base).rom)


def test_archipelago_accepts_and_ignores_it() -> None:
    assert GATEKEEPER not in {spec.key for spec in archipelago.option_fields()}
    [spec] = [spec for spec in archipelago.never_offered_fields() if spec.key == GATEKEEPER]
    # the value keys as beta 10's world named them
    assert spec.value_keys == ((0, "off"), (1, "anywhere"), (2, "late"), (3, "early"))
    assert spec.description == "Retired; a gate-based dungeon style is planned."
    for given in ("off", "anywhere", "late", "early", 0, 1, 2, 3, True, False):
        assert archipelago.never_offered_refusal(GATEKEEPER, given) is None
