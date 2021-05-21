import multiprocessing
import time
import argparse
import logging
from os import path, makedirs
from copy import deepcopy
from formal.utils import write_verilog, build_ce
from file.verilog import verilog2circuit, read_verilog_wires
from common.circuit import Wire
from formal import symbiyosys
from formal.attack_comps import AttackComponents
from common.utils import logo, execution_time
from formal import jaspergold


def main(config):
    logo()
    parser = argparse.ArgumentParser(description='Sequential SAT attack implementation with SymbiYosys')
    parser.add_argument("-p", action="store", default=0, type=int, help="print info=1 and debug=2, default warning=0")
    parser.add_argument("-b", action="store", required=True, type=str, help="original benchmark path")
    parser.add_argument("-o", action="store", required=True, type=str, help="obfuscated benchmark path")
    parser.add_argument("-l", action="store_true", default=False, required=False, help="load dis from file")
    parser.add_argument("-t", action="store", default=7200, type=int, help="timeout in seconds, default=7200")
    args = parser.parse_args()

    if args.p == 0:
        logging.getLogger().setLevel(level=logging.WARNING)
    elif args.p == 1:
        logging.getLogger().setLevel(level=logging.INFO)
    elif args.p == 2:
        logging.getLogger().setLevel(level=logging.DEBUG)

    timeout = args.t
    start = time.time()
    attacker = SeqAttack(args, config)
    p = multiprocessing.Process(target=attacker.perform)
    p.start()
    p.join(timeout)
    if p.is_alive():
        logging.critical("timeout reached!")
        p.terminate()
        p.join()

    end = time.time()
    execution_time(end - start)


class SeqAttack:
    def __init__(self, args, config):
        self.config = config
        self.solver = None

        # internal parameters
        self.keys = []
        self.key_constraints = ""
        self.skip = 0
        self.iteration = 0
        self.args = args
        self.org_cir = None
        self.obf_cir = None
        self.dip_list = []
        self.banned_states = []

    def perform(self):
        self.org_cir = verilog2circuit(self.args.b)
        self.obf_cir = verilog2circuit(self.args.o)

        if self.config.cycsat:
            self.preprocess_cycles()

        # add design modules to verilog modules list
        self.config.module_paths.append(self.args.b)
        self.config.module_paths.append(self.args.o)

        logging.warning('initial values for boundary={}, step={}'.format(self.config.depth, self.config.step))
        logging.warning('timeout={}s'.format(self.args.t))

        if self.config.solver == 'jaspergold':
            self.solver = jaspergold.JGInterface(self.config, self.org_cir.name)
        else:
            self.solver = symbiyosys.SymbiInterface(self.config, self.org_cir.name)

        self.config.exe_path += self.obf_cir.name + '/'
        if not path.exists(self.config.exe_path):
            makedirs(self.config.exe_path)

        if self.args.l:
            self.load_dips()

        while 1:
            self.dis_gen()
            if self.check_uc():
                self.keys = self.find_keys(equal_keys=True)
                logging.warning("key: " + str(self.keys[0]))
                return
            elif not self.config.enable_async:
                if self.check_ce():
                    self.keys = self.find_keys()
                    logging.warning("key: " + str(self.keys))
                    return
                elif self.check_umc():
                    self.keys = self.find_keys(equal_keys=True)
                    logging.warning("key: " + str(self.keys))
                    return
            self.skip = self.config.depth
            self.config.depth = self.config.depth + self.config.step
            logging.warning('increase depth to {}'.format(self.config.depth))

    def save_dips(self):
        file_path = self.config.exe_path + self.org_cir.name + ".txt"
        with open(file_path, 'w') as filehandle:
            for dip in self.dip_list:
                tmp = ''
                for d in dip:
                    tmp += d + ' '
                filehandle.writelines(tmp + "\n")

        logging.debug("dis(es) are written to: " + file_path)

    def load_dips(self):
        # load dips from exec directory (from previous run) to continue execution
        logging.warning('loading dips from file')
        file_path = self.config.exe_path + self.org_cir.name + ".txt"
        with open(file_path, 'r') as filehandle:
            filecontents = filehandle.readlines()
            for line in filecontents:
                current_place = line[:-1]
                self.dip_list.append(current_place.split())

        max_dip_size = 1
        for tmp in self.dip_list:
            if len(tmp) > max_dip_size:
                max_dip_size = len(tmp)
        self.config.depth = max_dip_size + 5
        self.skip = max_dip_size

    def find_keys(self, equal_keys=False):
        attack_comps = AttackComponents(self.org_cir, self.obf_cir, self.config.enable_async, self.key_constraints)
        dips = self.compile_dis_list()

        if self.config.solver == 'symbiyosys':
            attack_comps.get_keys_circuit(dips, self.config.depth-1, equal_keys)
        else:
            attack_comps.get_keys_circuit_formal(dips, self.config.depth - 1, equal_keys)

        ce, state_count = build_ce(self.obf_cir)
        f = open(self.config.exe_path + 'obf_ce.v', "w")
        f.write(ce)
        f.close()

        self.solver.gen_config('fk', skip=self.config.depth-2, depth=self.config.depth+1)
        write_verilog(attack_comps.main, "main.sv", self.config.exe_path)
        results = self.solver.execute_fk()

        # check status
        if results.passed:
            assumed_keys = self.solver.get_keys()
            logging.info("assigned keys: " + str(assumed_keys))
            return assumed_keys
        else:
            logging.critical("something is wrong!")
            exit()

    def check_umc(self):
        dips = self.compile_dis_list()
        self.solver.gen_config('umc', depth=0, skip=0)
        attack_comps = AttackComponents(self.org_cir, self.obf_cir, self.config.enable_async, self.key_constraints)

        if self.config.solver == 'symbiyosys':
            attack_comps.get_umc(dips)
        else:
            attack_comps.get_umc_formal(dips)
        write_verilog(attack_comps.main, "main.sv", self.config.exe_path)

        results = self.solver.execute_umc()

        # check results
        if results.passed:
            logging.warning("umc passed!")
            return True
        elif results.failed:
            logging.warning("umc failed!")
            return False
        elif results.unknown:
            logging.critical("umc returned unknown")
            exit()
        else:
            logging.critical("something is wrong!")
            exit()

    def check_ce(self):
        # check for combinational equivalency
        attack_comps = AttackComponents(self.org_cir, self.obf_cir, self.config.enable_async, self.key_constraints)

        ce, state_count = build_ce(self.obf_cir)
        logging.warning('found {} DFFs and LATs'.format(state_count))
        f = open(self.config.exe_path + 'obf_ce.v', "w")
        f.write(ce)
        f.close()

        if self.config.solver == 'symbiyosys':
            attack_comps.get_combinational_equivalence(self.obf_cir.name, state_count, self.dip_list)
        else:
            attack_comps.get_combinational_equivalence_formal(self.obf_cir.name, state_count, self.dip_list)
        write_verilog(attack_comps.main, "main.sv", self.config.exe_path)

        self.solver.gen_config('ce', depth=self.config.depth+1, skip=self.config.depth-1)
        results = self.solver.execute_ce()

        # check status
        if results.passed:
            logging.warning("ce passed!")
            return True
        else:
            logging.warning("ce failed!")
            return False

    def check_uc(self):
        dips = self.compile_dis_list()
        self.solver.gen_config('uc', depth=self.config.depth, skip=self.config.depth-1)
        attack_comps = AttackComponents(self.org_cir, self.obf_cir, self.config.enable_async, self.key_constraints)
        if self.config.solver == 'symbiyosys':
            attack_comps.get_unique_completion(dips)
        else:
            attack_comps.get_unique_completion_formal(dips)
        write_verilog(attack_comps.main, "main.sv", self.config.exe_path)
        results = self.solver.execute_uc()

        # check results
        if results.assumptions_failed:
            # unique key is available
            logging.warning("uc passed!")
            return True
        elif results.passed:
            # there is no unique key
            logging.warning("there is no unique key!")
            return False
        else:
            logging.critical("something is wrong!")
            exit()

    def compile_dis_list(self):
        max_dip_size = 1
        for tmp in self.dip_list:
            if len(tmp) > max_dip_size:
                max_dip_size = len(tmp)

        if self.skip < max_dip_size:
            self.skip = max_dip_size
        # all_zeros = str(self.org_cir.n_inputs-1) + "'b" + '0'*(self.org_cir.n_inputs-1)
        # all_ones = str(self.org_cir.n_inputs-1) + "'b" + '1'*(self.org_cir.n_inputs-1)
        # all_zeros = [all_zeros for x in range(self.config.depth)]
        # all_ones = [all_ones for x in range(self.config.depth)]
        # dips.append(all_zeros)
        # dips.append(all_ones)
        dips = deepcopy(self.dip_list)
        for d in dips:
            if len(d) < self.config.depth:
                all_x = str(self.org_cir.n_inputs - 1) + "'b" + 'x' * (self.org_cir.n_inputs - 1)
                all_x = [all_x for x in range(self.config.depth-len(d))]
                d.extend(all_x)
        return dips

    def dis_gen(self):
        # dis gen with hd, it decreases hd at the boundary
        attack_comps = AttackComponents(self.org_cir, self.obf_cir, self.config.enable_async, self.key_constraints)

        while 1:
            dips = self.compile_dis_list()
            # update ast and generate Verilog file again
            if self.config.solver == 'symbiyosys':
                attack_comps.get_dip_gen(dips)
            else:
                attack_comps.get_dip_gen_formal(dips)
            write_verilog(attack_comps.main, "main.sv", self.config.exe_path)
            self.solver.gen_config('dis', depth=self.config.depth, skip=self.skip - 1)
            results = self.solver.execute_dis()

            # if self.iteration == 1:
            #     exit()

            # check for termination
            if results.passed:
                logging.warning("there is no more dis(es) within boundary")
                self.save_dips()
                return
            elif results.assumptions_failed:
                logging.warning("there is no more dis(es) within boundary")
                self.save_dips()
                self.config.depth = len(self.dip_list[-1])
                return
            else:
                dis, keys = self.solver.get_dis()

                if self.config.enable_async:
                    dip_tmp = []
                    for i in range(len(dis)):
                        if i % 2 == 0:
                            dip_tmp.append(dis[i])
                    self.dip_list.append(dip_tmp)
                else:
                    self.dip_list.append(dis)

                logging.info("dip: {}".format(self.dip_list[-1]))
                self.iteration = self.iteration + 1
                logging.warning("iteration: {}, dip seq length: {}".format(self.iteration, len(self.dip_list[-1])))
                logging.info("keys: {}".format(keys))

    def preprocess_cycles(self):
        from graph import cycle

        self.obf_cir.wire_objs = read_verilog_wires(self.args.o, 'generic')
        cycles_list = cycle.find_cycles(self.args, self.obf_cir.wire_objs)
        wires = self.obf_cir.wire_objs
        constraints = ""

        # for lat based circuits
        if self.config.enable_async:
            lats_list = []
            for cycle in cycles_list:
                has_ff = False
                for w in cycle:
                    if wires[w].type == Wire.DFF:
                        has_ff = True
                        break
                if not has_ff:
                    tmp = []
                    for w in cycle:
                        if wires[w].type == Wire.LAT:
                            tmp.append(w)
                    lats_list.append(tmp)

            for lats in lats_list:
                tmp = []
                for l in lats:
                    tmp.append("({{{}, {}}} == 2'b00)".format(wires[l].operands[0], wires[l].operands[1]))
                tmp = ' || '.join(tmp)
                constraints += 'assume(({}) || (({}) && ({})) );\n'.format(tmp, tmp.replace('00', '01'), tmp.replace('00', '10'))
            self.key_constraints = constraints
            self.key_constraints = self.key_constraints.replace('keyinput', 'k1') + self.key_constraints.replace('keyinput', 'k2')
        else:
            # for mux based cycles (original cycsat)
            # TODO: to be implemented
            for cycle in cycles_list:
                for w in cycle:
                    if w.type == 'MUX2x1':
                        continue
            self.key_constraints = constraints
