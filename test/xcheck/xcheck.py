# SPDX-FileCopyrightText: © 2026 Max Gabriel Susman
# SPDX-License-Identifier: Apache-2.0
#
# Cross-checks test/rhd_model.py, the reference the cocotb tests compare the
# chip against, with argus_rhd2132_model.vhd, the model the Argus fabric
# runs. Random command streams go through both; every result must match.
#
# Run by hand; it needs GHDL and a checkout of argus-neural-codec:
#
#   python3 test/xcheck/xcheck.py ~/Documents/argus-neural-codec/rtl/argus_rhd2132_model.vhd
#
# The ASIC's one deliberate difference, CALIBRATE also clearing the mux and
# the sample index, is switched off here so the two can agree exactly.

import os
import random
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import rhd_model                      # noqa: E402
from rhd_model import RhdModel        # noqa: E402

SEEDS = 12
COMMANDS = 1500


class FabricModel(RhdModel):
    """RhdModel without the ASIC's CALIBRATE clear: the VHDL behaviour."""

    def step(self, cmd):
        mux, idx = self.mux_ch, self.sample_idx
        result = super().step(cmd)
        if cmd == rhd_model.CMD_CALIBRATE and self.cal_cnt == 9:
            self.mux_ch, self.sample_idx = mux, idx
        return result


def random_stream(rng, n):
    def one():
        r = rng.random()
        if r < 0.45:
            return rng.choice([63] * 4 + list(range(64))) << 8          # CONVERT
        if r < 0.65:
            return 0x8000 | (rng.randrange(64) << 8) | rng.randrange(256)  # WRITE
        if r < 0.90:
            return 0xC000 | (rng.randrange(64) << 8)                    # READ
        if r < 0.94:
            return rhd_model.CMD_CALIBRATE
        return 0x4000 | rng.randrange(0x4000)                         # other aux
    return [one() for _ in range(n)]


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: python3 test/xcheck/xcheck.py path/to/argus_rhd2132_model.vhd")
    vhdl_model = os.path.abspath(sys.argv[1])

    work = tempfile.mkdtemp(prefix="xcheck_")
    try:
        shutil.copy(os.path.join(HERE, "tb_xcheck.vhd"), work)
        open(os.path.join(work, "cmds.txt"), "w").write("0000\n")
        ghdl = ["ghdl", "--std=08", "-frelaxed"]
        subprocess.run([ghdl[0], "-a"] + ghdl[1:] + [vhdl_model, "tb_xcheck.vhd"],
                       cwd=work, check=True)
        subprocess.run([ghdl[0], "-e"] + ghdl[1:] + ["tb_xcheck"], cwd=work, check=True)

        failed = 0
        for seed in range(SEEDS):
            rng = random.Random(seed)
            chip, ramp = rng.randrange(4), bool(seed % 2)
            cmds = random_stream(rng, COMMANDS)
            with open(os.path.join(work, "cmds.txt"), "w") as f:
                f.write("".join(f"{c:04X}\n" for c in cmds))
            subprocess.run([ghdl[0], "-r"] + ghdl[1:] + ["tb_xcheck", f"-gchip={chip}",
                            f"-gpat={int(ramp)}"], cwd=work, check=True, capture_output=True)
            vhdl = [int(x, 16) for x in open(os.path.join(work, "results.txt")).read().split()]

            model = FabricModel(chip=chip, ramp=ramp)
            py = [model.step(c) for c in cmds]
            bad = [(i, c, v, p) for i, (c, v, p) in enumerate(zip(cmds, vhdl, py)) if v != p]
            line = (f"seed {seed:2d}: chip {chip} {'RAMP ' if ramp else 'IDENT'} "
                    f"{len(cmds)} commands, {len(bad)} mismatches")
            if bad:
                i, c, v, p = bad[0]
                line += f"; first at #{i}: command {c:04x}, VHDL {v:04x}, Python {p:04x}"
                failed += 1
            print(line)

        print("PASS" if not failed else f"FAIL: {failed} of {SEEDS} streams differ")
        sys.exit(1 if failed else 0)
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
