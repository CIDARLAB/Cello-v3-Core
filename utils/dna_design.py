"""
Class to generate the final circuit design/part order.
See and+Bth-dna_design-to-sbol_diagram.png for a visual depiction of the relationship between the file this class
produces and the SBOL diagram...

"""

import os
import csv
from dataclasses import dataclass, field


@dataclass
class CirRuleSet:
    """

    """

    after: list[str]
    startswith: bool
    endswith: bool
    not_startswith: bool
    not_endswith: bool
    nextto: list[str]
    not_nextto: list[str]


@dataclass
class DevRuleSet:
    """

    """

    after: list[str]
    startswith: bool
    endswith: bool
    not_startswith: bool
    not_endswith: bool
    nextto: list[str]
    not_nextto: list[str]


class DNADesign:
    """
    Object that generates DNA design (i.e. order of parts/dna sequences).
    Produces a csv of the part order. (Corresponds to v2.0 'dpl_dna_designs.csv'.)
    Relies heavily on the eugene.py object:
        ~ EugeneObject.structs_cas_dict{EugeneCassette{cassette name, inputs, outputs, components}}

    gen_seq()
    """

    def __init__(self, structs, cassettes, sequences, device_rules, circuit_rules):

        self.structs = structs  # mainly used for regulatory info file
        self.cassettes = cassettes  # contains the input, output, components, and color
        self.sequences = sequences  # contains the part type and actual dna sequence
        self.device_rules = device_rules  # rules govern short sequences of parts that make up devices
        self.circuit_rules = circuit_rules  # rules govern the broader order of those devices
        # rules types: 'NOT', 'EQUALS', 'NEXTTO', 'CONTAINS', 'STARTSWITH', 'ENDSWITH', 'BEFORE', 'AFTER', 'ALL_FORWARD'
        #                       TODO                 TODO                                                      TODO

        self.device_rule_sets: dict[DevRuleSet] = {}
        self.circuit_rule_sets: dict[CirRuleSet] = {}

        self.device_order: list[str] = []
        self.part_order: list[str] = []

    def gen_seq(self, filepath):
        """
        Traverses all parts in the cassettes, generating their order based on the provided rules.
        *Generally*, the component order for a device cassette is:
            1. 'output' from previous device
            2. cassette components (in order, ending in Terminator...)
            3. next device (not necessarily the device to which the current device outputs)
        '_nonce_pad' is inserted according to landing pad rules (?)

        :return: part_order
        """

        devices_placed: list[str] = []  # for memoization
        parts_placed: list[str] = []

        # Most rules are 'AFTER' and 'BEFORE' rules; these will be reformulated in terms of 'AFTER' rules for simplicity
        # Permutations of these parameters include:
        #     THIS AFTER  THAT -> THAT    *
        # NOT THIS AFTER  THAT -> [None]
        #     THAT AFTER  THIS -> [None]
        # NOT THAT AFTER  THIS -> THAT    *
        #     THIS BEFORE THAT -> [None]
        # NOT THIS BEFORE THAT -> THAT    *
        #     THAT BEFORE THIS -> THAT    *
        # NOT THAT BEFORE THIS -> [None]

        def rule_conversion(rule: list[str], x: str, y: str = ""):
            if rule in [[x, 'AFTER', y], ['NOT', y, 'AFTER', x], ['NOT', x, 'BEFORE', y], [y, 'BEFORE', x]]:
                # TODO: in case other rule absent...
                return y
            else:
                return False

        # Reformulate Cir Rules
        for device, cassette in self.cassettes.items():
            self.circuit_rule_sets[device] = CirRuleSet([], False, False, False, False, [], [])
            for rule in cassette.cir_rules:  # TODO: Account for Equals
                if 'Loc' not in rule:
                    if 'AFTER' in rule or 'BEFORE' in rule:
                        words = rule.split()
                        y = ""
                        for word in words:
                            if word not in [device, 'NOT', 'AFTER', 'BEFORE']:
                                y = word
                                break
                        res = rule_conversion(rule.split(), device, y)
                        if res and res not in self.circuit_rule_sets[device].after:
                            self.circuit_rule_sets[device].after.append(res)
                    elif 'STARTSWITH' in rule:
                        if 'NOT' in rule:
                            self.circuit_rule_sets[device].not_startswith = True
                        else:
                            self.device_order.append(device)
                            self.circuit_rule_sets[device].startswith = True
                    elif 'ENDSWITH' in rule:
                        if 'NOT' in rule:
                            self.circuit_rule_sets[device].not_endswith = True
                        else:
                            self.circuit_rule_sets[device].endswith = True
                    elif 'NEXTTO' in rule:
                        words = rule.split()
                        y = ""
                        for word in words:
                            if word not in [device, 'NOT', 'NEXTTO']:
                                y = word
                        if 'NOT' in rule:
                            self.circuit_rule_sets[device].not_nextto.append(y)
                        else:
                            self.circuit_rule_sets[device].nextto.append(y)
        # print(self.circuit_rule_sets)

        # Place devices
        devices = list(self.cassettes)
        while len(devices) > 0:
            for device in list(self.cassettes):
                self.circuit_rule_sets[device].after = [rule for rule in self.circuit_rule_sets[device].after
                                                        if rule not in devices_placed]
                if len(self.circuit_rule_sets[device].after) == 0 and device in devices:
                    devices_placed.append(device)
                    devices.remove(device)
        # print(devices_placed)

        # Reformulate Dev Rules  # NOTE: For UCFs that only have the 'ALL_FORWARD' device rule, this block has no effect
        for device, cassette in self.cassettes.items():
            for part in list(self.cassettes[device].inputs + self.cassettes[device].comps):
                self.device_rule_sets[part] = DevRuleSet([], False, False, False, False, [], [])
                for rule in self.sequences[part].dev_rules:  # TODO: Account for Equals
                    if 'Loc' not in rule:  # TODO: _nonce_pads
                        if 'AFTER' in rule or 'BEFORE' in rule:
                            words = rule.split()
                            y = ""
                            for word in words:
                                if word not in [part, 'NOT', 'AFTER', 'BEFORE']:
                                    y = word
                                    break
                            res = rule_conversion(rule.split(), device, y)
                            if res and res not in self.device_rule_sets[device].after:
                                self.device_rule_sets[device].after.append(res)
                        elif 'STARTSWITH' in rule:
                            if 'NOT' in rule:
                                self.device_rule_sets[device].not_startswith = True
                            else:
                                self.device_order.append(device)
                                self.device_rule_sets[device].startswith = True
                        elif 'ENDSWITH' in rule:
                            if 'NOT' in rule:
                                self.device_rule_sets[device].not_endswith = True
                            else:
                                self.device_rule_sets[device].endswith = True
                        elif 'NEXTTO' in rule:
                            words = rule.split()
                            y = ""
                            for word in words:
                                if word not in [device, 'NOT', 'NEXTTO']:
                                    y = word
                            if 'NOT' in rule:
                                self.device_rule_sets[device].not_nextto.append(y)
                            else:
                                self.device_rule_sets[device].nextto.append(y)
        # print(self.device_rule_sets)

        for device in self.cassettes:
            for part in list(self.cassettes[device].comps):
                self.sequences[part].color = self.cassettes[device].color
            for part in list(self.cassettes[device].outputs):
                self.sequences[part].color = self.cassettes[device].color

        # Place components/parts within each device
        for device in devices_placed:
            parts = list(self.cassettes[device].inputs + self.cassettes[device].comps)
            while len(parts) > 0:
                for part in list(self.cassettes[device].inputs + self.cassettes[device].comps):
                    self.device_rule_sets[part].after = [rule for rule in self.device_rule_sets[part].after
                                                         if rule not in devices_placed]
                    if len(self.device_rule_sets[part].after) == 0 and part in parts:
                        parts_placed.append(part)
                        parts.remove(part)
        # print(parts_placed)

        def hex_to_rgb(hex_value):
            """

            :param hex_value:
            :return:
            """
            if not hex_value:
                return '0.0;0.0;0.0'
            value = hex_value.lstrip('#')
            lv = len(value)
            vals = list(round(int(value[i:i + lv // 3], 16) / 255, 2) for i in range(0, lv, lv // 3))
            return ';'.join(str(val) for val in vals)

        # WRITE DNA_PARTS_INFO FILE (equivalent of 2.0 dpl_part_information.csv)
        dna_part_info_path = filepath + '_dna-part-info.csv'
        os.makedirs(os.path.dirname(dna_part_info_path), exist_ok=True)
        with open(dna_part_info_path, 'w', newline='') as dna_part_info:
            csv_writer = csv.writer(dna_part_info)
            csv_writer.writerow(['part_name', 'type', 'x_extent', 'y_extent', 'start_pad', 'end_pad', 'color',
                                 'hatch', 'arrowhead_height', 'arrowhead_length', 'linestyle', 'linewidth'])
            csv_writer.writerow(['_NONCE_PAD', 'UserDefined', '30', '', '', '', '1.00;1.00;1.00', '', '', '', '', ''])
            for seq in self.sequences.values():
                if seq.parts_type == 'cassette':
                    csv_writer.writerow([seq.parts_name, 'UserDefined', 25, 5, '', '', '0.00;0.00;0.00', '', '', '', '', ''])
                elif seq.parts_type in ['cds', 'rbs']:
                    csv_writer.writerow([seq.parts_name, seq.parts_type.upper(), '', '', '', '', hex_to_rgb(seq.color), '', '', '', '', ''])
                elif seq.parts_type == 'scar':
                    continue
                else:
                    csv_writer.writerow([seq.parts_name, seq.parts_type.capitalize(), '', '', '', '',
                                         hex_to_rgb(seq.color), '', '', '', '', ''])
            dna_part_info.close()

        # WRITE DNA_PARTS_ORDER FILE (equivalent of 2.0 dpl_dna_designs.csv)
        dna_part_order_path = filepath + '_dna-part-order.csv'
        os.makedirs(os.path.dirname(dna_part_order_path), exist_ok=True)
        with open(dna_part_order_path, 'w', newline='') as dna_part_order:
            csv_writer = csv.writer(dna_part_order)
            csv_writer.writerow(['design_name', 'parts'])
            new_row = ['first_device']
            for part in parts_placed:
                new_row.append(part)
            csv_writer.writerow(new_row)
            dna_part_order.close()

        # WRITE STATIC PLOT PARAMETERS FILE (equivalent of 2.0 plot_parameters.csv)
        plot_parameters = filepath + '_plot-parameters.csv'
        os.makedirs(os.path.dirname(plot_parameters), exist_ok=True)
        with open(plot_parameters, 'w', newline='') as plot_params:
            csv_writer = csv.writer(plot_params)
            csv_writer.writerows([['parameter', 'value'],
                                  ['linewidth', 1],
                                  ['y_scale', 1],
                                  ['show_title', 'N'],
                                  ['backbone_pad_left', 3],
                                  ['backbone_pad_right', 3],
                                  ['axis_y', 48]
                                  ])
            plot_params.close()

        # WRITE REGULATORY INFO FILE
        regulatory_info = filepath + '_regulatory-info.csv'
        os.makedirs(os.path.dirname(regulatory_info), exist_ok=True)
        with open(regulatory_info, 'w', newline='') as reg_info:
            csv_writer = csv.writer(reg_info)
            csv_writer.writerow(['from_partname', 'type', 'to_partname', 'arrowhead_length', 'linestyle',
                                 'linewidth', 'color'])
            for struct in self.structs.values():
                if struct.gates_group:
                    new_row = [struct.gates_group, 'Repression', struct.outputs[0], 3, '-', '', hex_to_rgb(
                               struct.color)]
                    csv_writer.writerow(new_row)
            reg_info.close()

        # return self.part_order
