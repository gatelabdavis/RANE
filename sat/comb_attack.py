import argparse
import logging
from pysmt.shortcuts import Solver, And, Iff, TRUE, FALSE, Not, substitute, simplify, Symbol, Xor, Or
from common.circuit import sort_circuits
from common.utils import logo, resource_usage
from file.bench import bench2circuit


class FormulaGenerator:
    def __init__(self, oracle_cir, obf_cir):
        self.orcl_cir = oracle_cir
        self.obf_cir = obf_cir
        self.key_subs = [{}, {}]

        orcl_wires = self.orcl_cir.wire_objs
        obf_wires = self.obf_cir.wire_objs

        # generate solver formulas
        self.gen_wire_formulas(self.orcl_cir)
        self.gen_wire_formulas(self.obf_cir)

        # create key substitution dictionary
        for w in self.obf_cir.key_wires:
            self.key_subs[0][Symbol(w)] = Symbol(w + '_0')
            self.key_subs[1][Symbol(w)] = Symbol(w + '_1')

        # generate formulas for two copies of obfuscated circuit
        ckt1 = []
        ckt2 = []
        for w in self.obf_cir.output_wires:
            ckt1.append(substitute(obf_wires[w].formula, self.key_subs[0]))
            ckt2.append(substitute(obf_wires[w].formula, self.key_subs[1]))
        output_xors = []
        for i in range(len(self.obf_cir.output_wires)):
            output_xors.append(Xor(ckt1[i], ckt2[i]))
        self.dip_gen_ckt = Or(output_xors)

        # key inequality circuit
        key_symbols1 = []
        key_symbols2 = []
        for w in self.obf_cir.key_wires:
            key_symbols1.append(Symbol(w + '_0'))
            key_symbols2.append(Symbol(w + '_1'))

        output_xors = []
        for i in range(len(key_symbols1)):
            output_xors.append(Xor(key_symbols1[i], key_symbols2[i]))
        self.key_inequality_ckt = Or(output_xors)

        # dip checker circuit
        self.dip_chk1 = []
        self.dip_chk2 = []
        for w in self.obf_cir.output_wires:
            self.dip_chk1.append(substitute(obf_wires[w].formula, self.key_subs[0]))
            self.dip_chk2.append(substitute(obf_wires[w].formula, self.key_subs[1]))

    def gen_wire_formulas(self, circuit):
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
            if wire.type == 'not':
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


class CombAttack:
    def __init__(self, args):
        self.args = args
        self.oracle_ast = None
        self.obf_ast = None
        self.oracle_cir = None
        self.obf_cir = None

    def perform(self):
        if '.bench' in args.b:
            logging.warning("reading bench inputs")
            self.obf_cir = bench2circuit(args.o)
            self.oracle_cir = bench2circuit(args.b)
        else:
            logging.critical('disabled!')
            exit
            # logging.warning("preprocessing verilog inputs")
            # self.oracle_ast = ASTWrapper(parse_verilog(self.args.b), self.args.b)
            # self.obf_ast = ASTWrapper(parse_verilog(self.args.o), self.args.o)

            # self.oracle_cir = self.oracle_ast.get_circuit(check_correctness=False, correct_order=False)
            # self.obf_cir = self.obf_ast.get_circuit(check_correctness=False, correct_order=False)

        # TODO: these three lines are added for .v format and has not been thoroughly tested
        self.oracle_cir.create_ce_circuit()
        self.obf_cir.create_ce_circuit()
        sort_circuits(self.oracle_cir, self.obf_cir)

        self.comb_attack()

    def comb_attack(self):
        # dis generator
        solver_name = 'btor'
        solver_obf = Solver(name=solver_name)
        solver_key = Solver(name=solver_name)
        solver_oracle = Solver(name=solver_name)
        attack_formulas = FormulaGenerator(self.oracle_cir, self.obf_cir)

        f = attack_formulas.dip_gen_ckt
        # f = simplify(f)
        solver_obf.add_assertion(f)

        f = attack_formulas.key_inequality_ckt
        # f = simplify(f)
        solver_obf.add_assertion(f)

        iteration = 0
        while 1:
            # query dip generator
            if solver_obf.solve():
                dip_formula = []
                dip_boolean = []
                for l in self.obf_cir.input_wires:
                    t = Symbol(l)
                    if solver_obf.get_py_value(t):
                        dip_formula.append(t)
                        dip_boolean.append(TRUE())
                    else:
                        dip_formula.append(Not(t))
                        dip_boolean.append(FALSE())
                logging.info(dip_formula)

                # query oracle
                dip_out = []
                for l in self.oracle_cir.output_wires:
                    t = self.oracle_cir.wire_objs[l].formula
                    solver_oracle.reset_assertions()
                    solver_oracle.add_assertion(t)
                    if solver_oracle.solve(dip_formula):
                        dip_out.append(TRUE())
                    else:
                        dip_out.append(FALSE())
                logging.info(dip_out)

                # add dip checker
                f = []
                for i in range(len(attack_formulas.dip_chk1)):
                    f.append(And(Iff(dip_out[i], attack_formulas.dip_chk1[i]),
                                 Iff(dip_out[i], attack_formulas.dip_chk2[i])))
                f = And(f)

                subs = {}
                for i in range(len(self.obf_cir.input_wires)):
                    subs[Symbol(self.obf_cir.input_wires[i])] = dip_boolean[i]

                # f = simplify(f)
                f = substitute(f, subs)
                solver_obf.add_assertion(f)
                solver_key.add_assertion(f)

                iteration += 1
                logging.warning('iteration: {}'.format(iteration))
            else:
                logging.warning('print keys')
                if solver_key.solve():
                    key = ''
                    for i in range(len(self.obf_cir.key_wires)):
                        k = 'keyinput{}_0'.format(i)
                        if solver_key.get_py_value(Symbol(k)):
                            key += '1'
                        else:
                            key += '0'
                    print("key=%s" % key)
                else:
                    logging.critical('key solver returned UNSAT')
                return


if __name__ == "__main__":
    logo()
    parser = argparse.ArgumentParser(description='Combinational SAT attack implementation with pySMT')
    parser.add_argument("-p", action="store", default=0, type=int, help="print info=1 and debug=2, default warning=0")
    parser.add_argument("-b", action="store", required=True, type=str, help="original benchmark path")
    parser.add_argument("-o", action="store", required=True, type=str, help="obfuscated benchmark path")
    args = parser.parse_args()

    if args.p == 0:
        logging.getLogger().setLevel(level=logging.WARNING)
    elif args.p == 1:
        logging.getLogger().setLevel(level=logging.INFO)
    elif args.p == 2:
        logging.getLogger().setLevel(level=logging.DEBUG)

    # perform attack
    attacker = CombAttack(args)
    attacker.perform()

    resource_usage()
