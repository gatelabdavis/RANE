
module dff
(
  input clk,
  output reg Q,
  input D
);

  //reg Q;
  initial Q = 0;

  always @(posedge clk) begin
    Q <= D;
  end


endmodule
