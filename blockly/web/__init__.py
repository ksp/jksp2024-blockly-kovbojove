from flask import Flask

from . import index

app = Flask(__name__, template_folder="../../templates", static_folder="../../static")

# Add parts of the web from independents files:
app.register_blueprint(index.app)
