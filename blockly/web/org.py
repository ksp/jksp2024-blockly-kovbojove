from flask import Blueprint, flash, redirect, render_template, session, g
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


@app.route('/org/')
def index():
    return render_template('org_index.html')
