import argparse
import logging
from pysmt.shortcuts import Solver, And, Iff, TRUE, FALSE, Not, Symbol, Xor, Or
from common.circuit import read_bench, Wire
from sat.ast_wrapper import ASTWrapper, parse_verilog
from common.utils import logo, resource_usage


class FormulaGenerator:
    def __init__(self, oracle_cir, obf_cir):
        self.oracle_cir = oracle_cir
        self.obf_cir = obf_cir

        # generate solver formulas
        for w in self.oracle_cir.wire_objs:
            lst = []
            for op in w.operands:
                lst.append(Symbol(op.name))
            r = self.get_wire_formulas(w, lst)
            w.formula = Iff(Symbol(w.name), r)

        # generate formulas for two copies of obfuscated circuit
        ckt1 = self.gen_dip_chk('dc1', '_0', None)
        ckt2 = self.gen_dip_chk('dc2', '_1', None)
        output_xors = []
        for w in self.obf_cir.output_wires:
            output_xors.append(Xor(Symbol(w.name + '@dc1'), Symbol(w.name + '@dc2')))
        self.dip_gen_ckt = And(Or(output_xors), ckt1, ckt2)

        # key inequality circuit
        key_symbols1 = []
        key_symbols2 = []
        for w in self.obf_cir.wire_objs:
            if 'keyinput' in w.name:
                key_symbols1.append(Symbol(w.name + '_0'))
                key_symbols2.append(Symbol(w.name + '_1'))
        output_xors = []
        for i in range(self.obf_cir.k_inputs):
            output_xors.append(Xor(key_symbols1[i], key_symbols2[i]))
        self.key_inequality_ckt = Or(output_xors)

    def gen_dip_chk(self, iteration, key_postfix, dip_list):
        dip_chk = []
        for w in self.obf_cir.wire_objs:
            r = None
            if w.type == Wire.INPUT:
                if 'keyinput' in w.name:
                    continue
                elif dip_list:
                    # for dip checkers
                    for i in range(len(self.oracle_cir.input_wires)):
                        if w.name == self.oracle_cir.input_wires[i].name:
                            r = dip_list[i]
                            break
                else:
                    # for dip generator
                    r = Symbol(w.name)
            else:
                lst = []
                for op in w.operands:
                    if 'keyinput' in op.name and 'inv_keyinput' not in op.name:
                        lst.append(Symbol(op.name + key_postfix))
                    else:
                        lst.append(Symbol(op.name + '@{}'.format(iteration)))
                r = self.get_wire_formulas(w, lst)
            dip_chk.append(Iff(Symbol(w.name + '@{}'.format(iteration)), r))
        return And(dip_chk)

    @staticmethod
    def get_wire_formulas(w, lst):
        r = None
        if w.type == Wire.INPUT:
            r = Symbol(w.name)
        elif w.type == 'not':
            r = Not(lst[0])
        elif w.type == 'buf':
            r = lst[0]
        elif w.type == 'buff':
            r = lst[0]
        elif w.type == 'and':
            r = And(lst)
        elif w.type == 'nand':
            r = And(lst)
            r = Not(r)
        elif w.type == 'or':
            r = Or(lst)
        elif w.type == 'nor':
            r = Or(lst)
            r = Not(r)
        elif w.type == 'xor':
            assert (len(lst) == 2)
            r = Xor(lst[0], lst[1])
        elif w.type == 'xnor':
            assert (len(lst) == 2)
            r = Xor(lst[0], lst[1])
            r = Not(r)
        elif w.type == 'mux':
            assert (len(lst) == 3)
            r = Or(And(Not(lst[0]), lst[1]), And(lst[0], lst[2]))
        else:
            logging.critical('unspecified gate type')
            exit()
        return r


class BeSAT:
    def __init__(self, args):
        self.args = args
        self.oracle_ast = None
        self.obf_ast = None
        self.oracle_cir = None
        self.obf_cir = None

    def perform(self):
        if '.bench' in args.b:
            logging.warning("reading bench inputs")
            self.obf_cir = read_bench(args.o, correct_order=False)
            self.oracle_cir = read_bench(args.b)
        else:
            logging.warning("preprocessing verilog inputs")
            self.oracle_ast = ASTWrapper(parse_verilog(self.args.b), self.args.b)
            self.obf_ast = ASTWrapper(parse_verilog(self.args.o), self.args.o)

        self.comb_attack()

    def query_oracle(self, dip_formula):
        # query oracle
        dip_out = []
        if not self.solver_oracle.solve(dip_formula):
            logging.critical('something is wrong with oracle circuit')
            exit()
        for l in self.oracle_cir.output_wires:
            if self.solver_oracle.get_py_value(Symbol(l.name)):
                dip_out.append(TRUE())
            else:
                dip_out.append(FALSE())
        return dip_out

    def comb_attack(self):
        # dis generator
        solver_name = 'yices'
        solver_obf = Solver(name=solver_name)
        solver_key = Solver(name=solver_name)
        self.solver_oracle = Solver(name=solver_name)
        attack_formulas = FormulaGenerator(self.oracle_cir, self.obf_cir)

        f = attack_formulas.dip_gen_ckt
        # f = simplify(f)
        solver_obf.add_assertion(f)

        f = attack_formulas.key_inequality_ckt
        # f = simplify(f)
        solver_obf.add_assertion(f)

        for l in self.oracle_cir.wire_objs:
            self.solver_oracle.add_assertion(l.formula)

        dip_list = []
        stateful_keys = []

        iteration = 0
        while 1:
            # query dip generator
            if solver_obf.solve():
                dip_formula = []
                dip_boolean = []
                for l in self.oracle_cir.input_wires:
                    s = Symbol(l.name)
                    if solver_obf.get_py_value(s):
                        dip_formula.append(s)
                        dip_boolean.append(TRUE())
                    else:
                        dip_formula.append(Not(s))
                        dip_boolean.append(FALSE())
                logging.info(dip_formula)

                # query oracle
                dip_out = self.query_oracle(dip_formula)
                logging.info(dip_out)

                # check for stateful condition
                if dip_formula in dip_list:
                    # ban stateful key
                    logging.info("found a repeated dip!")

                    # check outputs for both keys
                    key = None
                    for l in self.obf_cir.output_wires:
                        s1 = Symbol(l.name + '@dc1')
                        s2 = Symbol(l.name + '@dc2')
                        if solver_obf.get_py_value(s1) != solver_obf.get_py_value(s2):
                            if solver_obf.get_py_value(s1) != self.solver_oracle.get_py_value(Symbol(l.name)):
                                key = '0'
                            else:
                                key = '1'
                            break
                    if key == None:
                        logging.critical('something is wrong when banning keys')

                    # find assigned keys
                    key_list = []
                    for l in self.obf_cir.key_wires:
                        k = Symbol(l.name + '_' + key)
                        if solver_obf.get_py_value(k):
                            key_list.append(k)
                        else:
                            key_list.append(Not(k))

                    stateful_keys.append(key_list)

                    # ban the stateful key
                    f = Not(And(key_list))
                    solver_obf.add_assertion(f)
                    solver_key.add_assertion(f)
                    if len(stateful_keys) % 5000 == 0:
                        logging.warning('current stateful keys: {}'.format(len(stateful_keys)))
                    continue
                else:
                    dip_list.append(dip_formula)

                # add dip checker
                f = []
                f.append(attack_formulas.gen_dip_chk(iteration*2, '_0', dip_boolean))
                f.append(attack_formulas.gen_dip_chk(iteration*2+1, '_1', dip_boolean))
                for i in range(len(self.obf_cir.output_wires)):
                    l = self.obf_cir.output_wires[i].name
                    f.append(And(Iff(dip_out[i], Symbol(l + '@{}'.format(iteration*2))),
                                 Iff(dip_out[i], Symbol(l + '@{}'.format(iteration*2+1)))))
                f = And(f)

                solver_obf.add_assertion(f)
                solver_key.add_assertion(f)
                iteration += 1
                logging.warning('iteration: {}'.format(iteration))
            else:
                logging.warning('print keys')
                logging.warning('stateful keys: {}'.format(len(stateful_keys)))
                if solver_key.solve():
                    key = ''
                    for l in self.obf_cir.key_wires:
                        if solver_key.get_py_value(Symbol(l.name + '_0')):
                            key += '1'
                        else:
                            key += '0'
                    print("key=%s" % key)
                else:
                    logging.critical('key solver returned UNSAT')
                return


if __name__ == "__main__":
    logo()
    parser = argparse.ArgumentParser(description='Add Description')
    parser.add_argument("-p", action="store", default=0, type=int, help="print wire details")
    parser.add_argument("-b", action="store", required=True, type=str, help="original benchmark path")
    parser.add_argument("-o", action="store", required=True, type=str, help="obfuscated benchmark path")
    # parser.add_argument("-l", action="store_true", default=False, required=False, help="load dis from file")
    args = parser.parse_args()

    if args.p == 0:
        logging.getLogger().setLevel(level=logging.WARNING)
    elif args.p == 1:
        logging.getLogger().setLevel(level=logging.INFO)
    elif args.p == 2:
        logging.getLogger().setLevel(level=logging.DEBUG)

    # perform attack
    attacker = BeSAT(args)
    attacker.perform()

    resource_usage()
