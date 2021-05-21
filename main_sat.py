from sat.seq_attack import main


class Config:
    # cycsat = False
    stop = 30
    depth = 10
    step = 5
    solver = 'btor'


if __name__ == "__main__":
    main(Config)
