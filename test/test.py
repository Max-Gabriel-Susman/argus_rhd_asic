# SPDX-FileCopyrightText: © 2026 Max Gabriel Susman
# SPDX-License-Identifier: Apache-2.0
#
# A.0 stub test: SPI words in, the same words back two words later.
#
# The bus is driven the way argus_rhd_spi_master drives it on the Arty: SCLK
# idles low, 48 ns period (24 low, 24 high), MOSI changes while SCLK is low,
# MISO is sampled on the rising edge. clk is SCLK, so it only toggles during
# a word, exactly as on the real bus.

import cocotb
from cocotb.triggers import Timer

HALF_NS = 24      # SCLK half period: 48 ns, the Arty master at /6
CS_GAP_NS = 160   # CS high between words, as on the Arty

CS_N = 0          # ui_in bit
MOSI = 1          # ui_in bit


def set_ui(dut, cs_n, mosi):
    dut.ui_in.value = (mosi << MOSI) | (cs_n << CS_N)


async def spi_word(dut, word):
    """Send one 16-bit word MSB first; return the 16 bits read back."""
    set_ui(dut, 0, (word >> 15) & 1)       # CS falls, bit 15 on MOSI
    await Timer(HALF_NS, unit="ns")         # tCS1
    got = 0
    for i in range(15, -1, -1):
        set_ui(dut, 0, (word >> i) & 1)
        await Timer(HALF_NS, unit="ns")     # SCLK low phase
        got = (got << 1) | (int(dut.uo_out.value) & 1)   # sample MISO
        dut.clk.value = 1                   # rising: the chip samples MOSI
        await Timer(HALF_NS, unit="ns")     # SCLK high phase
        dut.clk.value = 0                   # falling: the chip moves MISO
    await Timer(HALF_NS, unit="ns")         # tCS2
    set_ui(dut, 1, 0)                       # CS rises
    await Timer(CS_GAP_NS, unit="ns")
    return got


@cocotb.test()
async def test_echo_pipeline(dut):
    dut.ena.value = 1
    dut.uio_in.value = 0
    dut.clk.value = 0
    set_ui(dut, 1, 0)
    dut.rst_n.value = 0
    await Timer(200, unit="ns")
    dut.rst_n.value = 1
    await Timer(200, unit="ns")

    sent = [0xA55A, 0x0F0F, 0x8001, 0x7FFE, 0x1234, 0xFFFF, 0x0000, 0xC3C3]
    got = []
    for w in sent:
        got.append(await spi_word(dut, w))
        dut._log.info(f"sent {w:04x}, got {got[-1]:04x}")

    # Two-word pipeline: the first two reads are the reset value, then each
    # word comes back two windows after it was sent.
    assert got[:2] == [0, 0], f"reset words {got[:2]}"
    for n in range(2, len(sent)):
        assert got[n] == sent[n - 2], \
            f"window {n}: got {got[n]:04x}, expected {sent[n - 2]:04x}"


@cocotb.test()
async def test_cs_echo_and_retire_toggle(dut):
    dut.ena.value = 1
    dut.uio_in.value = 0
    dut.clk.value = 0
    set_ui(dut, 1, 0)
    dut.rst_n.value = 0
    await Timer(200, unit="ns")
    dut.rst_n.value = 1
    await Timer(200, unit="ns")

    assert (int(dut.uo_out.value) >> 1) & 1 == 1, "CS_n echo should be high"
    toggle = (int(dut.uo_out.value) >> 2) & 1
    for _ in range(3):
        await spi_word(dut, 0x5555)
        now = (int(dut.uo_out.value) >> 2) & 1
        assert now != toggle, "retire output did not toggle"
        toggle = now
