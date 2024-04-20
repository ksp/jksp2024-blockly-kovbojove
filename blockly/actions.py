from dataclasses import dataclass
from enum import Enum


class ActionType(Enum):
    NOP = 0
    MOVE = 1
    FIRE = 2
    BULLET_TURN_L = 3
    BULLET_TURN_R = 4


class Direction(Enum):
    N = (0, 1)
    NE = (1, 1)
    E = (1, 0)
    SE = (1, -1)
    S = (0, -1)
    SW = (-1, -1)
    W = (-1, 0)
    NW = (-1, 1)


@dataclass
class Action:
    type: ActionType
    direction: Direction | None = None  # N/E/S/W for MOVE, any for FIRE
