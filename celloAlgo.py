import json
import sys
import itertools
sys.path.insert(0, 'utils/')  # links the utils folder to the search path
from cello_helpers import *
from gate_assignment import *
from logic_synthesis import *
from netlist_class import Netlist
from ucf_class import UCF


# CELLO arguments:
# 1. verilog name
# 2. ucf name (could be made optional)
# 3. path-to-verilog-and-ucf
# 4. path-for-output
# 5. options (optional)

# NOTE: if verilog has multiple outputs, SC1C1G1T1 is the only UCF with 2 output devices, 
# therefore so far it is the only one that will work for 2-output circuits
# TODO: fix the UCFs with syntax errors: ('Eco1C2G2T2', 'Eco2C1G6T1')
class CELLO3:
    def __init__(self, vname, ucfname, inpath, outpath, options=None):
        self.verbose = True 
        
        if options is not None:
            yosys_cmd_choice = options['yosys_choice']
            self.verbose = options['verbose']
        else:
            yosys_cmd_choice = 1  
            
        self.inpath = inpath
        self.outpath = outpath
        self.vrlgname = vname
        self.ucfname = ucfname
        
        print_centered(['CELLO V3', self.vrlgname + ' + ' + self.ucfname], padding=True)
        
        cont = call_YOSYS(inpath, outpath, vname, yosys_cmd_choice) # yosys command set 1 seems to work best after trial & error
        
        print_centered('End of Logic Synthesis', padding=True)
        if not cont:
            return # break if run into problem with yosys, call_YOSYS() will show the error.
        
        self.ucf = UCF(inpath, ucfname) # initialize UCF from file
        if self.ucf.valid == False:
            return # breaks early if UCF file has errors
        
        self.rnl = self.__load_netlist() # initialize RG from netlist JSON output from Yosys
        
        valid, iter = self.check_conditions(verbose=True)
        print()
        print(f'Condition check passed? {valid}\n')
        
        if valid:
            cont = input('\nContinue to evaluation? y/n ')
            if (cont == 'Y' or cont == 'y') and valid:
                    best_result, worst_score = self.techmap(iter) # Executing the algorithm if things check out

                    # NOTE: best_result = tuple(circuit_score, graph_obj, truth_table)
                    best_score = best_result[0]
                    best_graph = best_result[1]
                    truth_table = best_result[2]
                    truth_table_labels = best_result[3]
                    
                    graph_inputs_for_printing = list(zip(self.rnl.inputs, best_graph.inputs))
                    graph_gates_for_printing = list(zip(self.rnl.gates, best_graph.gates))
                    graph_outputs_for_printing = list(zip(self.rnl.outputs, best_graph.outputs))

                    debug_print(f'Worst result for {self.vrlgname}.v+{self.ucfname}: {worst_score}', padding=False)
                    debug_print(f'final result for {self.vrlgname}.v+{self.ucfname}: {best_result[0]}', padding=False)
                    debug_print(best_result[1], padding=False)
                    print()
                    
                    # if self.verbose:
                    print_centered('RESULTS:')
                    print()
                    
                    for rnl_in, g_in in graph_inputs_for_printing:
                        print(f'{rnl_in} {str(g_in)} with max sensor output of {str(list(g_in.out_scores.items()))}')
                        # print(g_in.out_scores)
                    print(f'in_eval: input_response = {best_graph.inputs[0].function}\n')
                    
                    for rnl_g, g_g in graph_gates_for_printing:
                        print(rnl_g, str(g_g))
                    print(f'gate_eval: hill_response = {best_graph.gates[0].hill_response}')
                    print(f'gate_eval: input_composition = {best_graph.gates[0].input_composition}\n')
                    
                    for rnl_out, g_out in graph_outputs_for_printing:
                        print(rnl_out, str(g_out))
                    print(f'output_eval: unit_conversion = {best_graph.outputs[0].function}\n')
                    
                    
                    debug_print('Truth Table: ', padding=False)
                    tb = [truth_table_labels] + truth_table
                    print_table(tb)
                    print()
                    debug_print("Truth Table (same as before, simpler format):", padding=False)
                    for r in tb:
                        print(r)
                    print()
                    
        return
        
        
    def __load_netlist(self):
        netpath = self.outpath + '/' + self.vrlgname + '/' + self.vrlgname + '.json'
        netpath = os.path.join(*netpath.split('/'))
        netfile = open(netpath, 'r')
        netjson = json.load(netfile)
        netlist = Netlist(netjson)
        if not netlist.is_valid_netlist():
            return None
        return netlist
                
                
    def techmap(self, iter):
        # NOTE: POE of the CELLO gate assignment simulation & optimization algorithm
        # TODO: Give it parameter for which evaluative algorithm to use regardless of iter (exhaustive vs simulation)
        print_centered('Beginning GATE ASSIGNMENT', padding=True)
        
        circuit = GraphParser(self.rnl.inputs, self.rnl.outputs, self.rnl.gates)
        
        debug_print('Netlist de-construction: ')
        print(circuit)
        # scrapped this because it uses networkx library for visualzations
        # G = circuit.to_networkx()
        # visualize_logic_circuit(G, preview=False, outfile=f'{self.outpath}/{self.vrlgname}/techmap_preview.png')
        
        in_sensors = self.ucf.query_top_level_collection(self.ucf.UCFin, 'input_sensors')
        I_list = []
        for sensor in in_sensors:
            I_list.append(sensor['name'])
            
        out_devices = self.ucf.query_top_level_collection(self.ucf.UCFout, 'output_devices')
        O_list = []
        for device in out_devices:
            O_list.append(device['name'])
            
        gates = self.ucf.query_top_level_collection(self.ucf.UCFmain, 'gates')
        G_list = []
        for gate in gates:
            # NOTE: below assumes that all gates in our UCFs are 'NOR' gates
            G_list.append(gate['group'])
        G_list = list(set(G_list))
        
        debug_print('Listing available assignments from UCF: ')
        print(I_list)
        print(O_list)
        print(G_list)
        
        debug_print('Netlist requirements: ')
        i = len(self.rnl.inputs)
        o = len(self.rnl.outputs)
        g = len(self.rnl.gates)
        print(f'need {i} inputs')
        print(f'need {o} outputs')
        print(f'need {g} gates')
        # NOTE: ^ This is the input to whatever algorithm to use
        
        bestassignments = []
        if iter is not None:
            bestassignments, allscores = self.exhaustive_assign(I_list, O_list, G_list, i, o, g, circuit, iter)
        else:
            # TODO: make the other simulation() functions
            bestassignments = self.genetic_simulation(I_list, O_list, G_list, i, o, g, circuit)
        
        print_centered('End of GATE ASSIGNMENT', padding=True)
        
        return max(bestassignments, key=lambda x: x[0]) if len(bestassignments) > 0 else bestassignments, min(allscores)
    
    # NOTE: alternative to exhaustive assignment - simulation
    def genetic_simulation(self, I_list: list, O_list: list, G_list: list, i: int, o: int, g: int, netgraph: GraphParser):
        # TODO: work on this algorithm
        print_centered('Running GENETIC SIMULATION gate-assignment algorithm...', padding=True)
        debug_print('Too many combinations for exhaustive search, using simulation algorithm instead.')
        bestassignments = [AssignGraph()]
        return bestassignments
        
    def exhaustive_assign(self, I_list: list, O_list: list, G_list: list, i: int, o: int, g: int, netgraph: GraphParser, iterations: int):
        print_centered('Running EXHAUSTIVE gate-assignment algorithm...', padding=True)
        count = 0
        bestgraphs = []
        allscores = []
        bestscore = 0
        # bestgraph = None
        for I_comb in itertools.permutations(I_list, i):
            for O_comb in itertools.permutations(O_list, o):
                for G_comb in itertools.permutations(G_list, g):
                    # Check if inputs, outputs, and gates are unique and the correct number
                    if len(set(I_comb + O_comb + G_comb)) == i+o+g:
                        count += 1
                        if self.verbose: print_centered(f'beginning iteration {count}:')
                        # Output the combination
                        map_helper = lambda l, c: list(map(lambda x, y: (x, y), l, c))
                        newI = map_helper(I_comb, netgraph.inputs)
                        newG = map_helper(G_comb, netgraph.gates)
                        newO = map_helper(O_comb, netgraph.outputs)
                        newI = [Input(i[0], i[1].id) for i in newI]
                        newO = [Output(o[0], o[1].id) for o in newO]
                        newG = [Gate(g[0], g[1].gate_type, g[1].inputs, g[1].output) for g in newG]
                        
                        graph = AssignGraph(newI, newO, newG)
                        (circuit_score, tb, tb_labels) = self.score_circuit(graph, verbose=self.verbose) # NOTE: follow the circuit scoring functions
                        
                        if not self.verbose:
                            block = '\u2588'
                            num_blocks = int(round(count/iterations, 2) * 100)
                            ph_pb = '_'*100
                            fmtd_cnt = format(count, ',')
                            fmtd_itr = format(iterations, ',')
                            print(f'{ph_pb} #{fmtd_cnt}/{fmtd_itr} | circuit score: {circuit_score} best: {bestscore}\r{num_blocks*block}', end='\r')
                        
                        if self.verbose: 
                            print_centered(f'end of iteration {count} : intermediate circuit score = {circuit_score}', padding=True)
                        
                        if circuit_score > bestscore:
                            bestscore = circuit_score
                            bestgraphs = [(circuit_score, graph, tb, tb_labels)]
                        elif circuit_score == bestscore:
                            bestgraphs.append((circuit_score, graph, tb_labels))
                        allscores.append(circuit_score)

        if not self.verbose:
            print()
        print(f'\nDONE!\nCOUNTed: {count:,} iterations')
        
        return bestgraphs, allscores
    
    
    # NOTE: this function calculates CIRCUIT SCORE
    # NOTE: modify it if you want circuit score to be caldulated differently
    def score_circuit(self, graph: AssignGraph, verbose=True):
        # NOTE: PLEASE ENSURE ALL FUTURE UCF FILES FOLLOW THE SAME FORAMT AS ORIGINALS
        # (THAT'S THE ONLY TO GET THIS TO WORK)
        
        # NOTE: RETURNS circuit_score
        # NOTE: this is the core mapping from UCF
        
        # NOTE: use one gate from each group only!
        # NOTE: try every gate from each group (graph.gates.gate_id = group name)
        # print(graph.gates)
        
        '''
        Pseudo code:
        
        initialize traversal circuit()
        
        for each input:
            assign input function
        
        for each gate(group):
            find all gates in group
            for each gate in group:
                assign response function
                (basically find all individual gate permutations)
                
        for each output:
            assign output function
            
        create truth table of circuit
        
        if toxicity & cytometry in all gates:
            label circuit for extra tox and cyt plot evaluations
            (maybe ignore this part because they can just look in the UCF instead to find the plots)
        
        for each truth table combination:
            for each individual gate assignment:
                traverse circuit from inputs (input composition is mostly x1+x2)
                evaluate output
        '''
        
        # First, make sure that all inputs use the same 'sensor_response' function
        # This has to do with UCF formatting
        input_function_json = self.ucf.query_top_level_collection(self.ucf.UCFin, 'functions')[0]
        input_function_str = input_function_json['equation'][1:] #remove the '$' sign
        
        input_model_names = [i.name+'_model' for i in graph.inputs]
        input_params = query_helper(self.ucf.query_top_level_collection(self.ucf.UCFin, 'models'), 'name', input_model_names)
        input_params = {c['name'][:-6]: {p['name']: p['value'] for p in c['parameters']} for c in input_params}
        
        if verbose:
            debug_print(f'Assignment configuration: {repr(graph)}')
            print(f'INPUT paramters:')
            for p in input_params:
                print(p, input_params[p])
            print(f'input_response = {input_function_str}\n')
        # print(f'Parameters in sensor_response function json: \n{input_function_params}\n')
            
        gate_groups = [(g.gate_id, g.gate_type) for g in graph.gates]
        gates = self.ucf.query_top_level_collection(self.ucf.UCFmain, 'gates')
        gate_query = query_helper(gates, 'group', [g[0] for g in gate_groups])
        gate_ids = [(g['group'] ,g['name']) for g in gate_query]
        
        gate_functions = self.ucf.query_top_level_collection(self.ucf.UCFmain, 'models')
        gate_id_names = [i[1]+'_model' for i in gate_ids]
        gate_functions = query_helper(gate_functions, 'name', gate_id_names)
        gate_params = {gf['name'][:-6]: {g['name']: g['value'] for g in gf['parameters']} for gf in gate_functions}
        if verbose:
            print(f'GATE parameters: ')
            for f in gate_params:
                print(f, gate_params[f])
        
        ucfmain_functions = self.ucf.query_top_level_collection(self.ucf.UCFmain, 'functions')
        hill_response = query_helper(ucfmain_functions, 'name', ['Hill_response'])[0]
        input_composition = query_helper(ucfmain_functions, 'name', ['linear_input_composition'])[0]
        hill_response_equation = hill_response['equation'].replace('^', '**') # substitute power operator
        linear_input_composition = input_composition['equation']
        if verbose:
            print(f'hill_response = {hill_response_equation}')
            print(f'linear_input_composition = {linear_input_composition}')
            print()
        
            
        output_names = [o.name for o in graph.outputs]
        output_model_names = [o+'_model' for o in output_names]
        output_jsons = query_helper(self.ucf.query_top_level_collection(self.ucf.UCFout, 'models'), 'name', output_model_names)
        output_params = {o['name'][:-6]: {p['name']: p['value'] for p in o['parameters']} for o in output_jsons}
        
        output_function_json = self.ucf.query_top_level_collection(self.ucf.UCFout, 'functions')[0]
        output_function_str = output_function_json['equation']
        
        if verbose:
            print('OUTPUT parameters: ')
            for op in output_params:
                print(op, output_params[op])
            print(f'output_response = {output_function_str}\n')
        
        # adding parameters to inputs
        for ginput in graph.inputs:
            if repr(ginput) in input_params:
                ginput.add_eval_params(input_function_str, input_params[repr(ginput)])
                
        # adding parameters to outputs
        for goutput in graph.outputs:
            if repr(goutput) in output_params:
                goutput.add_eval_params(output_function_str, output_params[repr(goutput)])
                
        # adding parameters and invividual gates to gates
        for (ggroup, gname) in gate_ids:
            gprams = gate_params[gname]
            for ggate in graph.gates:
                if ggate.gate_id == ggroup:
                    ggate.add_eval_params(hill_response_equation, linear_input_composition, gname, gprams)
        
        # NOTE: creating a truth table for each graph assignment
        num_inputs = len(graph.inputs)
        num_outputs = len(graph.outputs)
        num_gates = len(graph.gates)
        (truth_table, truth_table_labels) = generate_truth_table(num_inputs, num_gates, num_outputs, graph.inputs, graph.gates, graph.outputs)
        if verbose:
            print('generating truth table...\n')
        IO_indexes = [i for i, x in enumerate(truth_table_labels) if x.split('_')[-1] == 'I/O']
        IO_names = ['_'.join(x.split('_')[:-1]) for x in truth_table_labels if x.split('_')[-1] == 'I/O']
        
        
        def get_tb_IO_index(node_name):
            return truth_table_labels.index(node_name + '_I/O')
        
        circuit_scores = []
        for r in range(len(truth_table)):
            if verbose: print(f'row{r} {truth_table[r]}')
            
            for (input_name, input_onoff) in list(dict(zip(truth_table_labels[:num_inputs], truth_table[r][:num_inputs])).items()):
                input_name = input_name[:input_name.rfind('_')]
                for grinput in graph.inputs:
                    if repr(grinput) == input_name:
                        # switch input on/off
                        grinput.switch_onoff(input_onoff)
                        ginput_idx = truth_table_labels.index(input_name)
                        truth_table[r][ginput_idx] = grinput.out_scores[grinput.score_in_use]
                        
            # NOTE: filling out truth table IO values in this part
            def set_tb_IO(node_name, IO_val):
                tb_index = get_tb_IO_index(node_name)
                truth_table[r][tb_index] = IO_val
            
            def get_tb_IO_val(node_name):
                tb_index = get_tb_IO_index(node_name)
                return truth_table[r][tb_index]
            
            def fill_truth_table_IO(graph_node):
                if type(graph_node) == Gate:
                    gate_inputs = graph.find_prev(graph_node)
                    gate_type = graph_node.gate_type
                    gate_IO = None
                    if gate_type == 'NOR':  # gate_type is either 'NOR' or 'NOT'
                        IOs = []
                        for gate_input in gate_inputs: # should be exactly 2 inputs
                            input_IO = get_tb_IO_val(repr(gate_input))
                            if input_IO is None:
                                # this might happen if the gate_input is a gate
                                fill_truth_table_IO(gate_input)
                            input_IO = get_tb_IO_val(repr(gate_input))
                            IOs.append(input_IO)
                        if len(IOs) == 2 and sum(IOs) == 0:
                            gate_IO = 1
                        else:
                            gate_IO = 0
                    else: # (gate_type == 'NOT')
                        input_IO = get_tb_IO_val(repr(gate_inputs))
                        if input_IO is None:
                            fill_truth_table_IO(gate_inputs)
                        input_IO = get_tb_IO_val(repr(gate_inputs))
                        if input_IO == 0:
                            gate_IO = 1
                        elif input_IO == 1:
                            gate_IO = 0
                        else:
                            raise RecursionError
                    # finally, update the truth table for this gate 
                    set_tb_IO(repr(graph_node), gate_IO)
                    graph_node.IO = gate_IO
                elif type(graph_node) == Output:
                    input_gate = graph.find_prev(graph_node)
                    gate_IO = get_tb_IO_val(repr(input_gate))
                    if gate_IO == None:
                        fill_truth_table_IO(input_gate)
                    gate_IO = get_tb_IO_val(repr(input_gate))
                    set_tb_IO(repr(graph_node), gate_IO) # output just carries the gate I/O
                    graph_node.IO = gate_IO
                elif type(graph_node) == Input:
                    raise NameError('not suppose to recurse to input to fill truth table')
                else:
                    raise RecursionError
                
            for gout in graph.outputs:
                try:
                    fill_truth_table_IO(gout)
                except:
                    # NOTE: this happens for something like the sr_latch, it is not currently supported
                    # NOTE: but with modifications to the truth table, this type of unstable could work
                    debug_print(f'{self.vrlgname} has unsupported circuit configuration due to flip-flopping.') 
                    print_table([truth_table_labels] + truth_table)
                    print()
                    raise(RecursionError)
                    
                
            # if verbose:
            #     print_table([truth_table_labels] + truth_table)
                 
            for goutput in graph.outputs:
                # NOTE: add funtion to test whether goutput is intermediate or final
                output_name = goutput.name
                goutput_idx = truth_table_labels.index(output_name)
                if truth_table[r][goutput_idx] == None:
                    output_score = graph.get_score(goutput, verbose=verbose)
                    truth_table[r][goutput_idx] = output_score
                    circuit_scores.append((output_score, output_name))
                
            for grgate in graph.gates:
                grgate_idx = truth_table_labels.index(grgate.gate_id)
                truth_table[r][grgate_idx] = grgate.best_score
            
            if verbose: 
                print(circuit_scores)
                print(truth_table_labels)
                print(f'row{r} {truth_table[r]}\n')
        
        # this part does this: for each output, find minOn/maxOff, and save output device score for this design
        # try:
        #   Min(On) / Max(Off)
        # except:
        #   either Max() ?
        truth_tested_output_values = {}
        for o in graph.outputs:
            tb_IO_index = get_tb_IO_index(repr(o))
            tb_index = truth_table_labels.index(repr(o))
            truth_values = {0: [], 1: []}
            for r in range(len(truth_table)):
                o_IO_val = truth_table[r][tb_IO_index]
                truth_values[o_IO_val].append(truth_table[r][tb_index])
            try:
                truth_tested_output_values[repr(o)] = min(truth_values[1]) / max(truth_values[0])
            except:
                # this means that either all of the rows in the output is ON or all OFF
                try:
                    truth_tested_output_values[repr(o)] = max(truth_values[0])
                except:
                    truth_tested_output_values[repr(o)] = max(truth_values[1])

        graph_inputs_for_printing = list(zip(self.rnl.inputs, graph.inputs))
        graph_gates_for_printing = list(zip(self.rnl.gates, graph.gates))
        graph_outputs_for_printing = list(zip(self.rnl.outputs, graph.outputs))
        if verbose:
            print('reconstructing netlist: ')
            for rnl_in, g_in in graph_inputs_for_printing:
                print(f'{rnl_in} {str(g_in)} and max composition of {max(g_in.out_scores)}')
                # print(g_in.out_scores)
            for rnl_g, g_g in graph_gates_for_printing:
                print(rnl_g, str(g_g))
            for rnl_out, g_out in graph_outputs_for_printing:
                print(rnl_out, str(g_out))
            print()
        
        truth_table_vis = f'{truth_table_labels}\n'
        for r in truth_table:
            truth_table_vis += str(r) + '\n'
        if verbose: 
            print(truth_table_vis)
            print(truth_tested_output_values)
            print()
            print_table([truth_table_labels] + truth_table)
        # take the output colums of the truth table, and calculate the outputs
        
        # NOTE: **return the lower-scored output of the multiple outputs**
        score = min(truth_tested_output_values.values()), truth_table, truth_table_labels
        
        if verbose:
            print('\nscore_circuit returns:')
            print(score)
        return score
    
    
    def check_conditions(self, verbose=True):
        if verbose: print()
        if verbose: print_centered('condition checks for valid input')
        
        if verbose: print('\nNETLIST:')
        netlist_valid = False
        if self.rnl is not None:
            netlist_valid = self.rnl.is_valid_netlist()
        if verbose: print(f'isvalid: {netlist_valid}')

        in_sensors = self.ucf.query_top_level_collection(self.ucf.UCFin, 'input_sensors')
        num_ucf_input_sensors = len(in_sensors)
        num_ucf_input_structures = len(self.ucf.query_top_level_collection(self.ucf.UCFin, 'structures'))
        num_ucf_input_models = len(self.ucf.query_top_level_collection(self.ucf.UCFin, 'models'))
        num_ucf_input_parts = len(self.ucf.query_top_level_collection(self.ucf.UCFin, 'parts'))
        num_netlist_inputs = len(self.rnl.inputs) if netlist_valid else 99999
        inputs_match = (num_ucf_input_sensors == num_ucf_input_models == num_ucf_input_structures == num_ucf_input_parts) and (num_ucf_input_parts >= num_netlist_inputs)
        if verbose: print('\nINPUTS:')
        if verbose: print(f'num IN-SENSORS in {ucfname} in-UCF: {num_ucf_input_sensors}')
        if verbose: print(f'num IN-STRUCTURES in {ucfname} in-UCF: {num_ucf_input_structures}')
        if verbose: print(f'num IN-MODELS in {ucfname} in-UCF: {num_ucf_input_models}')
        if verbose: print(f'num IN-PARTS in {ucfname} in-UCF: {num_ucf_input_parts}')
        if verbose: print(f'num IN-NODES in {vname} netlist: {num_netlist_inputs}')
        
        if verbose: print([i['name'] for i in in_sensors])
        if verbose: print(('Valid' if inputs_match else 'NOT valid') + ' input match!')
        
        out_sensors = self.ucf.query_top_level_collection(self.ucf.UCFout, 'output_devices')
        num_ucf_output_sensors = len(out_sensors)
        num_ucf_output_structures = len(self.ucf.query_top_level_collection(self.ucf.UCFout, 'structures'))
        num_ucf_output_models = len(self.ucf.query_top_level_collection(self.ucf.UCFout, 'models'))
        num_ucf_output_parts = len(self.ucf.query_top_level_collection(self.ucf.UCFout, 'parts'))
        num_netlist_outputs = len(self.rnl.outputs) if netlist_valid else 99999
        outputs_match = (num_ucf_output_sensors == num_ucf_output_models == num_ucf_output_parts == num_ucf_output_structures) and (num_ucf_output_parts >= num_netlist_outputs)
        if verbose: print('\nOUTPUTS:')
        if verbose: print(f'num OUT-SENSORS in {ucfname} out-UCF: {num_ucf_output_sensors}')
        if verbose: print(f'num OUT-STRUCTURES in {ucfname} out-UCF: {num_ucf_output_structures}')
        if verbose: print(f'num OUT-MODELS in {ucfname} out-UCF: {num_ucf_output_models}')
        if verbose: print(f'num OUT-PARTS in {ucfname} out-UCF: {num_ucf_output_parts}')
        if verbose: print(f'num OUT-NODES in {vname} netlist: {num_netlist_outputs}')
        
        if verbose: print([out['name'] for out in out_sensors])
        if verbose: print(('Valid' if outputs_match else 'NOT valid') + ' output match!')
        
        numStructs = self.ucf.collection_count['structures']
        numModels = self.ucf.collection_count['models']
        numGates = self.ucf.collection_count['gates']
        numParts = self.ucf.collection_count['parts']
        ucf_gates = self.ucf.query_top_level_collection(self.ucf.UCFmain, 'gates')
        gate_names = []
        G_list = []
        for gate in ucf_gates:
            # NOTE: below assumes that all gates in our UCFs are 'NOR' gates (curently)
            gate_names.append(gate['name'])
            G_list.append(gate['group'])
        G_list = list(set(G_list))
        num_groups = len(G_list)
        # numFunctions = len(self.ucf.query_top_level_collection(self.ucf.UCFmain, 'functions'))
        if verbose: print('\nGATES:')
        if verbose: print(f'num PARTS in {ucfname} UCF: {numParts}')
        # if verbose: print(f'(ref only) num FUNCTIONS in {ucfname} UCF: {numFunctions}')
        if verbose: print(f'num STRUCTURES in {ucfname} UCF: {numStructs}')
        if verbose: print(f'num MODELS in {ucfname} UCF: {numModels}')
        if verbose: print(f'num GATES in {ucfname} UCF: {numGates}')
        
        num_gates_availabe = []
        logic_constraints = self.ucf.query_top_level_collection(self.ucf.UCFmain, 'logic_constraints')
        for l in logic_constraints:
            for g in l['available_gates']:
                num_gates_availabe.append(g['max_instances'])
        if verbose: print(f'num GATE USES: {num_gates_availabe}')
        num_netlist_gates = len(self.rnl.gates) if netlist_valid else 99999
        if verbose: print(f'num GATES in {vname} netlist: {num_netlist_gates}')
        
        
        if verbose: print(sorted(G_list))
        if verbose: print(sorted(gate_names))
        
        gates_match = (numStructs == numModels == numGates) and (num_gates_availabe[0] >= num_netlist_gates)
        if verbose: print(('Valid' if gates_match else 'NOT valid') + ' intermediate match!')
        
        pass_check = netlist_valid and inputs_match and outputs_match and gates_match
        
        (max_iterations, confirm) = permute_count_helper(num_netlist_inputs, num_netlist_outputs, num_netlist_gates, num_ucf_input_sensors, num_ucf_output_sensors, num_groups) if pass_check else (None, None)
        if verbose: debug_print(f'#{max_iterations} possible permutations for {self.vrlgname}.v+{self.ucfname}')
        if verbose: debug_print(f'#{confirm} permutations of UCF gate groups confirmed.\n', padding=False)
        
        if verbose: print_centered('End of condition checks')
        
        # NOTE: if max_iterations passes a threshold, switch from exhaustive algorithm to simulative algorithm
        threshold = 1000000 # 1 million iterations (which should take around an hour or so)
        # if max_iterations > threshold:
        #     max_iterations = None

        return pass_check, max_iterations
    
if __name__ == '__main__':
    ucflist = ['Bth1C1G1T1', 'Eco1C1G1T1', 'Eco1C2G2T2', 'Eco2C1G3T1', 'Eco2C1G5T1', 'Eco2C1G6T1', 'SC1C1G1T1']
    # problem_ucfs = ['Eco1C2G2T2', 'Eco2C1G6T1']
    
    
    # vname = 'nand'
    # vname = 'and'
    # vname = 'xor'
    # vname = 'priorityDetector'
    # vname = 'chat_3x2'
    # vname = 'g70_boolean'
    # vname = 'g77_boolean'
    # vname = 'g92_boolean'
    
    vname = input('which verilog to test, without the .v? (hint, ___.v from your folder) \nname=')
    print()
    ucfname = input(f'which ucf to use? \n{list(zip(range(len(ucflist)), ucflist))} \nselect an index=')
    try:
        ucfname = ucflist[int(ucfname)]
    except Exception as e:
        ucfname = 'Eco1C1G1T1'
        
    
    # (3in, 1out, 7gategroups)
    # ucfname = 'Bth1C1G1T1'
    
    # (4in, 1out, 12gategroups)
    # ucfname = 'Eco1C1G1T1'
    
    # (7in, 1out, 6gategroups)
    # ucfname = 'Eco2C1G3T1'
    
    # (7in, 1out, 13gategroups)
    # ucfname = 'Eco2C1G5T1'
    
    # (3in, 2out, 9gategroups)
    # ucfname = 'SC1C1G1T1'
    
    # TODO: source UCF files from CELLO-UCF instead
    inpath = 'sample_inputs/' # (contiains the verilog files, and UCF files)
    outpath = 'temp_out/' # (any path to a local folder)
    
    Cello3Process = CELLO3(vname, ucfname, inpath, outpath, options={'yosys_choice': 1, 'verbose': False})