from flask import Flask, render_template, request
from dotenv import load_dotenv
import os


# Variables secretas desde el archivo .env (no se sube a GitHub)
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ['SECRET_KEY']


# resgistro de las importaciones y configuraciones
from auth import autenticar
from dash import dashboard_bp
from web import web_bp
from api import api_bp


# Registro de blueprints
app.register_blueprint(web_bp)
app.register_blueprint(autenticar)
app.register_blueprint(dashboard_bp)
app.register_blueprint(api_bp)


if __name__ == '__main__':
    # HOST=0.0.0.0 en .env para que los agentes de la red puedan conectarse
    app.run(debug=os.environ.get('FLASK_DEBUG', '1') == '1',
            host=os.environ.get('HOST', '127.0.0.1'), port=5711)
