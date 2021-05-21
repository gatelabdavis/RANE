from pysmt.shortcuts import *
import logging
from common.circuit import Wire


def get_formulas(wire_list, bool_list, tag):
    if len(wire_list) != len(bool_list):
        logging.critical('something is wrong!')
        exit()

    formula_list = []
    for i in range(len(wire_list)):
        f = Symbol(wire_list[i] + tag)
        if bool_list[i] is TRUE():
            formula_list.append(f)
        else:
            formula_list.append(Not(f))
    return formula_list


class FormulaGenerator:
    def __init__(self, orcl_cir, obf_cir):
        self.orcl_cir = orcl_cir
        self.obf_cir = obf_cir
        self.key_subs = [{}, {}]
        self.dip_ckt0 = []
        self.dip_ckt1 = []
        self.dip_ckt0_frame = []
        self.dip_ckt1_frame = []
        self.oracle_ckt_frame = []

        # generate solver formulas
        gen_wire_formulas(self.orcl_cir)
        gen_wire_formulas(self.obf_cir)

        # create symbols for primary outputs and next state wires
        orcl_wires = self.orcl_cir.wire_objs
        obf_wires = self.obf_cir.wire_objs

        for w in self.orcl_cir.output_wires:
            orcl_wires[w].formula = Iff(Symbol(w), orcl_wires[w].formula)

        for w in set(orcl_cir.next_state_wires):
            if w in orcl_cir.input_wires:
                # TODO: test for the next states that are connecting to the inputs
                print(w)
                orcl_wires[w] = Wire(w, Wire.INPUT, [])
                orcl_wires[w].formula = Symbol(w)
            else:
                orcl_wires[w].formula = Iff(Symbol(w), orcl_wires[w].formula)

        for w in self.obf_cir.output_wires:
            obf_wires[w].formula = Iff(Symbol(w), obf_wires[w].formula)

        for w in set(obf_cir.next_state_wires):
            if w not in obf_cir.output_wires:
                if w in obf_cir.input_wires:
                    obf_wires[w] = Wire(w, Wire.INPUT, [])
                    obf_wires[w].formula = Symbol(w)
                else:
                    obf_wires[w].formula = Iff(Symbol(w), obf_wires[w].formula)

        # create key substitution dictionary
        for w in self.obf_cir.key_wires:
            self.key_subs[0][Symbol(w)] = Symbol(w + '_0')
            self.key_subs[1][Symbol(w)] = Symbol(w + '_1')

        # generate formulas for two copies of obfuscated circuit
        for w in self.obf_cir.output_wires:
            self.dip_ckt0.append(substitute(obf_wires[w].formula, self.key_subs[0]))
            self.dip_ckt1.append(substitute(obf_wires[w].formula, self.key_subs[1]))

        # converted to set to ignore duplicate next_state_wires
        for w in self.obf_cir.next_state_wires:
            self.dip_ckt0.append(substitute(obf_wires[w].formula, self.key_subs[0]))
            self.dip_ckt1.append(substitute(obf_wires[w].formula, self.key_subs[1]))

        # key inequality circuit
        key_xors = []
        for w in self.obf_cir.key_wires:
            key_xors.append(Xor(Symbol('{}_0'.format(w)), Symbol('{}_1'.format(w))))
        self.key_inequality_ckt = Or(key_xors)

    def ce_assumption(self, frame):
        c0 = []
        # set states of the two copies of the circuit as equal
        for i in range(len(self.obf_cir.next_state_wires)):
            c0.append(Iff(Symbol(self.obf_cir.next_state_wires[i] + '_0@0'),
                          Symbol(self.obf_cir.next_state_wires[i] + '_1@0')))

        output_xors = []
        for w in self.obf_cir.output_wires:
            output_xors.append(Xor(Symbol(w + '_0@{}'.format(frame)), Symbol(w + '_1@{}'.format(frame))))
        for w in self.obf_cir.next_state_wires:
            output_xors.append(Xor(Symbol(w + '_0@{}'.format(frame)), Symbol(w + '_1@{}'.format(frame))))
        return And([Or(output_xors)] + c0)

    def dip_gen_assumption(self, frame, initial=None, hd=1):
        c0 = []
        c1 = []

        # set initial states
        for i in range(len(self.obf_cir.next_state_wires)):
            if initial:
                if initial[i] is FALSE():
                    c0.append(Not(Symbol(self.obf_cir.next_state_wires[i] + '_0@0')))
                    c1.append(Not(Symbol(self.obf_cir.next_state_wires[i] + '_1@0')))
                elif initial[i] is TRUE():
                    c0.append(Symbol(self.obf_cir.next_state_wires[i] + '_0@0'))
                    c1.append(Symbol(self.obf_cir.next_state_wires[i] + '_1@0'))
                else:
                    # for ce check
                    print("should use ce_assumption")
                    exit()
            else:
                c0.append(Not(Symbol(self.obf_cir.next_state_wires[i] + '_0@0')))
                c1.append(Not(Symbol(self.obf_cir.next_state_wires[i] + '_1@0')))

        output_xors = []
        if frame > 0:
            for w in self.obf_cir.output_wires:
                output_xors.append(Xor(Symbol(w + '_0@{}'.format(frame)), Symbol(w + '_1@{}'.format(frame))))
        if hd > 1:
            # TODO: hd>1 is not tested with recent changes
            p = Ite(output_xors[0], BVOne(10), BVZero(10))

            for i in range(1, len(output_xors)):
                t = Ite(output_xors[i], BVOne(10), BVZero(10))
                p = BVAdd(t, p)
            return simplify(BVUGT(p, BV(hd, 10)))
        else:
            if output_xors:
                return And([Or(output_xors)] + c0 + c1)
            else:
                return And(c0 + c1)

    def subs_list(self, depth, copy):
        subs = {}
        depth = str(depth)
        c = '_{}@'.format(copy)
        for w in self.obf_cir.input_wires:
            subs[Symbol(w)] = Symbol(w + '@' + depth)
        for w in self.obf_cir.output_wires:
            subs[Symbol(w)] = Symbol(w + c + depth)
        for w in self.obf_cir.state_wires:
            subs[Symbol(w)] = Symbol(w + c + depth)
        for w in self.obf_cir.next_state_wires:
            subs[Symbol(w)] = Symbol(w + c + depth)
        return subs

    def obf_ckt_at_frame(self, frame):
        # check if it was produced before
        if len(self.dip_ckt0_frame) <= frame:
            c0 = []
            c1 = []

            subs0 = self.subs_list(frame, '0')
            subs1 = self.subs_list(frame, '1')

            # set initial state for the first copy
            if frame == 0:
                for i in range(len(self.obf_cir.next_state_wires)):
                    # set initial states
                    c0.append(Not(Symbol(self.obf_cir.next_state_wires[i] + '_0@0')))
                    c1.append(Not(Symbol(self.obf_cir.next_state_wires[i] + '_1@0')))
            else:
                for i in range(len(self.dip_ckt0)):
                    c0.append(substitute(self.dip_ckt0[i], subs0))
                    c1.append(substitute(self.dip_ckt1[i], subs1))

                for i in range(len(self.obf_cir.state_wires)):
                    # state of each frame should be equal with the next state of previous frame
                    c0.append(Iff(Symbol(self.obf_cir.state_wires[i] + '_0@' + str(frame)),
                                  Symbol(self.obf_cir.next_state_wires[i] + '_0@' + str(frame-1))))
                    c1.append(Iff(Symbol(self.obf_cir.state_wires[i] + '_1@' + str(frame)),
                                  Symbol(self.obf_cir.next_state_wires[i] + '_1@' + str(frame-1))))

            self.dip_ckt0_frame.append(c0)
            self.dip_ckt1_frame.append(c1)
        return self.dip_ckt0_frame[frame], self.dip_ckt1_frame[frame]

    def oracle_ckt_at_frame(self, frame):
        # check if it was produced before
        if len(self.oracle_ckt_frame) <= frame:
            subs = {}
            postfix = '@{}'.format(frame)
            for w in self.orcl_cir.input_wires:
                subs[Symbol(w)] = Symbol(w + postfix)
            for w in self.orcl_cir.output_wires:
                subs[Symbol(w)] = Symbol(w + postfix)
            for w in self.orcl_cir.state_wires:
                subs[Symbol(w)] = Symbol(w + postfix)
            for w in self.orcl_cir.next_state_wires:
                subs[Symbol(w)] = Symbol(w + postfix)

            c = []
            if frame == 0:
                for w in self.orcl_cir.next_state_wires:
                    # initial states are assumed to be zero
                    c.append(Not(Symbol(w + '@0')))
            else:
                for w in self.orcl_cir.output_wires:
                    c.append(substitute(self.orcl_cir.wire_objs[w].formula, subs))
                for w in self.orcl_cir.next_state_wires:
                    c.append(substitute(self.orcl_cir.wire_objs[w].formula, subs))
                for i in range(len(self.orcl_cir.state_wires)):
                    # state of each frame should be equal with the next state of previous frame
                    c.append(Iff(Symbol(self.orcl_cir.state_wires[i] + '@' + str(frame)),
                                 Symbol(self.orcl_cir.next_state_wires[i] + '@' + str(frame-1))))
            self.oracle_ckt_frame.append(c)
        return self.oracle_ckt_frame[frame]


def gen_wire_formulas(circuit):
    wires = circuit.wire_objs
    for w in circuit.sorted_wires:
        wire = wires[w]
        lst = []
        r = None
        for op in wire.operands:
            if op in (circuit.input_wires + circuit.key_wires):
                lst.append(Symbol(op))
            else:
                lst.append(wires[op].formula)
        if wire.type == Wire.DFF:
            r = Symbol(wire.name)
        elif wire.type == 'not':
            r = Not(lst[0])
        elif wire.type == 'buf':
            r = lst[0]
        elif wire.type == 'and':
            r = And(lst)
        elif wire.type == 'nand':
            r = And(lst)
            r = Not(r)
        elif wire.type == 'or':
            r = Or(lst)
        elif wire.type == 'nor':
            r = Or(lst)
            r = Not(r)
        elif wire.type == 'xor':
            assert (len(lst) == 2)
            r = Xor(lst[0], lst[1])
            # r = And(Or(lst[0], lst[1]), Not(And(lst[0], lst[1])))
        elif wire.type == 'xnor':
            assert (len(lst) == 2)
            r = Xor(lst[0], lst[1])
            # r = And(Or(lst[0], lst[1]), Not(And(lst[0], lst[1])))
            r = Not(r)
        else:
            logging.critical('unspecified gate type: {}'.format(wire.type))
            exit()
        wire.formula = r
