import argparse
import logging
from random import randint
import re
from common.circuit import Wire
from common.utils import logo
from file.verilog import read_verilog_wires, verilog2circuit, circuit2verilog


def converter(args):
    text = open(args.b).read()

    inputs = re.search(r'input (.*?);', text, re.DOTALL).group(1)
    outputs = re.search(r'output (.*?);', text, re.DOTALL).group(1)

    module = re.search(r'module .*?\((.*?)\);', text, re.DOTALL).group(1)

    text = re.sub(module, inputs + ',' + outputs, text)
    text = re.sub(r'VDD,', '', text)
    text = re.sub(r'FD1 ', 'dff ', text)
    text = re.sub(r'IV ', 'not', text)
    text = re.sub(r'AN. ', 'and ', text)
    text = re.sub(r'OR. ', 'or ', text)
    text = re.sub(r'ND. ', 'nand ', text)
    text = re.sub(r'NR. ', 'nor ', text)
    return text


def rnd_obf(args):
    circuit = verilog2circuit(args.b)
    circuit.wire_objs = read_verilog_wires(args.b, 'generic')
    wires = circuit.wire_objs

    i = 0
    obf_gates = {}
    rep_instances = []
    key_list = ""
    while i < args.k:
        rnd_w = circuit.get_random_wire()
        if (rnd_w not in rep_instances) and (wires[rnd_w].type != Wire.DFF) and \
                (wires[rnd_w] != Wire.INPUT) and (rnd_w not in circuit.output_wires):
            logging.warning(rnd_w + " is selected for obfuscation")
            key_val = randint(0, 1)
            if key_val == 0:
                gate_type = "xor"
                key_list += '0'
            else:
                gate_type = "xnor"
                key_list += '1'

            rep_instances.append(rnd_w)
            w_tmp = rnd_w + '_obf'
            obf_gates[rnd_w] = Wire(rnd_w, gate_type, ['keyinput[{}]'.format(i), w_tmp])
            obf_gates[w_tmp] = Wire(w_tmp, wires[rnd_w].type, wires[rnd_w].operands)
            obf_gates[w_tmp].tag = wires[rnd_w].tag
            i = i + 1

    # old wire names should be replaced in their instances (e.g., G13 to G13_obf)
    for w in rep_instances:
        del wires[w]
    for w in obf_gates:
        wires[w] = obf_gates[w]

    circuit.input_wires['keyinput'] = i
    circuit.port_defs.append('keyinput')

    bench_address = circuit.folder_path
    output_folder = bench_address[0: bench_address.rfind("/", 0, bench_address.rfind("/"))] + "/{}/".format(args.m)
    obf_file_name = circuit.name + "_" + str(args.k) + ".v"
    verilog_text = circuit2verilog(circuit, circuit.name + "_obf")

    key_list = key_list[::-1]
    key_list = "// key=" + key_list
    with open(output_folder + obf_file_name, 'w') as f:
        f.write(key_list.rstrip('\r\n') + '\n\n')
        f.write(verilog_text)
    return


def lbll_obf(args):
    # latch-based obfuscation
    circuit = verilog2circuit(args.b)
    circuit.wire_objs = read_verilog_wires(args.b, 'generic')
    wires = circuit.wire_objs

    i = 0
    obf_gates = {}
    rep_instances = []
    key_list = ""
    while i <= args.k:
        r = randint(0, 2)
        if r == 0:
            for w in wires:
                if (w not in rep_instances) and (wires[w].type == Wire.DFF):
                    logging.warning(w + " is selected as modified FF")
                    rep_instances.append(w)
                    w_tmp = w + '_obf'
                    obf_gates[w_tmp] = Wire(w_tmp, 'lat', ['keyinput[{}]'.format(i), 'keyinput[{}]'.format(i+1), wires[w].operands[0]])
                    obf_gates[w] = Wire(w, 'lat', ['keyinput[{}]'.format(i+2), 'keyinput[{}]'.format(i+3), w_tmp])
                    key_list += '1001'
                    i = i + 4
                    break
        elif r == 1:
            for w in wires:
                if (w not in rep_instances) and (wires[w].type != Wire.DFF):
                    logging.warning(w + " is selected as path delay decoy")
                    rep_instances.append(w)
                    w_tmp = w + '_obf'
                    obf_gates[w_tmp] = wires[w]
                    obf_gates[w_tmp].name = w_tmp
                    obf_gates[w] = Wire(w, 'lat', ['keyinput[{}]'.format(i), 'keyinput[{}]'.format(i+1), w_tmp])
                    key_list += '11'
                    i = i + 2
                    break
        else:
            # continue
            for w1 in wires:
                if (w1 not in rep_instances) and (wires[w1].type != Wire.DFF):
                    for w2 in wires:
                        if (w2 not in rep_instances) and (wires[w2].type != Wire.DFF) and (w2 != w1):
                            logging.warning(w1 + " is selected as logic decoy")
                            rep_instances.append(w1)
                            w_tmp = w1 + '_obf'
                            obf_gates[w_tmp] = wires[w1]
                            obf_gates[w_tmp].name = w_tmp
                            lat_tmp = 'w_lat{}'.format(i)
                            obf_gates[lat_tmp] = Wire(lat_tmp, 'lat', ['keyinput[{}]'.format(i), 'keyinput[{}]'.format(i + 1), w2])
                            obf_gates[w1] = Wire(w1, 'or', [w_tmp, lat_tmp])
                            key_list += '00'
                            i = i + 2
                            break
                    break

    for w in rep_instances:
        del wires[w]
    for w in obf_gates:
        wires[w] = obf_gates[w]

    circuit.input_wires['keyinput'] = i
    circuit.port_defs.append('keyinput')

    bench_address = circuit.folder_path
    output_folder = bench_address[0: bench_address.rfind("/", 0, bench_address.rfind("/"))] + "/{}/".format(args.m)
    obf_file_name = circuit.name + "_" + str(args.k) + ".v"
    verilog_text = circuit2verilog(circuit, circuit.name + "_obf")

    key_list = key_list[::-1]
    key_list = "// key=" + key_list
    with open(output_folder + obf_file_name, 'w') as f:
        f.write(key_list.rstrip('\r\n') + '\n\n')
        f.write(verilog_text)
    return


if __name__ == "__main__":
    logo()
    parser = argparse.ArgumentParser(description='Random obfuscation')
    parser.add_argument("-p", action="store", default=0, type=int, help="print wire details")
    parser.add_argument("-b", action="store", required=True, type=str, help="original benchmark path")
    parser.add_argument("-m", action="store", required=False, type=str, help="obfuscation method")
    parser.add_argument("-k", action="store", required=True, type=int, help="number of key bits")
    parser.add_argument("-c", action="store_true", default=False, required=False, help="correct gate types before obfuscation")
    args = parser.parse_args()

    if args.p == 0:
        logging.getLogger().setLevel(level=logging.WARNING)
    elif args.p == 1:
        logging.getLogger().setLevel(level=logging.INFO)
    elif args.p == 2:
        logging.getLogger().setLevel(level=logging.DEBUG)

    logging.warning("reading verilog inputs")

    if args.c:
        text = converter(args)
        # write the file in the same place with _c in name
        path = args.b
        circuit_name = path[path.rfind("/") + 1:path.rfind(".")]
        circuit_path = path[:path.rfind("/") + 1]
        path = circuit_path + circuit_name + '_c.v'
        file = open(path, 'w')
        file.write(text)
        file.close()
        logging.warning('converted file is written in: ' + path)
        ast = parse_verilog(path)

    if args.m == 'rnd':
        rnd_obf(args)
    elif args.m == 'lbll':
        lbll_obf(args)
    else:
        logging.critical('obfuscation {} is not implemented!'.format(args.m))
