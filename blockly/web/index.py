from flask import Blueprint, request, jsonify, render_template

app = Blueprint('index', __name__)


@app.route('/')
def index():
    return render_template('pokus.html')


@app.route('/turn', methods=['POST'])
def get_count_route():
    print("Hello world!")
    game_idx = request.json.get('game_idx', 1)
    print(game_idx)
    xml_code = request.json.get('xml_code', 1)

    print(xml_code)

    return jsonify({'positions': 'hello flask'})
