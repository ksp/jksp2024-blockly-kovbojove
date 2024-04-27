#!/usr/bin/env python3

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

game_map = GameMap(40, 40, teams)

blockly.game.G = blockly.game.Game(teams=teams, map=game_map, org_login="org", org_passwd="org")

debug = len(sys.argv) > 1 and sys.argv[1] in ("--debug", "-debug")

blockly.web.app.run(debug=debug, threaded=True, processes=1)
