import logging
from common.circuit import Wire, Circuit
import re


def read_verilog_wires(path, type):
    if type == 'generic':
        return read_generic_verilog_wires(path)
    elif type == 'cadence':
        return read_cadence_verilog_wires(path)
    elif type == 'harpoon':
        return read_dffwrst_wires(path)
    else:
        logging.critical('unknown verilog netlist format: {}'.format(type))


def read_cadence_verilog_wires(path):
    try:
        with open(path, "r") as f:
            design = f.read()
            line = ''.join(design)
    except EnvironmentError:
        logging.critical('{} not found'.format(path))
        exit()

    wires = {}
    # match assign
    assigns = re.findall(r'assign (.*?) = (.*?);', line)
    for a in assigns:
        wires[a[0]] = Wire(a[0], 'buf', 1)
        wires[a[0]].operands = [a[1]]

    # match gates
    # g[0]: gate type; g[1]: gate tag; g[2]: gate ports
    gates = re.findall(r'^\s*(\S*?)\s*(\S*?)\s*\(([\s\S]*?)\);', line, re.MULTILINE)
    for g in gates:
        ports = g[2].replace(' ', '').replace('\n', '')
        gate_ports = re.findall(r'\.(.*?)\s*\((.*?)\)', ports)
        type = g[0].lower()
        if 'dff' in type:
            in_port = ''
            q_port = ''
            qn_port = ''
            for p in gate_ports:
                if p[0] == 'D':
                    in_port = p[1]
                elif p[0] == 'Q':
                    q_port = p[1]
                elif p[0] == 'QN':
                    qn_port = p[1]

            if q_port and qn_port:
                wires[q_port] = Wire(q_port, 'dff', 1)
                wires[q_port].operands = [in_port]
                wires[qn_port] = Wire(qn_port, 'not', 1)
                wires[qn_port].operands = [q_port]
            elif q_port:
                wires[q_port] = Wire(q_port, 'dff', 1)
                wires[q_port].operands = [in_port]
            elif qn_port:
                q_tmp = 'tmp_' + qn_port
                wires[q_tmp] = Wire(q_tmp, 'dff', 1)
                wires[q_tmp].operands = [in_port]
                wires[qn_port] = Wire(qn_port, 'not', 1)
                wires[qn_port].operands = [q_tmp]
            else:
                logging.critical('undefined dff definition: {}'.format(g[1]))
                exit()
        else:
            if 'module' not in type:
                in_port = []
                out_port = ''
                for p in gate_ports:
                    if p[0] == 'Y':
                        out_port = p[1]
                    elif p[0] == 'S0':
                        in_port.insert(0, p[1])
                    else:
                        in_port.append(p[1])
                wires[out_port] = create_wire(type, in_port, out_port)
                wires[out_port].operands = in_port
    return wires


def create_wire(type, in_port, out_port):
    w = None
    if 'nand' in type:
        assert len(in_port) > 1
        w = Wire(out_port, 'nand', in_port)
    elif 'and' in type:
        assert len(in_port) > 1
        w = Wire(out_port, 'and', in_port)
    elif 'xnor' in type:
        assert len(in_port) > 1
        w = Wire(out_port, 'xnor', in_port)
    elif 'xor' in type:
        assert len(in_port) > 1
        w = Wire(out_port, 'xor', in_port)
    elif 'nor' in type:
        assert len(in_port) > 1
        w = Wire(out_port, 'nor', in_port)
    elif 'or' in type:
        assert len(in_port) > 1
        w = Wire(out_port, 'or', in_port)
    elif ('inv' in type) or ('not' in type):
        assert len(in_port) == 1
        w = Wire(out_port, 'not', in_port)
    elif 'buf' in type:
        assert len(in_port) == 1
        w = Wire(out_port, 'buf', in_port)
    elif 'mx2' in type:
        assert len(in_port) > 1
        w = Wire(out_port, 'mux', in_port)
    elif 'mux' in type:
        assert len(in_port) > 1
        w = Wire(out_port, 'mux', in_port)
    else:
        logging.critical('undefined gate type: {}'.format(type))
        exit()
    return w


def read_generic_verilog_wires(path):
    try:
        with open(path, "r") as f:
            design = f.read()
            line = ''.join(design)
    except EnvironmentError:
        logging.critical('{} not found'.format(path))
        exit()

    wires = {}
    # match assign
    assigns = re.findall(r'assign (.*?) = (.*?);', line)
    for a in assigns:
        wires[a[0]] = Wire(a[0], 'buf', 1)
        wires[a[0]].operands = [a[1]]

    # match gates
    # g[0]: gate type; g[1]: gate tag; g[2]: gate ports
    gates = re.findall(r'^\s*(\S*?)\s*(\S*?)\s*\(([\s\S]*?)\);', line, re.MULTILINE)
    for g in gates:
        ports = g[2].replace(' ', '').replace('\n', '').split(',')
        type = g[0].lower()
        if 'dff' in type:
            in_port = ports[2]
            q_port = ports[1]
            wires[q_port] = Wire(q_port, 'dff', 1)
            wires[q_port].operands = [in_port]
            wires[q_port].tag = g[1]
        elif 'lat' in type:
            in_port = ports[2:5]
            q_port = ports[1]
            wires[q_port] = Wire(q_port, 'lat', 1)
            wires[q_port].operands = in_port
            wires[q_port].tag = g[1]
        else:
            if 'module' not in type:
                out_port = ports[0]
                in_port = ports[1:]
                wires[out_port] = create_wire(type, in_port, out_port)
                wires[out_port].operands = in_port
                wires[out_port].tag = g[1]
    return wires


def read_dffwrst_wires(path):
    # for designs with ffs with rst port
    try:
        with open(path, "r") as f:
            design = f.read()
            line = ''.join(design)
    except EnvironmentError:
        logging.critical('{} not found'.format(path))
        exit()

    wires = {}
    # match assign
    assigns = re.findall(r'assign (.*?) = (.*?);', line)
    for a in assigns:
        wires[a[0]] = Wire(a[0], 'buf', 1)
        wires[a[0]].operands = [a[1]]

    # match gates
    # g[0]: gate type; g[1]: gate tag; g[2]: gate ports
    gates = re.findall(r'^\s*(\S*?)\s*(\S*?)\s*\(([\s\S]*?)\);', line, re.MULTILINE)
    for g in gates:
        ports = g[2].replace(' ', '').replace('\n', '').split(',')
        type = g[0].lower()
        if 'dff' in type:
            in_port = ports[4]
            q_port = ports[1]
            wires[q_port] = Wire(q_port, 'dff', 1)
            wires[q_port].operands = [in_port]
            wires[q_port].tag = g[1]
        else:
            if 'module' not in type:
                out_port = ports[0]
                in_port = ports[1:]
                wires[out_port] = create_wire(type, in_port, out_port)
                wires[out_port].operands = in_port
                wires[out_port].tag = g[1]
    return wires


def verilog2circuit(path):
    # read essential info from the verilog file and returns circuit
    def read_signals(signal_list):
        ports = {}
        for i in signal_list:
            len = 1
            if i[1]:
                # if input is a vector
                len = int(i[1][:i[1].find(':')])+1

            signals = i[2].replace('\n', '')
            signals = signals.replace(' ', '')
            signals = signals.split(',')
            for j in signals:
                ports[j] = len
        return ports

    try:
        with open(path, "r") as f:
            netlist = f.read()
    except EnvironmentError:
        logging.critical('{} not found'.format(path))
        exit()

    # circuit name
    circuit_name = re.findall(r'module (.*)\s*\S*\(', netlist)
    circuit_name = circuit_name[0].replace(' ', '')

    port_defs = re.findall(r'module [\s\S]*?\(([\s\S]*?)\);', netlist)
    port_defs = port_defs[0].replace('\n', '')
    port_defs = port_defs.replace(' ', '')
    port_defs = port_defs.split(',')

    # input signals
    input_list = re.findall(r'input (\[(.*)\]|)([\s\S]*?);', netlist)
    inputs = read_signals(input_list)

    # for i in inputs:
    #     if '] k' in i:
    #         inputs.remove(i)
    #         break

    output_list = re.findall(r'output (\[(.*)\]|)([\s\S]*?);', netlist)
    outputs = read_signals(output_list)

    # key length
    key_bits = re.findall(r'input \[(.*?):0\] keyinput', netlist)
    if key_bits:
        key_bits = int(key_bits[0]) + 1
    else:
        key_bits = 0

    input_bits = 0
    for key in inputs:
        input_bits += inputs[key]

    output_bits = 0
    for key in outputs:
        output_bits += outputs[key]

    circuit = Circuit(circuit_name)
    circuit.folder_path = path[:path.rfind("/") + 1]
    circuit.file_name = path[path.rfind("/") + 1:]
    circuit.input_wires = inputs
    circuit.output_wires = outputs
    circuit.port_defs = port_defs
    circuit.raw_netlist = netlist
    circuit.n_inputs = input_bits - key_bits
    circuit.n_keys = key_bits
    circuit.n_outputs = output_bits

    logging.warning(
        'circuit: {}, inputs: {}, outputs: {}, keyinputs: {}'.format(circuit_name, circuit.n_inputs, circuit.n_outputs,
                                                                     circuit.n_keys ))
    return circuit


def circuit2verilog(cir, cir_name):
    # write out a circuit to a verilog file
    verilog_text = 'module {}('.format(cir_name)
    verilog_text += ', '.join(cir.port_defs)
    verilog_text += ');\n'

    for w in cir.input_wires:
        if cir.input_wires[w] > 1:
            verilog_text += 'input [{}:0] {};\n'.format(cir.input_wires[w]-1, w)
        else:
            verilog_text += 'input {};\n'.format(w)

    for w in cir.output_wires:
        if cir.output_wires[w] > 1:
            verilog_text += 'output [{}:0] {};\n'.format(cir.output_wires[w]-1, w)
        else:
            verilog_text += 'output {};\n'.format(w)

    # reconstruct wire definitions
    wire_lst = []
    for w in cir.wire_objs:
        if (w not in wire_lst) and (w not in cir.input_wires) and (w not in cir.output_wires) and ('[' not in w):
            wire_lst.append(w)

    for w in wire_lst:
        verilog_text += 'wire {};\n'.format(w)

    # add gate declarations
    wires = cir.wire_objs
    i = 0
    for w in wires:
        if wires[w].tag == 0:
            wires[w].tag = 'tag{}'.format(i)
            i = i + 1
        if wires[w].type == 'buf':
            verilog_text += 'assign {} = {};\n'.format(w, wires[w].operands[0])
        elif wires[w].type == 'dff':
            opr = ', '.join(wires[w].operands)
            verilog_text += '{} {}({}, {}, {});\n'.format(wires[w].type, wires[w].tag, cir.clk, w, opr)
        elif wires[w].type == 'lat':
            opr = ', '.join(wires[w].operands)
            verilog_text += '{} {}(CK, {}, {});\n'.format(wires[w].type, wires[w].tag, w, opr)
        else:
            opr = ', '.join(wires[w].operands)
            verilog_text += '{} {}({}, {});\n'.format(wires[w].type, wires[w].tag, w, opr)

    verilog_text += 'endmodule'
    return verilog_text
