import os
from functools import wraps

from flask import Blueprint, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

# Blueprint de autenticación (login del panel administrativo)
autenticar = Blueprint('autenticar', __name__)


def credenciales_validas(correo, contrasena):
    # Usuario administrador definido en .env (la contraseña se guarda cifrada)
    admin_correo = os.environ.get('ADMIN_EMAIL', '')
    admin_hash = os.environ.get('ADMIN_PASSWORD_HASH', '')
    if not admin_correo or not admin_hash:
        return False
    return correo.lower() == admin_correo.lower() and check_password_hash(admin_hash, contrasena)


def login_requerido(vista):
    # Decorador para proteger las vistas del panel
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if 'usuario' not in session:
            return redirect(url_for('autenticar.login'))
        return vista(*args, **kwargs)
    return envoltura


@autenticar.route('/login', methods=['GET', 'POST'])
def login():
    if 'usuario' in session:
        return redirect(url_for('dashboard.dash_view'))

    error = None
    correo = ''

    if request.method == 'POST':
        correo = request.form.get('correo', '').strip()
        contrasena = request.form.get('contrasena', '')

        if not correo or not contrasena:
            error = 'Escribe tu correo y tu contraseña.'
        elif credenciales_validas(correo, contrasena):
            session.clear()
            session['usuario'] = correo.lower()
            return redirect(url_for('dashboard.dash_view'))
        else:
            error = 'Correo o contraseña incorrectos.'

    return render_template('auth/login.html', error=error, correo=correo)


@autenticar.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('autenticar.login'))
