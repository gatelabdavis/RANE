
module lat
(
  input en,
  output reg Q,
  input k0,
  input k1,
  input D
);

  initial Q = 0;
          
  always @(*) begin
    case({k0, k1})
      2'b00: Q <= 0; 
      2'b01: if (en) Q <= D;
      2'b10: if (!en) Q <= D;
      2'b11: Q <= 1;
      //default: Q <= Q;
    endcase
  end

endmodule
