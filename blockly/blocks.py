from __future__ import annotations
from abc import abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Type, TypeAlias, TypeVar, TYPE_CHECKING, cast

from .actions import Action, ActionType, all_directions, cowboy_directions, bullet_directions
from .exceptions import OutOfStepsException, ProgramParseException

# Brake circular dependency only used for type checking
if TYPE_CHECKING:
    from .map import GameMap, Cowboy, Bullet

Position = tuple[int, int]


class Run:
    max_steps: int
    steps: int
    variables: dict[str, int | bool | Position]
    map: GameMap
    context: Cowboy | Bullet

    def __init__(self, max_steps: int, variables: dict[str, int | bool | Position],
                 map: GameMap, context: Cowboy | Bullet) -> None:
        self.max_steps = max_steps
        self.steps = 0
        self.variables = variables
        self.map = map
        self.context = context

    def add_steps(self, steps: int):
        self.steps += steps
        if self.steps > self.max_steps:
            raise OutOfStepsException()


################################################################################

class Field:
    is_variable: bool = False

    name: str

    @abstractmethod
    def execute(self, run: Run) -> bool | int | str | Position:
        pass

    def check_type(self, wanted: type) -> None:
        pass


class VariableField(Field):
    is_variable = True
    var_type: type | Any

    def __init__(self, name: str) -> None:
        self.name = name
        self.var_type = Any

    def __str__(self) -> str:
        return f"variable {self.name}"

    def check_type(self, wanted: type) -> None:
        # Variable could be any type, will be checked after parsing the whole program
        self.var_type = wanted

    def execute(self, run: Run) -> bool | int | Position:
        return run.variables[self.name]


class StaticField(Field):
    # Cannot be Position
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

    def execute(self, run: Run) -> bool | int | str:
        return self.value


################################################################################

type_to_js_type: dict[type | TypeAlias, str] = {
    bool: "Boolean",
    int: "Number",
    str: "String",
    Position: "Position",
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
    attr: str | None  # name of the object attribute to save into
    name: str
    data_type: type | Any = Any
    dropdown: list[tuple[str, str]] | None = None
    variable: bool = False
    arg_group: int = 0  # for grouping block inputs in graphical blocks

    def json_definition(self) -> dict:
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
        out: dict = {
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
    inputs_inline: bool = True
    messages: list[str] = []  # texts displayed in graphical blocks
    returns: None | type | TypeAlias = None  # if itself returns something (bool / int)
    has_prev: bool = False  # could run after another block
    has_next: bool = False  # another block could run after this one

    # Instance variables:
    next: Block | None

    def __str__(self) -> str:
        return f"block '{self.name}'"

    @classmethod
    def json_definition(cls) -> dict:
        out: dict = {
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
        if cls.inputs_inline:
            out["inputsInline"] = True

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

    def execute(self, run: Run) -> Action | Position | bool | int | None:
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

    def __init__(self, mutation: dict[str, str],
                 fields: dict[str, Field], values: dict[str, Block],
                 statements: dict[str, Block], next: Block | None) -> None:

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
    messages = ["Stát"]
    has_prev = True
    color = 120
    tooltip = "Nedělat nic"

    def execute(self, run: Run) -> Action:
        return Action(ActionType.NOP)


class InfoTeam(Block):
    name = "info_team"
    messages = ["Můj tým"]
    returns = int
    color = 340
    tooltip = "Index mého týmu (int)"

    def execute(self, run: Run) -> int:
        run.add_steps(1)
        return run.context.team


class InfoPoints(Block):
    name = "info_points"
    messages = ["Počet bodů"]
    returns = int
    color = 340
    tooltip = "Počet bodů mého týmu (int)"

    def execute(self, run: Run) -> int:
        run.add_steps(1)
        return run.map.my_points(run.context)


class InfoIndex(Block):
    name = "info_index"
    messages = ["Můj index"]
    returns = int
    color = 340
    tooltip = "Moje pořadové číslo v týmu (stejné po celou hru)"

    def execute(self, run: Run) -> int:
        run.add_steps(1)
        return run.context.index


class InfoID(Block):
    name = "info_id"
    messages = ["Moje ID"]
    returns = int
    color = 300
    tooltip = "Moje ID v seznamu všech entit, mění se každé kolo"

    def execute(self, run: Run) -> int:
        run.add_steps(1)
        return run.map.my_id(run.context)


class InfoMyDirection(Block):
    name = "info_my_direction"
    messages = ["Můj směr"]
    returns = int
    color = 300
    tooltip = "Vrátí aktuální směr střely jako číslo (0 je ←, pořadí: ←,↖,↑,↗,→,↘,↓,↙)"

    def execute(self, run: Run) -> int:
        run.add_steps(1)
        assert isinstance(run.context, Bullet)
        return run.context.direction


class InfoMyRange(Block):
    name = "info_my_range"
    messages = ["Zbývá kroků"]
    returns = int
    color = 300
    tooltip = "Vrátí kolik střele zbývá kroků"

    def execute(self, run: Run) -> int:
        run.add_steps(1)
        assert isinstance(run.context, Bullet)
        return run.map.BULLET_LIFETIME - run.context.turns_made


class InfoTurn(Block):
    name = "info_turn"
    messages = ["Číslo kola"]
    returns = int
    color = 300
    tooltip = "Vrací číslo aktuálního kola"

    def execute(self, run: Run) -> int:
        run.add_steps(1)
        return run.map.turn_idx


class InfoMyPosition(Block):
    name = "info_position"
    messages = ["Moje pozice"]
    returns = Position
    color = 300
    tooltip = "Vrátí moji současnou pozici (X, Y)"

    def execute(self, run: Run) -> Position:
        run.add_steps(1)
        return run.map.my_position(run.context)


# Generic query:

class InfoMapPosition(Block):
    name = "info_map_position"
    messages = ["Je na %1 %2?"]
    inputs = [
        BlockInput(BlockInputKind.VALUE, "position", "POSITION", Position),
        BlockInput(BlockInputKind.FIELD, "entity", "ENTITY", str, dropdown=[
            ("Zeď", "WALL"), ("Zlato", "GOLD"),
            ("Kovboj", "COWBOY"), ("Střela", "BULLET"),
        ]),
    ]
    returns = bool
    color = 300
    tooltip = "Ověří, jestli je na daných souřadnicích zeď, zlato, kovboj nebo střela."

    position: Block
    entity: Field

    def execute(self, run: Run) -> int:
        run.add_steps(1)
        pos = cast(Position, self.position.execute(run))
        (c, r) = pos
        entity = self.entity.execute(run)
        if entity == "WALL":
            return run.map.wall_grid[r][c]
        elif entity == "GOLD":
            return run.map.gold_grid[r][c] is not None
        elif entity == "COWBOY":
            return run.map.cowboy_grid[r][c] is not None
        elif entity == "BULLET":
            return run.map.bullet_grid[r][c] is not None
        return False  # should not happen


# Golds:

class InfoGoldCount(Block):
    name = "info_gold_count"
    messages = ["# zlata"]
    returns = int
    color = 340
    tooltip = "Vrátí počet zlata na hracím plánu"

    def execute(self, run: Run) -> int:
        run.add_steps(1)
        return run.map.number_of_golds()


class InfoGoldPosition(Block):
    name = "info_gold_position"
    messages = ["Pozice zlata %1"]
    inputs = [
        BlockInput(BlockInputKind.VALUE, "gold_block", "GOLD", int),
    ]
    returns = Position
    color = 340
    tooltip = "Vrátí souřadnice (X, Y) zlata s daným ID"

    gold_block: Block

    def execute(self, run: Run) -> Position:
        run.add_steps(1)
        gold = self.gold_block.execute(run)
        assert isinstance(gold, int)
        return run.map.gold_i_position(gold)


# Cowboys:

class InfoCowboyCount(Block):
    name = "info_cowboy_count"
    messages = ["# kovbojů"]
    returns = int
    color = 340
    tooltip = "Vrátí počet kovbojů na hracím plánu"

    def execute(self, run: Run) -> int:
        run.add_steps(1)
        return run.map.number_of_cowboys()


class InfoCowboyTeam(Block):
    name = "info_cowboy_team"
    messages = ["Tým kovboje %1"]
    inputs = [
        BlockInput(BlockInputKind.VALUE, "cowboy_block", "COWBOY", int),
    ]
    returns = int
    color = 340
    tooltip = "Vrátí index týmu kovboje s daným ID"

    cowboy_block: Block

    def execute(self, run: Run) -> int:
        run.add_steps(1)
        cowboy = self.cowboy_block.execute(run)
        assert isinstance(cowboy, int)
        return run.map.cowboy_i_team(cowboy)


class InfoCowboyPosition(Block):
    name = "info_cowboy_position"
    messages = ["Pozice kovboje %1"]
    inputs = [
        BlockInput(BlockInputKind.VALUE, "cowboy_block", "COWBOY", int),
    ]
    returns = Position
    color = 340
    tooltip = "Vrátí souřadnice (X, Y) kovboje s daným ID"

    cowboy_block: Block

    def execute(self, run: Run) -> Position:
        run.add_steps(1)
        cowboy = self.cowboy_block.execute(run)
        assert isinstance(cowboy, int)
        return run.map.cowboy_i_position(cowboy)


# Bullets:

class InfoBulletCount(Block):
    name = "info_bullet_count"
    messages = ["# střel"]
    returns = int
    color = 340
    tooltip = "Vrátí počet střel na hracím plánu"

    def execute(self, run: Run) -> int:
        run.add_steps(1)
        return run.map.number_of_bullets()


class InfoBulletTeam(Block):
    name = "info_bullet_team"
    messages = ["Tým střely %1"]
    inputs = [
        BlockInput(BlockInputKind.VALUE, "bullet_block", "BULLET", int),
    ]
    returns = int
    color = 340
    tooltip = "Vrátí index týmu střely s daným ID"

    bullet_block: Block

    def execute(self, run: Run) -> int:
        run.add_steps(1)
        bullet = self.bullet_block.execute(run)
        assert isinstance(bullet, int)
        return run.map.bullet_i_team(bullet)


class InfoBulletPosition(Block):
    name = "info_bullet_position"
    messages = ["Pozice střely %1"]
    inputs = [
        BlockInput(BlockInputKind.VALUE, "bullet_block", "BULLET", int),
    ]
    returns = Position
    color = 340
    tooltip = "Vrátí souřadnice (X, Y) střely s daným ID"

    bullet_block: Block

    def execute(self, run: Run) -> Position:
        run.add_steps(1)
        bullet = self.bullet_block.execute(run)
        assert isinstance(bullet, int)
        return run.map.bullet_i_position(bullet)


# Position transformations:

class ModifyPosition(Block):
    name = "modify_position"
    messages = ["posuň %1 o %2"]
    inputs = [
        BlockInput(BlockInputKind.VALUE, "position", "POSITION", Position),
        BlockInput(BlockInputKind.VALUE, "direction", "DIRECTION", int),
    ]
    returns = Position
    color = 30
    tooltip = "Posune souřadnice o jedno políčko daným směrem (směr bere jako číslo modulo 8, ← je 0)"

    position: Block
    direction: Block

    def execute(self, run: Run) -> Position:
        run.add_steps(1)
        pos = cast(Position, self.position.execute(run))
        dir = self.direction.execute(run)
        assert type(dir) is int
        (dx, dy) = all_directions[dir % 8].value
        (x, y) = pos
        x = (x + dx) % run.map.width
        y = (y + dy) % run.map.height
        return (x, y)


class TransformPositionX(Block):
    name = "transform_position_x"
    messages = ["%1→X"]
    inputs = [
        BlockInput(BlockInputKind.VALUE, "block_position", "POSITION", Position),
    ]
    returns = int
    color = 30
    tooltip = "Vrátí X souřadnici z (X, Y)"

    block_position: Block

    def execute(self, run: Run) -> int:
        run.add_steps(1)
        pos = cast(Position, self.block_position.execute(run))
        return pos[0]


class TransformPositionY(Block):
    name = "transform_position_y"
    messages = ["%1→Y"]
    inputs = [
        BlockInput(BlockInputKind.VALUE, "block_position", "POSITION", Position),
    ]
    returns = int
    color = 30
    tooltip = "Vrátí Y souřadnici z (X, Y)"

    block_position: Block

    def execute(self, run: Run) -> int:
        run.add_steps(1)
        pos = cast(Position, self.block_position.execute(run))
        return pos[1]


class TransformXYPosition(Block):
    name = "transform_x_y_position"
    messages = ["(%1:%2)"]
    inputs = [
        BlockInput(BlockInputKind.VALUE, "block_x", "X", int),
        BlockInput(BlockInputKind.VALUE, "block_y", "Y", int),
    ]
    returns = Position
    color = 30
    tooltip = "Vytvoří (X, Y) souřadnice z X a Y"

    block_x: Block
    block_y: Block

    def execute(self, run: Run) -> Position:
        run.add_steps(1)
        x = self.block_x.execute(run)
        y = self.block_y.execute(run)
        assert isinstance(x, int) and isinstance(y, int)
        return (x, y)


class CountDistance(Block):
    name = "count_distance"
    messages = ["Přímá vzdálenost k %1"]
    inputs = [
        BlockInput(BlockInputKind.VALUE, "block_position", "POSITION", Position),
    ]
    returns = int
    color = 30
    tooltip = "Vrátí přímou vzdálenost k zadaným souřadnicím (při pohybu osmi směry)"

    block_position: Block

    def execute(self, run: Run) -> int:
        run.add_steps(1)
        pos = cast(Position, self.block_position.execute(run))
        assert run.context.position is not None
        return run.map.maximum_metric(run.context.position, pos)


class GetDirection(Block):
    name = "compute_direction"
    messages = ["Směr k %1"]
    inputs = [
        BlockInput(BlockInputKind.VALUE, "pos", "POSITION", Position),
    ]
    returns = int
    color = 30
    tooltip = "Vrátí nejlepší směr (z množiny [←,↖,↑,↗,→,↘,↓,↙]) k zadaným souřadnicím. Vrací číslo, ← je 0. Výpočet je bez ohledu na zdi."

    pos: Block

    def execute(self, run: Run) -> int:
        pos = cast(Position, self.pos.execute(run))
        run.add_steps(1)
        assert run.context.position is not None

        x, y = run.context.position
        tx, ty = pos
        dx, dy = (tx - x, ty - y)

        # Wrap over the edge of the map
        if dx > run.map.width/2:
            dx -= run.map.width
        elif dx < -run.map.width/2:
            dx += run.map.width

        if dy > run.map.height/2:
            dy -= run.map.height
        elif dy < -run.map.height/2:
            dy += run.map.height

        out_x, out_y = 0, 0
        # if difference in one axis is more than twice the difference in the
        # other axis -> move only in one axis
        if abs(dy) <= 2*abs(dx):
            out_x = 1 if dx > 0 else -1
        if abs(dx) <= 2*abs(dy):
            out_y = 1 if dy > 0 else -1
        direction = (out_x, out_y)

        for i, d in enumerate(bullet_directions):
            if d.value == direction:
                return i

        print(f"ERROR in ComputeDirection: {direction} not found")
        return -1  # Should not happen


# Computations:

class ComputeDistance(Block):
    name = "compute_distance"
    messages = ["Počet kroků k %1"]
    inputs = [
        BlockInput(BlockInputKind.VALUE, "pos", "POSITION", Position),
    ]
    returns = int
    color = 300
    tooltip = "Vrátí počet kroků kovboje od současné pozice k bodu X:Y (s uvažováním překážek ale bez kovbojů)"

    pos: Block

    def execute(self, run: Run) -> int:
        pos = cast(Position, self.pos.execute(run))
        run.add_steps(1)
        assert isinstance(run.context, Cowboy)
        return run.map.distance_from(run.context, pos)


class ComputeFirstStep(Block):
    name = "compute_first_step"
    messages = ["První krok k %1"]
    inputs = [
        BlockInput(BlockInputKind.VALUE, "pos", "POSITION", Position),
    ]
    returns = int
    color = 300
    # FIXME: indexování kroků?
    tooltip = ("Vrátí index (číslo 0, 2, 4 nebo 6) prvního kroku nejkratší cesty "
               "pro kovboje od současné pozice k bodu X:Y (s uvažováním překážek ale bez kovbojů). ")

    pos: Block

    def execute(self, run: Run) -> int:
        pos = cast(Position, self.pos.execute(run))
        run.add_steps(1)
        assert isinstance(run.context, Cowboy)
        direction = run.map.which_way(run.context, pos)
        for i, d in enumerate(all_directions):
            if d.value == direction:
                return i
        return -1


# Variables:

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

    def execute(self, run: Run) -> bool | int | Position:
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

    def __init__(self, mutation: dict[str, str],
                 fields: dict[str, Field], values: dict[str, Block],
                 statements: dict[str, Block], next: Block | None) -> None:

        super().__init__(mutation, fields, values, statements, next)
        if self.value.returns and self.value.returns != Any:
            self.var.check_type(self.value.returns)

    def execute(self, run: Run) -> Action | Position | int | None:
        run.add_steps(1)
        ret = self.value.execute(run)
        assert ret is not None and not isinstance(ret, Action)
        run.variables[self.var.name] = ret
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

    def __init__(self, mutation: dict[str, str],
                 fields: dict[str, Field], values: dict[str, Block],
                 statements: dict[str, Block], next: Block | None) -> None:

        super().__init__(mutation, fields, values, statements, next)
        if self.delta.returns and self.delta.returns != Any:
            self.var.check_type(self.delta.returns)

    def execute(self, run: Run) -> Action | Position | int | None:
        run.add_steps(1)
        delta = self.delta.execute(run)
        assert isinstance(delta, int)
        run.variables[self.var.name] += delta  # type: ignore
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
        ret = self.field.execute(run)
        assert isinstance(ret, bool)
        return ret


class ConstantDirection(Block):
    name = "constant_direction"
    messages = ["%1"]
    inputs = [
        BlockInput(BlockInputKind.FIELD, "direction", "DIRECTION", str, dropdown=[
            ("←", "0"), ("↖", "1"), ("↑", "2"), ("↗", "3"),
            ("→", "4"), ("↘", "5"), ("↓", "6"), ("↙", "7"),
        ]),
    ]
    returns = int
    color = 220
    tooltip = "Směr jako číslo (← je 0 a pak po směru hodinových ručiček)"

    direction: Field

    def execute(self, run: Run) -> int:
        run.add_steps(1)
        ret = self.direction.execute(run)
        assert isinstance(ret, int)
        return ret


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
        A = self.block_A.execute(run)
        B = self.block_B.execute(run)
        assert isinstance(A, bool) and isinstance(B, bool)
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
        ret = self.field.execute(run)
        assert isinstance(ret, int)
        return ret


class MathAbs(Block):
    name = "math_abs"
    messages = ["abs %1"]
    inputs = [
        BlockInput(BlockInputKind.VALUE, "number", "NUM", int),
    ]
    returns = int
    color = 220
    tooltip = "Absolutní hodnota čísla"

    number: Field

    def execute(self, run: Run) -> int:
        run.add_steps(1)
        ret = self.number.execute(run)
        assert isinstance(ret, int)
        return abs(ret)


class MathArithmeticCustom(Block):
    name = "math_arithmetic_custom"
    messages = ["%2%1%3"]
    inputs = [
        BlockInput(BlockInputKind.FIELD, "op", "OP", str, dropdown=[
            ("+", "ADD"), ("-", "MINUS"), ("×", "MULTIPLY"), ("/", "DIVIDE"),
            ("^", "POWER"), ("%", "MODULO"),
        ]),
        BlockInput(BlockInputKind.VALUE, "block_A", "A", int),
        BlockInput(BlockInputKind.VALUE, "block_B", "B", int),
    ]
    returns = int
    color = 220
    tooltip = ("Provede aritmetickou operaci (+ součet, - rozdíl, × násobení, "
               "/ celočíselné dělení, ^ umocňování, % zbytek po dělení)")
    # is_blockly_default = True

    op: Field
    block_A: Block
    block_B: Block

    def execute(self, run: Run) -> int:
        run.add_steps(1)
        op = self.op.execute(run)
        A = self.block_A.execute(run)
        B = self.block_B.execute(run)
        assert isinstance(A, int) and isinstance(B, int)
        if op == "ADD":
            return A + B
        elif op == "MINUS":
            return A - B
        elif op == "MULTIPLY":
            return A * B
        elif op == "DIVIDE":
            return A // B
        elif op == "POWER":
            return A ** B
        elif op == "MODULO":
            return A % B
        return 0  # should not happen


class MoveDirection(Block):
    name = "move_direction"
    messages = ["Move %1"]
    inputs = [
        BlockInput(BlockInputKind.FIELD, "direction", "DIRECTION", str, dropdown=[
            ("←", "W"), ("↑", "N"), ("→", "E"), ("↓", "S"),
        ]),
    ]
    has_prev = True
    color = 120
    tooltip = "Přesune kovboje v daném směru a ukončí tah"

    direction: Field

    def execute(self, run: Run) -> Action:
        run.add_steps(1)
        direction = self.direction.execute(run)
        for d in cowboy_directions:
            if d.name == direction:
                return Action(ActionType.MOVE, d)
        return Action(ActionType.NOP)  # should not happen


class BulletFly(Block):
    name = "bullet_fly"
    messages = ["Rovně"]
    has_prev = True
    color = 120
    tooltip = "Střela nic nedělá, jen si tak letí"

    def execute(self, run: Run) -> Action:
        return Action(ActionType.NOP)


class BulletLeft(Block):
    name = "bullet_left"
    messages = ["Doleva"]
    has_prev = True
    color = 120
    tooltip = "Střela zatočí o 45° doleva"

    def execute(self, run: Run) -> Action:
        return Action(ActionType.BULLET_TURN_L)


class BulletRight(Block):
    name = "bullet_right"
    messages = ["Doprava"]
    has_prev = True
    color = 120
    tooltip = "Střela zatočí o 45° doprava"

    def execute(self, run: Run) -> Action:
        return Action(ActionType.BULLET_TURN_R)


class FireDirection(Block):
    name = "fire_direction"
    messages = ["Fire %1"]
    inputs = [
        BlockInput(BlockInputKind.FIELD, "direction", "DIRECTION", str, dropdown=[
            ("←", "W"), ("↖", "NW"), ("↑", "N"), ("↗", "NE"),
            ("→", "E"), ("↘", "SE"), ("↓", "S"), ("↙", "SW"),
        ]),
    ]
    has_prev = True
    color = 120
    tooltip = "Vypálí střelu v daném směru a ukončí tah"

    direction: Field

    def execute(self, run: Run) -> Action:
        run.add_steps(1)
        direction = self.direction.execute(run)
        for d in bullet_directions:
            if d.name == direction:
                return Action(ActionType.FIRE, d)
        return Action(ActionType.NOP)  # should not happen


class MoveDirectionByNumber(Block):
    name = "move_direction_number"
    messages = ["Move %1"]
    inputs = [
        BlockInput(BlockInputKind.VALUE, "direction", "DIRECTION", int),
    ]
    has_prev = True
    color = 120
    tooltip = ("Přesune kovboje ve směru [←,↑,→,↓] podle zadaného čísla "
               "(počítáno modulo osmi, 0 a 1 je ←, 2 a 3 je ↑, 4 a 5 je →, 6 a 7 je ↓)")

    direction: Block

    def execute(self, run: Run) -> Action:
        run.add_steps(1)
        i = self.direction.execute(run)
        assert isinstance(i, int)
        if i < 0:
            return Action(ActionType.NOP)
        direction = cowboy_directions[(i % 8) // 2]
        return Action(ActionType.MOVE, direction)


class FireDirectionByNumber(Block):
    name = "fire_direction_by_number"
    messages = ["Fire %1"]
    inputs = [
        BlockInput(BlockInputKind.VALUE, "direction", "DIRECTION", int),
    ]
    has_prev = True
    color = 120
    tooltip = "Vypálí střelu ve směru [←,↖,↑,↗,→,↘,↓,↙] podle zadaného čísla (← je 0, počítá se modulo 8)"

    direction: Field

    def execute(self, run: Run) -> Action:
        run.add_steps(1)
        i = self.direction.execute(run)
        assert isinstance(i, int)
        if i < 0:
            return Action(ActionType.NOP)
        direction = bullet_directions[i % 8]
        return Action(ActionType.FIRE, direction)


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

    def execute(self, run: Run) -> Action | Position | int | None:
        times = self.times.execute(run)
        assert isinstance(times, int)
        for i in range(times):
            run.add_steps(1)
            ret = self.do.execute(run)
            if ret is not None:
                return ret

        return super().execute(run)


class ControlsFor(Block):
    name = "controls_for"
    inputs = [
        BlockInput(BlockInputKind.FIELD, "var", "VAR", int, variable=True),
        BlockInput(BlockInputKind.VALUE, "block_from", "FROM", int),
        BlockInput(BlockInputKind.VALUE, "block_to", "TO", int),
        BlockInput(BlockInputKind.VALUE, "block_by", "BY", int),
        BlockInput(BlockInputKind.STATEMENT, "do", "DO"),
    ]
    is_blockly_default = True
    has_prev = True
    has_next = True

    var: VariableField
    block_from: Block
    block_to: Block
    block_by: Block
    do: Block

    def execute(self, run: Run) -> Action | Position | int | None:
        start = self.block_from.execute(run)
        to = self.block_to.execute(run)
        by = self.block_by.execute(run)
        assert isinstance(start, int) and isinstance(to, int) and isinstance(by, int)
        if by == 0:
            return None

        for i in range(start, to, by):
            run.add_steps(1)
            run.variables[self.var.name] = i
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

    def __init__(self, mutation: dict[str, str],
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

    def execute(self, run: Run) -> Action | Position | int | None:
        run.add_steps(1)
        found = False
        ret = None
        for (condition, do) in self.conditions:
            if condition.execute(run) is True:
                found = True
                ret = do.execute(run)
                break

        if not found and self.do_else is not None:
            ret = self.do_else.execute(run)

        if ret is not None:
            return ret

        return super().execute(run)


################################################################################

cowboy_blocks: list[tuple[str, dict[str, str] | None, list[Type[Block]]]] = [
    ("Cykly a logika", None, [
        ControlsRepeatExt,
        ControlsFor,
        ControlsIf,
        LogicCompare,
        LogicOperation,
        LogicNegate,
    ]),
    ("Konstanty a matematika", None, [
        LogicBoolean,
        MathNumber,
        ConstantDirection,
        MathArithmeticCustom,
        MathAbs,
        # MathModulo, # TODO: maybe custom MathArithmetic with modulo?
    ]),
    ("Herní info", None, [
        InfoTeam,
        InfoPoints,
        InfoIndex,
        InfoID,
        InfoMyPosition,
        InfoTurn,

        InfoMapPosition,

        InfoGoldCount,
        InfoGoldPosition,

        InfoCowboyCount,
        InfoCowboyTeam,
        InfoCowboyPosition,

        InfoBulletCount,
        InfoBulletTeam,
        InfoBulletPosition,
    ]),
    ("Souřadnice a transformace", None, [
        ModifyPosition,
        TransformPositionX,
        TransformPositionY,
        TransformXYPosition,
        CountDistance,
        GetDirection
    ]),
    ("Herní výpočty", None, [
        ComputeDistance,
        ComputeFirstStep,
    ]),
    ("Herní akce", None, [
        Nop,
        MoveDirection,
        MoveDirectionByNumber,
        FireDirection,
        FireDirectionByNumber,
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
        ControlsFor,
        ControlsIf,
        LogicCompare,
        LogicOperation,
        LogicNegate,
    ]),
    ("Konstanty a matematika", None, [
        LogicBoolean,
        MathNumber,
        ConstantDirection,
        MathArithmeticCustom,
        MathAbs,
        # MathModulo, # TODO: maybe custom MathArithmetic with modulo?
    ]),
    ("Herní info", None, [
        InfoTeam,
        InfoPoints,
        # InfoIndex, # bullet has no index
        InfoID,
        InfoMyPosition,
        InfoTurn,
        InfoMyDirection,
        InfoMyRange,

        InfoMapPosition,

        # Bullet knows only about cowboys
        InfoCowboyCount,
        InfoCowboyTeam,
        InfoCowboyPosition,

        InfoBulletCount,
        InfoBulletTeam,
        InfoBulletPosition,
    ]),
    ("Souřadnice a transformace", None, [
        ModifyPosition,
        TransformPositionX,
        TransformPositionY,
        TransformXYPosition,
        CountDistance,
        GetDirection
    ]),
    ("Herní akce", None, [
        BulletFly,
        BulletLeft,
        BulletRight,
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
