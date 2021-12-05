from sat.seq_attack import main


class Config:
    stop = 100
    depth = 20
    step = 10
    solver = 'btor'


if __name__ == "__main__":
    main(Config)
