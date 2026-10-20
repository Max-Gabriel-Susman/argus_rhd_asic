/*
 * Copyright (c) 2026 Max Gabriel Susman
 * SPDX-License-Identifier: Apache-2.0
 *
 * argus_rhd: an RHD2132-compatible SPI command engine for Argus.
 *
 * A.0 STUB. This is not the RHD2132 yet. It echoes each 16-bit word back two
 * words later, which is the RHD2132's result pipeline depth, using the same
 * clocking the real core will use:
 *
 *   - clk is SCLK, fed to the demo board's CLK header from the Arty.
 *   - MOSI shifts in on SCLK rising.
 *   - A falling-edge counter, cleared while CS is high, picks the MISO bit:
 *     bit 15 is on the pin from CS falling, and each later bit appears just
 *     after a falling edge (SPI mode 0, as the RHD2000 datasheet specifies).
 *   - The 16th falling edge retires the word and moves the pipeline.
 *
 * The point of the stub is to prove, before any real RTL exists, that this
 * clocking (both clock edges, CS as an asynchronous clear) gets through the
 * Tiny Tapeout flow, and how much of a tile a pipeline this size uses.
 *
 * Pins:
 *   ui_in[0]  CS_n          uo_out[0]  MISO
 *   ui_in[1]  MOSI          uo_out[1]  CS_n echo
 *                           uo_out[2]  toggles on every retired word
 *   clk       SCLK          uo_out[7:3] 0
 *   rst_n     reset         uio        unused, inputs
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

  // MOSI, shifted in on SCLK rising. SCLK only toggles while CS is low.
  logic [15:0] shift_in;

  always_ff @(posedge clk) begin
    if (!cs_n) begin
      shift_in <= {shift_in[14:0], mosi};
    end
  end

  // Falling edges seen in this word, 0..16, held at 0 while CS is high.
  logic [4:0] fall_cnt;

  always_ff @(negedge clk or posedge cs_n) begin
    if (cs_n) begin
      fall_cnt <= 5'd0;
    end else if (fall_cnt != 5'd16) begin
      fall_cnt <= fall_cnt + 5'd1;
    end
  end

  // The 16th falling edge comes after the master has sampled the last bit,
  // so it is the safe point to retire the word and move the pipeline:
  // pending holds the word from the last window, out_word the one before.
  logic [15:0] pending;
  logic [15:0] out_word;
  logic        retired;

  wire last_fall = !cs_n && (fall_cnt == 5'd15);

  always_ff @(negedge clk or negedge rst_n) begin
    if (!rst_n) begin
      pending  <= 16'h0000;
      out_word <= 16'h0000;
      retired  <= 1'b0;
    end else if (last_fall) begin
      out_word <= pending;
      pending  <= shift_in;
      retired  <= !retired;
    end
  end

  // Bit 15 - fall_cnt; 15 - n is ~n in four bits. Low outside the word.
  wire miso = !cs_n && !fall_cnt[4] && out_word[~fall_cnt[3:0]];

  assign uo_out  = {5'b00000, retired, cs_n, miso};
  assign uio_out = 8'h00;
  assign uio_oe  = 8'h00;

  wire _unused = &{ena, ui_in[7:2], uio_in, 1'b0};

endmodule
