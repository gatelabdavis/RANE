from formal.seq_attack_formal import main
import os


def lib2list(path):
    for root, ds, fs in os.walk(path):
        for f in fs:
            fullname = os.path.join(root, f)
            yield fullname


class Config:
    module_paths = ['benchmarks/verilog/original/lat.v',
                    'benchmarks/verilog/original/dff.v']

    external_lib_path = '/library'
    if os.path.isdir(external_lib_path):
        for i in lib2list(external_lib_path):
            module_paths.append(i)

    enable_async = False
    cycsat = False
    depth = 20
    step = 5
    # solver = 'jaspergold'
    solver = 'symbiyosys'
    engine = 'yices'
    exe_path = os.path.expanduser('~') + "/lockbox/"


if __name__ == "__main__":
    main(Config)
