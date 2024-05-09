# Web: Menu

from flask import Blueprint, request, url_for, g
from typing import List, Optional

app = Blueprint('menu', __name__)


class MenuItem:
    url: str
    name: str
    active_prefix: str
    classes: List[str]

    def __init__(self, url: str, name: str, active_prefix: Optional[str] = None, classes: Optional[List[str]] = None):
        self.url = url
        self.name = name
        self.active_prefix = active_prefix or url
        self.classes = classes or []


@app.app_template_global(name="get_menu")
def get_menu():
    if g.is_org:
        items = [
            MenuItem(url_for('org.map'), "Mapa"),
            MenuItem(url_for('org.control'), "Ovládání"),
        ]

    elif g.team:
        items = [
            MenuItem(url_for('team.index'), "Mapa"),
            MenuItem(url_for('team.editor', entity="cowboy"), "Kovboj"),
            MenuItem(url_for('team.editor', entity="bullet"), "Střela"),
            MenuItem(url_for('team.debug'), "Log akcí"),
        ]

    else:
        items = [
            MenuItem(url_for('team.login', next=request.path), "Přihlásit se", classes=["right"]),
        ]

    active = None
    for item in items:
        if not request.path.startswith(item.active_prefix):
            continue
        if active is None or len(item.active_prefix) > len(active.active_prefix):
            active = item
    if active is not None:
        active.classes.append("active")

    return items
