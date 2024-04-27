from random import randrange as rr
import queue

from .team import Team


class Cowboy:
    # Changes every turn
    current_id: int = -1

    def __init__(self, team, index, position_x, position_y):
        self.team = team
        self.index = index
        # Will be None when the cowboy is shot down and waiting to respawn.
        self.position = (position_x, position_y)


class Bullet:
    def __init__(self, team, index, position_x, position_y, direction):
        self.team = team
        self.index = index
        self.position = (position_x, position_y)
        self.direction = direction


class GameMap:
    dirs_cowboy = [(-1, 0), (0, 1), (1, 0), (0, -1)]
    dirs_bullet = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]

    def __init__(
            self,
            width: int,
            height: int,
            teams: list[Team],
            cowboys_per_team: int,
            # The number of golds on the map will be kept constant
            gold_count: int,
            wall_fraction: int = 50,
            cluster_max: int = 5):
        self.width, self.height = width, height
        self.teams = teams
        self.cowboys_per_team = cowboys_per_team
        self.gold_count = gold_count
        self.generate_walls(wall_fraction, cluster_max)

    # `(width * height) // wall_fraction` wall clusters will be generated
    # randomly in the grid, with at most `cluster_max` wall squares each.
    def generate_walls(self, wall_fraction: int = 50, cluster_max: int = 5):
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
    def check_walls(self):
        squares_visited = [[False for _ in range(self.width)] for _ in range(self.height)]
        # Find a starting wall-free square, count the number of free squares.
        free_count = 0
        init_x, init_y = 0, 0
        for y in range(self.height):
            for x in range(self.width):
                if not self.wall_grid[y][x]:
                    free_count += 1
                    init_x, init_y = x, y
        if free_count == 0:
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

        return reached == free_count

    def simulate_cowboys_turn(self):
        pass

    def simulate_bullets_turn(self):
        pass

    # Methods providing information for cowboys and bullets:
    # In all cases, `context` is either a Cowboy or a Bullet object.

    # The objects x-coordinate on the map.
    # Returns -1 if the object is no longer valid.
    def my_x(self, context):
        return -1 if context is None or context.postion is None else context.position[0]

    # The objects y-coordinate on the map.
    # Returns -1 if the object is no longer valid.
    def my_y(self, context):
        return -1 if context is None or context.postion is None else context.position[1]

    # Returns a grid of computed distances from start.
    # Both `distance_from` and `which_way` can then compute what they need
    def a_star(self, start, goal, dirs, metric):
        dists_from_start = [[(2 * self.width * self.height) for _ in range(self.width)] for _ in range(self.height)]

        return dists_from_start

    # This is a method (rather than a separate function) because it depends on width and height
    # (the playfield is a toroid)
    def coord_diffs(self, start, goal):
        x_dif = min(goal[0] - start[0], (self.width + start[0]) - goal[0]) if start[0] < goal[0] else min(start[0] - goal[0], (self.width + goal[0]) - start[0])
        y_dif = min(goal[1] - start[1], (self.width + start[1]) - goal[1]) if start[1] < goal[1] else min(start[1] - goal[1], (self.width + goal[1]) - start[1])
        return (x_dif, y_dif)

    def manhattan_metric(self, start, goal):
        return sum(self.coord_diffs(start, goal))

    def maximum_metric(self, start, goal):
        return max(self.coord_diffs(start, goal))

    # Returns the length of the shortest path of the object to (x, y).
    # If unreachable, returns a sort of "infinite" value
    def distance_from(self, context, x, y):
        if context is None or x < 0 or x >= self.width or y < 0 or y >= self.height:
            return self.width * self.height

        distances = self.a_star(
            context.position,
            (x, y),
            dirs_cowboy if type(context) is Cowboy else dirs_bullet,
            self.manhattan_metric if type(context) is Cowboy else self.maximum_metric)

        return distances[y][x]

    # Returns the direction (index of direction) of the first step to (x, y).
    def which_way(self, context, x, y):
        if context.position == (x, y):
            return 0

        if context is None or x < 0 or x >= self.width or y < 0 or y >= self.height:
            return self.width * self.height

        dirs = dirs_cowboy if type(context) is Cowboy else dirs_bullet
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
                        return (d + (len(dirs) // 2)) % len(dirs)
                    x, y = new_x, new_y
                    xy_changed = True
                    break
            if not xy_changed:
                print("Problem in A*.")
                return 0

    def number_of_golds(self):
        return self.gold_count

    def number_of_cowboys(self):
        pass

    # Helper
    def gold_i_position(self, i):
        pass

    # The x-coordinate of the i-th currently present gold on the map.
    # Returns -1 if the index i is out of bounds.
    def gold_i_position_x(self, i):
        return -1 if i < 0 or i >= self.gold_count else self.gold_i_position(i)[0]

    # The y-coordinate of the i-th currently present gold on the map.
    # Returns -1 if the index i is out of bounds.
    def gold_i_position_y(self, i):
        return -1 if i < 0 or i >= self.gold_count else self.gold_i_position(i)[1]

    def number_of_bullets(self):
        pass

    # The x-coordinate of the i-th currently present bullet on the map.
    # Returns -1 if the index i is out of bounds.
    def bullet_i_position_x(self, i):
        pass

    # The y-coordinate of the i-th currently present bullet on the map.
    # Returns -1 if the index i is out of bounds.
    def bullet_i_position_y(self, i):
        pass

    # How many cowboys are there currently?
    def cowboy_count(self):
        pass

    # This cowboy's index for this turn (assigned randomly)
    def my_id(self):
        pass

    # My teams's ID
    def my_team(self):
        pass

    # The x-coordinate of the cowboy with currently assigned index i.
    # Returns -1 if the index i is out of bounds.
    def cowboy_i_position_x(self):
        pass

    # The y-coordinate of the cowboy with currently assigned index i.
    # Returns -1 if the index i is out of bounds.
    def cowboy_i_position_y(self):
        pass

    # The team index of the cowboy with current index i
    def cowboy_i_team(self):
        pass

    # Bullet-specific
    def my_direction(self, context):
        return -1 if type(context) is not Bullet else context.direction
