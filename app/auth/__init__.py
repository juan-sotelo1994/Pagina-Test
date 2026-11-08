from flask import Blueprint, render_template, request

# Blueprint de autenticación (login del panel administrativo)
autenticar = Blueprint('autenticar', __name__)


@autenticar.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    correo = ''

    if request.method == 'POST':
        correo = request.form.get('correo', '').strip()
        contrasena = request.form.get('contrasena', '')

        if not correo or not contrasena:
            error = 'Escribe tu correo y tu contraseña.'
        else:
            # Pendiente: validar contra la base de datos de usuarios
            error = 'El inicio de sesión todavía no está conectado a la base de datos de usuarios.'

    return render_template('auth/login.html', error=error, correo=correo)
