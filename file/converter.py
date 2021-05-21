import re
import argparse
import logging
from common.utils import logo
from file.verilog import verilog2circuit, read_verilog_wires


def insert_char2list(my_list, my_char):
    tmp = ""
    for i in range(len(my_list)):
        tmp += my_list[i]
        if i != len(my_list)-1:
            tmp += my_char
    return tmp


def bench2verilog(args):
    design = open(args.b, "r")
    line = ''.join(design)

    out_path = args.b.replace('.bench', '.v')
    out_verilog = open(out_path, "w")

    mod_name = out_path[out_path.rfind('/')+1:out_path.rfind('.')]

    input_match = re.findall('INPUT\((.*?)\)', line)
    output_match = re.findall('OUTPUT\((.*?)\)', line)
    gates_match = re.findall('(.*?) = (.*?)\((.*?)\)', line)

    wire_list = []
    for i in range(len(gates_match)):
        tmp = []
        tmp.append(gates_match[i][0])
        tmp += gates_match[i][2].replace(',', '').split()
        for c in tmp:
            if (c not in input_match) & (c not in output_match):
                wire_list.append(c)
    wire_list = set(wire_list)

    verilog_out = 'module ' + mod_name + '('
    verilog_out += insert_char2list(input_match, ', ') + ', ' + insert_char2list(output_match, ', ') + ');\n'
    verilog_out += 'input ' + insert_char2list(input_match, ', ') + ';\n'
    verilog_out += 'output ' + insert_char2list(output_match, ', ') + ';\n'
    verilog_out += 'wire ' + insert_char2list(list(wire_list), ', ') + ';\n'

    for i in range(len(gates_match)):
        if gates_match[i][1].lower() == 'mux':
            tmp = gates_match[i][2].split()
            verilog_out += '  ' + 'assign ' + gates_match[i][0] + ' = ' + tmp[0][0:-1] + ' ? ' + tmp[1][0:-1] + ' : ' + tmp[2] + ';\n'
        elif gates_match[i][1].lower() == 'buff':
            verilog_out += '  ' + 'assign ' + gates_match[i][0] + ' = ' + gates_match[i][2] + ';\n'
        else:
            verilog_out += '  ' + gates_match[i][1].lower() + ' g' + str(i) + '(' + gates_match[i][0] + ', ' + gates_match[i][2] + ');\n'

    verilog_out += 'endmodule'
    out_verilog.write(verilog_out)


def sanitize_name(text):
    text = text.replace('\\', '')
    text = text.replace(']', '')
    text = text.replace('.', '_')
    if 'keyinput' in text:
        text = text.replace('[', '')
    else:
        text = text.replace('[', '_')
    assert text != ''
    return text


def verilog2bench(args):
    tmp_circuit = verilog2circuit(args.b)
    wires = read_verilog_wires(args.b)

    inputs = []
    bench_file = ""
    for p in tmp_circuit.input_wires:
        if tmp_circuit.input_wires[p] > 1:
            for i in range(tmp_circuit.input_wires[p]):
                inputs.append(sanitize_name('{}[{}]'.format(p, i)))
        else:
            inputs.append(sanitize_name('{}'.format(p)))
    for p in inputs:
        bench_file += 'INPUT({})\n'.format(p)

    outputs = []
    for p in tmp_circuit.output_wires:
        if tmp_circuit.output_wires[p] > 1:
            for i in range(tmp_circuit.output_wires[p]):
                outputs.append(sanitize_name('{}[{}]'.format(p, i)))
        else:
            outputs.append(sanitize_name('{}'.format(p)))
    for p in outputs:
        bench_file += 'OUTPUT({})\n'.format(p)

    for p in wires:
        operands = ''
        if len(wires[p].operands) > 1:
            for o in wires[p].operands:
                operands += sanitize_name(o) + ', '
            operands = operands[:-2]
        else:
            operands = sanitize_name(wires[p].operands[0])
            if "1'b0" in operands:
                operands = 'zero'
            elif "1'b1" in operands:
                operands = 'one'
        output = sanitize_name(p)
        bench_file += '{} = {}( {} )\n'.format(output, wires[p].type, operands)

    # add zero and one for 1'b0 and 1'b1
    bench_file += 'not_tmp = not( {} )\n'.format(inputs[0])
    bench_file += 'one = or( not_tmp,{} )\n'.format(inputs[0])
    bench_file += 'zero = and( not_tmp,{} )\n'.format(inputs[0])

    # check ports
    missing_vars = []
    for p in inputs:
        if not re.search(r'= .*\(.*{}.*\)'.format(p), bench_file):
            missing_vars.append(p)
    logging.warning('these inputs have not been used: {}'.format(missing_vars))

    missing_vars = []
    for p in outputs:
        if not re.search(r'{} = '.format(p), bench_file):
            missing_vars.append(p)
    logging.warning('these outputs are not driven: {}'.format(missing_vars))

    new_path = args.b.replace('.v', '.bench')
    design = open(new_path, "w")
    design.write(bench_file)
    exit()


def keyinput2vector(args):
    # converts keyinput0 to keyinput[0]
    design = open(args.b, "r")
    line = ''.join(design)

    key_match = re.findall(r'keyinput(\d*)[,)]', line)

    # key_match.sort()
    # print(key_match)
    # exit()
    for k in key_match:
        tmp = 'keyinput[' + k + ']'
        # line = line.replace(k, tmp)
        line = re.sub('keyinput' + k + ',', tmp + ',', line)
        line = re.sub('keyinput' + k + ';', tmp + ';', line)
        line = re.sub('keyinput' + k + '\)', tmp + ')', line)
    design.close()

    design = open(args.b, "w")
    design.write(line)
    exit()


if __name__ == "__main__":
    logo()
    parser = argparse.ArgumentParser(description='Convert Bench and Verilog to each other')
    parser.add_argument("-p", action="store", default=0, type=int, help="print wire details")
    parser.add_argument("-m", action="store", required=True, type=str, help="operation")
    parser.add_argument("-b", action="store", required=True, type=str, help="file path")
    args = parser.parse_args()

    if args.p == 0:
        logging.getLogger().setLevel(level=logging.WARNING)
    elif args.p == 1:
        logging.getLogger().setLevel(level=logging.INFO)
    elif args.p == 2:
        logging.getLogger().setLevel(level=logging.DEBUG)

    if args.m == 'key':
        keyinput2vector(args)
    elif args.m == 'v2b':
        verilog2bench(args)
    elif args.m == 'b2v':
        bench2verilog(args)
    else:
        logging.critical('invalid operation')

