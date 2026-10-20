<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

An SPI slave for the Intan RHD2132 command set, built as a lane source for Argus, an open-source neural acquisition stack on a Zynq-7020. The chip is clocked by SCLK itself: MOSI shifts in on the rising edge, MISO changes after the falling edge, and the 16th falling edge of each word retires the command. Results come back two words later, as on the RHD2132.

It is being built in steps. So far it answers WRITE (0xFF and the data), READ of the ROM ("INTAN" in registers 40 to 44, die revision, amplifier count and chip ID in 60 to 63), CONVERT of the auxiliary channels (0xA000 and the channel), and CLEAR with the idle result. The register file, amplifier conversions and the CALIBRATE sequence come next.

## How to test

Feed SCLK from the bus master to the demo board's CLK header, with the RP2 in ASIC_MANUAL_INPUTS mode and its project clock stopped (`tt.clock_project_stop()`), and every input DIP switch off. CS_n goes to ui_in[0], MOSI to ui_in[1], MISO comes back on uo_out[0]. Send 16-bit commands in SPI mode 0 at up to 20.8 MHz; each command's result comes back two words later. READ of registers 40 to 44 returns "INTAN" and is the quickest check.

## External hardware

An SPI master that drives SCLK, CS_n and MOSI at 3.3 V: a Digilent Arty Z7-20 running Argus, on Pmod JA.
