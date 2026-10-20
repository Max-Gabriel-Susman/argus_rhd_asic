-- SPDX-FileCopyrightText: 2026 Max Gabriel Susman
-- SPDX-License-Identifier: Apache-2.0
--
-- Drives argus_rhd2132_model with commands from cmds.txt (one hex word per
-- line) and writes each command's result (dbg_last_resp after its retire)
-- to results.txt.
library ieee;
  use ieee.std_logic_1164.all;
  use ieee.numeric_std.all;
  use std.textio.all;
  use ieee.std_logic_textio.all;

entity tb_xcheck is
  generic (chip : natural := 0; pat : natural := 0);
end entity;

architecture sim of tb_xcheck is
  signal clk   : std_logic := '0';
  signal rst_n : std_logic := '0';
  signal sclk, mosi : std_logic := '0';
  signal cs_n  : std_logic := '1';
  signal miso, miso_oe, ext_req, cmd_valid : std_logic;
  signal ext_ch : unsigned(5 downto 0);
  signal last_cmd, last_resp : std_logic_vector(15 downto 0);
  signal done : boolean := false;
begin
  clk <= not clk after 4 ns when not done;

  dut : entity work.argus_rhd2132_model
    generic map (chip_id => chip, pattern => pat)
    port map (clk => clk, rst_n => rst_n, sclk => sclk, cs_n => cs_n,
              mosi => mosi, miso => miso, miso_oe => miso_oe,
              ext_req => ext_req, ext_ch => ext_ch,
              dbg_last_cmd => last_cmd, dbg_cmd_valid => cmd_valid,
              dbg_last_resp => last_resp);

  stim : process
    file fi : text open read_mode is "cmds.txt";
    file fo : text open write_mode is "results.txt";
    variable li, lo : line;
    variable w : std_logic_vector(15 downto 0);
  begin
    wait for 100 ns; rst_n <= '1'; wait for 100 ns;
    while not endfile(fi) loop
      readline(fi, li); hread(li, w);
      cs_n <= '0'; wait for 40 ns;
      for i in 15 downto 0 loop
        mosi <= w(i); wait for 40 ns;
        sclk <= '1'; wait for 40 ns;
        sclk <= '0';
      end loop;
      wait for 40 ns; cs_n <= '1'; wait for 80 ns;
      hwrite(lo, last_resp); writeline(fo, lo);
    end loop;
    done <= true; wait;
  end process;
end architecture;
