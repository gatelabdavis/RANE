import argparse
import logging
from random import randint
import re

from sat.ast_wrapper import ASTWrapper, parse_verilog, write_verilog
from common.circuit import Wire
from common.utils import logo


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


def rnd_obf(args, ast):
    ast_mgr = ASTWrapper(ast, args.b)
    circuit = ast_mgr.get_circuit(req_fanout=True, correct_order=False)
    wires = circuit.wire_objs

    i = 0
    obf_gates = []
    new_wires = []
    rep_wire_names = []
    rep_instances = []
    key_list = ""
    while i < args.k:
        rnd_w = wires[randint(0, len(wires) - 1)]
        if (rnd_w.type != Wire.INPUT) and (rnd_w.fanout != 0) and (rnd_w.instance not in rep_instances):
            key_val = randint(0, 1)
            key_list += str(key_val)
            if key_val == 0:
                gate_type = "xor"
            else:
                gate_type = "xnor"

            logging.warning(rnd_w.name + " is selected for obfuscation")

            new_w_name = rnd_w.name + "_obf"
            new_wires.append(new_w_name)
            rep_wire_names.append({rnd_w.name: new_w_name})
            rep_instances.append(rnd_w.instance)
            key_ports = Wire("keyinput" + str(i), "inp", [], 0)
            obf_gates.append(Wire(rnd_w.name, gate_type, [rnd_w, key_ports], 0))
            rnd_w.name = new_w_name
            i = i+1

    # old wire names should be replaced in their instances (for example G13 to G13_obf)
    ast_mgr.replace_wire_names(rep_wire_names, rep_instances)
    for i in range(args.k):
        ast_mgr.add_ports('keyinput{}'.format(i), 0, 'input')
    ast_mgr.add_wires(new_wires)
    ast_mgr.add_instances(obf_gates)
    ast_mgr.change_module_name(circuit.name + "_obf")

    bench_address = circuit.path
    bench_folder = bench_address[0: bench_address.rfind("/", 0, bench_address.rfind("/"))] + "/"
    output_folder = bench_folder + args.m + "/"
    obf_file_name = circuit.name + "_" + str(args.k) + ".v"
    write_verilog(ast_mgr.ast, obf_file_name, output_folder)

    key_list = key_list[::-1]
    key_list = "// key=" + key_list
    with open(output_folder + obf_file_name, 'r+') as f:
        content = f.read()
        f.seek(0, 0)
        f.write(key_list.rstrip('\r\n') + '\n' + content)
    return


if __name__ == "__main__":
    logo()
    parser = argparse.ArgumentParser(description='Random obfuscation for sat')
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

    args.m = "rnd"
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
    else:
        ast = parse_verilog(args.b)

    rnd_obf(args, ast)
