from flask import Flask, flash, g, redirect, request, session, url_for
from flask_bootstrap import Bootstrap5  # type: ignore
from werkzeug.exceptions import Unauthorized

import blockly.game

from . import team
from . import menu
from . import org

app = Flask(__name__, template_folder="../../templates", static_folder="../../static")

# Setup secret key (FIXME: config?)
app.secret_key = "supertajnySecretKey"

# Make bootstrap libs accessible for the app
Bootstrap5(app)

# Add parts of the web from independents files:
app.register_blueprint(team.app)
app.register_blueprint(menu.app)
app.register_blueprint(org.app)


@app.before_request
def init_request():
    path = request.path

    # Allow static without any login
    if path.startswith('/static/'):
        return

    # Set globals
    g.G = blockly.game.G
    g.team = None
    if 'team' in session:
        g.team = g.G.get_team(session['team'])
        if g.team is None:
            flash("Neznámý tým, přihlaste se prosím", "error")
            return redirect(url_for('login', next=path))
    g.is_org = False
    if 'is_org' in session:
        g.is_org = True

    # Check paths
    allow_paths = [url_for('team.login'), url_for('org.login'), url_for('logout')]
    if path in allow_paths:
        return

    elif path.startswith('/org/'):
        if g.is_org:
            return
        elif path.startswith('/org/api/'):
            raise Unauthorized()
        else:
            return redirect(url_for('org.login', next=path))

    elif g.team is None:
        if path.startswith('/api/'):
            raise Unauthorized()
        else:
            return redirect(url_for('team.login', next=path))


@app.route('/logout', methods=('POST',))
def logout():
    session.clear()
    return redirect(url_for('team.login'))
