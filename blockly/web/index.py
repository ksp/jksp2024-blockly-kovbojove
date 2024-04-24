from flask import Blueprint, request, jsonify, render_template
import jinja2.filters

from blockly.blocks import cowboy_blocks

import jinja2

app = Blueprint('index', __name__)


@app.route('/')
def index():
    custom_blocks = []
    toolbox_categories = []
    for (name, special, blocks) in cowboy_blocks:
        category = {
            "kind": "category",
            "name": name
        }
        if special and "custom" in special:
            category["custom"] = special["custom"]
        else:
            category["contents"] = []
            for block in blocks:
                category["contents"].append({"kind": "block", "type": block.name})
                if not block.is_blockly_default:
                    custom_blocks.append(block.json_definition())

        toolbox_categories.append(category)

    toolbox = {
        "kind": "categoryToolbox",
        "contents": toolbox_categories
    }

    return render_template(
        'pokus.html',
        toolbox=toolbox, custom_blocks=custom_blocks,
    )


@app.route('/turn', methods=['POST'])
def get_count_route():
    print("Hello world!")
    game_idx = request.json.get('game_idx', 1)
    print(game_idx)
    xml_code = request.json.get('xml_code', 1)

    print(xml_code)

    return jsonify({'positions': 'hello flask'})
