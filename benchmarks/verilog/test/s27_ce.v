
module s27_obf(CK,G0,G1,G2,G3,G17, keyinput);
input CK,G0,G1,G2,G3;
input [1:0] keyinput;
output G17;

  wire G5,G10,G6,G11,G7,G13,G14,G8,G15,G12,G16,G9;

  dff DFF_0(CK,G5,G10);
  dff DFF_1(CK,G6,G11);
  dff DFF_2(CK,G7,G13);
  not  NOT_0(G14,G0);
  not  NOT_1(G17_obf,G11);
  and AND2_0(G8,G14,G6);
  or OR2_0(G15,G12,G8);
  or OR2_1(G16,G3,G8);
  nand NAND2_0(G9,G16,G15);
  nor NOR2_0(G10,G14,G11);
  nor NOR2_1(G11,G5,G9);
  nor NOR2_2(G12,G1,G7);
  nor NOR2_3(G13,G2,G12);
  xor obf_0(G17_obf2, keyinput[0], G17_obf);
  xnor obf_1(G17, keyinput[1], G17_obf2);

endmodule

