"""Show Item Pickups (ZORA flag show_item_pickups; asm/flags2/item-line/): the flag and the texts' table."""
import pytest

from tests.needs import needs_base_rom
from zora.flags import zora_flags
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.model.enums import Item
from zora.rom import item_line
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.text_encoding import CHAR_TO_BYTE

ON = zora_flags.encode(zora_flags.ZoraFlags(show_item_pickups=ThreeState.ON))
TEXT_OF = {tile: char for char, tile in CHAR_TO_BYTE.items()}


def read_texts(table: bytes) -> dict[int, str]:
    """The table as the patch reads it: each item code's text, by code."""
    codes = item_line.ITEM_CODES
    out = {}
    for code in range(codes):
        if not table[codes + code]:
            continue
        start = (table[code] | table[codes + code] << 8) - item_line.TABLE_CPU
        length = table[start] & ~item_line.SHORT_BIT
        assert bool(table[start] & item_line.SHORT_BIT) == (code in item_line.SHORT)
        out[code] = item_line.PREFIX + "".join(TEXT_OF[tile] for tile in table[start + 1:start + 1 + length])
    return out


def test_the_field_is_version_23_and_off_by_default() -> None:
    field = next(field for field in zora_flags.FIELDS if field.name == zora_flags.ITEM_LINE_FIELD)
    assert field.version == 24
    assert zora_flags.ZoraFlags().show_item_pickups is ThreeState.OFF
    assert zora_flags.decode(ON).show_item_pickups is ThreeState.ON


@pytest.mark.parametrize("boots", [False, True], ids=["boomerangs", "pegasus-boots"])
def test_the_table_reads_back_and_fits(boots: bool) -> None:
    table = item_line.item_line_table(boots)
    assert len(table) <= item_line.TABLE_END - item_line.TABLE
    texts = read_texts(table)
    assert texts == item_line.item_texts(boots)
    assert all(len(text) <= item_line.ROW_TILES for text in texts.values())
    assert all(0 < len(text) - len(item_line.PREFIX) <= 24 for text in texts.values())     # the patch centers 1-24
    assert not {int(item) for item in item_line.QUIET} & set(texts)
    assert texts[Item.RAFT] == "GOT RAFT"
    assert texts[Item.BOMBS] == "GOT BOMBS" and texts[Item.KEY] == "GOT KEY"
    assert texts[Item.WOOD_BOOMERANG] == ("GOT PEGASUS BOOTS" if boots else "GOT BOOMERANG")


@needs_base_rom
def test_the_rom_holds_the_table_only_with_the_flag() -> None:
    on = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, remember_repo_base_rom(), zora_flag_string=ON).rom
    off = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, remember_repo_base_rom()).rom
    table = item_line.item_line_table()
    assert on[item_line.TABLE:item_line.TABLE + len(table)] == table
    assert set(off[item_line.TABLE:item_line.TABLE_END]) == {0xFF}


def test_an_empty_name_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(item_line, "item_texts", lambda boots=False: {int(Item.RAFT): item_line.PREFIX})
    with pytest.raises(ValueError, match="empty name"):
        item_line.item_line_table()
