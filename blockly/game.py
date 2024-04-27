from .team import Team
from .map import GameMap


class Game:
    org_login: str
    org_passwd: str
    teams: list[Team]
    teamsMap: dict[str, Team]
    map: GameMap

    def __init__(self, teams: list[Team], map: GameMap, org_login: str, org_passwd: str) -> None:
        self.teams = teams
        self.teamsMap = {team.login: team for team in teams}
        self.map = map
        self.org_login = org_login
        self.org_passwd = org_passwd

    def get_team(self, name: str) -> Team | None:
        return self.teamsMap.get(name)


# global singleton (to be overwritten externally)
G: Game
