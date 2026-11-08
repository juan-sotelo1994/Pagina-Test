from flask import Flask, render_template, request
import os


app = Flask(__name__)


# resgistro de las importaciones y configuraciones
from auth import autenticar
from dash import dashboard_bp
from web import web_bp


# Registro de blueprints
app.register_blueprint(web_bp)
app.register_blueprint(autenticar)
app.register_blueprint(dashboard_bp)


if __name__ == '__main__':
    app.run(debug=True, port=5711)
