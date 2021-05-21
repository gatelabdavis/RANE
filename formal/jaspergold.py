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


class JGInterface:
    def __init__(self, config, cir_name):
        self.config = config
        self.cir_name = cir_name

    def gen_config(self, mode, depth, skip=0):
        # generate tcl file
        content = "clear -all\n"

        for path in self.config.module_paths:
            content += "analyze -v2k {}\n".format(path)
        content += "analyze -sv {}\n".format(self.config.exe_path + "main.sv\n")
        if mode == 'ce':
            content += "analyze -sv {}\n".format(self.config.exe_path + "obf_ce.v\n")

        # TODO: change mode from uc to dis
        if mode == 'dis':
            content += 'elaborate -top {uc}\n'
        elif mode == 'umc':
            content += 'elaborate -top {umc}\n'
        elif mode == 'fk':
            content += 'elaborate -top {ce}\n'
        else:
            content += "elaborate -top {}\n".format(mode)

        content += "clock clk\n"
        # content += "reset -expression {!(rst)}\n"
        content += "reset -none -non_resettable_regs 0\n"

        # optimizations
        content += "set_engine_mode auto\n"
        # content += "set_proofgrid_max_local_jobs 6\n"
        # content += "set_engine_threads 4\n"
        # content += "set_prove_time_limit 500h\n"

        if mode != 'umc':
            content += "set_max_trace_length {}\n".format(depth)
        content += "prove -bg -all\n"
        content += "prove -wait\n"

        if mode == 'fk':
            content += "visualize -property <embedded>::ce._cover_0\n"
            content += "visualize -get_value k1 -radix 2\n"
        elif mode == 'ce':
            content += "visualize -property <embedded>::ce._assert_2\n"
            content += "visualize -get_value k1 -radix 2\n"
        elif mode == 'umc':
            content += "visualize -property <embedded>::umc.dg._assert_1\n"
            content += "visualize -get_value k1 -radix 2\n"
        else:
            content += "visualize -violation -property <embedded>::uc.dg._assert_1\n"
            content += "visualize -get_value iv -radix 2\n"
        content += "exit\n"

        file_path = self.config.exe_path + self.cir_name + ".tcl"
        out_file = open(file_path, 'w')
        out_file.write(content)
        out_file.close()
        logging.debug("tcl file is written to: " + file_path)

    def execute_uc(self):
        return self.execute()

    def exe_jg(self):
        logfile = open(self.config.exe_path + 'out.log', 'w')
        # execute jaspergold
        command = ["-acquire_proj", "-no_gui", "-tcl", self.config.exe_path + self.cir_name + ".tcl"]
        subprocess.call(["jaspergold"] + command, stdout=logfile)
        with open(self.config.exe_path + 'out.log', 'r') as file:
            logfile = file.read().replace('\n', '')
        return logfile

    def execute_ce(self):
        logfile = self.exe_jg()
        rslt = Results(logfile)
        rslt.passed = findall(r'proven                    : 2', logfile)
        return rslt

    def execute_dis(self):
        return self.execute()

    def execute_fk(self):
        logfile = self.exe_jg()
        rslt = Results(logfile)
        rslt.passed = findall(r'The cover property "ce._cover_0" was covered', logfile)
        return rslt

    def execute(self):
        logfile = self.exe_jg()
        rslt = Results(logfile)
        rslt.passed = findall(r'No trace satisfying ', logfile)
        rslt.assumptions_failed = findall(r'The Visualize configurations and/or assumptions overconstrain the design', logfile)
        return rslt

    def get_keys(self):
        try:
            file = open(self.config.exe_path + 'out.log', 'r')
            trace = file.read()
        except IOError:
            logging.critical('trace file is not generated')
            exit()

        assumed_keys = findall(r'-radix 2\s\S*?(.*?)\s\S[<embedded>]', trace)
        assumed_keys = assumed_keys[0].split(' ')
        return assumed_keys

    def execute_umc(self):
        logfile = self.exe_jg()
        rslt = Results(logfile)
        rslt.passed = findall(r'proven                    : 1', logfile)
        rslt.failed = findall(r'cex                       : 1', logfile)
        rslt.unknown = findall(r'unknown                   : 1', logfile)
        return rslt

    def get_dis(self):
        try:
            file = open(self.config.exe_path + 'out.log', 'r')
            trace = file.read()
        except IOError:
            logging.critical('trace file is not generated')
            exit()

        dis = findall(r'-radix 2\s\S*?(.*?)\s\S[<embedded>]', trace)
        dis = dis[0].split(' ')

        if self.config.enable_async:
            keys = findall(r'PI_k1 = (.*?);', trace)
            keys.extend(findall(r'PI_k2 = (.*?);', trace))
        else:
            keys = findall(r'UUT.k1 = (.*?);', trace)
            keys.extend(findall(r'UUT.k2 = (.*?);', trace))
        return dis, keys
