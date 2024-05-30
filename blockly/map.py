# from multiprocessing import Pool
# import os
import glob
import json
from random import randrange as rr
from random import shuffle
import queue
from collections import deque
import time
from typing import Any, Callable

from .team import Team
from .actions import Action, ActionType, Direction, all_directions, cowboy_directions, bullet_directions

Coords = tuple[int, int]


class Context:
    # Changes every turn
    team: int
    index: int

    position: Coords | None


class Cowboy(Context):
    def __init__(self, team: int, index: int, position: Coords | None):
        self.team = team
        self.index = index
        # Will be None when the cowboy is shot down and waiting to respawn.
        self.position = position

    def __str__(self) -> str:
        return f"Cowboy(team={self.team},index={self.index},position={self.position})"


class Bullet(Context):
    # `direction` is an index for bullet_directions
    def __init__(self, team: int, position: Coords, direction: int, turns_made: int = 0):
        self.team = team
        self.position = position
        self.direction = direction
        self.turns_made = turns_made

    def __str__(self) -> str:
        return (f"Bullet(team={self.team},position={self.position},"
                + f"direction={self.direction},turns_made={self.turns_made})")


class Gold:
    position: Coords | None


class TeamStats:
    points: int
    golds: int
    fired_bullets: int

    deaths: int
    kills: list[int]
    killed_bullets: int

    def __init__(self, kills_list, points=0, golds=0, fired_bullets=0, deaths=0, killed_bullets=0):
        self.points = points
        self.golds = golds
        self.fired_bullets = fired_bullets
        self.deaths = deaths
        self.kills = kills_list
        self.killed_bullets = killed_bullets


class GameMap:
    save_dir: str
    wall_grid: list[list[bool]]
    cowboy_grid: list[list[Cowboy | None]]
    bullet_grid: list[list[Bullet | None]]
    gold_grid: list[list[Gold | None]]

    team_stats: list[TeamStats]

    gold_list: list[Gold]
    cowboy_list: list[Cowboy]
    bullet_list: list[Bullet]

    cowboy_spawn_deque: deque[tuple[int, Cowboy]]

    # has value only during turn computation
    active_cowboys: list[Cowboy]

    current_explosions: list[Coords]
    current_gun_triggers: list[tuple[int, int, int]]

    # At each cowboy turn, once we compute a cowboy's BFS, we cache
    # the distances.
    cached_distances: dict[Coords, list[list[int]]]

    # Results of actions (not saved into JSON)
    # (list of rounds, for each round a list of teams)
    cowboy_results: list[list[list[str]]]
    bullet_results: list[list[list[str]]]

    a_star_time: float
    bfs_time: float

    # Only counts cowboy turns
    turn_idx: int
    # count bullet turns, reset with each turn_idx increase
    bullet_subturn: int
    # Constants:
    # Points taken for shooting
    BULLET_PRICE = 1
    # Points for reaching a coin.
    GOLD_PRICE = 10
    # Points for shooting down an enemy cowboy.
    SHOTDOWN_BOUNTY = 5
    # No. of turns between a cowboy being shot down and him respawning.
    TURNS_TO_RESPAWN = 5
    # For how many total (bullet) turns does a bullet object exist?
    BULLET_LIFETIME = 9
    # Maximum program lengths:
    COWBOY_MAX_STEPS = 6000
    BULLET_MAX_STEPS = 2000

    all_rounds: list[dict]

    def __init__(
            self,
            width: int,
            height: int,
            teams: list[Team],
            cowboys_per_team: int = 4,
            # The number of golds on the map will be kept constant
            gold_count: int = 5,
            load_saves: bool = False,
            save_dir: str = "save",
            wall_fraction: int = 50,
            cluster_max: int = 5):
        self.width, self.height = width, height
        self.infty = 2 * self.width * self.height
        self.teams = teams
        self.cowboys_per_team = cowboys_per_team
        self.gold_count = gold_count

        self.cached_distances = {}
        self.cowboy_results = []
        self.bullet_results = []

        self.save_dir = save_dir

        save_files = sorted(glob.glob(f"{save_dir}/save_*.json"))
        if load_saves and len(save_files) > 0:
            print(f"Loading previously saved {len(save_files)} rounds")
            self.load_rounds(save_files)
            print(f"Loading game from file '{save_files[-1]}'")
            self.load(self.all_rounds[-1])
            print("Loading completed")
        else:
            print("Initializing a new game")
            self.init_new(wall_fraction, cluster_max)
            self.all_rounds = []
            print("Game initialization done")

    def init_new(self, wall_fraction: int = 50, cluster_max: int = 5):
        self.team_stats = [TeamStats([0 for _ in range(len(self.teams))]) for _ in range(len(self.teams))]

        self.turn_idx = 0
        self.bullet_subturn = 0
        self.cowboy_grid = [[None for _ in range(self.width)] for _ in range(self.height)]
        self.bullet_grid = [[None for _ in range(self.width)] for _ in range(self.height)]
        self.gold_grid = [[None for _ in range(self.width)] for _ in range(self.height)]

        self.cowboy_list = []
        self.gold_list = [Gold() for _ in range(self.gold_count)]
        self.bullet_list = []
        self.current_explosions = []
        self.current_gun_triggers = []
        # Deque keeping track of when dead cowboys should respawn
        self.cowboy_spawn_deque = deque()

        self.generate_walls(wall_fraction, cluster_max)
        self.generate_cowboy_positions()
        self.generate_gold_positions()

    def save_filename(self, turn_idx: int, bullet_subturn: int) -> str:
        return f"{self.save_dir}/save_{turn_idx:06d}_{bullet_subturn}.json"

    def save(self) -> None:
        walls: list[Coords] = []
        for r in range(self.height):
            for c in range(self.width):
                pos = (c, r)
                if self.wall_grid[r][c]:
                    walls.append(pos)

        golds: list[Coords | None] = [gold.position for gold in self.gold_list]
        cowboys: list[dict] = [{
            "team": cowboy.team,
            "index": cowboy.index,
            "position": cowboy.position,
        } for cowboy in self.cowboy_list]
        bullets: list[dict] = [{
            "team": bullet.team,
            "position": bullet.position,
            "direction": bullet.direction,
            "turns_made": bullet.turns_made,
        } for bullet in self.bullet_list]

        cowboy_indices: dict[Cowboy, int] = {
            cowboy: i for i, cowboy in enumerate(self.cowboy_list)
        }
        respawn_queue: list[Coords] = [
            (respawn_round, cowboy_indices[cowboy]) for (respawn_round, cowboy) in self.cowboy_spawn_deque
        ]

        out = {
            "width": self.width,
            "height": self.height,
            "turn_idx": self.turn_idx,
            "bullet_subturn": self.bullet_subturn,

            "team_stats_points": [self.team_stats[i].points for i in range(len(self.team_stats))],
            "team_stats_golds": [self.team_stats[i].golds for i in range(len(self.team_stats))],
            "team_stats_fired_bullets": [self.team_stats[i].fired_bullets for i in range(len(self.team_stats))],
            "team_stats_deaths": [self.team_stats[i].deaths for i in range(len(self.team_stats))],
            "team_stats_kills": [self.team_stats[i].kills for i in range(len(self.team_stats))],
            "team_stats_killed_bullets": [self.team_stats[i].killed_bullets for i in range(len(self.team_stats))],

            "walls": walls,
            "golds": golds,
            "cowboys": cowboys,
            "bullets": bullets,

            "explosions": self.current_explosions,
            "shot_directions": self.current_gun_triggers,

            "respawn_queue": respawn_queue,
        }

        self.all_rounds.append(out)

        with open(self.save_filename(self.turn_idx, self.bullet_subturn), "w") as f:
            json.dump(out, f)

    def load_rounds(self, filenames: list[str]) -> None:
        self.all_rounds = []

        shot_directions: list[tuple[int, int, int]] = []

        for filename in filenames:
            with open(filename, "r") as f:
                data = json.load(f)
                print(f"loading from {filename}")

                # Reconstruction of shot_directions should be exact
                if "shot_directions" not in data:
                    # Bullets are shot only during cowboy main turn
                    if data["bullet_subturn"] == 0:
                        shot_directions = []
                        prev_bullets: dict[Coords, Any] = {}
                        if len(self.all_rounds) > 0:
                            prev_bullets = {tuple(b["position"]): True for b in self.all_rounds[-1]["bullets"]}

                        for b in data["bullets"]:
                            if tuple(b["position"]) not in prev_bullets:

                                (x, y) = b["position"]
                                d = bullet_directions[b["direction"]]
                                x = (x - d.value[0]) % data["width"]
                                y = (y - d.value[1]) % data["height"]
                                shot_directions.append((x, y, b["direction"]))

                    cowboys = {tuple(cb["position"]): True for cb in data["cowboys"] if cb["position"] is not None}
                    data["shot_directions"] = []
                    for (x, y, d) in shot_directions:
                        if (x, y) in cowboys:
                            data["shot_directions"].append((x, y, d))
                else:
                    # shot directions survives until next cowboy turn
                    shot_directions = data["shot_directions"]

                # Reconstruction of explosions is only an extrapolation (some explosions are missing)
                if "explosions" not in data:
                    explosions = []
                    # If some cowboy stopped to exists from the last turn, add the explosion
                    if len(self.all_rounds) > 0:
                        prev_round = self.all_rounds[-1]
                        prev_cowboys = {(cb["team"], cb["index"]): cb["position"] for cb in prev_round["cowboys"]}

                        for cb in data["cowboys"]:
                            prev_position = prev_cowboys[(cb["team"], cb["index"])]
                            if cb["position"] is None and prev_position is not None:
                                explosions.append(tuple(prev_position))

                    prev_bullets = {}
                    if len(self.all_rounds) > 0:
                        prev_bullets = {tuple(b["position"]): b for b in self.all_rounds[-1]["bullets"]}

                    if data["bullet_subturn"] == 0:
                        # Check bullets shot down by cowboys
                        alive_cowboys = {tuple(cb["position"]) for cb in data["cowboys"] if cb["position"] is not None}
                        for b in data["bullets"]:
                            (x, y) = b["position"]
                            if (x, y) in prev_bullets:
                                del prev_bullets[(x, y)]
                        for b in prev_bullets.values():
                            for dd in range(len(bullet_directions)):
                                (x, y) = b["position"]
                                d = bullet_directions[dd]
                                x = (x - d.value[0]) % data["width"]
                                y = (y - d.value[1]) % data["height"]
                                if (x, y) in alive_cowboys:
                                    explosions.append(tuple(b["position"]))
                                    shot_directions.append((x, y, dd))
                                    data["shot_directions"].append((x, y, dd))
                                    break

                    else:
                        # Check bullets that disappeared after their turn
                        walls = {tuple(w) for w in data["walls"]}
                        for b in data["bullets"]:
                            (x, y) = b["position"]
                            d = bullet_directions[b["direction"]]
                            x = (x - d.value[0]) % data["width"]
                            y = (y - d.value[1]) % data["height"]

                            if (x, y) in prev_bullets:
                                del prev_bullets[(x, y)]
                            elif tuple(b["position"]) in prev_bullets:
                                # fixup for not moved bullets
                                del prev_bullets[tuple(b["position"])]

                        missing_bullets_target_fields = []
                        for b in prev_bullets.values():
                            if b is None or b["turns_made"] + 1 == self.BULLET_LIFETIME:
                                continue
                            # test where could the bullet go
                            found = False
                            wall_hit = None
                            bullet_hit = None
                            targets = []
                            for dd in (0, -1, 1):
                                d = bullet_directions[(b["direction"] + dd) % len(bullet_directions)]
                                (x, y) = b["position"]
                                x = (x + d.value[0]) % data["width"]
                                y = (y + d.value[1]) % data["height"]
                                targets.append((x, y))
                                if (x, y) in explosions:
                                    found = True
                                    break
                                if (x, y) in walls:
                                    wall_hit = (x, y)
                                if (x, y) in prev_bullets:
                                    bullet_hit = (x, y)
                                if (x, y) in missing_bullets_target_fields:
                                    bullet_hit = (x, y)  # double hit, both bullets have to make one step

                            if not found:
                                if bullet_hit is not None:
                                    explosions.append(bullet_hit)
                                    if bullet_hit in prev_bullets:
                                        prev_bullets[bullet_hit] = None
                                elif wall_hit is not None:
                                    explosions.append(wall_hit)
                                else:
                                    missing_bullets_target_fields.extend(targets)
                                    # print(f"BULLET {b} missing in this round")

                    data["explosions"] = explosions

                self.all_rounds.append(data)

    def load(self, data: dict) -> None:
        self.width = data["width"]
        self.height = data["height"]
        self.turn_idx = data["turn_idx"]
        self.bullet_subturn = data["bullet_subturn"]

        self.team_stats: list[TeamStats] = []
        for i in range(len(data["team_stats_points"])):
            self.team_stats.append(
                TeamStats(
                    data["team_stats_kills"][i],
                    data["team_stats_points"][i],
                    data["team_stats_golds"][i],
                    data["team_stats_fired_bullets"][i],
                    data["team_stats_deaths"][i],
                    data["team_stats_killed_bullets"][i],
                )
            )

        # Number of teams cannot be changed!
        if len(self.team_stats) != len(self.teams):
            raise Exception(f"Different number of teams! ({len(self.team_stats)}, {len(self.teams)} teams in config)")

        self.current_explosions = data["explosions"]
        self.current_gun_triggers = data["shot_directions"]

        self.wall_grid = [[False for _ in range(self.width)] for _ in range(self.height)]
        self.gold_grid = [[None for _ in range(self.width)] for _ in range(self.height)]
        self.gold_list = []
        self.cowboy_grid = [[None for _ in range(self.width)] for _ in range(self.height)]
        self.cowboy_list = []
        self.bullet_grid = [[None for _ in range(self.width)] for _ in range(self.height)]
        self.bullet_list = []

        for (c, r) in data['walls']:
            self.wall_grid[r][c] = True

        # Golds:
        for (c, r) in data['golds']:
            gold = Gold()
            gold.position = (c, r)
            # Fix gold count 1/2 (when lowered)
            if len(self.gold_list) < self.gold_count:
                self.gold_list.append(gold)
                self.gold_grid[r][c] = gold
        # Fix gold count 2/2 (when new golds added)
        while len(self.gold_list) < self.gold_count:
            gold = Gold()
            self.gold_list.append(gold)
            self.spawn_gold(gold)

        # Cowboys:
        team_counts = [0 for _ in range(len(self.teams))]
        for record in data['cowboys']:
            pos = record["position"]
            if pos is not None:
                pos = tuple(pos)
            team = record['team']
            # Fix cowboy count 1/2 (when lowered)
            if record['index'] < self.cowboys_per_team:
                team_counts[team] += 1
                cowboy = Cowboy(record['team'], record['index'], pos)
                self.cowboy_list.append(cowboy)
                if pos is not None:
                    c, r = pos
                    self.cowboy_grid[r][c] = cowboy
        # Fix cowboy count 2/2 (when new cowboys added)
        for i, count in enumerate(team_counts):
            while count < self.cowboys_per_team:
                pos = self.random_free_position()
                cowboy = Cowboy(i, count, pos)
                count += 1
                self.cowboy_list.append(cowboy)
                self.cowboy_grid[pos[1]][pos[0]] = cowboy

        # Respawn queue:
        self.cowboy_spawn_deque = deque()
        for (respawn_round, i) in data['respawn_queue']:
            if i < len(self.cowboy_list):
                self.cowboy_spawn_deque.append((respawn_round, self.cowboy_list[i]))

        for record in data['bullets']:
            pos = tuple(record["position"])
            bullet = Bullet(record['team'], pos, record['direction'], record['turns_made'])
            self.bullet_list.append(bullet)
            c, r = pos
            self.bullet_grid[r][c] = bullet

    # `(width * height) // wall_fraction` wall clusters will be generated
    # randomly in the grid, with at most `cluster_max` wall squares each.
    def generate_walls(self, wall_fraction: int = 50, cluster_max: int = 5) -> None:
        self.wall_grid = [[False for _ in range(self.width)] for _ in range(self.height)]

        for _ in range((self.width * self.height) // wall_fraction):
            x, y = rr(self.width), rr(self.height)
            d = rr(4)
            for i in range(cluster_max):
                dirchange = rr(6)
                if dirchange == 0:
                    d = (d + 1) % 4
                elif dirchange == 1:
                    d = (d + 3) % 4
                dx, dy = cowboy_directions[d].value[0], cowboy_directions[d].value[1]
                x, y = (x + dx) % self.width, (y + dy) % self.height
                self.wall_grid[y][x] = True

                if rr(cluster_max - i) == 0:
                    break

        if not self.check_walls():
            self.generate_walls()

    # Returns True if there is only one connected component of reachable squares.
    def check_walls(self) -> bool:
        squares_visited = [[False for _ in range(self.width)] for _ in range(self.height)]
        # Find a starting wall-free square, count the number of free squares.
        self.free_square_count = 0
        init_x, init_y = 0, 0
        for y in range(self.height):
            for x in range(self.width):
                if not self.wall_grid[y][x]:
                    self.free_square_count += 1
                    init_x, init_y = x, y
        if self.free_square_count == 0:
            return False

        # Check that as many are reachable from (init_x, init_y) as are free.
        # BFS:
        reached = 0
        q: queue.Queue[Coords] = queue.Queue()
        q.put((init_x, init_y))
        while not q.empty():
            x, y = q.get()
            if squares_visited[y][x] or self.wall_grid[y][x]:
                continue
            squares_visited[y][x] = True
            reached += 1
            for d in cowboy_directions:
                q.put(((x + d.value[0]) % self.width, (y + d.value[1]) % self.height))

        return reached == self.free_square_count

    def random_free_position(self) -> Coords:
        pos = rr(self.width), rr(self.height)
        seen = set()
        q: queue.Queue[Coords] = queue.Queue()
        q.put(pos)
        while not q.empty():
            x, y = q.get()
            if (x, y) in seen:
                continue
            if (not self.wall_grid[y][x] and self.cowboy_grid[y][x] is None
                    and self.bullet_grid[y][x] is None
                    and self.gold_grid[y][x] is None):
                return (x, y)
            seen.add((x, y))
            for d in bullet_directions:
                new_pos = ((x + d.value[0]) % self.width, (y + d.value[1]) % self.height)
                q.put(new_pos)
        return (-1, -1)  # should not happen

    def generate_cowboy_positions(self) -> None:
        # For each cowboy, generate a random spot and then place him at the nearest free square
        for i in range(len(self.teams)):
            for j in range(self.cowboys_per_team):
                position = self.random_free_position()
                cowboy = Cowboy(i, j, position)
                self.cowboy_list.append(cowboy)
                self.cowboy_grid[position[1]][position[0]] = cowboy

    def generate_gold_positions(self) -> None:
        for g in self.gold_list:
            self.spawn_gold(g)

    # (Re)spawns a gold coin at a random spot, prefering squares far away from everything else.
    def spawn_gold(self, gold: Gold) -> None:
        distances_from_objects = [[self.infty for _ in range(self.width)] for _ in range(self.height)]
        bfs_queue: queue.Queue[tuple[int, Coords]] = queue.Queue()
        for x in range(self.width):
            for y in range(self.height):
                if self.gold_grid[y][x] is not None or self.cowboy_grid[y][x]:
                    bfs_queue.put((0, (x, y)))
        distance_total = 0
        while not bfs_queue.empty():
            dist, (x, y) = bfs_queue.get()
            if self.wall_grid[y][x] or distances_from_objects[y][x] < self.infty:
                continue
            distances_from_objects[y][x] = dist
            distance_total += dist
            for d in bullet_directions:
                new_pos = ((x + d.value[0]) % self.width, (y + d.value[1]) % self.height)
                bfs_queue.put((dist + 1, new_pos))

        rand_choice = rr(distance_total)
        for x in range(self.width):
            for y in range(self.height):
                if distances_from_objects[y][x] == self.infty:
                    continue
                if distances_from_objects[y][x] > rand_choice:
                    gold.position = (x, y)
                    self.gold_grid[y][x] = gold
                    return
                rand_choice -= distances_from_objects[y][x]

    # Respawns a cowboy at (one of) the most distant square from everything else
    def spawn_cowboy(self, cowboy: Cowboy) -> None:
        if cowboy.position is not None:
            return
        seen = [[False for _ in range(self.width)] for _ in range(self.height)]
        bfs_queue: queue.Queue[tuple[int, Coords]] = queue.Queue()
        for c in self.cowboy_list:
            if c.position is not None:
                bfs_queue.put((0, c.position))
        for g in self.gold_list:
            if g.position is not None:
                bfs_queue.put((0, g.position))
        dist_max = -1
        max_list: list[Coords] = []
        while not bfs_queue.empty():
            dist, (x, y) = bfs_queue.get()
            if self.wall_grid[y][x] or seen[y][x]:
                continue
            if dist > dist_max:
                dist_max = dist
                max_list = []
            max_list.append((x, y))
            seen[y][x] = True
            for d in cowboy_directions:
                new_pos = ((x + d.value[0]) % self.width, (y + d.value[1]) % self.height)
                bfs_queue.put((dist + 1, new_pos))
        x, y = max_list[rr(len(max_list))]
        cowboy.position = (x, y)
        print(f"GAME[INFO]: {cowboy} spawned after death")
        self.cowboy_grid[y][x] = cowboy

    def bullet_disappear(self, bullet: Bullet) -> None:
        if bullet.position is None:
            return
        x, y = bullet.position
        bullet.position = None
        self.bullet_list.remove(bullet)
        self.bullet_grid[y][x] = None

    def bullet_hit(self, cowboy: Cowboy, bullet: Bullet):
        if cowboy.position is None or cowboy.position != bullet.position:
            return
        print(f"GAME[INFO]: {cowboy} hit by {bullet}")
        self.team_stats[bullet.team].kills[cowboy.team] += 1
        self.team_stats[cowboy.team].deaths += 1
        if cowboy.team != bullet.team:
            self.team_stats[bullet.team].points += self.SHOTDOWN_BOUNTY
        x, y = cowboy.position
        self.bullet_disappear(bullet)
        self.cowboy_grid[y][x] = None
        cowboy.position = None
        self.active_cowboys.remove(cowboy)
        self.cowboy_spawn_deque.append((self.turn_idx + self.TURNS_TO_RESPAWN, cowboy))
        self.current_explosions.append((x, y))

    def bullet_collision(self, b1: Bullet, b2: Bullet) -> None:
        if b1.position is None or b1.position != b2.position:
            return
        x, y = b1.position
        self.bullet_disappear(b1)
        self.bullet_disappear(b2)
        self.current_explosions.append((x, y))
        self.team_stats[b1.team].killed_bullets += 1
        self.team_stats[b2.team].killed_bullets += 1

    def get_statistics(self) -> list[tuple[str, TeamStats]]:
        return [(team.login, self.team_stats[i]) for (i, team) in enumerate(self.teams)]

    def get_state(self, round: int | None = None) -> dict[str, Any] | None:
        if round is not None:
            if round < 0 or round >= len(self.all_rounds):
                return None
            data = self.all_rounds[round]
            return {
                "width": data["width"],
                "height": data["height"],
                "cowboys": [(cb["position"], self.teams[cb["team"]].login) for cb in data["cowboys"] if cb["position"] is not None],
                "bullets": [(b["position"], self.teams[b["team"]].login) for b in data["bullets"]],
                "walls": data["walls"],
                "golds": [g for g in data["golds"] if g is not None],
                "explosions": data["explosions"],
                "shot_directions": data["shot_directions"],
                'points': [
                    (team.login, data["team_stats_points"][i]) for (i, team) in enumerate(self.teams)
                ],
            }

        walls = []
        cowboys = []
        bullets = []
        golds = [g.position for g in self.gold_list if g.position is not None]

        for r in range(self.height):
            for c in range(self.width):
                if self.wall_grid[r][c]:
                    walls.append((c, r))
        for cb in self.cowboy_list:
            if cb.position is not None:
                cowboys.append((cb.position, self.teams[cb.team].login))
        for b in self.bullet_list:
            bullets.append((b.position, self.teams[b.team].login))

        return {
            "width": self.width,
            "height": self.height,
            "cowboys": cowboys,
            "bullets": bullets,
            "walls": walls,
            "golds": golds,
            "explosions": self.current_explosions,
            "shot_directions": self.current_gun_triggers,
            'points': [
                (team.login, self.team_stats[i].points) for (i, team) in enumerate(self.teams)
            ],
        }

    def simulate_cowboys_turn(self) -> None:
        start_time = time.time()
        self.a_star_time = 0
        self.bfs_time = 0

        self.current_explosions = []
        self.current_gun_triggers = []
        golds_to_respawn = []
        # If any cowboys ought to be respawned, do it.
        while len(self.cowboy_spawn_deque) > 0:
            spawn_turn, cowboy = self.cowboy_spawn_deque.popleft()
            if spawn_turn > self.turn_idx:
                self.cowboy_spawn_deque.appendleft((spawn_turn, cowboy))
                break
            self.spawn_cowboy(cowboy)

        # Generate a random shuffling of the cowboys.
        self.active_cowboys = []
        for c in self.cowboy_list:
            if c.position is not None:
                self.active_cowboys.append(c)

        shuffle(self.active_cowboys)
        # make copy so that self.active_cowboys could be modified during the turn (when cowboy is hit)
        cowboys_to_proceed = self.active_cowboys.copy()

        # Ensure BFS is computed for all position of cowboys (in parallel)
        # cowboys_to_compute = [cowboy for cowboy in cowboys_to_proceed if cowboy.position not in self.cached_distances]
        # if len(cowboys_to_compute) > 0:
        #     cpus = len(os.sched_getaffinity(0))
        #     with Pool(cpus) as pool:
        #         results = pool.starmap(
        #             self.bfs,
        #             [(cowboy.position, cowboy_directions) for cowboy in cowboys_to_compute]
        #         )
        #     for (cowboy, result) in zip(cowboys_to_compute, results):
        #         self.cached_distances[cowboy.position] = result
        #     self.bfs_time += time.time() - start_time

        cowboy_results: list[list[str]] = [[] for _ in self.teams]

        # In this order, process their moves.
        for cowboy in cowboys_to_proceed:
            if cowboy.position is None:
                continue  # cowboy was hit in this turn

            program = self.teams[cowboy.team].get_cowboy_program()
            status, action, steps = program.execute(self.COWBOY_MAX_STEPS, self, cowboy)
            print(f"GAME[ACTION]: {cowboy}: status={status}, steps={steps}, result={action}")

            if not status:
                cowboy_results[cowboy.team].append(
                    f"Kovboj na pozici {cowboy.position}: ERROR: {action} ({steps} kroků výpočtu)"
                )
                continue

            assert isinstance(action, Action)

            cowboy_results[cowboy.team].append(
                f"Kovboj na pozici {cowboy.position}: akce {action.type} (směr {action.direction}), {steps} kroků výpočtu"
            )

            if action.type != ActionType.NOP and action.direction is not None:
                # In all invalid cases, the cowboys keeps his position
                x, y = cowboy.position
                d = action.direction
                new_x, new_y = (x + d.value[0]) % self.width, (y + d.value[1]) % self.height

                if action.type == ActionType.MOVE:
                    if self.wall_grid[new_y][new_x] or self.cowboy_grid[new_y][new_x] is not None:
                        continue
                    # Make the move
                    self.cowboy_grid[y][x] = None
                    cowboy.position = (new_x, new_y)
                    self.cowboy_grid[new_y][new_x] = cowboy
                    # Check for collision:
                    bullet = self.bullet_grid[new_y][new_x]
                    if bullet is not None:
                        self.bullet_hit(cowboy, bullet)
                        continue
                    gold = self.gold_grid[new_y][new_x]
                    if gold is not None:
                        gold.position = None
                        self.gold_grid[new_y][new_x] = None
                        golds_to_respawn.append(gold)
                        self.team_stats[cowboy.team].golds += 1
                        self.team_stats[cowboy.team].points += self.GOLD_PRICE

                elif action.type == ActionType.FIRE:
                    self.team_stats[cowboy.team].points -= self.BULLET_PRICE
                    self.team_stats[cowboy.team].fired_bullets += 1
                    self.current_gun_triggers.append((x, y, bullet_directions.index(d)))

                    print(f"GAME[ACTION]: Fired bullet at {new_x},{new_y} with direction {d}")

                    if self.wall_grid[new_y][new_x] or self.bullet_grid[new_y][new_x]:
                        self.current_explosions.append((new_x, new_y))
                        another_bullet = self.bullet_grid[new_y][new_x]
                        if another_bullet is not None:
                            self.bullet_disappear(another_bullet)
                        continue

                    bullet = Bullet(cowboy.team, (new_x, new_y), bullet_directions.index(d))
                    self.bullet_grid[new_y][new_x] = bullet
                    other_cowboy = self.cowboy_grid[new_y][new_x]
                    self.bullet_list.append(bullet)
                    if other_cowboy is not None:
                        self.bullet_hit(other_cowboy, bullet)

        # Respawn golds that were taken this turn:
        for gold in golds_to_respawn:
            self.spawn_gold(gold)

        self.turn_idx += 1
        self.bullet_subturn = 0
        self.save()

        self.cowboy_results.append(cowboy_results)

        elapsed = time.time() - start_time
        print(f"GAME[TURN] Cowboy turn {self.turn_idx - 1} completed in {elapsed}s (bfs time: {self.bfs_time}s)")

    def simulate_bullets_turn(self) -> None:
        start_time = time.time()

        bullet_results: list[list[str]] = [[] for _ in self.teams]

        self.current_explosions = []
        # Bullets fly in order in which they are fired
        # Make copy of the list to not skip any when bullet_list is modified
        bullets_order = self.bullet_list.copy()
        for bullet in bullets_order:
            if bullet.position is None:
                continue

            program = self.teams[bullet.team].get_bullet_program()
            status, action, steps = program.execute(self.BULLET_MAX_STEPS, self, bullet)
            print(f"GAME[ACTION]: {bullet}: status={status}, steps={steps}, result={action}")

            if not status:
                bullet_results[bullet.team].append(
                    f"Střela na pozici {bullet.position}: ERROR: {action} ({steps} kroků výpočtu)"
                )

            assert isinstance(action, Action)

            bullet_results[bullet.team].append(
                f"Střela na pozici {bullet.position}: akce {action.type}, {steps} kroků výpočtu"
            )

            if status and action.type == ActionType.BULLET_TURN_L:
                bullet.direction = (bullet.direction - 1) % len(bullet_directions)
            elif status and action.type == ActionType.BULLET_TURN_R:
                bullet.direction = (bullet.direction + 1) % len(bullet_directions)

            x, y = bullet.position
            d = bullet_directions[bullet.direction]
            new_x, new_y = (x + d.value[0]) % self.width, (y + d.value[1]) % self.height

            if self.wall_grid[new_y][new_x]:
                self.bullet_disappear(bullet)
                self.current_explosions.append((new_x, new_y))
                continue

            self.bullet_grid[y][x] = None
            bullet.position = (new_x, new_y)

            another_bullet = self.bullet_grid[new_y][new_x]
            if another_bullet is not None:
                self.bullet_collision(bullet, another_bullet)
                continue

            cowboy = self.cowboy_grid[new_y][new_x]
            if cowboy is not None:
                self.bullet_hit(cowboy, bullet)
                continue

            self.bullet_grid[new_y][new_x] = bullet
            bullet.turns_made += 1
            if bullet.turns_made >= self.BULLET_LIFETIME:
                self.bullet_disappear(bullet)

        # Filter gun triggers
        new_gun_triggers: list[tuple[int, int, int]] = []
        for (x, y, dd) in self.current_gun_triggers:
            if self.cowboy_grid[y][x] is not None:
                new_gun_triggers.append((x, y, dd))
        self.current_gun_triggers = new_gun_triggers

        self.bullet_subturn += 1
        self.save()

        self.bullet_results.append(bullet_results)

        elapsed = time.time() - start_time
        print(f"GAME[TURN] Bullet subturn {self.turn_idx}:{self.bullet_subturn - 1} completed in {elapsed}s")

    def get_cowboy_results(self, team: Team, last_n_round: int = 5):
        index = self.teams.index(team)
        return [
            results[index]
            for results in self.cowboy_results[-last_n_round:]
        ]

    def get_bullet_results(self, team: Team, last_n_round: int = 5):
        index = self.teams.index(team)
        return [
            results[index]
            for results in self.bullet_results[-last_n_round:]
        ]

    # Methods providing information for cowboys and bullets:
    # In all cases, `context` is either a Cowboy or a Bullet object.

    # A cowboy's lasting id inside his team
    def my_index(self, cowboy: Cowboy) -> int:
        return cowboy.index

    # The objects coordinates on the map.
    # Returns (-1, -1) if the object is no longer valid.
    def my_position(self, context: Cowboy | Bullet) -> Coords:
        return (-1, -1) if context is None or context.position is None else context.position

    # Returns a grid of computed distances from start.
    # Both `distance_from` and `which_way` can then compute what they need
    def a_star(self, start: Coords, goal: Coords, dirs: list[Direction], metric: Callable[[Coords, Coords], int]) -> list[list[int]]:
        start_time = time.time()

        dists_from_start = [[self.infty for _ in range(self.width)] for _ in range(self.height)]
        pq: queue.PriorityQueue[tuple[int, tuple[int, Coords]]] = queue.PriorityQueue()
        pq.put((0, (0, start)))
        while not pq.empty():
            _, (dist, (x, y)) = pq.get()
            if dists_from_start[y][x] < self.infty or self.wall_grid[y][x]:
                continue
            dists_from_start[y][x] = dist
            if (x, y) == goal:
                self.a_star_time += time.time() - start_time
                return dists_from_start
            for d in dirs:
                new_coords = (x + d.value[0]) % self.width, (y + d.value[1]) % self.height
                new_dist = dist + 1
                new_priority = new_dist + metric(goal, new_coords)
                pq.put((new_priority, (new_dist, new_coords)))

        print("A* didn't reach the goal.")
        self.a_star_time += time.time() - start_time
        return dists_from_start

    # This is a method (rather than a separate function) because it depends on width and height
    # (the playfield is a toroid)
    def coord_diffs(self, start: Coords, goal: Coords) -> Coords:
        x_dif = (
            min(goal[0] - start[0], (self.width + start[0]) - goal[0])
            if start[0] < goal[0]
            else min(start[0] - goal[0], (self.width + goal[0]) - start[0])
        )
        y_dif = (
            min(goal[1] - start[1], (self.width + start[1]) - goal[1])
            if start[1] < goal[1]
            else min(start[1] - goal[1], (self.width + goal[1]) - start[1])
        )
        return (x_dif, y_dif)

    def manhattan_metric(self, start: Coords, goal: Coords) -> int:
        return sum(self.coord_diffs(start, goal))

    def maximum_metric(self, start: Coords, goal: Coords) -> int:
        return max(self.coord_diffs(start, goal))

    def bfs(self, start: Coords, dirs: list[Direction]):
        start_time = time.time()

        dists_from_start = [[self.infty for _ in range(self.width)] for _ in range(self.height)]
        q: queue.Queue[tuple[int, Coords]] = queue.Queue()
        q.put((0, start))
        while not q.empty():
            dist, (x, y) = q.get()
            if dists_from_start[y][x] < self.infty or self.wall_grid[y][x]:
                continue
            dists_from_start[y][x] = dist
            for d in dirs:
                q.put((dist + 1, ((x + d.value[0]) % self.width, (y + d.value[1]) % self.height)))

        self.bfs_time += time.time() - start_time
        return dists_from_start

    def compute_cowboy_distances(self, cowboy: Cowboy) -> list[list[int]] | None:
        if cowboy.position is None:
            return None
        if cowboy.position not in self.cached_distances:
            self.cached_distances[cowboy.position] = self.bfs(cowboy.position, cowboy_directions)

        return self.cached_distances[cowboy.position]

    # Returns the length of the shortest path of the object to (x, y).
    # If unreachable, returns a sort of "infinite" value
    def distance_from(self, context: Cowboy, pos: Coords) -> int:
        x, y = pos
        if context is None or x < 0 or x >= self.width or y < 0 or y >= self.height:
            return self.width * self.height

        distances = self.compute_cowboy_distances(context)
        if distances is None:
            return self.infty

        return distances[y][x]

    # Returns the direction (index of direction) of the first step to (x, y).
    def which_way(self, context: Cowboy, pos: Coords) -> Coords:
        x, y = pos
        if context.position == (x, y):
            return (0, 0)

        if context is None or x < 0 or x >= self.width or y < 0 or y >= self.height:
            return (0, 0)

        distances = self.compute_cowboy_distances(context)
        if distances is None:
            return (0, 0)

        # (x, y) will change from here
        while True:
            xy_changed = False
            for d in cowboy_directions:
                new_x, new_y = (x + d.value[0]) % self.width, (y + d.value[1]) % self.height
                if distances[new_y][new_x] < distances[y][x]:
                    if context.position == (new_x, new_y):
                        return (-d.value[0], -d.value[1])
                    x, y = new_x, new_y
                    xy_changed = True
                    break
            if not xy_changed:
                print("Problem in BFS output!")
                return (0, 0)

    def number_of_golds(self):
        return sum([0 if self.gold_list[i].position is None else 1 for i in range(self.gold_count)])

    def number_of_cowboys(self):
        return len(self.active_cowboys)

    # The coordinates of the i-th currently present gold on the map.
    # Returns (-1, -1) if the index i is out of bounds.
    def gold_i_position(self, i: int) -> Coords:
        idx = 0
        for gold in self.gold_list:
            if gold.position is not None:
                if idx == i:
                    return gold.position
                idx += 1
        return (-1, -1)

    def number_of_bullets(self):
        return len(self.bullet_list)

    # helper
    def bullet_i(self, i: int) -> Bullet | None:
        if i < 0 or i >= len(self.bullet_list):
            return None
        return self.bullet_list[i]

    # The coordinates of the i-th currently present bullet on the map.
    # Returns (-1, -1) if the index i is out of bounds.
    def bullet_i_position(self, i: int) -> Coords:
        bullet = self.bullet_i(i)
        if bullet and bullet.position:
            return bullet.position
        else:
            return (-1, -1)

    def bullet_i_team(self, i: int) -> int:
        c = self.bullet_i(i)
        return -1 if c is None else c.team

    # This cowboy's index for this turn (assigned randomly)
    def my_id(self, context: Cowboy | Bullet) -> int:
        if type(context) is Cowboy:
            return self.active_cowboys.index(context)
        elif type(context) is Bullet:
            return self.bullet_list.index(context)
        return -1

    # My teams's ID
    def my_team(self, context: Cowboy | Bullet) -> int:
        return context.team

    def my_points(self, context: Cowboy | Bullet) -> int:
        return self.team_stats[context.team].points

    # Helper
    def cowboy_i(self, i: int) -> Cowboy | None:
        if i < 0 or i >= len(self.active_cowboys):
            return None
        return self.active_cowboys[i]

    # The coordinates of the cowboy with currently assigned index i.
    # Returns (-1, -1) if the index i is out of bounds.
    def cowboy_i_position(self, i: int) -> Coords:
        cowboy = self.cowboy_i(i)
        if cowboy and cowboy.position:
            return cowboy.position
        else:
            return (-1, -1)

    # The team index of the cowboy with current index i
    # Returns -1 if i is out of bounds.
    def cowboy_i_team(self, i: int) -> int:
        c = self.cowboy_i(i)
        return -1 if c is None else c.team

    # Bullet-specific
    def my_direction(self, bullet: Bullet) -> Direction:
        return all_directions[bullet.direction]

    # Bullet's time to live
    def ttl(self, bullet: Bullet) -> int:
        return self.BULLET_LIFETIME - bullet.turns_made
