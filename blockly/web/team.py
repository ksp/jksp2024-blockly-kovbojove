import string
from flask import Blueprint, Response, flash, g, jsonify, redirect, render_template, request, session
from flask_wtf import FlaskForm  # type: ignore
from werkzeug.exceptions import NotFound
import wtforms
from uuid import uuid4
from simple_websocket import Server, ConnectionClosed

from blockly import game
from blockly.team import Team
from blockly.parser import Parser
from blockly.blocks import bullet_blocks, bullet_factories, cowboy_blocks, cowboy_factories

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
    G: game.Game = g.G

    return render_template(
        'team_index.html',
        map_state=G.map.get_state(),
    )


@app.route('/ws/map', websocket=True)
def ws_map():
    ws = Server.accept(request.environ)

    G: game.Game = g.G
    G.ws_connect(ws)
    try:
        while True:
            data = ws.receive()
            ws.send(data)
    except ConnectionClosed:
        G.ws_disconnect(ws)

    return ''


@app.route('/<string:entity>-editor')
def editor(entity: str):
    if entity == "cowboy":
        entity_name = "Kovboj"
        blocks = cowboy_blocks
    elif entity == "bullet":
        entity_name = "Střela"
        blocks = bullet_blocks
    else:
        raise NotFound()

    custom_blocks = []
    toolbox_categories = []
    for (name, special, blocks) in blocks:
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
        'team_editor.html',
        entity=entity, entity_name=entity_name,
        toolbox=toolbox, custom_blocks=custom_blocks,
    )


@app.route('/api/<string:entity>', methods=['GET'])
def get_programs(entity: str):
    team: Team = g.team

    if entity == "cowboy":
        active = team.active_cowboy
        programs = team.cowboy_programs
    elif entity == "bullet":
        active = team.active_bullet
        programs = team.bullet_programs
    else:
        raise NotFound()

    out = []
    for uuid, program in programs.items():
        out.append({
            "uuid": uuid,
            "name": program.name,
            "description": program.description,
            "last_modified": program.last_modified,
            "active": uuid == active
        })

    out.sort(key=lambda x: x['name'])

    return jsonify(out)


@app.route('/api/<string:entity>/<string:uuid>/code', methods=['GET'])
def get_program_code(entity: str, uuid: str):
    team: Team = g.team

    if entity == "cowboy":
        programs = team.cowboy_programs
    elif entity == "bullet":
        programs = team.bullet_programs
    else:
        raise NotFound()

    program_info = programs.get(uuid)
    if program_info is None:
        raise NotFound()
    return Response(program_info.program.raw_xml, mimetype='text/xml')


@app.route('/api/<string:entity>/<string:uuid>/active', methods=['POST'])
def set_active_program(entity: str, uuid: str):
    G: game.Game = g.G
    with G.lock:
        team: Team = g.team

        if entity == "cowboy":
            program_info = team.cowboy_programs.get(uuid)
            if program_info is None:
                raise NotFound()
            team.set_active_cowboy(uuid)
        elif entity == "bullet":
            program_info = team.bullet_programs.get(uuid)
            if program_info is None:
                raise NotFound()
            team.set_active_bullet(uuid)
        else:
            raise NotFound()

        return jsonify({'ok': 'ok'})


@app.route('/api/<string:entity>/<string:uuid>', methods=['DELETE'])
def delete_program(entity: str, uuid: str):
    G: game.Game = g.G
    with G.lock:
        team: Team = g.team

        if entity == "cowboy":
            program_info = team.cowboy_programs.get(uuid)
            active = team.active_cowboy
            d_func = team.delete_cowboy
        elif entity == "bullet":
            program_info = team.bullet_programs.get(uuid)
            active = team.active_bullet
            d_func = team.delete_bullet
        else:
            raise NotFound()

        if program_info is None:
            return jsonify({'error': 'Program neexistuje'}), 404
        elif uuid == active:
            return jsonify({'error': 'Nelze smazat aktivní program'}), 400
        else:
            d_func(uuid)
            return jsonify({'ok': 'ok'})


@app.route('/api/<string:entity>', methods=['POST'])
def set_program(entity: str):
    if entity == "cowboy":
        factories = cowboy_factories
    elif entity == "bullet":
        factories = bullet_factories
    else:
        raise NotFound()

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
        parser = Parser(factories)
        program = parser.parse_program(data.get("program"))
    except Exception as e:
        return jsonify({'error': f'Problém při parsování programu: {e}'}), 400

    G: game.Game = g.G
    with G.lock:
        team: Team = g.team
        if entity == "cowboy":
            program = team.save_cowboy(uuid, name, description, program)
            active = team.active_cowboy
        elif entity == "bullet":
            program = team.save_bullet(uuid, name, description, program)
            active = team.active_bullet

        return jsonify({
            "uuid": uuid,
            "name": program.name,
            "description": program.description,
            "last_modified": program.last_modified,
            "active": uuid == active
        })
