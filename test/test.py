# SPDX-FileCopyrightText: © 2026 Max Gabriel Susman
# SPDX-License-Identifier: Apache-2.0
#
# argus_rhd against the RHD2132 contract (argus_rhd2132_model.vhd in
# argus-neural-codec). Step A.1 covers every result that needs no stored
# state; A.2 adds the register file, CONVERT of amplifier channels and the
# CALIBRATE countdown.

import cocotb

import rhd


def check(cmds, got, want):
    for c, g, w in zip(cmds, got, want):
        assert g == w, f"command {c:04x}: got {g:04x}, expected {w:04x}"


@cocotb.test()
async def test_reset_words(dut):
    """The first two words after reset read back as zero: the pipeline."""
    await rhd.reset(dut)
    first = [await rhd.word(dut, rhd.CLEAR) for _ in range(3)]
    assert first[:2] == [0, 0], f"reset words {first[:2]}"
    assert first[2] == rhd.IDLE, f"third word {first[2]:04x}, the first CLEAR's result"


@cocotb.test()
async def test_write_ack(dut):
    """WRITE returns 0xFF and the data, to any address, RAM or not."""
    await rhd.reset(dut)
    cmds = [rhd.write(0, 0xDE), rhd.write(4, 0x80), rhd.write(17, 0x00),
            rhd.write(18, 0x5A), rhd.write(40, 0xFF), rhd.write(63, 0x01)]
    got = await rhd.results(dut, cmds)
    check(cmds, got, [rhd.write_ack(c & 0xFF) for c in cmds])


@cocotb.test()
async def test_rom(dut):
    """READ of the ROM: "INTAN", die revision 1, unipolar, 32 amps, ID 1."""
    await rhd.reset(dut)
    rom = {40: ord("I"), 41: ord("N"), 42: ord("T"), 43: ord("A"), 44: ord("N"),
           60: 1, 61: 1, 62: 32, 63: 1}
    cmds = [rhd.read(a) for a in rom]
    got = await rhd.results(dut, cmds)
    check(cmds, got, list(rom.values()))
    dut._log.info("ROM 40-44: " + "".join(chr(g) for g in got[:5]))


@cocotb.test()
async def test_unmapped_reads(dut):
    """Addresses between the RAM and the ROM read zero."""
    await rhd.reset(dut)
    addrs = [18, 25, 39, 45, 50, 59]
    cmds = [rhd.read(a) for a in addrs]
    got = await rhd.results(dut, cmds)
    check(cmds, got, [0] * len(addrs))


@cocotb.test()
async def test_aux_channels(dut):
    """CONVERT of channels 32 to 62 returns the aux marker 0xA000 | c."""
    await rhd.reset(dut)
    chans = [32, 33, 34, 48, 49, 62]
    cmds = [rhd.convert(c) for c in chans]
    got = await rhd.results(dut, cmds)
    check(cmds, got, [rhd.aux_marker(c) for c in chans])


@cocotb.test()
async def test_aux_commands_idle(dut):
    """CLEAR and the other aux commands return the idle result.

    CALIBRATE is left for A.2: its result is idle too, but it also starts
    the countdown that swallows the next nine commands.
    """
    await rhd.reset(dut)
    cmds = [rhd.CLEAR, 0x4000, 0x7FFF, 0x6A00]
    got = await rhd.results(dut, cmds)
    check(cmds, got, [rhd.IDLE] * len(cmds))


@cocotb.test()
async def test_pipeline_interleaved(dut):
    """Mixed commands back to back: each result lands two words later."""
    await rhd.reset(dut)
    cmds = [rhd.read(40), rhd.write(3, 0x33), rhd.convert(40), rhd.CLEAR,
            rhd.read(62), rhd.write(9, 0x99), rhd.read(44)]
    want = [ord("I"), rhd.write_ack(0x33), rhd.aux_marker(40), rhd.IDLE,
            32, rhd.write_ack(0x99), ord("N")]
    got = await rhd.results(dut, cmds)
    check(cmds, got, want)


@cocotb.test()
async def test_cs_echo_and_retire_toggle(dut):
    """uo_out[1] follows CS_n; uo_out[2] toggles once per word."""
    await rhd.reset(dut)
    assert rhd.uo_bit(dut, rhd.CS_ECHO) == 1, "CS_n echo should be high"
    toggle = rhd.uo_bit(dut, rhd.RETIRED)
    for _ in range(3):
        await rhd.word(dut, rhd.CLEAR)
        now = rhd.uo_bit(dut, rhd.RETIRED)
        assert now != toggle, "retire output did not toggle"
        toggle = now
