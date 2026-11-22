import os
import re
import time
from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from nucleo import correo as correos
from nucleo import db
from nucleo import mensajes
from web import EMPRESA
from . import usuarios

# Blueprint de autenticación (login del panel administrativo)
autenticar = Blueprint('autenticar', __name__)


def correo_admin():
    return os.environ.get('ADMIN_EMAIL', '').strip().lower()


def nombre_admin():
    """(nombres, apellidos) del superadministrador del .env."""
    nombres = ' '.join(os.environ.get('ADMIN_NOMBRES', '').split())
    apellidos = ' '.join(os.environ.get('ADMIN_APELLIDOS', '').split())
    return (nombres, apellidos) if nombres else ('Administrador del sistema', '')


def nombre_de(correo):
    """(nombre completo, nombre corto) de quien inició sesión, para mostrarlo en el panel."""
    if correo and correo == correo_admin():
        nombres, apellidos = nombre_admin()
    else:
        try:
            usuario = usuarios.buscar(correo or '')
        except db.Error:
            usuario = None  # sin conexión a la base: se muestra el correo
        if usuario is None:
            return correo or '', (correo or '').split('@')[0]
        nombres, apellidos = usuarios.separar(usuario)
    return f'{nombres} {apellidos}'.strip(), usuarios.nombre_corto(nombres, apellidos)


def credenciales_validas(correo, contrasena):
    # Usuario administrador definido en .env (la contraseña se guarda cifrada)
    admin_correo = correo_admin()
    admin_hash = os.environ.get('ADMIN_PASSWORD_HASH', '')
    if not admin_correo or not admin_hash:
        return False
    return correo.lower() == admin_correo.lower() and check_password_hash(admin_hash, contrasena)


def login_requerido(vista):
    # Decorador para proteger las vistas del panel
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if 'usuario' not in session or 'rol' not in session:
            session.clear()
            return redirect(url_for('autenticar.login'))
        # En cada clic se revisa que la cuenta siga activa: si la bloquearon, la sesión se cierra
        # y si le cambiaron el rol, se aplica de inmediato
        if session['usuario'] != correo_admin():
            try:
                usuario = usuarios.buscar(session['usuario'])
            except db.Error:
                usuario = False  # sin conexión a la base no se puede revisar; se sigue con la sesión
            if usuario is None or (usuario and not usuario['activo']):
                session.clear()
                flash('Tu cuenta está bloqueada. Si crees que es un error, habla con el administrador.'
                      if usuario else 'Tu sesión terminó. Vuelve a entrar.', 'error')
                return redirect(url_for('autenticar.login'))
            if usuario:
                session['rol'] = usuario['rol']
        return vista(*args, **kwargs)
    return envoltura


@autenticar.route('/login', methods=['GET', 'POST'])
def login():
    if 'usuario' in session and 'rol' in session:
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
            # El administrador del .env es el superadministrador del sistema
            session['rol'] = 'superadmin'
            return redirect(url_for('dashboard.dash_view'))
        else:
            try:
                usuario = usuarios.autenticar(correo, contrasena)
            except db.Error:
                usuario, error = None, 'No hay conexión con la base de datos. Intenta de nuevo en un momento.'
            if usuario and not usuario['activo']:
                # Solo se dice que está bloqueada si la contraseña era correcta
                usuario, error = None, 'Tu cuenta está bloqueada. Si crees que es un error, habla con el administrador.'
            if usuario:
                session.clear()
                session['usuario'] = usuario['correo']
                session['rol'] = usuario['rol']
                session['aviso_inicio'] = True  # la primera página muestra las notificaciones
                return redirect(url_for('dashboard.dash_view'))
            error = error or 'Correo o contraseña incorrectos.'

    return render_template('auth/login.html', error=error, correo=correo)


@autenticar.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('autenticar.login'))


# ---------------------------------------------------------------- Recuperar la cuenta

ESPERA_REENVIO = 30  # segundos antes de poder pedir otro código (lo controla también la base)


def _ocultar(correo):
    """juan.sotelo@gmail.com -> ju*********@gmail.com"""
    usuario, _, dominio = correo.partition('@')
    return f"{usuario[:2]}{'*' * max(len(usuario) - 2, 3)}@{dominio}"


CANALES = {'correo': 'correo electrónico', 'whatsapp': 'WhatsApp'}


def _enviar_codigo(correo, canal):
    """Pide el código a la base y lo envía por el canal elegido. Devuelve un mensaje de error o None."""
    usuario = None
    try:
        usuario = usuarios.buscar(correo)
        # Por WhatsApp solo si el usuario tiene celular; si no, se responde igual pero no se genera nada
        if canal == 'whatsapp' and not (usuario or {}).get('celular'):
            estado, codigo = 'sin_usuario', None
        else:
            estado, codigo = usuarios.solicitar_codigo(correo, request.remote_addr or '')
    except db.Error:
        return 'No hay conexión con la base de datos. Intenta de nuevo en un momento.'
    if estado == 'espera':
        return f'Ya te enviamos un código hace poco. Espera {ESPERA_REENVIO} segundos para pedir otro.'
    if estado == 'enviar':
        try:
            if canal == 'whatsapp':
                mensajes.enviar_codigo(usuario['celular'], codigo, EMPRESA['nombre'], usuarios.MINUTOS_CODIGO)
            else:
                texto = (f'Hola,\n\nTu código para recuperar la contraseña del panel de {EMPRESA["nombre"]} es:\n\n'
                         f'    {codigo}\n\nVence en {usuarios.MINUTOS_CODIGO} minutos y sirve una sola vez.\n'
                         'Si no lo pediste, ignora este correo: tu contraseña sigue igual.')
                html = (f'<p>Hola,</p><p>Tu código para recuperar la contraseña del panel es:</p>'
                        f'<p style="font-size:28px;font-weight:700;letter-spacing:6px">{codigo}</p>'
                        f'<p>Vence en <b>{usuarios.MINUTOS_CODIGO} minutos</b> y sirve una sola vez.</p>'
                        '<p style="color:#666">Si no lo pediste, ignora este correo: tu contraseña sigue igual.</p>')
                correos.enviar(correo, 'Código para recuperar tu contraseña', texto, html)
        except Exception:
            return (f'No se pudo enviar el código por {CANALES[canal]}. Prueba con el otro medio '
                    'o pide ayuda al administrador.')
    # 'sin_usuario' no se informa: así nadie puede averiguar qué correos están registrados
    session['recuperar'] = {'correo': correo, 'canal': canal, 'desde': time.time()}
    return None


@autenticar.route('/recuperar', methods=['GET', 'POST'])
def recuperar():
    error, correo, canal = None, '', 'correo'
    if request.method == 'POST':
        correo = request.form.get('correo', '').strip().lower()
        canal = request.form.get('canal', 'correo')
        if canal not in CANALES:
            canal = 'correo'
        if not usuarios.PATRON_CORREO.match(correo):
            error = 'Escribe un correo válido.'
        elif correo_admin() and correo == correo_admin():
            # Un superadministrador del .env no está en la base: no se le envía código,
            # pero se responde igual que a cualquier correo para no revelar cuál es esa cuenta
            session['recuperar'] = {'correo': correo, 'canal': canal, 'desde': time.time()}
            return redirect(url_for('autenticar.recuperar_codigo'))
        else:
            error = _enviar_codigo(correo, canal)
            if error is None:
                return redirect(url_for('autenticar.recuperar_codigo'))
    return render_template('auth/recuperar.html', error=error, correo=correo, canal=canal)


@autenticar.route('/recuperar/codigo', methods=['GET', 'POST'])
def recuperar_codigo():
    datos = session.get('recuperar')
    if not datos:
        return redirect(url_for('autenticar.recuperar'))
    error, errores = None, {}

    if request.method == 'POST':
        if request.form.get('accion') == 'reenviar':
            error = _enviar_codigo(datos['correo'], datos.get('canal', 'correo'))
            if error is None:
                flash('Te enviamos un código nuevo. El anterior ya no sirve.', 'ok')
                return redirect(url_for('autenticar.recuperar_codigo'))
        else:
            codigo = re.sub(r'\D', '', request.form.get('codigo', ''))
            contrasena = request.form.get('contrasena', '')
            errores = usuarios.validar_contrasena(contrasena, request.form.get('confirmacion', ''))
            if len(codigo) != 6:
                errores['codigo'] = 'El código tiene 6 números.'
            if not errores:
                try:
                    cambiada = usuarios.cambiar_con_codigo(datos['correo'], codigo, contrasena)
                except db.Error:
                    cambiada, error = False, 'No hay conexión con la base de datos. Intenta de nuevo en un momento.'
                if cambiada:
                    session.pop('recuperar', None)
                    flash('Listo: tu contraseña se cambió. Ya puedes ingresar con la nueva.', 'ok')
                    return redirect(url_for('autenticar.login'))
                error = error or 'El código no es correcto o ya venció. Revisa el correo o pide uno nuevo.'

    restante = max(0, int(datos['desde'] + usuarios.MINUTOS_CODIGO * 60 - time.time()))
    reenviar_en = max(0, int(datos['desde'] + ESPERA_REENVIO - time.time()))
    return render_template('auth/recuperar_codigo.html', error=error, errores=errores,
                           correo_oculto=_ocultar(datos['correo']), canal=datos.get('canal', 'correo'),
                           restante=restante, reenviar_en=reenviar_en)
