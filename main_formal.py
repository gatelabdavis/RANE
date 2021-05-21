from formal.seq_attack_formal import main
from os import path


class Config:
    module_paths = ['benchmarks/verilog/original/lat.v',
                    'benchmarks/verilog/original/dff.v']
    enable_async = False
    cycsat = False
    depth = 20
    step = 5
    # solver = 'jaspergold'
    solver = 'symbiyosys'
    engine = 'yices'
    exe_path = path.expanduser('~') + "/lockbox/"


if __name__ == "__main__":
    main(Config)
