import argparse
import logging
import multiprocessing
import time
import pysmt.shortcuts as pystm
from common.circuit import sort_circuits
from file.bench import bench2circuit
from sat.attack_comps import FormulaGenerator, get_formulas
from common.utils import logo, execution_time


def main(config):
    logo()
    parser = argparse.ArgumentParser(description='Sequential SAT attack implementation with pySMT')
    parser.add_argument("-p", action="store", default=0, type=int, help="print info=1 and debug=2, default warning=0")
    parser.add_argument("-b", action="store", required=True, type=str, help="original benchmark path")
    parser.add_argument("-o", action="store", required=True, type=str, help="obfuscated benchmark path")
    parser.add_argument("-t", action="store", default=7200, type=int, help="timeout in seconds, default=7200")
    parser.add_argument("-s", action="store", required=False, type=str, help="solver: btor, msat, z3, yices, picosat, cvc4")
    args = parser.parse_args()

    if args.p == 0:
        logging.getLogger().setLevel(level=logging.WARNING)
    elif args.p == 1:
        logging.getLogger().setLevel(level=logging.INFO)
    elif args.p == 2:
        logging.getLogger().setLevel(level=logging.DEBUG)

    if args.s:
        config.solver = args.s

    timeout = args.t
    start = time.time()
    attacker = PyAttack(args, config)
    p = multiprocessing.Process(target=attacker.perform)
    p.start()
    p.join(timeout)
    if p.is_alive():
        logging.critical("timeout reached!")
        p.terminate()
        p.join()

    end = time.time()
    execution_time(end - start)


class PyAttack:
    def __init__(self, args, config):
        self.boundary = config.depth
        self.step = config.step
        self.solver_name = config.solver
        self.stop = config.stop
        
        # internal parameters
        self.config = config
        self.args = args
        self.oracle_ast = None
        self.obf_ast = None
        self.oracle_cir = None
        self.obf_cir = None

        self.unroll_depth = 1
        self.highest_depth = 0
        self.iteration = 0
        self.solver_obf = None
        self.solver_key = None
        self.solver_oracle = None
        self.attack_formulas = None

    def perform(self):
        # process inputs
        if '.bench' in self.args.b:
            self.obf_cir = bench2circuit(self.args.o)
            self.oracle_cir = bench2circuit(self.args.b)
        else:
            logging.critical('verilog input is disabled! use main_formal')
            exit()
        #     self.oracle_ast = ASTWrapper(parse_verilog(self.args.b), self.args.b)
        #     self.obf_ast = ASTWrapper(parse_verilog(self.args.o), self.args.o)
        #
        #     self.oracle_cir = self.oracle_ast.get_circuit(check_correctness=False, correct_order=False)
        #     self.obf_cir = self.obf_ast.get_circuit(check_correctness=False, correct_order=False)

        self.oracle_cir.create_ce_circuit()
        self.obf_cir.create_ce_circuit()
        sort_circuits(self.oracle_cir, self.obf_cir)

        # perform attack
        self.solver_obf = pystm.Solver(name=self.solver_name)
        self.solver_key = pystm.Solver(name=self.solver_name)
        self.solver_oracle = pystm.Solver(name=self.solver_name)

        logging.warning('initial value for boundary={}, step={}, stop={}'.format(self.boundary, self.step, self.stop))
        logging.warning('solver={}'.format(self.solver_name))

        self.attack_formulas = FormulaGenerator(self.oracle_cir, self.obf_cir)

        # add k0 != k1
        self.solver_obf.add_assertion(self.attack_formulas.key_inequality_ckt)

        # assumptions for inequality of dip generator outputs
        assumptions = self.attack_formulas.dip_gen_assumption(1)

        # get initial states and the first copy of the circuit
        for i in range(2):
            c0, c1 = self.attack_formulas.obf_ckt_at_frame(i)
            for j in range(len(c0)):
                self.solver_obf.add_assertion(c0[j])
                self.solver_obf.add_assertion(c1[j])

        while 1:
            # query dip generator
            if self.solver_obf.is_sat(assumptions):
                dis_boolean = self.query_dip_generator()

                dis_formula = []
                for i in range(1, len(dis_boolean) + 1):
                    dis_formula.append(get_formulas(self.obf_cir.input_wires, dis_boolean[i-1], '@{}'.format(i)))
                logging.info(dis_formula)

                dis_out = self.query_oracle(dis_formula)
                self.add_dip_checker(dis_boolean, dis_out)

                self.iteration += 1
                logging.warning('iteration={}, depth={}'.format(self.iteration, self.unroll_depth))
                self.highest_depth = self.unroll_depth
            else:
                if (self.solver_obf.is_sat(pystm.TRUE()) or self.iteration == 0) and self.unroll_depth < self.stop:
                    # two agreeing keys are found, but no dip can be found
                    # also it should keep unrolling the circuit until at least one dip is found
                    #  then it can decide on uc success
                    if self.unroll_depth == self.boundary:
                        logging.warning('uc failed')

                        # check ce
                        if self.ce_check():
                            return True
                        elif self.umc_check():
                            continue
                        else:
                            # increase boundary
                            # self.unroll_depth += 1
                            self.boundary += self.step
                    else:
                        # increase unroll depth
                        self.unroll_depth += 1
                        assumptions = self.attack_formulas.dip_gen_assumption(self.unroll_depth)

                        c0, c1 = self.attack_formulas.obf_ckt_at_frame(self.unroll_depth)
                        for i in range(len(c0)):
                            self.solver_obf.add_assertion(c0[i])
                            self.solver_obf.add_assertion(c1[i])
                        logging.warning('increasing unroll depth to {}'.format(self.unroll_depth))
                elif self.unroll_depth >= self.stop:
                    logging.warning('stopped at {}'.format(self.stop))
                    self.print_keys()
                    return True
                else:
                    # key is unique
                    logging.warning('uc successful')
                    self.print_keys()
                    return True

    def query_dip_generator(self):
        dis_boolean = []

        for d in range(1, self.unroll_depth + 1):
            dip_boolean = []
            for w in self.obf_cir.input_wires:
                f = pystm.Symbol(w + '@{}'.format(d))
                if self.solver_obf.get_py_value(f):
                    dip_boolean.append(pystm.TRUE())
                else:
                    dip_boolean.append(pystm.FALSE())
            dis_boolean.append(dip_boolean)

        return dis_boolean

    def query_oracle(self, dis_formula):
        self.solver_oracle.reset_assertions()
        c0 = self.attack_formulas.oracle_ckt_at_frame(0)
        for i in range(len(c0)):
            self.solver_oracle.add_assertion(c0[i])

        dis_out = []
        for d in range(1, self.unroll_depth + 1):
            c0 = self.attack_formulas.oracle_ckt_at_frame(d)
            for i in range(len(c0)):
                self.solver_oracle.add_assertion(c0[i])

            self.solver_oracle.add_assertion(pystm.And(dis_formula[d - 1]))
            if not self.solver_oracle.is_sat(pystm.TRUE()):
                logging.critical('something is wrong in oracle query')
                exit()
            else:
                dip_out = []
                # for w in self.oracle_cir.output_wires:
                for w in self.obf_cir.output_wires:
                    f = pystm.Symbol(w + '@{}'.format(d))
                    dip_out.append(self.solver_oracle.get_value(f))
                dis_out.append(dip_out)
        logging.info(dis_out)
        return dis_out

    def add_dip_checker(self, dis_boolean, dis_out):
        for d in range(self.unroll_depth + 1):
            c0, c1 = self.attack_formulas.obf_ckt_at_frame(d)
            subs = {}
            c2 = []

            if d > 0:
                dip_out = dis_out[d - 1]
                for i in range(len(self.obf_cir.output_wires)):
                    subs[pystm.Symbol(self.obf_cir.output_wires[i] + '_0@{}'.format(d))] = dip_out[i]
                    subs[pystm.Symbol(self.obf_cir.output_wires[i] + '_1@{}'.format(d))] = dip_out[i]

                dip_boolean = dis_boolean[d - 1]
                for i in range(len(self.obf_cir.input_wires)):
                    subs[pystm.Symbol(self.obf_cir.input_wires[i] + '@{}'.format(d))] = dip_boolean[i]

                for i in range(len(self.obf_cir.next_state_wires)):
                    subs[pystm.Symbol(self.obf_cir.next_state_wires[i] + '_0@{}'.format(d - 1))] = pystm.Symbol(self.obf_cir.next_state_wires[i] + '_0_{}@{}'.format(self.iteration, d - 1))
                    subs[pystm.Symbol(self.obf_cir.next_state_wires[i] + '_1@{}'.format(d - 1))] = pystm.Symbol(self.obf_cir.next_state_wires[i] + '_1_{}@{}'.format(self.iteration, d - 1))
                    subs[pystm.Symbol(self.obf_cir.next_state_wires[i] + '_0@{}'.format(d))] = pystm.Symbol(self.obf_cir.next_state_wires[i] + '_0_{}@{}'.format(self.iteration, d))
                    subs[pystm.Symbol(self.obf_cir.next_state_wires[i] + '_1@{}'.format(d))] = pystm.Symbol(self.obf_cir.next_state_wires[i] + '_1_{}@{}'.format(self.iteration, d))
                    subs[pystm.Symbol(self.obf_cir.state_wires[i] + '_0@{}'.format(d))] = pystm.Symbol(self.obf_cir.state_wires[i] + '_0_{}@{}'.format(self.iteration, d))
                    subs[pystm.Symbol(self.obf_cir.state_wires[i] + '_1@{}'.format(d))] = pystm.Symbol(self.obf_cir.state_wires[i] + '_1_{}@{}'.format(self.iteration, d))
            else:
                for i in range(len(self.obf_cir.next_state_wires)):
                    subs[pystm.Symbol(self.obf_cir.next_state_wires[i] + '_0@{}'.format(d))] = pystm.Symbol(self.obf_cir.next_state_wires[i] + '_0_{}@{}'.format(self.iteration, d))
                    subs[pystm.Symbol(self.obf_cir.next_state_wires[i] + '_1@{}'.format(d))] = pystm.Symbol(self.obf_cir.next_state_wires[i] + '_1_{}@{}'.format(self.iteration, d))

            c = pystm.substitute(pystm.And(c0 + c1 + c2), subs)
            self.solver_obf.add_assertion(c)
            self.solver_key.add_assertion(c)

    def ce_check(self):
        c0, c1 = self.attack_formulas.obf_ckt_at_frame(1)
        for i in range(len(c0)):
            self.solver_key.add_assertion(c0[i])
            self.solver_key.add_assertion(c1[i])

        assumptions = self.attack_formulas.ce_assumption(1)
        if self.solver_key.is_sat(assumptions):
            logging.warning('ce failed')
            return False
        else:
            logging.warning('ce successful')
            self.print_keys()
            return True

    def umc_check(self):
        # TODO: umc check has not yet implemented
        logging.warning('umc check has not been implemented')
        return False

    def print_keys(self):
        # logging.warning('print keys')
        # add initial states
        c0, c1 = self.attack_formulas.obf_ckt_at_frame(0)
        for i in range(len(c0)):
            self.solver_key.add_assertion(c0[i])
            self.solver_key.add_assertion(c1[i])
        if self.solver_key.solve():
            key = ''
            for w in self.obf_cir.key_wires:
                k = w + '_0'
                if self.solver_key.get_py_value(pystm.Symbol(k)):
                    key += '1'
                else:
                    key += '0'
            logging.warning('iterations={}, highest depth={}'.format(self.iteration, self.highest_depth))
            # logging.warning("key=%s" % key[::-1])
            logging.warning("key=%s" % key)
        else:
            logging.warning('something is wrong! could not find a correct key')
