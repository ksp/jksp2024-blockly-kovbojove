import string
from flask import Blueprint, Response, flash, g, jsonify, redirect, render_template, request, session
from flask_wtf import FlaskForm  # type: ignore
from werkzeug.exceptions import NotFound
import wtforms
from uuid import uuid4
from simple_websocket import Server, ConnectionClosed  # type: ignore

from blockly import game
from blockly.exceptions import ProgramParseException
from blockly.program import Program
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
def index() -> str:
    G: game.Game = g.G

    return render_template(
        'team_index.html',
        map_state=G.map.get_state(),
    )


@app.route('/statistics')
def statistics() -> str:
    G: game.Game = g.G

    return render_template(
        'statistics.html',
        statistics=G.map.get_statistics(),
    )


@app.route('/ws/map', websocket=True)
def ws_map() -> str:
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
def editor(entity: str) -> str:
    if entity == "cowboy":
        entity_name = "Kovboj"
        blocks_categories = cowboy_blocks
    elif entity == "bullet":
        entity_name = "Střela"
        blocks_categories = bullet_blocks
    else:
        raise NotFound()

    custom_blocks = []
    toolbox_categories = []
    for (name, special, blocks) in blocks_categories:
        category: dict[str, str | list] = {
            "kind": "category",
            "name": name
        }
        if special and "custom" in special:
            category["custom"] = special["custom"]
        else:
            contents = []
            for block in blocks:
                contents.append({"kind": "block", "type": block.name})
                if not block.is_blockly_default:
                    custom_blocks.append(block.json_definition())
            category["contents"] = contents

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


@app.route('/manual')
def manual() -> str:
    G: game.Game = g.G

    return render_template(
        'team_manual.html',
        gold_price=G.map.GOLD_PRICE,
        shotdown_bounty=G.map.SHOTDOWN_BOUNTY,
        turns_to_respawn=G.map.TURNS_TO_RESPAWN,
        bullet_lifetime=G.map.BULLET_LIFETIME
    )


@app.route('/debug')
def debug() -> str:
    G: game.Game = g.G
    team: Team = g.team

    return render_template(
        'team_debug.html',
        cowboy_results=reversed(G.map.get_cowboy_results(team, 5)),
        bullet_results=reversed(G.map.get_bullet_results(team, 5)),
    )


@app.route('/api/<string:entity>', methods=['GET'])
def get_programs(entity: str) -> Response:
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
            "active": uuid == active,
            "valid": program.program.valid()
        })

    out.sort(key=lambda x: str(x['name']))

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
            ok = team.set_active_cowboy(uuid)
        elif entity == "bullet":
            program_info = team.bullet_programs.get(uuid)
            if program_info is None:
                raise NotFound()
            ok = team.set_active_bullet(uuid)
        else:
            raise NotFound()

        if not ok:
            return jsonify({'error': 'Program nelze nastavit jako aktivní'}), 400
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
def set_program(entity: str) -> tuple[Response, int]:
    if entity == "cowboy":
        factories = cowboy_factories
    elif entity == "bullet":
        factories = bullet_factories
    else:
        raise NotFound()

    # Everything comes inside JSON
    data = request.json
    if not isinstance(data, dict):
        return jsonify({'error': 'očekáván JSON objekt'}), 400

    if "uuid" not in data:
        uuid = str(uuid4())
    else:
        uuid = data["uuid"]
        allowed = set(string.ascii_lowercase + string.digits + '-')
        if not set(uuid).issubset(allowed):
            return jsonify({'error': 'uuid obsahuje nepovolené znaky'}), 400

    name = data.get("name")
    description = data.get("description", "")
    raw_program = data.get("program")
    if not isinstance(name, str) or name == "":
        return jsonify({'error': 'Název nesmí být prázdný'}), 400
    if not isinstance(description, str):
        return jsonify({'error': 'Popis není string'}), 400
    if not isinstance(raw_program, str):
        return jsonify({'error': 'Program není string'}), 400

    err: ProgramParseException | None = None
    try:
        parser = Parser(factories)
        program = parser.parse_program(raw_program)
    except ProgramParseException as e:
        err = e
        program = Program(None, None, raw_program)
    except Exception as e:
        return jsonify({'error': f'Problém při parsování programu: {e}'}), 400

    G: game.Game = g.G
    with G.lock:
        team: Team = g.team
        if entity == "cowboy":
            if team.active_cowboy == uuid and not program.valid():
                return jsonify({'error': f'Nelze uložit nevalidní program jako aktivní. Uložte ho jako nový: {err}'}), 400
            team_program = team.save_cowboy(uuid, name, description, program)
            active = team.active_cowboy
        elif entity == "bullet":
            if team.active_bullet == uuid and not program.valid():
                return jsonify({'error': f'Nelze uložit nevalidní program jako aktivní. Uložte ho jako nový: {err}'}), 400
            team_program = team.save_bullet(uuid, name, description, program)
            active = team.active_bullet

    return jsonify({
        "uuid": uuid,
        "name": team_program.name,
        "description": team_program.description,
        "last_modified": team_program.last_modified,
        "active": uuid == active,
        "valid": team_program.program.valid(),
        "error": str(err) if err else None,
    }), 200
