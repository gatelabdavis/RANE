import logging
from os import devnull
import subprocess
from re import findall


class Results:
    def __init__(self, logfile):
        self.logfile = logfile
        self.passed = None
        self.failed = None
        self.unknown = None
        self.assumptions_failed = None


class SymbiInterface:
    def __init__(self, config, cir_name):
        self.config = config
        self.cir_name = cir_name

    def gen_config(self, mode, depth, skip=0):
        # generate sby file
        sby_txt = "[options]\n"
        if mode == 'cover':
            sby_txt += "mode cover\n"
        elif mode == 'fk':
            sby_txt += "mode cover\n"
        elif mode == 'umc':
            sby_txt += "mode prove\n"
        else:
            sby_txt += "mode bmc\n"

        if mode != 'umc':
            if self.config.enable_async:
                sby_txt += "depth {}\n".format(depth * 2)
            else:
                sby_txt += "depth {}\n".format(depth)
            sby_txt += "skip {}\n".format(skip)
        sby_txt += "tbtop dg\n"

        if self.config.enable_async:
            sby_txt += "multiclock on\n"

        sby_txt += "\n[engines]\n"
        if (mode == 'dis') or (mode == 'fk'):
            # sby_txt += "smtbmc --syn --nounroll --nopresat " + self.engine
            sby_txt += "smtbmc --syn --nounroll " + self.config.engine
            # sby_txt += "smtbmc"
        elif mode == 'uc':
            sby_txt += "smtbmc --syn --nounroll " + self.config.engine
            # sby_txt += "smtbmc"
        elif mode == 'umc':
            sby_txt += "aiger suprove"
        elif mode == 'ce':
            sby_txt += "smtbmc --syn --nounroll " + self.config.engine
        else:
            sby_txt += "smtbmc --syn --nounroll " + self.config.engine

        sby_txt += "\n\n[script]\n"
        for path in self.config.module_paths:
            sby_txt += "read_verilog {}\n".format(path[path.rfind('/') + 1:])
        if mode == 'ce':
            sby_txt += "read_verilog obf_ce.v\n"
        # if mode == 'se':
        #     sby_txt += "read_verilog obf_ce.v\n"
        sby_txt += "read -formal main.sv\n"

        # TODO: change mode from uc to dis
        if mode == 'dis':
            sby_txt += 'prep -top uc\n'
        elif mode == 'umc':
            sby_txt += 'prep -top umc\n'
        elif mode == 'fk':
            sby_txt += 'prep -top ce\n'
        else:
            sby_txt += "prep -top {}\n".format(mode)

        sby_txt += "\n[files]\n"
        for f in self.config.module_paths:
            sby_txt += f + '\n'
        sby_txt += self.config.exe_path + "main.sv\n"
        if mode == 'ce':
            sby_txt += self.config.exe_path + "obf_ce.v\n"
        # if mode == 'se':
        #     sby_txt += self.exe_path + "obf_ce.v\n"

        file_path = self.config.exe_path + self.cir_name + ".sby"
        out_file = open(file_path, 'w')
        out_file.write(sby_txt)
        out_file.close()
        logging.debug("sby is written to: " + file_path)

    def execute_uc(self):
        return self.execute()

    def execute_ce(self):
        return self.execute()

    def execute_dis(self):
        return self.execute()

    def execute_fk(self):
        return self.execute()

    def execute(self):
        FNULL = open(devnull, 'w')
        # execute symbiyosis
        command = ["-f", "-d", self.config.exe_path + "exec", self.config.exe_path + self.cir_name + ".sby"]
        subprocess.call(["sby"] + command, stdout=FNULL)
        with open(self.config.exe_path + 'exec/engine_0/logfile.txt', 'r') as file:
            logfile = file.read().replace('\n', '')
        rslt = Results(logfile)
        rslt.passed = findall(r'passed', logfile)
        rslt.assumptions_failed = findall(r'PREUNSAT', logfile)
        return rslt

    def get_keys(self):
        with open(self.config.exe_path + 'exec/engine_0/trace0_tb.v', 'r') as file:
            trace = file.read().replace('\n', '')

        assumed_keys = findall(r'UUT.k1 = (.*?);', trace)
        assumed_keys.extend(findall(r'UUT.k2 = (.*?);', trace))
        return assumed_keys

    def execute_umc(self):
        FNULL = open(devnull, 'w')
        command = ["-f", "-d", self.config.exe_path + "exec", self.config.exe_path + self.cir_name + ".sby"]
        subprocess.call(["sby"] + command, stdout=FNULL)
        with open(self.config.exe_path + 'exec/logfile.txt', 'r') as file:
            logfile = file.read().replace('\n', '')
        rslt = Results(logfile)
        rslt.failed = findall(r'Status returned by engine: FAIL', logfile)
        rslt.passed = findall(r'Status returned by engine: PASS', logfile)
        rslt.unknown = findall(r'returned UNKNOWN', logfile)
        return rslt

    def get_dis(self):
        # read trace_tb.v
        try:
            file = open(self.config.exe_path + 'exec/engine_0/trace_tb.v', 'r')
            trace = file.read().replace('\n', '')
        except IOError:
            logging.critical('trace file is not generated')
            file = open(self.config.exe_path + 'exec/logfile.txt', 'r')
            error = findall(r'ERROR: (.*)', file.read())
            print(error)
            exit()

        dis = findall(r'PI_iv = (.*?);', trace)
        dis.extend(findall(r'PI_iv <= (.*?);', trace))

        if self.config.enable_async:
            keys = findall(r'PI_k1 = (.*?);', trace)
            keys.extend(findall(r'PI_k2 = (.*?);', trace))
        else:
            keys = findall(r'UUT.k1 = (.*?);', trace)
            keys.extend(findall(r'UUT.k2 = (.*?);', trace))
        return dis, keys
