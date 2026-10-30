"""PS-MERCH-05 (the 2026-10-28 export): Add Money or Life Rooms on (B22) with Change "Leave your..."
Rooms off (B23). The merchants are added and keep PRG0's toll: the payment routine, the ware types, the
price display and the toll text space hold PRG0's bytes. Their text slot (27) keeps the pointer the hint
pass gave it: PRG0's text 27 under normal hints, a drawn slot-27 quote under the other generated styles
(HT-TEXT-02: the rebuild MUST generate it like any other slot) and its empty text under blank hints."""
import pytest

from tests.needs import needs_base_rom
from zora.flags.codec import decode, encode
from zora.flags.fields import HINT_STYLE, HintStyle, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.generate.steps.hint_text import POOL, TOLL_SLOT
from zora.model.enums import RoomAction, TollOption
from zora.model.rooms import LifeOrMoneyToll
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.layout import TOLL_TEXT_POINTER, TOLL_TEXT_POINTER_ADDRESS
from zora.rom.parse.rom_file import parse_rom
from zora.rom.person_code import encode as toll_writes

SEED = 3
POINTER_BYTES = 2
PAD, LINE_BREAK = "~", "|"            # the parsed text's centering tile and line break
# One toll of each kind: together their writes cover every byte PS-MERCH-04 can change
EVERY_TOLL_KIND = (LifeOrMoneyToll(TollOption.MAX_BOMBS, TollOption.KEYS, key_cost=3),
                   LifeOrMoneyToll(TollOption.LIFE, TollOption.MONEY, money_cost=40),
                   LifeOrMoneyToll(TollOption.LIFE, TollOption.MAX_BOMBS))
STARTING_CONTAINERS = 3


def toll_offsets() -> set[int]:
    return {offset for toll in EVERY_TOLL_KIND for start, data in toll_writes(toll, None, STARTING_CONTAINERS)
            for offset in range(start, start + len(data))}


def merchants_without_the_toll(style: HintStyle) -> bytes:
    settings = decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(options={HINT_STYLE.id: style},
                                                               toggles={"B22": ThreeState.ON, "B23": ThreeState.OFF})
    return generate_rom(encode(settings), SEED, remember_repo_base_rom()).rom


def slot_27_pointer(rom: bytes) -> bytes:
    return rom[TOLL_TEXT_POINTER_ADDRESS:TOLL_TEXT_POINTER_ADDRESS + POINTER_BYTES]


@needs_base_rom
@pytest.mark.parametrize("style", [HintStyle.NORMAL, HintStyle.MIXED, HintStyle.COMMUNITY, HintStyle.BLANK])
def test_the_merchants_keep_prg0s_toll(style: HintStyle) -> None:
    base, rom = remember_repo_base_rom(), merchants_without_the_toll(style)
    assert all(rom[offset] == base[offset] for offset in toll_offsets())
    assert slot_27_pointer(rom) != TOLL_TEXT_POINTER
    world = parse_rom(rom)
    assert any(room.room_action == RoomAction.MONEY_OR_LIFE for level in world.levels for room in level.rooms)
    text = world.quotes[TOLL_SLOT].text
    if style == HintStyle.NORMAL:
        assert slot_27_pointer(rom) == slot_27_pointer(base)          # PRG0's text 27, its own toll text
    elif style == HintStyle.BLANK:
        assert text == ""
    else:
        slot_27_quotes = {entry.lines for entry in POOL if entry.reserved and entry.routing_class == "slot 27"}
        assert tuple(line.lstrip(PAD) for line in text.split(LINE_BREAK)) in slot_27_quotes, text
