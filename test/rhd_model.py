# SPDX-FileCopyrightText: © 2026 Max Gabriel Susman
# SPDX-License-Identifier: Apache-2.0
#
# A reference model of the RHD2132 command engine, transcribed from
# argus_rhd2132_model.vhd in argus-neural-codec (the model the Argus fabric
# already runs), plus the one deliberate difference: CALIBRATE also clears
# the mux and the sample index.
#
# step(cmd) applies one retired command and returns its result. The result
# comes out on MISO two words later; that delay is the bus's business, not
# the model's.

CH_PER_CHIP = 32
N_RAM = 18
CMD_CALIBRATE = 0x5500

ROM = {40: ord("I"), 41: ord("N"), 42: ord("T"), 43: ord("A"), 44: ord("N"),
       60: 1,             # die revision
       61: 1,             # unipolar amplifiers
       62: CH_PER_CHIP,
       63: 1}             # chip ID: RHD2132


class RhdModel:
    def __init__(self, chip=0, ramp=False):
        self.chip = chip & 3
        self.ramp = ramp
        self.reset()

    def reset(self):
        self.ram = [0] * N_RAM
        self.mux_ch = 0
        self.sample_idx = 0
        self.cal_cnt = 0

    @property
    def twoscomp(self):
        return (self.ram[4] >> 6) & 1

    @property
    def calibrating(self):
        return self.cal_cnt != 0

    def idle(self):
        return 0x0000 if self.twoscomp else 0x8000

    def reg(self, addr):
        return self.ram[addr] if addr < N_RAM else ROM.get(addr, 0)

    def sample(self, ch):
        if self.ramp:
            phase = (self.sample_idx + ch) & 0xFF
            signed = phase - 256 if phase & 0x80 else phase
            value = (signed << 6) & 0xFFFF
            return value if self.twoscomp else (value + 0x8000) & 0xFFFF
        return (self.chip << 14) | (ch << 8) | self.sample_idx

    def step(self, cmd):
        """Retire one command; return its result and update the state."""
        op, addr, data = cmd >> 14, (cmd >> 8) & 0x3F, cmd & 0xFF

        if self.cal_cnt:
            # The nine commands after CALIBRATE are consumed, not executed.
            self.cal_cnt -= 1
            return self.idle()

        if op == 0:                                    # CONVERT
            ch = addr
            if ch == 63:
                ch = 0 if self.mux_ch == CH_PER_CHIP - 1 else (self.mux_ch + 1) & 0x3F
            result = self.sample(ch) if ch < CH_PER_CHIP else 0xA000 | ch
            self.mux_ch = ch
            if ch == CH_PER_CHIP - 1:
                self.sample_idx = (self.sample_idx + 1) & 0xFF
            return result

        if op == 2:                                    # WRITE
            if addr < N_RAM:
                self.ram[addr] = data
            return 0xFF00 | data

        if op == 3:                                    # READ
            return self.reg(addr)

        result = self.idle()                           # aux
        if cmd == CMD_CALIBRATE:
            self.cal_cnt = 9
            self.mux_ch = 0
            self.sample_idx = 0
        return result
