from random import randrange as rr
import queue


class GameMap:
    dirs_cowboy = [(-1, 0), (0, 1), (1, 0), (0, -1)]
    dirs_bullet = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]

    def __init__(
            self,
            width: int,
            height: int,
            wall_fraction: int = 50,
            cluster_max: int = 5):
        self.width, self.height = width, height
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
