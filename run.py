#!/usr/bin/env python3

import glob
import signal
import sys
from pathlib import Path

import blockly.web
import blockly.game
from blockly.map import GameMap
from blockly.team import Team, data_dir as teams_dir

save_dir = "save"

# Ensure directories exists
Path(save_dir).mkdir(parents=True, exist_ok=True)
Path(teams_dir).mkdir(parents=True, exist_ok=True)

teams = [
    Team("red", "steamCrazyHorse"),
    Team("green", "lazyCoalSprings"),
    Team("blue", "dryWaterMine"),
    Team("yellow", "burningCoalSprings"),
]


def stop_handler(sig, frame):
    blockly.game.G.stop_timer()
    sys.exit(0)


load_from_file = None
save_files = glob.glob(f"{save_dir}/save_*.json")
if len(save_files) > 0:
    load_from_file = sorted(save_files)[-1]
    print(f"Loading game from file '{load_from_file}'")

game_map = GameMap(width=40, height=40, teams=teams,
                   cowboys_per_team=4,
                   gold_count=5,
                   load_from_file=load_from_file,
                   save_dir=save_dir)

blockly.game.G = blockly.game.Game(teams=teams, map=game_map, org_login="org", org_passwd="org")

# blockly.game.G.startTimer()
signal.signal(signal.SIGINT, stop_handler)

debug = len(sys.argv) > 1 and sys.argv[1] in ("--debug", "-debug")

blockly.web.app.run(debug=debug, threaded=True, processes=1)
