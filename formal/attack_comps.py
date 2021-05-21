import pyverilog.vparser.ast as vast


def read_port_arg(ast_instance, port_number):
    return ast_instance.instances[0].portlist[port_number].argname


def create_ports(prefix1, prefix2, circuit):
    ports = [vast.PortArg("", vast.Identifier('clk'))]
    input_index = 0
    output_index = 0
    for p in circuit.port_defs:
        if ('clk' not in p) and ('keyinput' not in p) and ('CK' not in p):
            if p in circuit.input_wires:
                next_index = input_index + circuit.input_wires[p] - 1
                ports.append(vast.PortArg("", vast.Identifier('{}[{}:{}]'.format(prefix1, input_index, next_index))))
                input_index += circuit.input_wires[p]
            if p in circuit.output_wires:
                next_index = output_index + circuit.output_wires[p] - 1
                ports.append(vast.PortArg("", vast.Identifier('{}[{}:{}]'.format(prefix2, output_index, next_index))))
                output_index += circuit.output_wires[p]
    return ports


class AttackComponents:
    def __init__(self, orcl_cir, obf_cir, enable_async, key_constraints):
        self.dip_gen = None
        self.dis_gen = None
        self.dip_chk = None
        self.uc = None
        self.ce = None
        self.umc = None
        self.state_size_msb = 0
        self.main = None
        self.enable_async = enable_async
        self.key_constraints = key_constraints
        self.orcl_cir = orcl_cir

        # create common components module
        if obf_cir:
            self.key_size_msb = obf_cir.n_keys - 1
        self.input_size_msb = orcl_cir.n_inputs - 2
        self.output_size_msb = orcl_cir.n_outputs - 1
        self.key_width = vast.Width(vast.IntConst(self.key_size_msb), vast.IntConst('0'))
        self.inp_width = vast.Width(vast.IntConst(str(self.input_size_msb)), vast.IntConst('0'))
        self.out_width = vast.Width(vast.IntConst(str(self.output_size_msb)), vast.IntConst('0'))

        # create instances for org0 and obf1 and obf2
        ports = create_ports('iv', 'ov0', orcl_cir)
        inst = vast.Instance(orcl_cir.name, "org0", ports, "")
        self.org0 = vast.InstanceList(orcl_cir.name, "", [inst])

        ports = create_ports('iv', 'ov1', orcl_cir)
        key_ports = [vast.PortArg("", vast.Identifier('k1'))]
        inst = vast.Instance(orcl_cir.name + '_obf', "obf1", ports + key_ports, "")
        self.obf1 = vast.InstanceList(orcl_cir.name + '_obf', "", [inst])

        ports = create_ports('iv', 'ov2', orcl_cir)
        key_ports = [vast.PortArg("", vast.Identifier('k2'))]
        inst = vast.Instance(orcl_cir.name + '_obf', "obf2", ports + key_ports, "")
        self.obf2 = vast.InstanceList(orcl_cir.name + '_obf', "", [inst])

    def dip_chk_module(self):
        # create dip_checker module
        portslist = []
        portslist.append(vast.Ioport(vast.Input('clk')))
        portslist.append(vast.Ioport(vast.Input('iv', width=self.inp_width)))
        portslist.append(vast.Ioport(vast.Input('k1', width=self.key_width)))
        portslist.append(vast.Ioport(vast.Input('k2', width=self.key_width)))
        portslist = vast.Portlist(portslist)

        inst_list = []
        inst_list.append(vast.Wire('ov0', width=self.out_width))
        inst_list.append(vast.Wire('ov1', width=self.out_width))
        inst_list.append(vast.Wire('ov2', width=self.out_width))
        inst_list.extend([self.org0, self.obf1, self.obf2])

        # add always block
        sens = vast.Sens(vast.Identifier('clk'), type='posedge')
        senslist = vast.SensList([sens])

        blocks = []
        blocks.append(vast.Identifier('assume (ov0 == ov1);'))
        blocks.append(vast.Identifier('assume (ov0 == ov2);'))
        statement = vast.Block(blocks)
        inst_list.append(vast.Always(senslist, statement))
        self.dip_chk = vast.ModuleDef("dip_checker", None, portslist, inst_list)

    def dip_gen_module(self):
        # creates dip_generator module
        # a more complicated version of dip_gen_module_uc
        # uses if in place of assume, it is faster but couldn't be used for uc termination
        portslist = []
        portslist.append(vast.Ioport(vast.Input('clk')))
        portslist.append(vast.Ioport(vast.Input('iv', width=self.inp_width)))
        portslist.append(vast.Ioport(vast.Input('k1', width=self.key_width)))
        portslist.append(vast.Ioport(vast.Input('k2', width=self.key_width)))
        portslist = vast.Portlist(portslist)

        inst_list = []
        inst_list.append(vast.Wire('ov1', width=self.out_width))
        inst_list.append(vast.Wire('ov2', width=self.out_width))
        inst_list.extend([self.obf1, self.obf2])

        # add always* block
        blocks = []
        # blocks.append(vast.IfStatement(vast.Identifier('k1 != k2'),
        #                                vast.IfStatement(vast.Identifier('ov1 != ov2'),
        #                                                 vast.Identifier('assert (ov1 == ov2);'), None),
        #                                None))
        # TODO: changed for latch locking
        blocks.append(vast.Identifier('assume (k1 != k2);'))
        blocks.append(vast.Identifier('assert (ov1 == ov2);'))

        statement = vast.Block(blocks)

        # TODO: posedge in case of latch
        # sens = vast.Sens(None, type='all')
        sens = vast.Sens(vast.Identifier('clk'), type='posedge')

        inst_list.append(vast.Always(vast.SensList([sens]), statement))

        self.dip_gen = vast.ModuleDef("dip_generator", None, portslist, inst_list)

    def dip_gen_module_uc(self):
        # create dip_generator module
        # this is the assume based version
        # slower than dip_gen_module() due to the assume
        portslist = []
        portslist.append(vast.Ioport(vast.Input('clk')))
        portslist.append(vast.Ioport(vast.Input('iv', width=self.inp_width)))
        portslist.append(vast.Ioport(vast.Input('k1', width=self.key_width)))
        portslist.append(vast.Ioport(vast.Input('k2', width=self.key_width)))
        portslist = vast.Portlist(portslist)

        inst_list = []
        inst_list.append(vast.Wire('ov1', width=self.out_width))
        inst_list.append(vast.Wire('ov2', width=self.out_width))
        inst_list.extend([self.obf1, self.obf2])

        # add always* block
        blocks = []
        blocks.append(vast.Identifier('assume (k1 != k2);'))
        blocks.append(vast.Identifier('assert (ov1 == ov2);'))
        statement = vast.Block(blocks)

        # sens = vast.Sens(None, type='all')
        sens = vast.Sens(vast.Identifier('clk'), type='posedge')
        inst_list.append(vast.Always(vast.SensList([sens]), statement))

        self.dip_gen = vast.ModuleDef("dip_generator", None, portslist, inst_list)

    def uc_module_ext_sby(self):
        # create additional blocks for symbiyosys
        if not self.enable_async:
            self.uc.portlist.ports.append(vast.Ioport(vast.Input('clk = 0')))
        else:
            self.uc.items.append(vast.Identifier('reg clk = 0;'))

        self.uc.items.append(vast.Identifier('reg [10:0] cycle = 0;'))
        self.uc.items.append(vast.Identifier('(* anyconst *) wire [{}:0] k1;'.format(self.key_size_msb)))
        self.uc.items.append(vast.Identifier('(* anyconst *) wire [{}:0] k2;'.format(self.key_size_msb)))

        if self.enable_async:
            self.uc.items.append(vast.Identifier('(* gclk *) reg gbl_clk;'))
            self.uc.items.append(vast.Identifier('always @(posedge gbl_clk)'))
            self.uc.items.append(vast.Identifier('clk = !clk;'))

            self.uc.items.append(vast.Identifier('always @(posedge gbl_clk)'))
            self.uc.items.append(vast.Identifier('if (!$rose(clk))'))
            self.uc.items.append(vast.Identifier('assume($stable(iv));'))

    def uc_module(self, dip_list):
        # create base module for unique completion
        portslist = []
        portslist.append(vast.Ioport(vast.Input('iv', width=self.inp_width)))
        portslist = vast.Portlist(portslist)

        inst_list = []
        if len(dip_list) > 0:
            for i, dip in enumerate(dip_list):
                inst_list.append(vast.Identifier('reg [{}:0] dip{} [0:{}];'.format(self.input_size_msb, i, len(dip)-1)))

        # add instance for dip_generator
        dip_ports = [vast.PortArg("", vast.Identifier('clk'))]
        dip_ports.append(vast.PortArg("", vast.Identifier('iv')))
        dip_ports.append(vast.PortArg("", vast.Identifier('k1')))
        dip_ports.append(vast.PortArg("", vast.Identifier('k2')))
        inst = vast.Instance('dip_generator', 'dg', dip_ports, "")
        inst_list.append(vast.InstanceList('dip_generator', "", [inst]))

        # add always block
        blocks = []
        blocks.append(vast.Identifier('cycle <= cycle + 1;'))
        statement = vast.Block(blocks)
        sens = vast.Sens(vast.Identifier('clk'), type='posedge')
        inst_list.append(vast.Always(vast.SensList([sens]), statement))

        statement = vast.Block([vast.Identifier(self.key_constraints)])
        sens = vast.Sens(None, type='all')
        inst_list.append(vast.Always(vast.SensList([sens]), statement))

        if len(dip_list) > 0:
            for i, dip in enumerate(dip_list):
                inst_list.append(vast.Identifier('dip_checker dc{} (clk, dip{}[cycle], k1, k2);'.format(i, i)))

        # add always block for initial values
        blocks = []
        for i, dip in enumerate(dip_list):
            for j, inp in enumerate(dip):
                blocks.append(vast.Identifier('dip{}[{}] <= {};'.format(i, j, inp)))
        statement = vast.Block(blocks)
        sens = vast.Sens(vast.Identifier('clk'), type='posedge')
        inst_list.append(vast.Always(vast.SensList([sens]), statement))

        self.uc = vast.ModuleDef("uc", None, portslist, inst_list)

    def uc_module_ext_formal(self, ):
        # create additional blocks for jaspergold
        self.uc.portlist.ports.append(vast.Ioport(vast.Input('clk')))
        self.uc.portlist.ports.append(vast.Ioport(vast.Input('k1', width=self.key_width)))
        self.uc.portlist.ports.append(vast.Ioport(vast.Input('k2', width=self.key_width)))

        self.uc.items.append(vast.Identifier('reg [10:0] cycle;'))
        self.uc.items.append(vast.Identifier('assume property (@(clk) $stable(k1));'))
        self.uc.items.append(vast.Identifier('assume property (@(clk) $stable(k2));'))

    def get_dip_gen(self, dip_list):
        self.uc_module(dip_list)
        self.uc_module_ext_sby()
        self.dip_gen_module()
        # self.dip_gen_module_uc()
        self.dip_chk_module()
        self.main = vast.Description([self.dip_gen, self.dip_chk, self.uc])

    def get_dip_gen_formal(self, dip_list):
        self.uc_module(dip_list)
        self.uc_module_ext_formal()
        self.dip_gen_module()
        # self.dip_gen_module_uc()
        self.dip_chk_module()
        self.main = vast.Description([self.dip_gen, self.dip_chk, self.uc])

    def get_unique_completion(self, dip_list):
        self.uc_module(dip_list)
        self.uc_module_ext_sby()
        self.dip_gen_module_uc()
        self.dip_chk_module()
        self.main = vast.Description([self.dip_gen, self.dip_chk, self.uc])

    def get_unique_completion_formal(self, dip_list):
        self.uc_module(dip_list)
        self.uc_module_ext_formal()
        self.dip_gen_module_uc()
        self.dip_chk_module()
        self.main = vast.Description([self.dip_gen, self.dip_chk, self.uc])

    def umc_module_ext_formal(self):
        self.umc.portlist.ports.append(vast.Ioport(vast.Input('k1', width=self.key_width)))
        self.umc.portlist.ports.append(vast.Ioport(vast.Input('k2', width=self.key_width)))

        self.umc.items.append(vast.Identifier('assume property (@(clk) $stable(k1));'))
        self.umc.items.append(vast.Identifier('assume property (@(clk) $stable(k2));'))
        self.umc.items.append(vast.Identifier('reg [10:0] cycle;'))

    def umc_module_ext_sby(self):
        self.umc.items.append(vast.Identifier("(* anyconst *) wire [{}:0] k1;".format(self.key_size_msb)))
        self.umc.items.append(vast.Identifier("(* anyconst *) wire [{}:0] k2;".format(self.key_size_msb)))
        self.umc.items.append(vast.Identifier('reg [10:0] cycle = 0;'))

    def umc_module(self, dip_list):
        # create umc module
        portslist = []
        portslist.append(vast.Ioport(vast.Input('clk')))
        portslist.append(vast.Ioport(vast.Input('iv', width=self.inp_width)))
        portslist = vast.Portlist(portslist)

        inst_list = []
        # add instance for dip_generator
        dip_ports = [vast.PortArg("", vast.Identifier('clk'))]
        dip_ports.append(vast.PortArg("", vast.Identifier('iv')))
        dip_ports.append(vast.PortArg("", vast.Identifier('k1')))
        dip_ports.append(vast.PortArg("", vast.Identifier('k2')))
        inst = vast.Instance('dip_generator', 'dg', dip_ports, "")
        inst_list.append(vast.InstanceList('dip_generator', "", [inst]))

        if len(dip_list) > 0:
            for i, dip in enumerate(dip_list):
                inst_list.append(vast.Identifier('reg [{}:0] dip{} [0:{}];'.format(self.input_size_msb, i, len(dip)-1)))

        blocks = []
        # add always block
        blocks.append(vast.Identifier('cycle <= cycle + 1;'))
        statement = vast.Block(blocks)
        sens = vast.Sens(vast.Identifier('clk'), type='posedge')
        inst_list.append(vast.Always(vast.SensList([sens]), statement))

        statement = vast.Block([vast.Identifier(self.key_constraints)])
        sens = vast.Sens(None, type='all')
        inst_list.append(vast.Always(vast.SensList([sens]), statement))

        if len(dip_list) > 0:
            for i, dip in enumerate(dip_list):
                inst_list.append(vast.Identifier('dip_checker dc{} (clk, dip{}[cycle], k1, k2);'.format(i, i)))

        # add initial block
        blocks = []
        for i, dip in enumerate(dip_list):
            for j, inp in enumerate(dip):
                blocks.append(vast.Identifier('dip{}[{}] <= {};'.format(i, j, inp)))
        statement = vast.Block(blocks)
        sens = vast.Sens(vast.Identifier('clk'), type='posedge')
        inst_list.append(vast.Always(vast.SensList([sens]), statement))

        self.umc = vast.ModuleDef("umc", None, portslist, inst_list)

    def get_umc(self, dip_list):
        self.dip_chk_module()
        self.umc_module(dip_list)
        self.umc_module_ext_sby()
        self.dip_gen_module()
        self.main = vast.Description([self.dip_chk, self.dip_gen, self.umc])

    def get_umc_formal(self, dip_list):
        self.dip_chk_module()
        self.umc_module(dip_list)
        self.umc_module_ext_formal()
        self.dip_gen_module()
        self.main = vast.Description([self.dip_chk, self.dip_gen, self.umc])

    def ce_module_ext_formal(self):
        self.ce.portlist.ports.append(vast.Ioport(vast.Input('k1', width=self.key_width)))
        self.ce.portlist.ports.append(vast.Ioport(vast.Input('k2', width=self.key_width)))

        self.ce.items.append(vast.Identifier('assume property (@(clk) $stable(k1));'))
        self.ce.items.append(vast.Identifier('assume property (@(clk) $stable(k2));'))
        self.ce.items.append(vast.Identifier('reg [10:0] cycle;'))

    def ce_module_ext_sby(self):
        self.ce.items.append(vast.Identifier('(* anyconst *) wire [{}:0] k1;'.format(self.key_size_msb)))
        self.ce.items.append(vast.Identifier('(* anyconst *) wire [{}:0] k2;'.format(self.key_size_msb)))
        self.ce.items.append(vast.Identifier('reg [10:0] cycle = 0;'))

    def ce_module(self, module_name, dip_list):
        # module for checking ce
        state_width = vast.Width(vast.IntConst(self.state_size_msb), vast.IntConst('0'))
        ce_name = module_name + '_ce'
        step = 1

        # module port list
        portslist = []
        portslist.append(vast.Ioport(vast.Input('clk')))
        portslist.append(vast.Ioport(vast.Input('ce_iv_s0', width=self.inp_width)))
        portslist.append(vast.Ioport(vast.Input('ce_state_s0', width=state_width)))
        portslist = vast.Portlist(portslist)

        # create other components for dis_generator
        inst_list = []
        inst_list.append(vast.Wire('ce_state1_s0', width=state_width))
        inst_list.append(vast.Wire('ce_state2_s0', width=state_width))
        inst_list.append(vast.Wire('ce_state1_s1', width=state_width))
        inst_list.append(vast.Wire('ce_state2_s1', width=state_width))

        inst_list.append(vast.Wire('ce_ov1_s0', width=self.out_width))
        inst_list.append(vast.Wire('ce_ov2_s0', width=self.out_width))

        inst_list.append(vast.Identifier('assign ce_state1_s0 = ce_state_s0;'))
        inst_list.append(vast.Identifier('assign ce_state2_s0 = ce_state_s0;'))

        for s in range(step):
            # create instances for obf1_ce, obf2_ce
            ports = create_ports('ce_iv_s' + str(s), 'ce_ov1_s' + str(s), self.orcl_cir)
            key_ports = [vast.PortArg("", vast.Identifier('k1'))]
            state_ports = [vast.PortArg("", vast.Identifier('ce_state1_s{}'.format(s)))]
            nstate_ports = [vast.PortArg("", vast.Identifier('ce_state1_s{}'.format(s+1)))]
            inst = vast.Instance(ce_name, "obf1_ce_s{}".format(s), ports + key_ports + state_ports + nstate_ports, "")
            obf1_ce = vast.InstanceList(ce_name, "", [inst])

            ports = create_ports('ce_iv_s' + str(s), 'ce_ov2_s' + str(s), self.orcl_cir)
            state_ports = [vast.PortArg("", vast.Identifier('ce_state2_s{}'.format(s)))]
            key_ports = [vast.PortArg("", vast.Identifier('k2'))]
            nstate_ports = [vast.PortArg("", vast.Identifier('ce_state2_s{}'.format(s+1)))]
            inst = vast.Instance(ce_name, 'obf2_ce_s{}'.format(s), ports + key_ports + state_ports + nstate_ports, "")
            obf2_ce = vast.InstanceList(ce_name, "", [inst])

            inst_list.extend([obf1_ce, obf2_ce])

        # add always block
        sens = vast.Sens(vast.Identifier('clk'), type='posedge')
        senslist = vast.SensList([sens])

        blocks = []
        for s in range(step):
            blocks.append(vast.Identifier('assert (ce_ov1_s{} == ce_ov2_s{});'.format(s, s)))
            blocks.append(vast.Identifier('assert (ce_state1_s{} == ce_state2_s{});'.format(s+1, s+1)))

        if len(dip_list) > 0:
            for i, dip in enumerate(dip_list):
                inst_list.append(vast.Identifier('reg [{}:0] dip{} [0:{}];'.format(self.input_size_msb, i, len(dip)-1)))

        # add always block
        blocks.append(vast.Identifier('cycle <= cycle + 1;'))
        statement = vast.Block(blocks)

        sens = vast.Sens(vast.Identifier('clk'), type='posedge')
        inst_list.append(vast.Always(vast.SensList([sens]), statement))

        if len(dip_list) > 0:
            for i, dip in enumerate(dip_list):
                inst_list.append(vast.Identifier('dip_checker dc{} (clk, dip{}[cycle], k1, k2);'.format(i, i)))

        # add always block
        blocks = []
        for i, dip in enumerate(dip_list):
            for j, inp in enumerate(dip):
                blocks.append(vast.Identifier('dip{}[{}] = {};'.format(i, j, inp)))
        statement = vast.Block(blocks)
        inst_list.append(vast.Always(senslist, statement))

        # for s in range(step):
        #     blocks.append(vast.Identifier('assume (ce_state1_s{} != ce_state2_s{});'.format(s+1, s+1)))

        statement = vast.Block(blocks)
        inst_list.append(vast.Always(senslist, statement))
        self.ce = vast.ModuleDef("ce", None, portslist, inst_list)

    def get_combinational_equivalence(self, module_name, state_count, dip_list):
        # based on assumptions on next states and no assertions
        self.state_size_msb = state_count - 1
        self.dip_chk_module()
        self.ce_module(module_name, dip_list)
        self.ce_module_ext_sby()
        self.main = vast.Description([self.dip_chk, self.ce])

    def get_combinational_equivalence_formal(self, module_name, state_count, dip_list):
        self.state_size_msb = state_count - 1
        self.dip_chk_module()
        self.ce_module(module_name, dip_list)
        self.ce_module_ext_formal()
        self.main = vast.Description([self.dip_chk, self.ce])

    def fk_module(self, dip_list, skip_cycles, equal_keys):
        # this module finds the correct keys after termination
        inst_list = []
        if len(dip_list) > 0:
            for i, dip in enumerate(dip_list):
                inst_list.append(
                    vast.Identifier('reg [{}:0] dip{} [0:{}];'.format(self.input_size_msb, i, len(dip) - 1)))

       # add always block
        blocks = []
        if equal_keys:
            blocks.append(vast.Identifier('assume (k1 == k2);'))
        else:
            blocks.append(vast.Identifier('assume (k1 != k2);'))
        blocks.append(vast.Identifier('cycle <= cycle + 1;'))
        blocks.append(vast.Identifier('if (cycle == {})'.format(skip_cycles)))
        blocks.append(vast.Identifier('  cover(1);'))
        statement = vast.Block(blocks)
        sens = vast.Sens(vast.Identifier('clk'), type='posedge')
        inst_list.append(vast.Always(vast.SensList([sens]), statement))

        statement = vast.Block([vast.Identifier(self.key_constraints)])
        sens = vast.Sens(None, type='all')
        inst_list.append(vast.Always(vast.SensList([sens]), statement))

        if len(dip_list) > 0:
            for i, dip in enumerate(dip_list):
                inst_list.append(vast.Identifier('dip_checker dc{} (clk, dip{}[cycle], k1, k2);'.format(i, i)))

        # add initial block
        blocks = []
        sens = vast.Sens(vast.Identifier('clk'), type='posedge')
        senslist = vast.SensList([sens])
        for i, dip in enumerate(dip_list):
            for j, inp in enumerate(dip):
                blocks.append(vast.Identifier('dip{}[{}] = {};'.format(i, j, inp)))
        statement = vast.Block(blocks)
        inst_list.append(vast.Always(senslist, statement))

        portslist = vast.Portlist([])
        self.ce = vast.ModuleDef("ce", None, portslist, inst_list)

    def fk_module_ext_sby(self):
        if self.enable_async:
            self.ce.items.append(vast.Identifier('reg clk = 0;'))
            self.ce.items.append(vast.Identifier('(* gclk *) reg gbl_clk;'))
            self.ce.items.append(vast.Identifier('always @(posedge gbl_clk)'))
            self.ce.items.append(vast.Identifier('clk =! clk;'))
        else:
            self.ce.portlist.ports.append(vast.Ioport(vast.Input('clk')))

        self.ce.items.append(vast.Identifier('reg [10:0] cycle = 0;'))

        self.ce.items.append(vast.Identifier('(* anyconst *) wire [' + str(self.key_size_msb) + ':0] k1;'))
        self.ce.items.append(vast.Identifier('(* anyconst *) wire [' + str(self.key_size_msb) + ':0] k2;'))

    def fk_module_ext_formal(self):
        self.ce.portlist.ports.append(vast.Ioport(vast.Input('clk')))
        self.ce.portlist.ports.append(vast.Ioport(vast.Input('k1', width=self.key_width)))
        self.ce.portlist.ports.append(vast.Ioport(vast.Input('k2', width=self.key_width)))

        self.ce.items.append(vast.Identifier('reg [10:0] cycle;'))
        self.ce.items.append(vast.Identifier('assume property (@(clk) $stable(k1));'))
        self.ce.items.append(vast.Identifier('assume property (@(clk) $stable(k2));'))

    def get_keys_circuit(self, dip_list, skip_cycles, equal_keys):
        # this module finds the agreeing keys
        self.dip_chk_module()
        self.fk_module(dip_list, skip_cycles, equal_keys)
        self.fk_module_ext_sby()
        self.main = vast.Description([self.dip_chk, self.ce])

    def get_keys_circuit_formal(self, dip_list, skip_cycles, equal_keys):
        # this module finds the agreeing keys
        self.dip_chk_module()
        self.fk_module(dip_list, skip_cycles, equal_keys)
        self.fk_module_ext_formal()
        self.main = vast.Description([self.dip_chk, self.ce])