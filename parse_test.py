#!/usr/bin/python3

from blockly.blocks import cowboy_factories
from blockly.parser import Parser, ProgramParseException

################################################################################

with open("test.xml", "r") as f:
    xml_input = f.read()

parser = Parser(cowboy_factories)

try:
    program = parser.parse_program(xml_input)
    ok, result, steps = program.execute(10_000)
    print(f"Ok: {ok}, steps: {steps}, result: {result}")

except ProgramParseException as e:
    print(e)
