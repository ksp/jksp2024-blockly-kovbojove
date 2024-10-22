import json
from simple_websocket import Server  # type: ignore
from threading import Timer, Lock
import time

from .team import Team
from .map import GameMap


class Game:
    org_login: str
    org_passwd: str
    teams: list[Team]
    teamsMap: dict[str, Team]
    map: GameMap

    lock: Lock

    timer: Timer | None = None
    timer_cowboy_turn_period: float
    timer_bullet_turn_period: float
    timer_bullet_turns: int  # how many bullet turns after each cowboy turn

    map_listeners: list[Server]

    def __init__(self, teams: list[Team], map: GameMap, org_login: str, org_passwd: str) -> None:
        self.teams = teams
        self.teamsMap = {team.login: team for team in teams}
        self.map = map
        self.org_login = org_login
        self.org_passwd = org_passwd

        self.timer_cowboy_turn_period = 1
        self.timer_bullet_turn_period = 0.3
        self.timer_bullet_turns = 3

        self.map_listeners = []

        self.lock = Lock()

    def get_team(self, name: str) -> Team | None:
        return self.teamsMap.get(name)

    def start_timer(self, cowboy_turn_period: float,
                    bullet_turn_period: float,
                    bullet_turns: int) -> None:
        self.timer_cowboy_turn_period = cowboy_turn_period
        self.timer_bullet_turn_period = bullet_turn_period
        self.timer_bullet_turns = bullet_turns
        if self.timer is None:
            self.timer = Timer(self.timer_cowboy_turn_period, self._timer_do)
            self.timer.start()

    def stop_timer(self) -> None:
        if self.timer:
            self.timer.cancel()
            self.timer = None

    def _timer_notify_listeners(self) -> None:
        msg = json.dumps({
            "type": "map",
            "data": self.map.get_state(),
        })
        for listener in self.map_listeners:
            listener.send(msg)

    def _timer_do(self) -> None:
        """Compute one cowboy turn and then `timerBulletTurns` bullet turns."""
        cowboy_start = time.time()

        self.lock.acquire()
        self.map.simulate_cowboys_turn()
        self.lock.release()

        self._timer_notify_listeners()

        bullet_start = time.time()
        for i in range(1, self.timer_bullet_turns + 1):
            remaining = max(0, bullet_start + i * self.timer_bullet_turn_period - time.time())
            time.sleep(remaining)

            self.lock.acquire()
            self.map.simulate_bullets_turn()
            self.lock.release()

            self._timer_notify_listeners()

        # Plan timer (only if it wasn't cancelled in meantime)
        self.lock.acquire()
        if self.timer is not None:
            remaining = max(0, cowboy_start + self.timer_cowboy_turn_period - time.time())
            self.timer = Timer(remaining, self._timer_do)
            self.timer.start()
        self.lock.release()

    def ws_connect(self, ws: Server):
        self.map_listeners.append(ws)

    def ws_disconnect(self, ws: Server):
        self.map_listeners.remove(ws)


# global singleton (to be overwritten externally)
G: Game
