/*
 * Copyright (c) 2026 Max Gabriel Susman
 * SPDX-License-Identifier: Apache-2.0
 *
 * argus_rhd_core: the RHD2132 command engine. Decodes the command being
 * retired, produces its result (argus_rhd_spi sends it back two words
 * later) and updates the chip's state on the same SCLK falling edge. The
 * contract is argus_rhd2132_model.vhd in argus-neural-codec, the RHD2000
 * datasheet protocol as the Argus fabric already uses it.
 *
 * Commands (bits 15:14 are the opcode):
 *
 *   00 CONVERT(c)  c in 13:8. c = 63 advances the mux instead, wrapping
 *                  from 31 to 0. The mux moves to the converted channel.
 *                  Channels below 32 return a sample; the rest return the
 *                  aux marker 0xA000 | c. Converting channel 31 advances the
 *                  sample index, after its own result.
 *   01 aux         CALIBRATE is 0x5500: the next nine commands are consumed
 *                  without effect and return the idle result. CLEAR is
 *                  0x6A00. Every aux command returns the idle result.
 *   10 WRITE(a,d)  a in 13:8, d in 7:0. Result: 0xFF, then d. Stored only
 *                  for a < 18.
 *   11 READ(a)     a in 13:8. Result: 0x00, then the register.
 *
 * Registers 0 to 17 are RAM, cleared by reset. 40 to 44 read "INTAN"; 60 to
 * 63 are the die revision, the unipolar flag, the amplifier count and the
 * chip ID; every other address reads 0. Register 4 bit 6 is twoscomp: the
 * idle result is 0x8000 when it is 0, 0x0000 when it is 1, and it sets the
 * RAMP pattern's format.
 *
 * Samples (there is no analog front end), chosen by the pattern strap:
 *
 *   IDENT  {chip[1:0], channel[5:0], index[7:0]}: every word names the lane,
 *          channel and sweep it came from, which is what the Argus
 *          firmware's per-lane frame check reads.
 *   RAMP   ((index + channel) mod 256) as a signed byte, shifted left by 6;
 *          offset binary (0x8000 added) unless twoscomp is set.
 *
 * One deliberate difference from the model: CALIBRATE also clears the mux
 * and the sample index. The fabric resets its models just before the init
 * sequence, and that sequence sends no CONVERT before CALIBRATE, so the two
 * agree word for word; an external chip that is not reset with the chain
 * gets the same starting point from CALIBRATE instead.
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
    output logic [15:0] result,

    input  wire  [1:0] strap_chip,    // bits 15:14 of the IDENT pattern
    input  wire        strap_ramp,    // 0 IDENT, 1 RAMP
    output wire        calibrating,
    output wire        twoscomp
);

  localparam logic [1:0] OP_CONVERT = 2'b00;
  localparam logic [1:0] OP_AUX     = 2'b01;
  localparam logic [1:0] OP_WRITE   = 2'b10;
  localparam logic [1:0] OP_READ    = 2'b11;

  localparam logic [15:0] CMD_CALIBRATE = 16'h5500;

  localparam int         N_RAM      = 18;
  localparam logic [5:0] N_RAM_ADDR = 6'd18;

  // The parameters as bytes and channel numbers.
  localparam logic [7:0] DIE_REVISION_B = DIE_REVISION[7:0];
  localparam logic [7:0] CH_PER_CHIP_B  = CH_PER_CHIP[7:0];
  localparam logic [7:0] CHIP_ID_B      = CHIP_ID[7:0];
  localparam logic [5:0] LAST_CH        = CH_PER_CHIP_B[5:0] - 6'd1;

  wire [1:0] op   = cmd[15:14];
  wire [5:0] addr = cmd[13:8];   // the channel, for CONVERT
  wire [7:0] data = cmd[7:0];

  // -- State, all on the retiring falling edge ---------------------------

  logic [7:0] ram [0:N_RAM-1];
  logic [5:0] mux_ch;            // the channel converted last
  logic [7:0] sample_idx;        // sweeps completed, mod 256
  logic [3:0] cal_cnt;           // commands left to swallow after CALIBRATE

  assign twoscomp    = ram[4][6];
  assign calibrating = (cal_cnt != 4'd0);

  wire [15:0] idle = {!twoscomp, 15'h0000};

  // -- The channel a CONVERT acts on -------------------------------------

  logic [5:0] conv_ch;

  always_comb begin
    if (addr != 6'd63) begin
      conv_ch = addr;
    end else if (mux_ch == LAST_CH) begin
      conv_ch = 6'd0;
    end else begin
      conv_ch = mux_ch + 6'd1;
    end
  end

  wire is_amp = ({2'b00, conv_ch} < CH_PER_CHIP_B);

  // -- Registers ---------------------------------------------------------

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
      default: rom = 8'h00;
    endcase
  endfunction

  wire is_ram = (addr < N_RAM_ADDR);
  wire [7:0] reg_value = is_ram ? ram[addr[4:0]] : rom(addr);

  // -- Samples -----------------------------------------------------------

  wire [7:0] phase = sample_idx + {2'b00, conv_ch};

  wire [15:0] sample = strap_ramp
      ? {phase[7] ^ !twoscomp, phase[7], phase, 6'b000000}
      : {strap_chip, conv_ch, sample_idx};

  // -- The result --------------------------------------------------------

  always_comb begin
    if (calibrating) begin
      result = idle;
    end else begin
      case (op)
        OP_CONVERT: result = is_amp ? sample : {8'hA0, 2'b00, conv_ch};
        OP_WRITE:   result = {8'hFF, data};
        OP_READ:    result = {8'h00, reg_value};
        OP_AUX:     result = idle;
      endcase
    end
  end

  // -- State updates -----------------------------------------------------

  always_ff @(negedge sclk or negedge rst_n) begin
    if (!rst_n) begin
      for (int i = 0; i < N_RAM; i++) begin
        ram[i] <= 8'h00;
      end
      mux_ch     <= 6'd0;
      sample_idx <= 8'd0;
      cal_cnt    <= 4'd0;
    end else if (retire) begin
      if (calibrating) begin
        cal_cnt <= cal_cnt - 4'd1;
      end else begin
        if (op == OP_CONVERT) begin
          mux_ch <= conv_ch;
          if (conv_ch == LAST_CH) begin
            sample_idx <= sample_idx + 8'd1;
          end
        end
        if ((op == OP_WRITE) && is_ram) begin
          ram[addr[4:0]] <= data;
        end
        if (cmd == CMD_CALIBRATE) begin
          cal_cnt    <= 4'd9;
          mux_ch     <= 6'd0;
          sample_idx <= 8'd0;
        end
      end
    end
  end

endmodule
