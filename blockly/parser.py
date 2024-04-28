from typing import Type, Any
import xml.etree.ElementTree as ET

from .blocks import Block, StaticField, VariableField
from .exceptions import ProgramParseException
from .program import Program


class Parser:
    factories: dict[str, Type[Block]]

    def __init__(self, factories: dict[str, Type[Block]]) -> None:
        self.factories = factories

    def parse_program(self, xml_input: str) -> Program:
        parser = ParserInstance(self.factories)
        root_block, variables = parser.parse_program(xml_input)
        return Program(root_block, variables, xml_input)


class ParserInstance:
    """Instance for one parsing, keeps internally track of parsed variables.
    Should not be reused multiple times.
    """
    factories: dict[str, Type[Block]]
    variables: dict[str, list[VariableField]]

    def __init__(self, factories: dict[str, Type[Block]]) -> None:
        self.factories = factories
        self.variables = {}

    def parse_program(self, xml_input: str) -> Program:
        root_block: Block | None = None

        for el in ET.XML(xml_input):
            tag = el.tag.split("}")[-1]
            if tag == "variables":
                self.parse_variables(el)
            elif tag == "block":
                if root_block is not None:
                    raise ProgramParseException("Multiple blocks, don't know where the program starts")
                root_block = self.parse_block(f"block[{el.attrib['type']}]", el)
            else:
                raise ProgramParseException(f"Unknown element {tag}")

        if root_block is None:
            raise ProgramParseException("No block to execute")

        # Check variable types
        variables: dict[str, type] = {}
        for variable, instances in self.variables.items():
            for instance in instances:
                if instance.var_type is Any:
                    # raise ProgramParseException(f"Instance of variable {variable} has not determined type")
                    continue
                if variable in variables and variables[variable] != instance.var_type:
                    raise ProgramParseException(f"Variable {variable} has type conflict ({variables[variable]} and {instance.var_type})")
                variables[variable] = instance.var_type

        return root_block, variables

    def parse_variables(self, xml_variables: ET.Element):
        self.variables = {}
        for variable in xml_variables:
            var = variable.text.strip()
            if var in self.variables:
                raise ProgramParseException(f"Duplicate variable {var}")
            self.variables[var] = []

    def parse_block(self, path: str, block: ET.Element) -> Block:
        type = block.attrib['type']
        if type not in self.factories:
            raise ProgramParseException(f"Unknown block {type}")
        factory = self.factories[type]

        # Get mutation, fields, values, statements and next
        mutation: dict[str, str | int] = {}
        fields: dict[str, StaticField] = {}
        values: dict[str, Block] = {}
        statements: dict[str, Block] = {}
        next: Block | None = None

        for el in block:
            tag = el.tag.split("}")[-1]
            if tag == "mutation":
                mutation = el.attrib

            elif tag == "field":
                name = el.attrib['name']
                el_path = f"{path}.field[{name}]"
                value = el.text.strip()
                if name == "VAR":
                    if value not in self.variables:
                        raise ProgramParseException(f"{el_path}: Variable {value} not specified in <variables>")
                    field = VariableField(value)
                    self.variables[value].append(field)
                else:
                    field = StaticField(name, value)
                fields[name] = field

            elif tag in ("value", "statement", "next"):
                name = el.attrib.get('name', '')
                el_path = name and f"{path}.{tag}[{name}]" or f"{path}.{tag}"

                if len(el) == 2 and el[0].tag.split("}")[-1] == "shadow":
                    el = [el[1]]

                if len(el) != 1:
                    raise ProgramParseException(f"{el_path}: Element <{tag} name=\"{name}\"> needs exactly 1 child")
                child = el[0]
                child_tag = child.tag.split("}")[-1]
                if child_tag not in ("block", "shadow"):
                    raise ProgramParseException(f"{el_path}: Expected <block> inside <{tag}> but <{child_tag}> found")
                child_type = child.attrib['type']

                el_path = f"{el_path}.{child_tag}[{child_type}]"
                if tag == "value":
                    values[name] = self.parse_block(el_path, child)
                elif tag == "statement":
                    statements[name] = self.parse_block(el_path, child)
                else:
                    if next is not None:
                        raise ProgramParseException("There cannot be multiple <next> in one block")
                    next = self.parse_block(el_path, child)

        try:
            return factory(mutation=mutation, fields=fields, values=values,
                           statements=statements, next=next)
        except ProgramParseException as e:
            raise ProgramParseException(f"{path}: {e}")
