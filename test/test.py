# SPDX-FileCopyrightText: © 2026 Max Gabriel Susman
# SPDX-License-Identifier: Apache-2.0
#
# argus_rhd against the RHD2132 contract (argus_rhd2132_model.vhd in
# argus-neural-codec). The stateless results from A.1 are checked against
# fixed values; the stateful ones from A.2 against rhd_model.RhdModel, a
# Python transcription of the VHDL model, command by command.

import random

import cocotb

import rhd
from rhd_model import RhdModel


def check(cmds, got, want):
    for n, (c, g, w) in enumerate(zip(cmds, got, want)):
        assert g == w, f"command {n} ({c:04x}): got {g:04x}, expected {w:04x}"


async def against_model(dut, model, cmds):
    """Send cmds; check every result against the model, flush included."""
    got = await rhd.results(dut, cmds)
    want = [model.step(c) for c in cmds]
    model.step(rhd.CLEAR)                  # the two flush words
    model.step(rhd.CLEAR)
    check(cmds, got, want)
    return got


# -- A.1: stateless results --------------------------------------------------

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
    """CLEAR and the other aux commands (not CALIBRATE) return idle."""
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


# -- A.2: state --------------------------------------------------------------

@cocotb.test()
async def test_ram(dut):
    """RAM reads 0 after reset, then reads back what was written; 18 up is not RAM."""
    await rhd.reset(dut)
    values = [(0x11 * a + 0x07) & 0xFF for a in range(18)]
    cmds = ([rhd.read(a) for a in range(18)]
            + [rhd.write(a, v) for a, v in enumerate(values)]
            + [rhd.write(18, 0x5A)]
            + [rhd.read(a) for a in range(19)])
    want = ([0] * 18
            + [rhd.write_ack(v) for v in values]
            + [rhd.write_ack(0x5A)]
            + values + [0])
    got = await rhd.results(dut, cmds)
    check(cmds, got, want)


@cocotb.test()
async def test_twoscomp(dut):
    """Register 4 bit 6 flips the idle result and drives uo_out[4]."""
    await rhd.reset(dut)
    cmds = [rhd.CLEAR, rhd.write(4, 0x40), rhd.CLEAR, rhd.write(4, 0xBF), rhd.CLEAR]
    want = [0x8000, rhd.write_ack(0x40), 0x0000, rhd.write_ack(0xBF), 0x8000]
    got = await rhd.results(dut, cmds[:2])
    assert rhd.uo_bit(dut, rhd.TWOSCOMP) == 1, "twoscomp pin should be set"
    got += await rhd.results(dut, cmds[2:])
    assert rhd.uo_bit(dut, rhd.TWOSCOMP) == 0, "twoscomp pin should be clear"
    check(cmds, got, want)


@cocotb.test()
async def test_init_and_ident_sweeps(dut):
    """The Arty master's exact init sequence, then sweeps of the IDENT pattern.

    Strapped as chip 2. Every amplifier word must be {2, channel, sweep},
    which is what the Argus firmware's per-lane frame check reads; the two
    aux slots return their markers.
    """
    chip = 2
    await rhd.reset(dut, chip=chip)
    model = RhdModel(chip=chip)

    init = rhd.init_sequence()
    await against_model(dut, model, init)

    sweeps = 3
    got = await against_model(dut, model, rhd.SWEEP * sweeps)
    for s in range(sweeps):
        for c in range(34):
            g = got[s * 34 + c]
            w = (chip << 14) | (c << 8) | s if c < 32 else rhd.aux_marker(c)
            assert g == w, f"sweep {s} channel {c}: got {g:04x}, expected {w:04x}"
    dut._log.info(f"sweep 2: ch0 {got[68]:04x} ch31 {got[99]:04x} aux {got[100]:04x} {got[101]:04x}")


@cocotb.test()
async def test_calibrate(dut):
    """CALIBRATE swallows the next nine commands, raises uo_out[3], and
    clears the mux and the sample index."""
    await rhd.reset(dut)
    model = RhdModel()

    # Move the sample index and the mux away from zero first.
    await against_model(dut, model, rhd.SWEEP * 2 + [rhd.convert(7)])
    assert model.sample_idx == 2 and model.mux_ch == 7

    # CALIBRATE, then nine commands that would all change state if executed.
    swallowed = [rhd.write(0, 0x11), rhd.convert(31), rhd.write(4, 0x40),
                 rhd.convert(63), rhd.read(40), rhd.CALIBRATE, rhd.write(17, 0x22),
                 rhd.convert(31), rhd.read(0)]
    await rhd.word(dut, rhd.CALIBRATE)
    assert rhd.uo_bit(dut, rhd.CALIBRATING) == 1, "calibrating pin should be set"
    model.step(rhd.CALIBRATE)
    got = await against_model(dut, model, swallowed)
    assert got == [rhd.IDLE] * 9, [f"{g:04x}" for g in got]
    assert rhd.uo_bit(dut, rhd.CALIBRATING) == 0, "calibrating pin should be clear"

    # Nothing changed, and CONVERT(63) now starts from channel 0, sweep 0.
    await against_model(dut, model, [rhd.read(0), rhd.read(4), rhd.read(17),
                                     rhd.convert(63), rhd.convert(63)])


@cocotb.test()
async def test_convert_63_walk(dut):
    """CONVERT(63) walks the mux and wraps from 31 to 0, advancing the index."""
    await rhd.reset(dut, chip=1)
    model = RhdModel(chip=1)
    got = await against_model(dut, model, [rhd.convert(29)] + [rhd.convert(63)] * 6)
    chans = [(g >> 8) & 0x3F for g in got]
    idxs = [g & 0xFF for g in got]
    assert chans == [29, 30, 31, 0, 1, 2, 3], chans
    assert idxs == [0, 0, 0, 1, 1, 1, 1], idxs
    # From an aux channel, CONVERT(63) keeps counting up: 40 -> 41.
    await against_model(dut, model, [rhd.convert(40), rhd.convert(63)])


@cocotb.test()
async def test_ramp(dut):
    """The RAMP pattern, offset binary and then two's complement."""
    await rhd.reset(dut, ramp=True)
    model = RhdModel(ramp=True)
    await against_model(dut, model, rhd.init_sequence())
    await against_model(dut, model, rhd.SWEEP * 2)
    await against_model(dut, model, [rhd.write(4, 0x40)] + rhd.SWEEP * 2)


@cocotb.test()
async def test_random_against_model(dut):
    """A random command stream, every result checked against the model."""
    rng = random.Random(random.getrandbits(32))   # cocotb seeds `random`; it is logged
    chip, ramp = rng.randrange(4), rng.random() < 0.5
    await rhd.reset(dut, chip=chip, ramp=ramp)
    model = RhdModel(chip=chip, ramp=ramp)

    def one():
        r = rng.random()
        if r < 0.40:
            return rhd.convert(rng.choice([63] * 4 + list(range(64))))
        if r < 0.65:
            return rhd.write(rng.randrange(64), rng.randrange(256))
        if r < 0.90:
            return rhd.read(rng.randrange(64))
        if r < 0.94:
            return rhd.CALIBRATE
        return 0x4000 | rng.randrange(0x4000)       # any aux command

    cmds = [one() for _ in range(300)]
    await against_model(dut, model, cmds)
    dut._log.info(f"300 random commands match (chip {chip}, {'RAMP' if ramp else 'IDENT'})")
