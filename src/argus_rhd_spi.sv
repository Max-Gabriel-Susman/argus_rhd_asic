/*
 * Copyright (c) 2026 Max Gabriel Susman
 * SPDX-License-Identifier: Apache-2.0
 *
 * argus_rhd_spi: the RHD2132's SPI framing and two-word result pipeline,
 * clocked by SCLK itself.
 *
 *   - MOSI shifts in on SCLK rising.
 *   - A falling-edge counter, cleared while CS is high, picks the MISO bit:
 *     bit 15 is on the pin from CS falling, and each later bit appears just
 *     after a falling edge (SPI mode 0, as the RHD2000 datasheet specifies).
 *   - The 16th falling edge comes after the master has sampled the last bit.
 *     It retires the word: `retire` is high in the half period before it,
 *     with the received command on `cmd`, so the command engine updates its
 *     state on that same edge and this module captures `result`.
 *   - The result of the command in window n is shifted out in window n+2,
 *     as on the RHD2132. The first two windows after reset return zeros.
 *
 * Nothing happens while CS is high: there are no SCLK edges.
 */

`default_nettype none

module argus_rhd_spi (
    input  wire        sclk,
    input  wire        rst_n,
    // CS_n is used two ways: as the asynchronous clear of the falling-edge
    // counter, and as a synchronous enable of the MOSI shift register and of
    // the retire. Both are safe because CS only changes while SCLK is idle
    // low, at least half an SCLK period (24 ns) from any edge, and the flow
    // times the synchronous uses as ordinary inputs.
    /* verilator lint_off SYNCASYNCNET */
    input  wire        cs_n,
    /* verilator lint_on SYNCASYNCNET */
    input  wire        mosi,
    output wire        miso,

    output wire [15:0] cmd,
    output wire        retire,
    input  wire [15:0] result,

    output wire        retired_toggle
);

  // MOSI, shifted in on SCLK rising.
  logic [15:0] shift_in;

  always_ff @(posedge sclk) begin
    if (!cs_n) begin
      shift_in <= {shift_in[14:0], mosi};
    end
  end

  // Falling edges seen in this word, 0..16, held at 0 while CS is high.
  logic [4:0] fall_cnt;

  always_ff @(negedge sclk or posedge cs_n) begin
    if (cs_n) begin
      fall_cnt <= 5'd0;
    end else if (fall_cnt != 5'd16) begin
      fall_cnt <= fall_cnt + 5'd1;
    end
  end

  // High from the 16th rising edge to the 16th falling edge.
  assign retire = !cs_n && (fall_cnt == 5'd15);
  assign cmd    = shift_in;

  // The pipeline: pending holds the last window's result, out_word the one
  // before, which is the one going out now.
  logic [15:0] pending;
  logic [15:0] out_word;
  logic        toggle;

  always_ff @(negedge sclk or negedge rst_n) begin
    if (!rst_n) begin
      pending  <= 16'h0000;
      out_word <= 16'h0000;
      toggle   <= 1'b0;
    end else if (retire) begin
      out_word <= pending;
      pending  <= result;
      toggle   <= !toggle;
    end
  end

  // Bit 15 - fall_cnt; 15 - n is ~n in four bits. Low outside the word.
  assign miso           = !cs_n && !fall_cnt[4] && out_word[~fall_cnt[3:0]];
  assign retired_toggle = toggle;

endmodule
