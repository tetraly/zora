"""Tests for zora/rom_layout.py."""

from zora.rom_layout import read_le16, write_le16


class TestReadLe16:

    def test_basic(self):
        data = bytes([0x34, 0x12])
        assert read_le16(data, 0) == 0x1234

    def test_second_entry(self):
        data = bytes([0x00, 0x00, 0xCD, 0xAB])
        assert read_le16(data, 1) == 0xABCD

    def test_zero(self):
        data = bytes([0x00, 0x00])
        assert read_le16(data, 0) == 0x00

    def test_max(self):
        data = bytes([0xFF, 0xFF])
        assert read_le16(data, 0) == 0xFFFF

    def test_low_byte_only(self):
        data = bytes([0x42, 0x00])
        assert read_le16(data, 0) == 0x42

    def test_high_byte_only(self):
        data = bytes([0x00, 0x80])
        assert read_le16(data, 0) == 0x8000


class TestWriteLe16:

    def test_basic(self):
        buf = bytearray(2)
        write_le16(buf, 0, 0x1234)
        assert buf[0] == 0x34
        assert buf[1] == 0x12

    def test_second_entry(self):
        buf = bytearray(4)
        write_le16(buf, 1, 0xABCD)
        assert buf[0] == 0x00
        assert buf[1] == 0x00
        assert buf[2] == 0xCD
        assert buf[3] == 0xAB

    def test_zero(self):
        buf = bytearray([0xFF, 0xFF])
        write_le16(buf, 0, 0x0000)
        assert buf == bytearray([0x00, 0x00])

    def test_max(self):
        buf = bytearray(2)
        write_le16(buf, 0, 0xFFFF)
        assert buf == bytearray([0xFF, 0xFF])


class TestReadWriteRoundtrip:

    def test_roundtrip(self):
        values = [0x0000, 0x0001, 0x00FF, 0x0100, 0x8000, 0xC010, 0xFFFF]
        buf = bytearray(len(values) * 2)
        for i, v in enumerate(values):
            write_le16(buf, i, v)
        for i, v in enumerate(values):
            assert read_le16(bytes(buf), i) == v

    def test_does_not_disturb_neighbors(self):
        buf = bytearray(6)
        write_le16(buf, 1, 0x1234)
        assert buf[0] == 0x00
        assert buf[1] == 0x00
        assert buf[2] == 0x34
        assert buf[3] == 0x12
        assert buf[4] == 0x00
        assert buf[5] == 0x00
