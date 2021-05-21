import re
from common.circuit import Wire, Circuit
import logging


def bench2circuit(path):
    try:
        with open(path, "r") as f:
            bench_file = f.read()
    except EnvironmentError:
        logging.critical('{} not found'.format(path))
        exit()

    inputs = re.findall(r'INPUT\((.*?)\)', bench_file)
    outputs = re.findall(r'OUTPUT\((.*?)\)', bench_file)
    gates_match = re.findall(r'(.*?) = (.*?)\((.*?)\)', bench_file)

    wires = {}
    for g in gates_match:
        in_port = g[2].replace(' ', '').replace('\n', '').split(',')
        out_port = g[0]
        gate_type = g[1].lower()

        if 'dff' in gate_type:
            assert len(in_port) == 1
            wires[out_port] = Wire(out_port, 'dff', in_port)
        elif 'nand' in gate_type:
            assert len(in_port) > 1
            wires[out_port] = Wire(out_port, 'nand', in_port)
        elif 'and' in gate_type:
            assert len(in_port) > 1
            wires[out_port] = Wire(out_port, 'and', in_port)
        elif 'xnor' in gate_type:
            assert len(in_port) > 1
            wires[out_port] = Wire(out_port, 'xnor', in_port)
        elif 'xor' in gate_type:
            assert len(in_port) > 1
            wires[out_port] = Wire(out_port, 'xor', in_port)
        elif 'nor' in gate_type:
            assert len(in_port) > 1
            wires[out_port] = Wire(out_port, 'nor', in_port)
        elif 'or' in gate_type:
            assert len(in_port) > 1
            wires[out_port] = Wire(out_port, 'or', in_port)
        elif 'not' in gate_type:
            assert len(in_port) == 1
            wires[out_port] = Wire(out_port, 'not', in_port)
        elif 'buf' in gate_type:
            assert len(in_port) == 1
            wires[out_port] = Wire(out_port, 'buf', in_port)
        elif 'mux' in gate_type:
            assert len(in_port) == 3
            wires[out_port] = Wire(out_port, 'mux', in_port)
        else:
            logging.critical('undefined gate type: {}'.format(gate_type))
            exit()
        wires[out_port].operands = in_port

    for w in wires:
        for o in wires[w].operands:
            if (o in wires) or (o in inputs):
                continue
            else:
                logging.critical('wire {} is used but is not connected to anywhere'.format(o))
                exit()

    keys = []
    for i in inputs:
        if 'keyinput' in i:
            keys.append(i)

    for k in keys:
        inputs.remove(k)

    circuit = Circuit(path[path.rfind("/")+1:path.rfind(".")])
    circuit.folder_path = path[:path.rfind("/")+1]
    circuit.file_name = path[path.rfind("/")+1:]
    circuit.input_wires = inputs
    circuit.output_wires = outputs
    circuit.wire_objs = wires
    circuit.key_wires = keys

    logging.warning(
        'circuit: {}, inputs: {}, outputs: {}, keyinputs: {}'.format(circuit.name, len(circuit.input_wires), len(circuit.output_wires),
                                                                     len(keys)))
    return circuit