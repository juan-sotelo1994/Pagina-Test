from flask import Blueprint

# Blueprint de autenticación (login del panel administrativo)
autenticar = Blueprint('autenticar', __name__)


@autenticar.route('/login')
def login():
    # Pendiente: formulario de login con templates/baselogin.html
    return 'Login en construcción'
