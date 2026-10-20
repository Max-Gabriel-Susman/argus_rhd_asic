/*
 * Copyright (c) 2026 Max Gabriel Susman
 * SPDX-License-Identifier: Apache-2.0
 *
 * argus_rhd_core: the RHD2132 command engine. Decodes the command being
 * retired and produces its result, which argus_rhd_spi sends back two words
 * later. The contract is argus_rhd2132_model.vhd in argus-neural-codec, the
 * RHD2000 datasheet protocol as the Argus fabric already uses it.
 *
 * Commands (bits 15:14 are the opcode):
 *
 *   00 CONVERT(c)  c in 13:8. c < 32: the sample for channel c. c = 63:
 *                  advance the mux and convert. Otherwise an aux input:
 *                  the marker 0xA000 | c.
 *   01 aux         CALIBRATE is 0x5500, CLEAR is 0x6A00. Result: idle.
 *   10 WRITE(a,d)  a in 13:8, d in 7:0. Result: 0xFF, then d.
 *   11 READ(a)     a in 13:8. Result: 0x00, then the register.
 *
 * Registers 0 to 17 are RAM; 40 to 44 read "INTAN"; 60 to 63 are the die
 * revision, the unipolar flag, the amplifier count and the chip ID; every
 * other address reads 0. The idle result is 0x8000 when register 4 bit 6
 * (twoscomp) is 0, 0x0000 when it is 1.
 *
 * STEP A.1: stateless. Every result that does not depend on stored state is
 * final here: the WRITE acknowledgement, ROM reads, the aux marker and the
 * idle result. A.2 adds the state: the register file (RAM reads return 0
 * until then, and twoscomp is 0), the mux and sample counters behind
 * CONVERT of an amplifier channel and CONVERT(63) (0 until then), and the
 * CALIBRATE countdown. clk, rst_n and retire are already wired for it.
 */

`default_nettype none

module argus_rhd_core #(
    parameter int CH_PER_CHIP  = 32,
    parameter int DIE_REVISION = 1,
    parameter int CHIP_ID      = 1    // the ROM chip ID: 1 is the RHD2132
) (
    input  wire        sclk,
    input  wire        rst_n,
    input  wire [15:0] cmd,
    input  wire        retire,
    output logic [15:0] result
);

  localparam logic [1:0] OP_CONVERT = 2'b00;
  localparam logic [1:0] OP_AUX     = 2'b01;
  localparam logic [1:0] OP_WRITE   = 2'b10;
  localparam logic [1:0] OP_READ    = 2'b11;

  wire [1:0] op   = cmd[15:14];
  wire [5:0] addr = cmd[13:8];   // the channel, for CONVERT
  wire [7:0] data = cmd[7:0];

  // A.2: register 4 bit 6.
  wire twoscomp = 1'b0;

  // The parameters as bytes, for the ROM.
  localparam logic [7:0] DIE_REVISION_B = DIE_REVISION[7:0];
  localparam logic [7:0] CH_PER_CHIP_B  = CH_PER_CHIP[7:0];
  localparam logic [7:0] CHIP_ID_B      = CHIP_ID[7:0];

  wire [15:0] idle = {!twoscomp, 15'h0000};

  // The read-only registers.
  function automatic logic [7:0] rom(input logic [5:0] a);
    case (a)
      6'd40:   rom = 8'h49;                    // I
      6'd41:   rom = 8'h4E;                    // N
      6'd42:   rom = 8'h54;                    // T
      6'd43:   rom = 8'h41;                    // A
      6'd44:   rom = 8'h4E;                    // N
      6'd60:   rom = DIE_REVISION_B;
      6'd61:   rom = 8'd1;                     // unipolar amplifiers
      6'd62:   rom = CH_PER_CHIP_B;
      6'd63:   rom = CHIP_ID_B;
      default: rom = 8'h00;                    // A.2: RAM for 0 to 17
    endcase
  endfunction

  always_comb begin
    case (op)
      OP_CONVERT: begin
        if (({2'b00, addr} >= CH_PER_CHIP_B) && (addr != 6'd63)) begin
          result = {8'hA0, 2'b00, addr};
        end else begin
          result = 16'h0000;                   // A.2: the sample
        end
      end
      OP_WRITE: result = {8'hFF, data};
      OP_READ:  result = {8'h00, rom(addr)};
      OP_AUX:   result = idle;
    endcase
  end

  wire _unused = &{sclk, rst_n, retire, 1'b0};

endmodule
