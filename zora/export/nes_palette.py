"""The NES palette as RGB, for the level colours of the seed document."""

# The NES (2C02) palette, entries $00 to $3F as RGB, emphasis bits off: the same table as
# web/zora-web.js. Source: the first 64 entries of PALETTE_COLORS in src/ppu.cpp of cynes (the emulator
# ZORA's tests use), https://github.com/Youlixx/cynes, commit 6f8d3a4 (read
# 2026-10-06). Used under cynes' licence, which follows:
#
# MIT License
#
# Copyright (c) 2021 - 2025 Combey Theo
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
NES_PALETTE: tuple[str, ...] = (
    "#545454", "#001e74", "#081090", "#300088", "#440064", "#5c0030", "#540400", "#3c1800",
    "#202a00", "#083a00", "#004000", "#003c00", "#00323c", "#000000", "#000000", "#000000",
    "#989698", "#084cc4", "#3032ec", "#5c1ee4", "#8814b0", "#a01464", "#982220", "#783c00",
    "#545a00", "#287200", "#087c00", "#007628", "#006678", "#000000", "#000000", "#000000",
    "#eceeec", "#4c9aec", "#787cec", "#b062ec", "#e454ec", "#ec58b4", "#ec6a64", "#d48820",
    "#a0aa00", "#74c400", "#4cd020", "#38cc6c", "#38b4cc", "#3c3c3c", "#000000", "#000000",
    "#eceeec", "#a8ccec", "#bcbcec", "#d4b2ec", "#ecaeec", "#ecaed4", "#ecb4b0", "#e4c490",
    "#ccd278", "#b4de78", "#a8e290", "#98e2b4", "#a0d6e4", "#a0a2a0", "#000000", "#000000",
)
