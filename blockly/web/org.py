from flask import Blueprint, flash, redirect, render_template, session, url_for, g
from flask_wtf import FlaskForm  # type: ignore
import wtforms

from blockly import game

app = Blueprint('org', __name__)


class LoginForm(FlaskForm):
    login = wtforms.StringField('Login')
    passwd = wtforms.PasswordField('Heslo')
    submit = wtforms.SubmitField('Přihlásit se')


@app.route('/org/login', methods=('GET', 'POST'))
def login(next: str = "/org/"):
    form = LoginForm()

    if g.is_org:
        return redirect(next)

    if form.validate_on_submit():
        G: game.Game = g.G

        if form.login.data == G.org_login and form.passwd.data == G.org_passwd:
            session.clear()
            session['is_org'] = True
            return redirect(next)
        else:
            flash("Špatný login nebo heslo", "error")

    return render_template('org_login.html', form=form)


class ActionForm(FlaskForm):
    calc_cowboys = wtforms.SubmitField('Kolo kovbojů')
    calc_bullets = wtforms.SubmitField('Kolo střel')


@app.route('/org/', methods=('GET', 'POST'))
def index():
    action_form = ActionForm()
    G: game.Game = g.G

    if action_form.validate_on_submit():
        if action_form.calc_cowboys.data:
            G.map.simulate_cowboys_turn()
            flash("Kolo kovbojů spočítáno", "success")

        elif action_form.calc_bullets.data:
            G.map.simulate_bullets_turn()
            flash("Kolo střel spočítáno", "success")

        return redirect(url_for("org.index"))

    grid_size, cowboys, bullets, walls, golds = G.map.get_state_debug()

    return render_template(
        'org_index.html',
        action_form=action_form,
        square_half=10,
        grid_width=grid_size[0],
        grid_height=grid_size[1],
        walls = [[w[0], w[1]] for w in walls],
        golds = [[g[0], g[1]] for g in golds],
        cowboys = [[x, y, t] for ((x, y), t) in cowboys],
        bullets = [[x, y, t] for ((x, y), t) in bullets])
