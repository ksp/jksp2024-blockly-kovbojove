#!/usr/bin/env python3

import glob
import sys

import blockly.web
import blockly.game
from blockly.map import GameMap
from blockly.team import Team

teams = [
    Team("red", "steamCrazyHorse"),
    Team("green", "lazyCoalSprings"),
    Team("blue", "dryWaterMine"),
    Team("yellow", "burningCoalSprings"),
]

load_from_file = None
save_files = glob.glob("save/save_*.json")
if len(save_files) > 0:
    load_from_file = sorted(save_files)[-1]
    print(f"Loading game from file '{load_from_file}'")

game_map = GameMap(width=40, height=40, teams=teams,
                   cowboys_per_team=4,
                   gold_count=5,
                   load_from_file=load_from_file)

blockly.game.G = blockly.game.Game(teams=teams, map=game_map, org_login="org", org_passwd="org")

debug = len(sys.argv) > 1 and sys.argv[1] in ("--debug", "-debug")

blockly.web.app.run(debug=debug, threaded=True, processes=1)
