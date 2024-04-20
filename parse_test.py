#!/usr/bin/python3

from typing import Type
from blockly.blocks import (Block, ControlsIf, ControlsRepeatExt,
                            LogicBoolean, LogicCompare,
                            MoveDirection, IdxParam,
                            VariablesGet, VariablesSet,
                            MathArithmetic, MathNumber)
from blockly.parser import Parser, ProgramParseException

################################################################################

with open("test.xml", "r") as f:
    xml_input = f.read()

factories: dict[str, Type[Block]] = {
    "controls_if": ControlsIf,
    "controls_repeat_ext": ControlsRepeatExt,

    "logic_boolean": LogicBoolean,
    "logic_compare": LogicCompare,

    "math_number": MathNumber,
    "math_arithmetic": MathArithmetic,

    "move_direction": MoveDirection,
    "idx_param": IdxParam,

    # TODO: auto simplify these?
    "variables_get": VariablesGet,
    "variables_set": VariablesSet,
}

parser = Parser(factories)

try:
    program = parser.parse_program(xml_input)
    ok, result, steps = program.execute(10_000)
    print(f"Ok: {ok}, steps: {steps}, result: {result}")

except ProgramParseException as e:
    print(e)
