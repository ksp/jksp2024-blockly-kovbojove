#!/usr/bin/env python3

import glob
import signal
import sys
from pathlib import Path

import blockly.web
import blockly.game
from blockly.map import GameMap
from blockly.team import Team, data_dir as teams_dir


# Ensure directories exists
save_dirs = ["save_small", "save_medium", "save_large"]
for save_dir in save_dirs:
    Path(save_dir).mkdir(parents=True, exist_ok=True)

Path(teams_dir).mkdir(parents=True, exist_ok=True)

teams = [
    Team("red", "steamCrazyHorse"),
    Team("green", "lazyCoalSprings"),
    Team("blue", "dryWaterMine"),
    Team("yellow", "burningCoalSprings"),
    Team("pink", "drySteamTelegram"),
    Team("violet", "heroicOldCowboy"),
    Team("olive", "funnySmallBuffalo"),
    Team("maroon", "sweetDeadWhisky"),
    Team("black", "brokenLittleRevolver"),
    Team("white", "lazyWiseSheriff"),
]


def stop_handler(sig, frame):
    blockly.game.G.stop_timer()
    sys.exit(0)


load_from_file = {}
for save_dir in save_dirs:
    load_from_file[save_dir] = None
    save_files = glob.glob(f"{save_dir}/save_*.json")
    if len(save_files) > 0:
        load_from_file[save_dir] = sorted(save_files)[-1]
        print(f"Loading game from file '{load_from_file[save_dir]}'")

# MALÁ MAPA:
# game_map = GameMap(width=20, height=20, teams=teams,
#                    cowboys_per_team=1,
#                    gold_count=10,
#                    load_from_file=load_from_file["save_small"],
#                    save_dir="save_small")

# STŘEDNÍ MAPA:
# game_map = GameMap(width=40, height=40, teams=teams,
#                    cowboys_per_team=4,
#                    gold_count=20,
#                    load_from_file=load_from_file["save_medium"],
#                    save_dir="save_medium")

# VELKÁ MAPA:
game_map = GameMap(width=50, height=50, teams=teams,
                   cowboys_per_team=10,
                   gold_count=50,
                   wall_fraction=2, cluster_max=500,
                   load_from_file=load_from_file["save_large"],
                   save_dir="save_large")

blockly.game.G = blockly.game.Game(teams=teams, map=game_map, org_login="org", org_passwd="org")

# blockly.game.G.startTimer()
signal.signal(signal.SIGINT, stop_handler)

debug = len(sys.argv) > 1 and sys.argv[1] in ("--debug", "-debug")

blockly.web.app.run(debug=debug, threaded=True, processes=1)
