from random import randrange as rr
from random import shuffle
import queue
from collections import deque
from typing import Callable

from .team import Team
from .actions import ActionType, Direction


class Context:
    # Changes every turn
    team: int
    index: int


class Cowboy(Context):
    def __init__(self, team: int, index: int, position: tuple[int, int] | None):
        self.team = team
        self.index = index
        # Will be None when the cowboy is shot down and waiting to respawn.
        self.position = position


class Bullet(Context):
    # `direction` is an index for dirs_bullet
    def __init__(self, team: int, position: tuple[int, int], direction: int, turns_made: int = 0):
        self.team = team
        self.position = position
        self.direction = direction
        self.turns_made = turns_made


class Gold:
    position: tuple[int, int]


class GameMap:
    dirs_cowboy = [(-1, 0), (0, 1), (1, 0), (0, -1)]
    dirs_bullet = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]
    action_dirs_list = [Direction.W, Direction.NW, Direction.N, Direction.NE, Direction.E, Direction.SE, Direction.S, Direction.SW]
    action_dirs_dict = {
        (0, 1): 2,
        (1, 1): 3,
        (1, 0): 4,
        (1, -1): 5,
        (0, -1): 6,
        (-1, -1): 7,
        (-1, 0): 0,
        (-1, 1): 1
    }
    wall_grid: list[list[bool]]
    cowboy_grid: list[list[Cowboy]]
    bullet_grid: list[list[Bullet]]
    gold_grid: list[list[Gold]]

    team_points: list[int]

    gold_list: list[Gold]
    cowboy_list: list[Cowboy]
    bullet_list: list[Bullet]

    cowboy_spawn_deque: deque[tuple[int, Cowboy]]

    # has value only during turn computation
    active_cowboys: list[Cowboy]

    # Only counts cowboy turns
    turn_idx: int
    # count bullet turns, reset with each turn_idx increase
    bullet_subturn: int
    # Constants:
    # Points taken for shooting
    BULLET_PRICE = 1
    # Points for reaching a coin.
    GOLD_PRICE = 3
    # Points for shooting down an enemy cowboy.
    SHOTDOWN_BOUNTY = 10
    # No. of turns between a cowboy being shot down and him respawning.
    TURNS_TO_RESPAWN = 10
    # For how many total (bullet) turns does a bullet object exist?
    BULLET_LIFETIME = 15
    # Maximum program lengths:
    COWBOY_MAX_STEPS = 3000
    BULLET_MAX_STEPS = 300

    def __init__(
            self,
            width: int,
            height: int,
            teams: list[Team],
            cowboys_per_team: int = 4,
            # The number of golds on the map will be kept constant
            gold_count: int = 5,
            wall_fraction: int = 50,
            cluster_max: int = 5):
        self.width, self.height = width, height
        self.infty = 2 * self.width * self.height
        self.teams = teams
        self.cowboys_per_team = cowboys_per_team
        self.gold_count = gold_count

        self.init_new(wall_fraction, cluster_max)

    def init_new(self, wall_fraction: int = 50, cluster_max: int = 5):
        self.team_points = [0 for _ in range(len(self.teams))]
        self.turn_idx = 0
        self.bullet_subturn = 0
        self.cowboy_grid = [[None for _ in range(self.width)] for _ in range(self.height)]
        self.bullet_grid = [[None for _ in range(self.width)] for _ in range(self.height)]
        self.gold_grid = [[None for _ in range(self.width)] for _ in range(self.height)]

        self.cowboy_list = []
        self.gold_list = [Gold() for _ in range(self.gold_count)]
        self.bullet_list = []
        self.current_explosions = []
        # Deque keeping track of when dead cowboys should respawn
        self.cowboy_spawn_deque = deque()
#
        self.generate_walls(wall_fraction, cluster_max)
        self.generate_cowboy_positions()
        self.generate_gold_positions()

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
                dx, dy = self.dirs_cowboy[d][0], self.dirs_cowboy[d][1]
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
        q = queue.Queue()
        q.put((init_x, init_y))
        while not q.empty():
            x, y = q.get()
            if squares_visited[y][x] or self.wall_grid[y][x]:
                continue
            squares_visited[y][x] = True
            reached += 1
            for d in self.dirs_cowboy:
                q.put(((x + d[0]) % self.width, (y + d[1]) % self.height))

        return reached == self.free_square_count

    def random_free_position(self) -> tuple[int, int]:
        pos = rr(self.width), rr(self.height)
        seen = set()
        q = queue.Queue()
        q.put(pos)
        while not q.empty():
            x, y = q.get()
            if (x, y) in seen:
                continue
            if not self.wall_grid[y][x] and self.cowboy_grid[y][x] is None and self.bullet_grid[y][x] is None and self.gold_grid[y][x] is None:
                return (x, y)
            seen.add((x, y))
            for d in self.dirs_bullet:
                new_pos = ((x + d[0]) % self.width, (y + d[1]) % self.height)
                q.put(new_pos)

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
        bfs_queue = queue.Queue()
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
            for d in self.dirs_bullet:
                new_pos = ((x + d[0]) % self.width, (y + d[1]) % self.height)
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
        bfs_queue = queue.Queue()
        for c in self.cowboy_list:
            if c.position is not None:
                bfs_queue.put((0, c.position))
        for g in self.gold_list:
            bfs_queue.put((0, g.position))
        dist_max = -1
        max_list = []
        while not bfs_queue.empty():
            dist, (x, y) = bfs_queue.get()
            if self.wall_grid[y][x] or seen[y][x]:
                continue
            if dist > dist_max:
                dist_max = dist
                max_list = []
            max_list.append((x, y))
            seen[y][x] = True
            for d in self.dirs_cowboy:
                new_pos = ((x + d[0]) % self.width, (y + d[1]) % self.height)
                bfs_queue.put((dist + 1, new_pos))
        x, y = max_list[rr(len(max_list))]
        cowboy.position = (x, y)
        self.cowboy_grid[y][x] = cowboy

    def bullet_disappear(self, bullet: Bullet) -> None:
        x, y = bullet.position
        bullet.position = None
        self.bullet_list.remove(bullet)
        self.bullet_grid[y][x] = None

    def bullet_hit(self, cowboy: Cowboy, bullet: Bullet):
        if cowboy.position is None or cowboy.position != bullet.position:
            return
        if cowboy.team != bullet.team:
            self.team_points[bullet.team] += self.SHOTDOWN_BOUNTY
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

    def simulate_cowboys_turn(self) -> None:
        self.current_explosions = []
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

        # In this order, process their moves.
        for cowboy in cowboys_to_proceed:
            if cowboy.position is None:
                continue  # cowboy was hit in this turn

            program = self.teams[cowboy.team].get_cowboy_program()
            status, action, steps = program.execute(self.COWBOY_MAX_STEPS, self, cowboy)

            if status and action.type != ActionType.NOP and action.direction is not None:
                # In all invalid cases, the cowboys keeps his position
                x, y = cowboy.position
                d = action.direction.value
                new_x, new_y = (x + d[0]) % self.width, (y + d[1]) % self.height
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
                        self.team_points[cowboy.team] += self.GOLD_PRICE

                elif action.type == ActionType.FIRE:
                    self.team_points[cowboy.team] -= self.BULLET_PRICE

                    print(f"GAME[ACTION]: Fired bullet at {new_x},{new_y} with direction {d}")

                    if self.wall_grid[new_y][new_x] or self.bullet_grid[new_y][new_x]:
                        self.current_explosions.append((new_x, new_y))
                        if self.bullet_grid[new_y][new_x] is not None:
                            self.bullet_disappear(self.bullet_grid[new_y][new_x])
                        continue

                    bullet = Bullet(cowboy.team, (new_x, new_y), self.action_dirs_dict[d])
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

    def simulate_bullets_turn(self) -> None:
        # Bullets fly in order in which they are fired
        # Make copy of the list to not skip any when bullet_list is modified
        bullets_order = self.bullet_list.copy()
        for bullet in bullets_order:
            if bullet.position is None:
                continue

            program = self.teams[bullet.team].get_bullet_program()
            status, action, steps = program.execute(self.BULLET_MAX_STEPS, self, bullet)
            print(f"GAME[ACTION]: {bullet}: status={status}, steps={steps}, result={action}")

            if status and action.type == ActionType.BULLET_TURN_L:
                bullet.direction = (bullet.direction - 1) % len(self.dirs_bullet)
            elif status and action.type == ActionType.BULLET_TURN_R:
                bullet.direction = (bullet.direction + 1) % len(self.dirs_bullet)

            x, y = bullet.position
            d = self.dirs_bullet[bullet.direction]
            new_x, new_y = (x + d[0]) % self.width, (y + d[1]) % self.height

            if self.wall_grid[new_y][new_x]:
                self.bullet_disappear(bullet)
                self.current_explosions.append((new_x, new_y))
                continue
            self.bullet_grid[y][x] = None
            bullet.position = (new_x, new_y)
            bullet.direction = self.action_dirs_dict[d]

            if self.bullet_grid[new_y][new_x] is not None:
                self.bullet_collision(bullet, self.bullet_grid[new_y][new_x])
                continue

            if self.cowboy_grid[new_y][new_x] is not None:
                self.bullet_hit(self.cowboy_grid[new_y][new_x], bullet)
                continue

            self.bullet_grid[new_y][new_x] = bullet
            bullet.turns_made += 1
            if bullet.turns_made >= self.BULLET_LIFETIME:
                self.bullet_disappear(bullet)

        self.bullet_subturn += 1

    # Methods providing information for cowboys and bullets:
    # In all cases, `context` is either a Cowboy or a Bullet object.

    # A cowboy's lasting id inside his team
    def my_index(self, cowboy: Cowboy) -> int:
        return cowboy.index

    # The objects coordinates on the map.
    # Returns (-1, -1) if the object is no longer valid.
    def my_position(self, context: Cowboy | Bullet) -> tuple[int, int]:
        return (-1, -1) if context is None or context.position is None else context.position

    # Returns a grid of computed distances from start.
    # Both `distance_from` and `which_way` can then compute what they need
    def a_star(self, start: tuple[int, int], goal: tuple[int, int], dirs: list[tuple[int, int]], metric: Callable[[tuple[int, int], tuple[int, int]], int]) -> list[list[int]]:
        self.infty = 2 * self.width * self.height
        dists_from_start = [[self.infty for _ in range(self.width)] for _ in range(self.height)]
        pq = queue.PriorityQueue()
        pq.put((0, (0, start)))
        while not pq.empty():
            _, (dist, (x, y)) = pq.get()
            if dists_from_start[y][x] < self.infty or self.wall_grid[y][x]:
                continue
            dists_from_start[y][x] = dist
            if (x, y) == goal:
                return dists_from_start
            for d in dirs:
                new_coords = (x + d[0]) % self.width, (y + d[1]) % self.height
                new_dist = dist + 1
                new_priority = new_dist + metric(goal, new_coords)
                pq.put((new_priority, (new_dist, new_coords)))

        print("A* didn't reach the goal.")
        return dists_from_start

    # This is a method (rather than a separate function) because it depends on width and height
    # (the playfield is a toroid)
    def coord_diffs(self, start: tuple[int, int], goal: tuple[int, int]) -> tuple[int, int]:
        x_dif = min(goal[0] - start[0], (self.width + start[0]) - goal[0]) if start[0] < goal[0] else min(start[0] - goal[0], (self.width + goal[0]) - start[0])
        y_dif = min(goal[1] - start[1], (self.width + start[1]) - goal[1]) if start[1] < goal[1] else min(start[1] - goal[1], (self.width + goal[1]) - start[1])
        return (x_dif, y_dif)

    def manhattan_metric(self, start: tuple[int, int], goal: tuple[int, int]) -> int:
        return sum(self.coord_diffs(start, goal))

    def maximum_metric(self, start: tuple[int, int], goal: tuple[int, int]) -> int:
        return max(self.coord_diffs(start, goal))

    # Returns the length of the shortest path of the object to (x, y).
    # If unreachable, returns a sort of "infinite" value
    def distance_from(self, context: Cowboy | Bullet, pos: tuple[int, int]) -> int:
        x, y = pos
        if context is None or x < 0 or x >= self.width or y < 0 or y >= self.height:
            return self.width * self.height

        distances = self.a_star(
            context.position,
            (x, y),
            self.dirs_cowboy if type(context) is Cowboy else self.dirs_bullet,
            self.manhattan_metric if type(context) is Cowboy else self.maximum_metric)

        return distances[y][x]

    # Returns the direction (index of direction) of the first step to (x, y).
    def which_way(self, context: Cowboy | Bullet, pos: tuple[int, int]) -> tuple[int, int]:
        x, y = pos
        if context.position == (x, y):
            return (0, 0)

        if context is None or x < 0 or x >= self.width or y < 0 or y >= self.height:
            return (0, 0)

        dirs = self.dirs_cowboy if type(context) is Cowboy else self.dirs_bullet
        distances = self.a_star(
            context.position,
            (x, y),
            dirs,
            self.manhattan_metric if type(context) is Cowboy else self.maximum_metric)

        # (x, y) will change from here
        while True:
            xy_changed = False
            for d in dirs:
                new_x, new_y = (x + d[0]) % self.width, (y + d[1]) % self.height
                if distances[new_y][new_x] < distances[y][x]:
                    if context.position == (new_x, new_y):
                        return (-d[0], -d[1])
                    x, y = new_x, new_y
                    xy_changed = True
                    break
            if not xy_changed:
                print("Problem in A*.")
                return (0, 0)

    def number_of_golds(self):
        return sum([0 if self.gold_list[i].position is None else 1 for i in range(self.gold_count)])

    def number_of_cowboys(self):
        return len(self.active_cowboys)

    # The coordinates of the i-th currently present gold on the map.
    # Returns (-1, -1) if the index i is out of bounds.
    def gold_i_position(self, i: int) -> tuple[int, int]:
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
    def my_id(self, cowboy: Cowboy) -> int:
        return self.active_cowboys.index(cowboy)

    # My teams's ID
    def my_team(self, context: Cowboy | Bullet) -> int:
        return context.team

    # Helper
    def cowboy_i(self, i: int) -> Cowboy | None:
        if i < 0 or i >= len(self.active_cowboys):
            return None
        return self.active_cowboys[i]

    # The team index of the cowboy with current index i
    # Returns -1 if i is out of bounds.
    def cowboy_i_team(self, i: int) -> int:
        c = self.cowboy_i(i)
        return -1 if c is None else c.team

    # Bullet-specific
    def my_direction(self, bullet: Bullet) -> Direction:
        return self.action_dirs_list[bullet.direction]

    # Bullet's time to live
    def ttl(self, bullet: Bullet) -> int:
        return self.BULLET_LIFETIME - bullet.turns_made