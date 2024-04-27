import string
from flask import Blueprint, Response, flash, g, jsonify, redirect, render_template, request, session
from flask_wtf import FlaskForm  # type: ignore
from werkzeug.exceptions import NotFound
import wtforms
from uuid import uuid4

from blockly import game
from blockly.team import Team
from blockly.parser import Parser
from blockly.blocks import cowboy_blocks, cowboy_factories

app = Blueprint('team', __name__)


class LoginForm(FlaskForm):
    login = wtforms.StringField('Login')
    passwd = wtforms.PasswordField('Heslo')
    submit = wtforms.SubmitField('Přihlásit se')


@app.route('/login', methods=('GET', 'POST'))
def login(next: str = "/"):
    form = LoginForm()

    if g.team:
        return redirect(next)

    if form.validate_on_submit():
        G: game.Game = g.G
        if form.login.data is not None:
            team = G.get_team(form.login.data)
        if team is None:
            flash("Neexistující tým", "danger")
        elif team.password != form.passwd.data:
            flash("Chybné heslo", "danger")
        else:
            session.clear()
            session['team'] = team.login
            return redirect(next)

    return render_template('team_login.html', form=form)


@app.route('/')
def index():
    return render_template('team_index.html')


@app.route('/cowboy-editor')
def cowboy_editor():
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
        'team_cowboy.html',
        toolbox=toolbox, custom_blocks=custom_blocks,
    )


@app.route('/api/cowboy', methods=['GET'])
def get_cowboys():
    team: Team = g.team
    active = team.active_cowboy
    cowboys = team.cowboy_programs

    out = []
    for uuid, cowboy in cowboys.items():
        out.append({
            "uuid": uuid,
            "name": cowboy.name,
            "description": cowboy.description,
            "last_modified": cowboy.last_modified,
            "active": uuid == active
        })

    out.sort(key=lambda x: x['name'])

    return jsonify(out)


@app.route('/api/cowboy/<string:uuid>/code', methods=['GET'])
def get_cowboy_code(uuid: str):
    team: Team = g.team
    program_info = team.cowboy_programs.get(uuid)
    if program_info is None:
        raise NotFound()
    return Response(program_info.program.raw_xml, mimetype='text/xml')


@app.route('/api/cowboy/<string:uuid>/active', methods=['POST'])
def cowboy_set_active(uuid: str):
    team: Team = g.team
    program_info = team.cowboy_programs.get(uuid)
    if program_info is None:
        raise NotFound()
    team.set_active_cowboy(uuid)

    return jsonify({'ok': 'ok'})


@app.route('/api/cowboy/<string:uuid>', methods=['DELETE'])
def delete_cowboy(uuid: str):
    team: Team = g.team
    program_info = team.cowboy_programs.get(uuid)
    active = team.active_cowboy

    if program_info is None:
        return jsonify({'error': 'Kovboj neexistuje'}), 404
    elif uuid == active:
        return jsonify({'error': 'Nelze smazat aktivního kovboje'}), 400
    else:
        team.delete_cowboy(uuid)
        return jsonify({'ok': 'ok'})


@app.route('/api/cowboy', methods=['POST'])
def set_cowboy():
    # Everything comes inside JSON
    data = request.json
    if "uuid" not in data:
        uuid = str(uuid4())
    else:
        uuid = data["uuid"]
        allowed = set(string.ascii_lowercase + string.digits + '-')
        if not set(uuid).issubset(allowed):
            return jsonify({'error': 'uuid obsahuje nepovolené znaky'}), 400

    name = data.get("name", "")
    if name == "":
        return jsonify({'error': 'Název nesmí být prázdný'}), 400
    description = data.get("description", "")

    try:
        parser = Parser(cowboy_factories)
        program = parser.parse_program(data.get("program"))
    except Exception as e:
        return jsonify({'error': f'Problém při parsování programu: {e}'}), 400

    team: Team = g.team
    cowboy = team.save_cowboy(uuid, name, description, program)
    active = team.active_cowboy

    return jsonify({
        "uuid": uuid,
        "name": cowboy.name,
        "description": cowboy.description,
        "last_modified": cowboy.last_modified,
        "active": uuid == active
    })


@app.route('/turn', methods=['POST'])
def get_count_route():
    print("Hello world!")
    game_idx = request.json.get('game_idx', 1)
    print(game_idx)
    xml_code = request.json.get('xml_code', 1)

    print(xml_code)

    return jsonify({'positions': 'hello flask'})
