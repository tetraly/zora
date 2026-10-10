"""Archipelago's options (zora/archipelago.py option_fields and flag_strings; docs/archipelago.md
"Interface"), Archipelago Phase 4a test 2 and the owner's additions 1 and 2:
  - every offered value round-trips through flag_strings and the decoders; B82 is never offered
    and always off; the defaults are the page's default preset; a new field appears by itself;
  - only values ZORA generates are offered (the support matrix's, "?" only where it allows one):
    each value of each field alone generates, or is refused at flag_strings with a named
    dependency conflict, never refused later as not produced;
  - each dependency rule is named when it refuses, and B23 with B22 off is corrected, as the page
    does, with the page's note."""
import pytest

from zora.archipelago import OptionsConflict, OptionSpec, flag_strings, option_corrections, option_fields
from zora.flags import form as flag_form
from zora.flags import zora_flags, zora_form
from zora.flags.codec import canonicalize, decode
from zora.flags.fields import ENCODE_LEVEL_DATA, OptionField, ThreeState, ToggleField
from zora.generate.pipeline import build, plan
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom

SPECS = option_fields()
SINGLE_VALUES = [(spec.id, value) for spec in SPECS for value in spec.values if value != spec.default]
# The single changes from the page's preset that a dependency rule refuses, and the rule's words.
EXPECTED_CONFLICTS = {
    ("progressive_items", 1): "Extra Candles",                      # PI-FLAG-03, B09 on in the preset
    ("randomize_magical_sword", 1): "Randomize Magical Sword",     # the heart cap, B10 on in the preset
    # Add L4 Sword's three-way control (Off 0, Level 2 1, Level 9 2) needs Progressive Items; Level 9
    # Entrance = Level 4 sword needs Add L4 Sword = Level 2 (docs/design/asnb.md section 2)
    ("add_l4_sword", 1): "Add L4 Sword needs Progressive Items",
    ("add_l4_sword", 2): "Add L4 Sword needs Progressive Items",
    ("level_9_entrance_sword", 1): "needs Add L4 Sword = Level 2",
    ("extra_power_bracelet_blocks", int(ThreeState.ON)): "Extra Power Bracelet Blocks",   # B04 on
}


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("vanilla ROM missing")
    return remember_repo_base_rom()


def value_in(strings: tuple[str, str], spec: OptionSpec) -> int:
    """The option's value as the flag strings hold it."""
    flags, zora = strings
    if spec.id in flag_form.FIELDS_BY_ID:
        field = flag_form.FIELDS_BY_ID[spec.id]
        settings = decode(flags)
        return settings.option(field) if isinstance(field, OptionField) else int(settings.toggle(field))
    return zora_form.control_value(zora_flags.decode(zora), spec.id)


def test_the_defaults_are_the_pages_preset() -> None:
    page = flag_form.metadata()
    assert flag_strings({}) == (canonicalize(page["defaultFlags"]), "")
    assert all(spec.default in spec.values for spec in SPECS)


def test_encode_level_data_is_never_offered_and_always_off() -> None:
    assert ENCODE_LEVEL_DATA.id not in {spec.id for spec in SPECS}
    for option, value in SINGLE_VALUES:
        try:
            flags, _zora = flag_strings({option: value})
        except OptionsConflict:
            continue
        assert decode(flags).toggle(ENCODE_LEVEL_DATA) is ThreeState.OFF


def test_only_supported_values_are_offered() -> None:
    for spec in SPECS:
        if spec.id in flag_form.FIELDS_BY_ID:
            assert spec.values == tuple(int(v) for v in flag_form.supported_values(flag_form.FIELDS_BY_ID[spec.id]))
    assert {spec.id for spec in SPECS} == ({field.id for field in flag_form.ALL_FIELDS} - {ENCODE_LEVEL_DATA.id}
                                           | set(zora_form.FIELD_NAMES))


@pytest.mark.parametrize(("option", "value"), SINGLE_VALUES)
def test_each_value_alone_round_trips_or_is_a_named_conflict(option: str, value: int) -> None:
    spec = next(spec for spec in SPECS if spec.id == option)
    try:
        strings = flag_strings({option: value})
    except OptionsConflict as conflict:
        assert EXPECTED_CONFLICTS.get((option, value), "\x00") in str(conflict), conflict
        return
    assert (option, value) not in EXPECTED_CONFLICTS
    corrected = option == "B22" and value == ThreeState.OFF       # B23 off with it, the page's correction
    assert value_in(strings, spec) == value or corrected
    plan(strings[0], 1, strings[1])                                # no "not produced" refusal


@pytest.mark.slow
@pytest.mark.parametrize(("option", "value"), [pair for pair in SINGLE_VALUES if pair not in EXPECTED_CONFLICTS])
def test_each_value_alone_generates(base: bytes, option: str, value: int) -> None:
    flags, zora = flag_strings({option: value})
    build(plan(flags, 1, zora), base)


def test_each_conflict_resolves_with_its_counterpart() -> None:
    off, on = int(ThreeState.OFF), int(ThreeState.ON)
    flag_strings({"progressive_items": 1, "B09": off})
    flag_strings({"randomize_magical_sword": 1, "B10": off})
    flag_strings({"randomize_magical_sword": 1, "magical_sword_hearts_highest": 3})     # at most 12 hearts
    flag_strings({"add_l4_sword": on, "progressive_items": 1, "B09": off})
    flag_strings({"extra_power_bracelet_blocks": on, "B04": off})


def test_merchant_toll_is_corrected_as_on_the_page() -> None:
    flags, _zora = flag_strings({"B22": int(ThreeState.OFF)})
    assert decode(flags).toggle("B23") is ThreeState.OFF
    assert option_corrections({"B22": int(ThreeState.OFF)}) == [flag_form.TOLL_TURNED_OFF_NOTE]
    assert option_corrections({}) == []


def test_values_must_be_offered() -> None:
    with pytest.raises(OptionsConflict, match="Hint"):
        flag_strings({"C03": 0})                 # Normal hints: not produced
    with pytest.raises(OptionsConflict, match="unknown options"):
        flag_strings({"B82": 1})


def test_a_new_flag_field_appears(monkeypatch: pytest.MonkeyPatch) -> None:
    """option_fields reads zora/flags' tables when called: a field added there is offered, at its
    first supported value until the default preset holds it."""
    new_toggle = ToggleField("B99", "A new switch")
    supported = flag_form.supported_values
    monkeypatch.setattr(flag_form, "ALL_FIELDS", (*flag_form.ALL_FIELDS, new_toggle))
    monkeypatch.setattr(flag_form, "supported_values",
                        lambda field: (ThreeState.OFF, ThreeState.ON) if field == new_toggle else supported(field))
    monkeypatch.setattr(flag_form, "value_label", lambda field, value: str(value))
    new_extra = {"name": "a_new_extra", "kind": "toggle", "label": "A New Extra", "help": "New."}
    monkeypatch.setattr(zora_form, "FIELDS", (*zora_form.FIELDS, new_extra))
    specs = {spec.id: spec for spec in option_fields()}
    assert specs["B99"].values == (0, 1) and specs["B99"].default == 0
    assert specs["a_new_extra"].kind == "switch" and specs["a_new_extra"].default == 0
