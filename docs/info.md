<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

An SPI slave for the Intan RHD2132 command set, built as a lane source for Argus, an open-source neural acquisition stack on a Zynq-7020. It answers every command the way the RHD2132's digital interface does, with a test pattern in place of the amplifiers and ADC, so the Argus host cannot tell it from the chip model it runs in the FPGA fabric.

The chip is clocked by SCLK itself: MOSI shifts in on the rising edge, MISO changes after the falling edge, and the 16th falling edge of each word retires the command. Each result comes back two words later, as on the RHD2132.

| Command | Result |
| --- | --- |
| CONVERT(c), c < 32 | a sample: IDENT `{chip, c, sweep}` or RAMP, chosen by `ui[4]` |
| CONVERT(63) | advances the mux (31 wraps to 0) and converts that channel |
| CONVERT(c), 32 to 62 | the aux marker `0xA000 \| c` |
| WRITE(a, d) | `0xFF`, then `d`; stored for registers 0 to 17 |
| READ(a) | `0x00`, then the register: RAM 0 to 17, "INTAN" at 40 to 44, die revision, unipolar flag, amplifier count (32) and chip ID (1) at 60 to 63 |
| CALIBRATE (`0x5500`) | idle; the next nine commands are consumed and return idle; also clears the mux and sweep counter |
| CLEAR and other aux | idle: `0x8000`, or `0x0000` when register 4 bit 6 (twoscomp) is set |

## How to test

Feed SCLK from the bus master to the demo board's CLK header (J9), with the RP2 in ASIC_MANUAL_INPUTS mode and its project clock stopped (`tt.clock_project_stop()`), and every input DIP switch off. CS_n goes to ui_in[0], MOSI to ui_in[1], MISO comes back on uo_out[0]. Set the chip strap on ui_in[3:2] and the pattern on ui_in[4].

Send 16-bit commands in SPI mode 0 at up to 20.8 MHz. READ of registers 40 to 44 returns "INTAN" and is the quickest check. After CALIBRATE and nine more commands, a sweep of CONVERT(0) to CONVERT(31) returns `{chip, channel, sweep}` in every word with the IDENT pattern.

## External hardware

An SPI master that drives SCLK, CS_n and MOSI at 3.3 V: a Digilent Arty Z7-20 running Argus, on Pmod JA.
