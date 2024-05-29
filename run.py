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


# MALÁ MAPA:
# game_map = GameMap(width=20, height=20, teams=teams,
#                    cowboys_per_team=1,
#                    gold_count=10,
#                    load_saves=True,
#                    save_dir="save_small")

# STŘEDNÍ MAPA:
# game_map = GameMap(width=40, height=40, teams=teams,
#                    cowboys_per_team=4,
#                    gold_count=20,
#                    load_saves=True,
#                    save_dir="save_medium")

# VELKÁ MAPA:
game_map = GameMap(width=50, height=50, teams=teams,
                   cowboys_per_team=10,
                   gold_count=50,
                   wall_fraction=2, cluster_max=500,
                   load_saves=True,
                   save_dir="save_large")

blockly.game.G = blockly.game.Game(teams=teams, map=game_map, org_login="org", org_passwd="org")

# blockly.game.G.startTimer()
signal.signal(signal.SIGINT, stop_handler)

debug = len(sys.argv) > 1 and sys.argv[1] in ("--debug", "-debug")

blockly.web.app.run(debug=debug, threaded=True, processes=1)
