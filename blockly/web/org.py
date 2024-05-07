from flask import Blueprint, flash, redirect, render_template, session, url_for, g
from flask_wtf import FlaskForm  # type: ignore
import wtforms
from wtforms import validators

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


@app.route('/org/', methods=('GET', 'POST'))
def index():
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
                        cowboy_turn_period=float(timer_form.cowboy_turn_period.data),
                        bullet_turn_period=float(timer_form.bullet_turn_period.data),
                        bullet_turns=timer_form.bullet_turns.data,
                    )
                    flash("Timer spuštěn", "success")

                elif timer_form.stop.data:
                    G.stop_timer()
                    flash("Timer zastaven", "warning")

        return redirect(url_for("org.index"))

    timer_form.cowboy_turn_period.data = G.timer_cowboy_turn_period
    timer_form.bullet_turn_period.data = G.timer_bullet_turn_period
    timer_form.bullet_turns.data = G.timer_bullet_turns

    grid_size, cowboys, bullets, walls, golds, current_explosions, current_gun_triggers = G.map.get_state_debug()

    return render_template(
        'org_index.html',
        action_form=action_form,
        timer_form=timer_form,
        square_half=10,
        grid_width=grid_size[0],
        grid_height=grid_size[1],
        walls = [[w[0], w[1]] for w in walls],
        golds = [[g[0], g[1]] for g in golds],
        cowboys = [[x, y, t] for ((x, y), t) in cowboys],
        bullets = [[x, y, t] for ((x, y), t) in bullets],
        explosions = [[ce[0], ce[1]] for ce in current_explosions],
        shot_directions = [[cgt[0], cgt[1], cgt[2]] for cgt in current_gun_triggers])
