import logging
from pyverilog.ast_code_generator.codegen import ASTCodeGenerator
import pyverilog.vparser.ast as vast
from common.circuit import Wire
from file.verilog import read_verilog_wires, circuit2verilog


def write_verilog(ast, filename, path):
    codegen = ASTCodeGenerator()
    out_file = open(path + filename, 'w')
    out_file.write(codegen.visit(ast))
    out_file.close()
    logging.debug("bench is written to: " + path + filename)


def build_ce(cir):
    # ce_netlist = copy.copy(obf_cir.raw_netlist)
    rep_wire_names = {}
    seq_elements = []
    count = 0
    # cir = obf_cir
    cir.wire_objs = read_verilog_wires(cir.folder_path + cir.file_name, 'generic')

    added_wires = {}
    for w in cir.wire_objs:
        if cir.wire_objs[w].type == 'dff':
            Q = w
            D = cir.wire_objs[w].operands[0]
            rep_wire_names[str(Q)] = "state[" + str(count) + "]"
            if ("'b" in D) or (D in cir.input_wires) or (D[:D.rfind('[')] in cir.input_wires):
                # for constant 1'b1 and 1'b0 inputs
                r = "next_state[{}]".format(count)
                added_wires[r] = Wire(r, 'buf', [str(D)])
            else:
                rep_wire_names[str(D)] = "next_state[{}]".format(count)
            seq_elements.append(w)
            count = count + 1
    cir.wire_objs = {**cir.wire_objs, **added_wires}

    for w in cir.wire_objs:
        if cir.wire_objs[w].type == 'lat':
            Q = w
            D = cir.wire_objs[w].operands[0]
            rst = cir.wire_objs[w].operands[1]
            rep_wire_names[str(Q)] = "state[" + str(count) + "]"
            rep_wire_names[str(D)] = "next_state[" + str(count) + "]"
            rep_wire_names[str(rst)] = "next_state[" + str(count+1) + "]"
            seq_elements.append(w)
            count = count + 2

    # remove dffs/lats
    for w in seq_elements:
        cir.wire_objs.pop(w)

    # change dff input/output wires to next_state/state
    for r in rep_wire_names:
        if r in cir.wire_objs:
            cir.wire_objs[rep_wire_names[r]] = cir.wire_objs[r]
            cir.wire_objs.pop(r)
        for w in cir.wire_objs:
            if r in cir.wire_objs[w].operands:
                cir.wire_objs[w].operands[cir.wire_objs[w].operands.index(r)] = rep_wire_names[r]

    # add new buf gates for replaced outputs
    for r in rep_wire_names:
        if r in cir.output_wires:
            cir.wire_objs[r] = Wire(r, 'buf', [rep_wire_names[r]])
    # for vectorized wires
    for r in rep_wire_names:
        if r[:r.rfind('[')] in cir.output_wires:
            cir.wire_objs[r] = Wire(r, 'buf', [rep_wire_names[r]])

    # add ports
    cir.port_defs = cir.port_defs + ['state', 'next_state']
    cir.input_wires['state'] = count
    cir.output_wires['next_state'] = count

    verilog_text = circuit2verilog(cir, cir.name + '_ce')
    return verilog_text, count


def gen_dff(path):
    clk = vast.Ioport(vast.Input('clk'))
    q = vast.Ioport(vast.Output('Q'))
    d = vast.Ioport(vast.Input('D'))
    ports = vast.Portlist([clk, q, d])

    q_reg = vast.Identifier('reg Q = 0;')

    sens = vast.Sens(vast.Identifier('clk'), type='posedge')
    senslist = vast.SensList([sens])

    assign_q = vast.NonblockingSubstitution(
        vast.Lvalue(vast.Identifier('Q')),
        vast.Rvalue(vast.Identifier('D')))

    statement = vast.Block([assign_q])
    always = vast.Always(senslist, statement)

    items = []
    items.append(q_reg)
    items.append(always)
    ast = vast.ModuleDef("dff", None, ports, items)

    write_verilog(ast, 'dff.v', path)


def gen_lat(path):
    clk = vast.Ioport(vast.Input('en'))
    q = vast.Ioport(vast.Output('Q'))
    d = vast.Ioport(vast.Input('D'))
    r = vast.Ioport(vast.Input('rst'))
    ports = vast.Portlist([clk, q, d, r])

    q_reg = vast.Identifier('reg Q = 0;')

    sens = []
    sens.append(vast.Sens(vast.Identifier('en'), type='level'))
    sens.append(vast.Sens(vast.Identifier('rst'), type='level'))
    sens.append(vast.Sens(vast.Identifier('D'), type='level'))

    senslist = vast.SensList(sens)

    assign_q = vast.NonblockingSubstitution(
        vast.Lvalue(vast.Identifier('Q')),
        vast.Rvalue(vast.Identifier('D')))

    blocks = []
    blocks.append(vast.IfStatement(vast.Identifier('rst'),
                    vast.Identifier('Q <= 0;'),
                    vast.IfStatement(vast.Identifier('en'), assign_q, None), None))

    statement = vast.Block(blocks)
    always = vast.Always(senslist, statement)

    items = []
    items.append(q_reg)
    items.append(always)
    ast = vast.ModuleDef("lat", None, ports, items)

    write_verilog(ast, 'lat.v', path)
