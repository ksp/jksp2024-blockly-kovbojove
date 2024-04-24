from dataclasses import dataclass
from enum import Enum
from typing import Self, Any, Type, TypeVar

from .actions import Action, ActionType, Direction
from .exceptions import OutOfStepsException, ProgramParseException


class Run:
    max_steps: int
    steps: int
    variables: dict[str, int | bool]

    def __init__(self, max_steps: int, variables: dict[str, int | bool]) -> None:
        self.max_steps = max_steps
        self.steps = 0
        self.variables = variables

    def add_steps(self, steps: int):
        self.steps += steps
        if self.steps > self.max_steps:
            raise OutOfStepsException()


################################################################################

class Field:
    is_variable: bool = False

    name: str

    def execute(self, run: Run) -> bool | int | str:
        pass

    def check_type(self, wanted: type) -> None:
        pass


class VariableField(Field):
    is_variable = True
    var_type: type

    def __init__(self, name: str) -> None:
        self.name = name
        self.var_type = Any

    def __str__(self) -> str:
        return f"variable {self.name}"

    def check_type(self, wanted: type) -> None:
        # Variable could be any type, will be checked after parsing the whole program
        self.var_type = wanted

    def execute(self, run: Run) -> int | bool:
        return run.variables[self.name]


class StaticField(Field):
    value: bool | int | str
    returns: type

    def __init__(self, name: str, raw_value: str) -> None:
        self.name = name
        if name == "BOOL":
            self.value = raw_value.lower() == "true"
            self.returns = bool
        elif name == "NUM":
            self.value = int(raw_value)
            self.returns = int
        else:
            self.value = raw_value
            self.returns = str

    def __str__(self) -> str:
        return f"field {self.name}"

    def check_type(self, wanted: type) -> None:
        if wanted != self.returns:
            raise ProgramParseException(f"{self.name} is {self.returns} but {wanted} wanted")

    def execute(self, run: Run) -> str | bool:
        return self.value


################################################################################

type_to_js_type: dict[type, str] = {
    bool: "Boolean",
    int: "Number",
    str: "String",
}


class BlockInputKind(Enum):
    FIELD = "field"
    VALUE = "value"
    STATEMENT = "statement"

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class BlockInput:
    kind: BlockInputKind
    attr: str  # name of the object attribute to save into
    name: str
    data_type: type = Any
    dropdown: list[tuple[str, str]] | None = None
    variable: bool = False
    arg_group: int = 0  # for grouping block inputs in graphical blocks

    def json_definition(self) -> dict[str]:
        if self.kind == BlockInputKind.FIELD:
            t = "field_input"
            if self.dropdown is not None:
                t = "field_dropdown"
            elif self.data_type == int:
                t = "field_number"
            elif self.variable:
                t = "field_variable"
        elif self.kind == BlockInputKind.VALUE:
            t = "input_value"
        elif self.kind == BlockInputKind.STATEMENT:
            t = "input_statement"
        out = {
            "type": t,
            "name": self.name,
        }
        if self.dropdown:
            out["options"] = self.dropdown
        elif self.data_type != Any:
            out["check"] = type_to_js_type[self.data_type]
        return out


################################################################################

class Block:
    is_blockly_default: bool = False  # do not generate JSON definition for this block

    # For generating Blockly definition and for checks:
    name: str = "???"
    color: int | None = None
    tooltip: str | None = None
    inputs: list[BlockInput] = []
    messages: list[str] = []  # texts displayed in graphical blocks
    returns: None | type = None  # if itself returns something (bool / int)
    has_prev: bool = False  # could run after another block
    has_next: bool = False  # another block could run after this one

    # Instance variables:
    next: Self | None

    def __str__(self) -> str:
        return f"block '{self.name}'"

    @classmethod
    def json_definition(cls) -> dict[str]:
        out = {
            "type": cls.name,
        }
        if cls.has_prev:
            out["previousStatement"] = None
        if cls.has_next:
            out["nextStatement"] = None
        if cls.returns is not None:
            out["output"] = type_to_js_type[cls.returns]
        if cls.color is not None:
            out["colour"] = cls.color
        if cls.tooltip is not None:
            out["tooltip"] = cls.tooltip

        for i, message in enumerate(cls.messages):
            out[f"message{i}"] = message

        arg_groups: dict[int, list[BlockInput]] = {}
        for input in cls.inputs:
            if input.arg_group not in arg_groups:
                arg_groups[input.arg_group] = []
            arg_groups[input.arg_group].append(input)
        for i, arg_group in arg_groups.items():
            out[f"args{i}"] = [input.json_definition() for input in arg_group]

        return out

    def execute(self, run: Run) -> Action | bool | None:
        if self.next:
            return self.next.execute(run)
        return None

    def _set_return_type(self, return_type: type):
        raise ProgramParseException(f"cannot set return type for {self.name}")

    U = TypeVar('U')

    def _get_inputs(self, kind: BlockInputKind, given: dict[str, U]) -> list[tuple[BlockInput, U]]:
        wanted = [x for x in self.inputs if x.kind == kind]

        if len(wanted) == 0 and len(given) > 0:
            raise ProgramParseException(f"no {kind} allowed ({given} given)")

        wanted_keys = [x.name for x in wanted]
        missing = set(wanted_keys).difference(given.keys())
        extra = set(given.keys()).difference(wanted_keys)
        if len(missing) > 0:
            raise ProgramParseException(f"missing {kind}: {missing}")
        if len(extra) > 0:
            raise ProgramParseException(f"extra {kind}: {extra}")

        return [(input, given[input.name]) for input in wanted]

    def __init__(self, mutation: dict[str, str | int],
                 fields: dict[str, Field], values: dict[str, Self],
                 statements: dict[str, Self], next: Self | None) -> None:

        wanted_fields = self._get_inputs(BlockInputKind.FIELD, fields)
        for input, field in wanted_fields:
            if input.attr is not None:
                setattr(self, input.attr, field)
            field.check_type(input.data_type)

        wanted_values = self._get_inputs(BlockInputKind.VALUE, values)
        for input, val in wanted_values:
            if input.attr is not None:
                setattr(self, input.attr, val)
            if input.data_type == Any:
                continue
            if val.returns == Any:
                val._set_return_type(input.data_type)
            if val.returns != input.data_type:
                raise ProgramParseException(f"value {input.name}: return {val.returns} but {input.data_type} expected")

        wanted_statements = self._get_inputs(BlockInputKind.STATEMENT, statements)
        for input, st in wanted_statements:
            if input.attr is not None:
                setattr(self, input.attr, st)
            if st.returns is not None:
                raise ProgramParseException(f"statement {input.name}: should not return value (returns {st.returns})")

        if self.has_next:
            self.next = next
        elif next is not None:
            raise ProgramParseException(f"Block {self.name}: next not supported")


class Nop(Block):
    name = "nop"

    def execute(self, run: Run) -> Action:
        return Action(ActionType.NOP)


class IdxParam(Block):
    name = "idx_param"
    messages = ["Index"]
    returns = int
    color = 300
    tooltip = "Index kovboje"

    def execute(self, run: Run) -> int:
        run.add_steps(1)
        # FIXME: add real id
        return 0


class VariablesGet(Block):
    name = "variables_get"
    inputs = [
        BlockInput(BlockInputKind.FIELD, "var", "VAR", variable=True),
    ]
    returns = Any
    is_blockly_default = True

    var: VariableField

    def _set_return_type(self, return_type: type):
        self.var.check_type(return_type)
        self.returns = return_type

    def execute(self, run: Run) -> int:
        run.add_steps(1)
        return self.var.execute(run)


class VariablesSet(Block):
    name = "variables_set"
    inputs = [
        BlockInput(BlockInputKind.FIELD, "var", "VAR", variable=True),
        BlockInput(BlockInputKind.VALUE, "value", "VALUE"),
    ]
    is_blockly_default = True
    has_next = True

    var: VariableField
    value: Block

    def __init__(self, mutation: dict[str, str | int],
                 fields: dict[str, Field], values: dict[str, Block],
                 statements: dict[str, Block], next: Block | None) -> None:

        super().__init__(mutation, fields, values, statements, next)
        if self.value.returns != Any:
            self.var.check_type(self.value.returns)

    def execute(self, run: Run) -> Action | None:
        run.add_steps(1)
        run.variables[self.var.name] = self.value.execute(run)
        return super().execute(run)


class MathChange(Block):
    name = "math_change"
    inputs = [
        BlockInput(BlockInputKind.FIELD, "var", "VAR", int, variable=True),
        BlockInput(BlockInputKind.VALUE, "delta", "DELTA", int),
    ]
    is_blockly_default = True
    has_next = True

    var: VariableField
    delta: Block

    def __init__(self, mutation: dict[str, str | int],
                 fields: dict[str, Field], values: dict[str, Block],
                 statements: dict[str, Block], next: Block | None) -> None:

        super().__init__(mutation, fields, values, statements, next)
        if self.delta.returns != Any:
            self.var.check_type(self.delta.returns)

    def execute(self, run: Run) -> Action | None:
        run.add_steps(1)
        run.variables[self.var.name] += self.delta.execute(run)
        return super().execute(run)


class LogicBoolean(Block):
    name = "logic_boolean"
    inputs = [
        BlockInput(BlockInputKind.FIELD, "field", "BOOL", bool),
    ]
    is_blockly_default = True
    returns = bool

    field: Field

    def execute(self, run: Run) -> bool:
        run.add_steps(1)
        return self.field.execute(run)


class LogicCompare(Block):
    name = "logic_compare"
    inputs = [
        BlockInput(BlockInputKind.FIELD, "op", "OP", str, dropdown=[]),  # TODO: add dropdown
        BlockInput(BlockInputKind.VALUE, "block_A", "A", Any),
        BlockInput(BlockInputKind.VALUE, "block_B", "B", Any),
    ]
    returns = bool
    is_blockly_default = True

    op: Field
    block_A: Block
    block_B: Block

    def execute(self, run: Run) -> bool:
        run.add_steps(1)
        op = self.op.execute(run)
        # A and B could be any comparable type:
        A = self.block_A.execute(run)
        B = self.block_B.execute(run)
        if op == "EQ":
            return A == B
        elif op == "NEQ":
            return A != B
        elif op == "LT":
            return A < B  # type: ignore
        elif op == "LTE":
            return A <= B  # type: ignore
        elif op == "GT":
            return A > B  # type: ignore
        elif op == "GTE":
            return A >= B  # type: ignore
        return False  # should not happen


class LogicOperation(Block):
    name = "logic_operation"
    inputs = [
        BlockInput(BlockInputKind.FIELD, "op", "OP", str, dropdown=[]),  # TODO: add dropdown
        BlockInput(BlockInputKind.VALUE, "block_A", "A", bool),
        BlockInput(BlockInputKind.VALUE, "block_B", "B", bool),
    ]
    returns = bool
    is_blockly_default = True

    op: Field
    block_A: Block
    block_B: Block

    def execute(self, run: Run) -> bool:
        run.add_steps(1)
        op = self.op.execute(run)
        A: bool = self.block_A.execute(run)
        B: bool = self.block_B.execute(run)
        if op == "AND":
            return A and B
        elif op == "OR":
            return A or B
        return False  # should not happen


class LogicNegate(Block):
    name = "logic_negate"
    inputs = [
        BlockInput(BlockInputKind.VALUE, "bool_child", "BOOL", bool),
    ]
    returns = bool
    is_blockly_default = True

    bool_child: Block

    def execute(self, run: Run) -> bool:
        run.add_steps(1)
        return not self.bool_child.execute(run)


class MathNumber(Block):
    name = "math_number"
    inputs = [
        BlockInput(BlockInputKind.FIELD, "field", "NUM", int),
    ]
    returns = int
    is_blockly_default = True

    field: Field

    def execute(self, run: Run) -> int:
        run.add_steps(1)
        return self.field.execute(run)


class MathArithmetic(Block):
    name = "math_arithmetic"
    inputs = [
        BlockInput(BlockInputKind.FIELD, "op", "OP", str, dropdown=[]),  # TODO: add dropdown
        BlockInput(BlockInputKind.VALUE, "block_A", "A", int),
        BlockInput(BlockInputKind.VALUE, "block_B", "B", int),
    ]
    returns = int
    is_blockly_default = True

    op: Field
    block_A: Block
    block_B: Block

    def execute(self, run: Run) -> int:
        run.add_steps(1)
        op = self.op.execute(run)
        A: int = self.block_A.execute(run)
        B: int = self.block_B.execute(run)
        if op == "ADD":
            return A + B
        elif op == "MINUS":
            return A - B
        elif op == "MULTIPLY":
            return A * B
        elif op == "DIVIDE":
            return A / B
        elif op == "POWER":
            return A ** B
        return 0  # should not happen


class MoveDirection(Block):
    name = "move_direction"
    messages = ["Move %1"]
    inputs = [
        BlockInput(BlockInputKind.FIELD, "direction", "DIRECTION", str, dropdown=[
            ("←", "LEFT"), ("↑", "UP"), ("→", "RIGHT"), ("↓", "DOWN"),
        ]),
    ]
    has_prev = True
    color = 120
    tooltip = "Přesune kovboje v daném směru a ukončí tah"

    direction: Field

    def execute(self, run: Run) -> Action:
        run.add_steps(1)
        direction = self.direction.execute(run)
        if direction == "UP":
            return Action(ActionType.MOVE, Direction.N)
        elif direction == "RIGHT":
            return Action(ActionType.MOVE, Direction.E)
        elif direction == "DOWN":
            return Action(ActionType.MOVE, Direction.S)
        elif direction == "LEFT":
            return Action(ActionType.MOVE, Direction.W)
        return Action(ActionType.NOP)  # should not happen


class ControlsRepeatExt(Block):
    name = "controls_repeat_ext"
    inputs = [
        BlockInput(BlockInputKind.VALUE, "times", "TIMES", int),
        BlockInput(BlockInputKind.STATEMENT, "do", "DO"),
    ]
    is_blockly_default = True
    has_prev = True
    has_next = True

    times: Block
    do: Block

    def execute(self, run: Run) -> Action | None:
        times = self.times.execute(run)
        for i in range(times):
            run.add_steps(1)
            ret = self.do.execute(run)
            if ret is not None:
                return ret

        return super().execute(run)


class ControlsIf(Block):
    name = "controls_if"
    is_blockly_default = True
    has_prev = True
    has_next = True

    conditions: list[tuple[Block, Block]]
    do_else: Block | None

    def __init__(self, mutation: dict[str, str | int],
                 fields: dict[str, Field], values: dict[str, Block],
                 statements: dict[str, Block], next: Block | None) -> None:

        c_elseif = int(mutation.get('elseif', 0))
        c_else = int(mutation.get('else', 0))
        if c_elseif < 0 or c_else not in (0, 1):
            raise ProgramParseException(f"Block {self.name}: Invalid mutation {mutation}")

        self.inputs = []
        for i in range(c_elseif + 1):
            self.inputs.append(BlockInput(BlockInputKind.VALUE, None, f"IF{i}", bool))
            self.inputs.append(BlockInput(BlockInputKind.STATEMENT, None, f"DO{i}"))
        if c_else:
            self.inputs.append(BlockInput(BlockInputKind.STATEMENT, None, "ELSE"))

        super().__init__(mutation, fields, values, statements, next)

        self.conditions = []
        for i in range(c_elseif + 1):
            self.conditions.append((values[f"IF{i}"], statements[f"DO{i}"]))

        self.do_else = c_else and statements["ELSE"] or None

        self.next = next

    def execute(self, run: Run) -> Action | None:
        run.add_steps(1)
        found = False
        ret = None
        for (condition, do) in self.conditions:
            if condition.execute(run) is True:
                found = True
                ret = do.execute(run)

        if not found and self.do_else is not None:
            ret = do.execute(run)

        if ret is not None:
            return ret

        return super().execute(run)


################################################################################

cowboy_blocks: list[tuple[str, dict[str, str] | None, list[Type[Block]]]] = [
    ("Cykly a logika", None, [
        ControlsRepeatExt,
        ControlsIf,
        LogicCompare,
        LogicOperation,
        LogicNegate,
    ]),
    ("Konstanty a matematika", None, [
        IdxParam,
        LogicBoolean,
        MathNumber,
        MathArithmetic,
        # MathModulo, # TODO: maybe custom MathArithmetic with modulo?
    ]),
    ("Akce", None, [
        MoveDirection,
    ]),
    ("Proměnné", {"custom": "VARIABLE"}, [
        VariablesGet,
        VariablesSet,
        MathChange,
    ]),
]

cowboy_factories: dict[str, Type[Block]] = {
    block.name: block for category in cowboy_blocks for block in category[2]
}

bullet_blocks: list[tuple[str, dict[str, str] | None, list[Type[Block]]]] = [
    ("Cykly a logika", None, [
        ControlsRepeatExt,
        ControlsIf,
        LogicCompare,
        LogicOperation,
        LogicNegate,
    ]),
    ("Konstanty a matematika", None, [
        IdxParam,
        LogicBoolean,
        MathNumber,
        MathArithmetic,
        # MathModulo, # TODO: maybe custom MathArithmetic with modulo?
    ]),
    ("Akce", None, [
    ]),
    ("Proměnné", {"custom": "VARIABLE"}, [
        VariablesGet,
        VariablesSet,
        MathChange,
    ]),
]

bullet_factories: dict[str, Type[Block]] = {
    block.name: block for category in bullet_blocks for block in category[2]
}
