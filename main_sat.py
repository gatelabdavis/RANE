from sat.seq_attack import main


class Config:
    stop = 100
    depth = 10
    step = 5
    solver = 'btor'


if __name__ == "__main__":
    main(Config)
