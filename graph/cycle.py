from datetime import datetime
import logging

from networkx.utils import *
from graph_tool import Graph, topology
from dateutil.relativedelta import relativedelta


cnt = 0


def diff(t_a, t_b):
    t_diff = relativedelta(t_b, t_a)  # later/end time comes first!
    return '{h}h {m}m {s}s'.format(h=t_diff.hours, m=t_diff.minutes, s=t_diff.seconds)


def get_cyclic_cone(wire_in, fanin_cone):
    if wire_in.type != "inp":
        if wire_in not in fanin_cone:
            fanin_cone.add(wire_in)
            for i in range(len(wire_in.operands)):
                get_cyclic_cone(wire_in.operands[i], fanin_cone)


def find_cycles(args, wires):
    # implemented with networkx
    G = nx.DiGraph()
    lst = []
    # for i in range(0, len(wires)):
    #     lst.append(i)
    # G.add_nodes_from(lst)

    for w in wires:
        if wires[w].type != "inp":
            for j in range(len(wires[w].operands)):
                G.add_edges_from(zip([wires[w].operands[j]], [w]))

    cycles = list(nx.simple_cycles(G))
    logging.warning("there are {} cycles".format(len(cycles)))
    if args.p > 0:
        logging.info("list of cycles:")
        for cycle in cycles:
            tmp = ""
            for c in cycle:
                tmp += c + " "
            print(tmp)
    return cycles


def find_cycles2(args, wires):
    # implemented with graph-tools
    g = Graph()
    t_a = datetime.now()
    lst = []
    for i in range(0, len(wires)):
        lst.append(g.add_vertex())

    for i in range(0, len(wires)):
        if wires[i].type != "inp":
            for j in range(len(wires[i].operands)):
                g.add_edge(lst[wires[i].operands[j].index], lst[wires[i].index])

    cycles = []
    for c in all_circuits(g):
        if len(cycles) > 100000:
            logging.info("number of cycles is limited.")
            break
        cycles.append(c.tolist())

    t_b = datetime.now()
    logging.info("time of finding cycles: " + diff(t_a, t_b))
    logging.info("there are" + str(len(cycles)) + "cycles")
    if args.p:
        logging.info("list of cycles:")
        for cycle in cycles:
            tmp = ""
            for i in range(len(cycle)):
                tmp += wires[cycle[i]].name + " "
            logging.info(tmp)
        print()
    return cycles
