# SPDX-FileCopyrightText: © 2026 Max Gabriel Susman
# SPDX-License-Identifier: Apache-2.0
#
# The RHD2132 bus, driven the way argus_rhd_spi_master drives it on the
# Arty: SCLK idles low, 48 ns period (24 low, 24 high), MOSI changes while
# SCLK is low, MISO is sampled on the rising edge, 160 ns of CS high between
# words. clk is SCLK, so it only toggles during a word, exactly as on the
# real bus. Plus command builders that match argus_rhd2132_model.vhd.

from cocotb.triggers import Timer

HALF_NS = 24      # SCLK half period: 48 ns, the Arty master at /6
CS_GAP_NS = 160   # CS high between words

CS_N = 0          # ui_in bits
MOSI = 1
CHIP = 2          # 3:2, the chip number strap
RAMP = 4          # the pattern strap: 0 IDENT, 1 RAMP

# uo_out bits
MISO = 0
CS_ECHO = 1
RETIRED = 2
CALIBRATING = 3
TWOSCOMP = 4


# -- Commands --------------------------------------------------------------

def convert(ch):
    return (ch & 0x3F) << 8


def write(addr, data):
    return 0x8000 | ((addr & 0x3F) << 8) | (data & 0xFF)


def read(addr):
    return 0xC000 | ((addr & 0x3F) << 8)


CALIBRATE = 0x5500
CLEAR = 0x6A00

# The init sequence argus_rhd_spi_master sends after reset, word for word:
# two dummy reads, the 18 RAM registers, CALIBRATE and nine reads for it to
# swallow.
INIT_REGS = [0xDE, 0x42, 0x04, 0x00, 0x80, 0x40, 0x80, 0x00, 0x16,
             0x80, 0x17, 0x80, 0x2C, 0x86, 0xFF, 0xFF, 0xFF, 0xFF]


def init_sequence():
    return ([read(63), read(63)]
            + [write(a, d) for a, d in enumerate(INIT_REGS)]
            + [CALIBRATE] + [read(63)] * 9)


# One sweep as the master sends it: the 32 amplifier channels and two aux.
SWEEP = [convert(c) for c in range(34)]

# -- Results ---------------------------------------------------------------

IDLE = 0x8000     # twoscomp = 0, the reset value


def write_ack(data):
    return 0xFF00 | (data & 0xFF)


def aux_marker(ch):
    return 0xA000 | (ch & 0x3F)


# -- The bus ---------------------------------------------------------------

_straps = 0       # held on ui_in across words; set by reset()


def _set_ui(dut, cs_n, mosi):
    dut.ui_in.value = _straps | (mosi << MOSI) | (cs_n << CS_N)


def uo_bit(dut, bit):
    return (int(dut.uo_out.value) >> bit) & 1


async def reset(dut, chip=0, ramp=False):
    """Straps set, bus idle, chip in reset for 200 ns, then released."""
    global _straps
    _straps = ((chip & 3) << CHIP) | (int(ramp) << RAMP)
    dut.ena.value = 1
    dut.uio_in.value = 0
    dut.clk.value = 0
    _set_ui(dut, 1, 0)
    dut.rst_n.value = 0
    await Timer(200, unit="ns")
    dut.rst_n.value = 1
    await Timer(200, unit="ns")


async def word(dut, w):
    """Send one 16-bit word MSB first; return the 16 bits read back."""
    _set_ui(dut, 0, (w >> 15) & 1)         # CS falls, bit 15 on MOSI
    await Timer(HALF_NS, unit="ns")         # tCS1
    got = 0
    for i in range(15, -1, -1):
        _set_ui(dut, 0, (w >> i) & 1)
        await Timer(HALF_NS, unit="ns")     # SCLK low phase
        got = (got << 1) | uo_bit(dut, MISO)    # sample MISO
        dut.clk.value = 1                   # rising: the chip samples MOSI
        await Timer(HALF_NS, unit="ns")     # SCLK high phase
        dut.clk.value = 0                   # falling: the chip moves MISO
    await Timer(HALF_NS, unit="ns")         # tCS2
    _set_ui(dut, 1, 0)                      # CS rises
    await Timer(CS_GAP_NS, unit="ns")
    return got


async def results(dut, cmds, flush=CLEAR):
    """Send cmds and return each one's result, from two words later.

    Two flush words go after the last command to bring its result out.
    CLEAR is the default flush because it changes no state.
    """
    got = [await word(dut, c) for c in list(cmds) + [flush, flush]]
    return got[2:]
