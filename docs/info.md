<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

An SPI slave for the Intan RHD2132 command set, built as a lane source for Argus, an open-source neural acquisition stack on a Zynq-7020. The chip is clocked by SCLK itself: MOSI shifts in on the rising edge, MISO changes after the falling edge, and the 16th falling edge of each word retires the command. Results come back two words later, as on the RHD2132.

This is the A.0 stub: it echoes each word back two words later, to prove the clocking through the flow before the full command set goes in.

## How to test

Feed SCLK from the bus master to the demo board's CLK header, with the RP2 in ASIC_MANUAL_INPUTS mode and its project clock stopped (`tt.clock_project_stop()`), and every input DIP switch off. CS_n goes to ui_in[0], MOSI to ui_in[1], MISO comes back on uo_out[0]. Send 16-bit words in SPI mode 0 at up to 20.8 MHz; each word comes back two words later.

## External hardware

An SPI master that drives SCLK, CS_n and MOSI at 3.3 V: a Digilent Arty Z7-20 running Argus, on Pmod JA.
