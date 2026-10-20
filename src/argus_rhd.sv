/*
 * Copyright (c) 2026 Max Gabriel Susman
 * SPDX-License-Identifier: Apache-2.0
 *
 * argus_rhd: an RHD2132-compatible SPI command engine for Argus, the
 * Tiny Tapeout top. argus_rhd_spi does the framing and the result pipeline,
 * argus_rhd_core decodes the commands.
 *
 * The chip is clocked by SCLK: on the demo board, the Arty's SCLK goes to
 * the CLK pin of header J9, with the RP2's project clock stopped
 * (tt.clock_project_stop()) so the line is free.
 *
 * Pins:
 *   ui_in[0]    CS_n                  uo_out[0]   MISO
 *   ui_in[1]    MOSI                  uo_out[1]   CS_n echo
 *   ui_in[3:2]  chip number strap     uo_out[2]   toggles on every retired command
 *   ui_in[4]    pattern: 0 IDENT,     uo_out[3]   calibrating
 *               1 RAMP                uo_out[4]   twoscomp (register 4 bit 6)
 *   ui_in[7:5]  unused, tie low       uo_out[7:5] 0
 *   clk         SCLK                  uio         unused, inputs
 *   rst_n       reset
 *
 * Strap the chip number to the Argus lane the chip is on (0 for lane 0):
 * the IDENT pattern carries it in bits 15:14 of every sample, and the
 * firmware's frame check expects the lane's own number there.
 */

`default_nettype none

module tt_um_max_gabriel_susman_argus_rhd (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);

  wire cs_n = ui_in[0];
  wire mosi = ui_in[1];

  wire        miso;
  wire [15:0] cmd;
  wire        retire;
  wire [15:0] result;
  wire        retired_toggle;
  wire        calibrating;
  wire        twoscomp;

  argus_rhd_spi spi (
      .sclk          (clk),
      .rst_n         (rst_n),
      .cs_n          (cs_n),
      .mosi          (mosi),
      .miso          (miso),
      .cmd           (cmd),
      .retire        (retire),
      .result        (result),
      .retired_toggle(retired_toggle)
  );

  argus_rhd_core core (
      .sclk       (clk),
      .rst_n      (rst_n),
      .cmd        (cmd),
      .retire     (retire),
      .result     (result),
      .strap_chip (ui_in[3:2]),
      .strap_ramp (ui_in[4]),
      .calibrating(calibrating),
      .twoscomp   (twoscomp)
  );

  assign uo_out  = {3'b000, twoscomp, calibrating, retired_toggle, cs_n, miso};
  assign uio_out = 8'h00;
  assign uio_oe  = 8'h00;

  wire _unused = &{ena, ui_in[7:5], uio_in, 1'b0};

endmodule
