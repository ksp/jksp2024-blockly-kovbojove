from decimal import Decimal
from flask import Blueprint, flash, redirect, render_template, request, session, url_for, g
from flask_wtf import FlaskForm  # type: ignore
from werkzeug.wrappers.response import Response
import wtforms
from wtforms import validators
from simple_websocket import Server, ConnectionClosed  # type: ignore

from blockly import game

app = Blueprint('org', __name__)


class LoginForm(FlaskForm):
    login = wtforms.StringField('Login')
    passwd = wtforms.PasswordField('Heslo')
    submit = wtforms.SubmitField('Přihlásit se')


@app.route('/org/login', methods=('GET', 'POST'))
def login(next: str = "/org/") -> Response | str:
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
def map() -> str:
    G: game.Game = g.G

    states = [G.map.get_state()]

    return render_template('org_map.html', states=states)


@app.route('/org/playback')
def map_playback() -> str:
    G: game.Game = g.G

    states = [
        G.map.get_state(i) for i in range(len(G.map.all_rounds))
    ]

    return render_template('org_map.html', states=states)


@app.route('/org/statistics')
def statistics() -> str:
    G: game.Game = g.G

    return render_template(
        'statistics.html',
        statistics=G.map.get_statistics(),
    )


class ActionForm(FlaskForm):
    calc_cowboys = wtforms.SubmitField('Kolo kovbojů')
    calc_bullets = wtforms.SubmitField('Kolo střel')


class TimerForm(FlaskForm):
    cowboy_turn_period = wtforms.DecimalField("Kolo kovboje (s)", validators=[
        validators.DataRequired(), validators.NumberRange(0.1),
    ], render_kw={'step': 0.1})
    bullet_turn_period = wtforms.DecimalField("Kolo střely (s)", validators=[
        validators.DataRequired(), validators.NumberRange(0.1),
    ], render_kw={'step': 0.1})
    bullet_turns = wtforms.IntegerField("Počet tahů střel", validators=[
        validators.DataRequired(), validators.NumberRange(1),
    ], render_kw={'step': 1})
    stop = wtforms.SubmitField('Zastavit timer')
    start = wtforms.SubmitField('Spustit timer')


@app.route('/org/control', methods=('GET', 'POST'))
def control() -> Response | str:
    G: game.Game = g.G
    action_form = ActionForm()
    timer_form = TimerForm()

    if action_form.is_submitted():
        with G.lock:
            if action_form.validate_on_submit():
                if action_form.calc_cowboys.data:
                    G.map.simulate_cowboys_turn()
                    flash("Kolo kovbojů spočítáno", "success")

                elif action_form.calc_bullets.data:
                    G.map.simulate_bullets_turn()
                    flash("Kolo střel spočítáno", "success")

            if timer_form.validate_on_submit():
                if timer_form.start.data:
                    G.start_timer(
                        cowboy_turn_period=float(timer_form.cowboy_turn_period.data or G.timer_cowboy_turn_period),
                        bullet_turn_period=float(timer_form.bullet_turn_period.data or G.timer_bullet_turn_period),
                        bullet_turns=timer_form.bullet_turns.data or G.timer_bullet_turns,
                    )
                    flash("Timer spuštěn", "success")

                elif timer_form.stop.data:
                    G.stop_timer()
                    flash("Timer zastaven", "warning")

        return redirect(url_for("org.control"))

    timer_form.cowboy_turn_period.data = Decimal(G.timer_cowboy_turn_period)
    timer_form.bullet_turn_period.data = Decimal(G.timer_bullet_turn_period)
    timer_form.bullet_turns.data = G.timer_bullet_turns

    return render_template(
        'org_control.html',
        timer_running=G.timer is not None,
        action_form=action_form,
        timer_form=timer_form,
    )


@app.route('/org/ws/map', websocket=True)
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
