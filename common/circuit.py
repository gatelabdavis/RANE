import logging
import random


class Wire:
    INPUT = "inp"
    OUTPUT = "out"
    DFF = "dff"
    LAT = 'lat'

    def __init__(self, cell_name, cell_type, operands):
        self.name = cell_name
        self.type = cell_type
        self.operands = operands
        self.index = 0
        self.instance = 0

        self.mark = 0
        self.logic_level = -1
        self.prob0 = 0.5  # initial value should be 0.5 for inputs
        self.prob1 = 0.5  # initial value should be 0.5 for inputs
        self.absprob = 0
        self.fanout = 0
        self.tag = 0
        self.delay = 0
        self.slack = 0
        self.fanouts = []
        self.lit = 0
        self.formula = None


class Circuit:
    def __init__(self, name):
        self.name = name

        self.raw_netlist = None
        self.folder_path = None
        self.file_name = None
        self.input_wires = None
        self.output_wires = None
        self.port_defs = None
        self.info = None

        self.n_inputs = 0
        self.n_keys = 0
        self.n_outputs = 0

        self.cone_index = None
        self.clk_period = None
        self.max_level = None
        self.b2b = True
        self.mainout = False
        self.wire_objs = None
        self.state_wires = None
        self.sorted_wires = None
        self.next_state_wires = None
        self.key_wires = None
        self.key_value = ""
        self.clk = 'CK'

    def get_random_wire(self):
        return list(self.wire_objs.keys())[random.randint(0, len(self.wire_objs) - 1)]

    def get_random_input(self):
        return list(self.input_wires.keys())[random.randint(0, len(self.input_wires) - 1)]

    def fan_outs(self, wire):
        fan_out = []
        for w in self.wire_objs:
            if wire in self.wire_objs[w].operands:
                fan_out.append(w)
        return fan_out

    def create_ce_circuit(self):
        self.state_wires = []
        self.next_state_wires = []
        wires = self.wire_objs
        for w in wires:
            if wires[w].type == Wire.DFF:
                self.state_wires.append(w)
                self.next_state_wires.append(wires[w].operands[0])
        # sort wires so the gate outputs are before gate inputs
        self.sorted_wires = []
        while len(wires) != len(self.sorted_wires):
            for w in wires:
                if wires[w].logic_level != -1:
                    continue
                elif wires[w].type == Wire.DFF:
                    wires[w].logic_level = 0
                    self.sorted_wires.append(w)
                else:
                    available = True
                    level = 0
                    for o in wires[w].operands:
                        if (o not in self.sorted_wires) and (o not in self.input_wires) and (o not in self.key_wires):
                            available = False
                            break
                        else:
                            if (o in self.input_wires) or (o in self.key_wires):
                                level = max(level, 0)
                            else:
                                level = max(level, wires[o].logic_level)
                    if available:
                        wires[w].logic_level = level + 1
                        self.sorted_wires.append(w)

    def max_dep(self, wire):
        # calculates depth of a wire object (logic level)
        if self.wire_objs[wire].type == "inp":
            return 0
        elif self.wire_objs[wire].logic_level != 0:
            return wire.logic_level
        else:
            max = 0
            for i in range(len(self.wire_objs[wire].operands)):
                curr = self.max_dep(self.wire_objs[wire].operands[i])
                if curr > max:
                    max = curr
        return max+1

    def get_fanin_cone(self, wire):
        visited, queue = [], [wire]
        while queue:
            vertex = queue.pop(0)
            if vertex not in visited:
                visited.append(vertex)
                for v in self.wire_objs[vertex].operands:
                    # if (v.type != Wire.DFF) and (v.type != Wire.INPUT):
                    queue.append(v)
        return visited


def sort_circuits(ora_cir, obf_cir):
    # inputs and output wires of each circuit should be equal and in the same order
    outputs1 = ora_cir.output_wires
    outputs2 = obf_cir.output_wires
    inputs1 = ora_cir.input_wires
    inputs2 = obf_cir.input_wires

    if (len(outputs1) != len(outputs2)) or (len(inputs1) != len(inputs2)):
        logging.critical('number of inputs or outputs are not the same')
        exit()

    if outputs1 != outputs2:
        logging.warning('output order/names are not correct')
        exit()

    if inputs1 != inputs2:
        logging.warning('input order/names are not correct')
        exit()
    return
