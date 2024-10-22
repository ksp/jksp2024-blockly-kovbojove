from __future__ import annotations
from typing import TYPE_CHECKING
import traceback

from .actions import Action
from .blocks import Block, Run, Nop, Position
from .exceptions import OutOfStepsException

# Brake circular dependency only used for type checking
if TYPE_CHECKING:
    from .map import GameMap, Cowboy, Bullet



class Program:
    raw_xml: str
    root: Block | None
    variables: dict[str, type] | None

    def __init__(self, root: Block | None, variables: dict[str, type] | None, raw_xml: str) -> None:
        self.root = root
        self.variables = variables
        self.raw_xml = raw_xml

    def valid(self) -> bool:
        return self.root is not None

    # returns (True/False, action/string error, #steps)
    def execute(self, max_steps: int, map: GameMap, context: Cowboy | Bullet) -> tuple[bool, Action | str, int]:
        if self.root is None or self.variables is None:
            return False, "Not executable", 0

        variables: dict[str, bool | int | Position] = {}
        for key, t in self.variables.items():
            if t == bool:
                variables[key] = False
            elif t == int:
                variables[key] = 0
            elif t == Position:
                variables[key] = (0, 0)

        run = Run(max_steps=max_steps, variables=variables, map=map, context=context)

        try:
            result = self.root.execute(run)
            steps = run.steps
            if result is None:
                return False, "No action", steps
            elif type(result) is not Action:
                return False, f"Expected Action, {type(result)} returned", steps
            return True, result, steps
        except OutOfStepsException:
            return False, "Out of steps", run.steps
        except Exception as e:
            traceback.print_tb(e.__traceback__)
            return False, f"Should not happen, exception: {e}", run.steps


nop_program = Program(Nop({}, {}, {}, {}, None), {}, '<xml xmlns="https://developers.google.com/blockly/xml"></xml>')
