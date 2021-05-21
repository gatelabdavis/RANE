import logging
import resource


def logo():
    logging.basicConfig(format="%(asctime)s %(levelname)s:: %(message)s", datefmt="%H:%M:%S")
    logging.getLogger().handlers[0].setFormatter(logging.Formatter("%(message)s"))
    logging.warning(r'  _____            _   _ ______ ')
    logging.warning(r' |  __ \     /\   | \ | |  ____|')
    logging.warning(r' | |__) |   /  \  |  \| | |__   ')
    logging.warning(r' |  _  /   / /\ \ | . ` |  __|  ')
    logging.warning(r' | | \ \  / ____ \| |\  | |____ ')
    logging.warning(r' |_|  \_\/_/    \_\_| \_|______|')
    logging.warning(r'      by GATE Lab, George Mason University')
    logging.warning(r'')
    logging.getLogger().handlers[0].setFormatter(
        logging.Formatter("[%(asctime)s.%(msecs)04d %(funcName)s %(levelname)s] %(message)s", datefmt="%H:%M:%S"))
    # logging.getLogger().handlers[0].setFormatter(
    #     logging.Formatter("[%(asctime)s.%(msecs)04d] %(message)s", datefmt="%H:%M:%S"))


def execution_time(diff):
    logging.warning("total time: {0:.2f}s".format(diff))


def resource_usage():
    usage = resource.getrusage(resource.RUSAGE_SELF)
    for name, desc in [
        ('ru_utime', 'User time'),
        ('ru_stime', 'System time'),
        ('ru_maxrss', 'Max. Resident Set Size'),
        ('ru_inblock', 'Block inputs'),
        ('ru_oublock', 'Block outputs'),
    ]:
        print('%-25s (%-10s) = %s' % (desc, name, getattr(usage, name)))
