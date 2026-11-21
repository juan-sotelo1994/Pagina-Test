"""Usuarios del panel, guardados en PostgreSQL (tabla usuarios).

La contraseña se guarda cifrada (columna hash); nunca en texto plano.
La recuperación de contraseña usa las funciones solicitar_recuperacion() y
validar_recuperacion() de la base (ver db/esquema.sql).
"""
import hashlib
import hmac
import os
import re
import secrets

from werkzeug.security import check_password_hash, generate_password_hash

from nucleo import db

LARGO_MINIMO = 8
PATRON_CORREO = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
MINUTOS_CODIGO = 2  # el vencimiento lo pone la base (recuperacion_clave.vence)


def _formato(fila):
    # Mismo formato que usa el resto del panel
    if fila is None:
        return None
    return {**fila, 'nombre': f"{fila['nombres']} {fila['apellidos']}".strip(),
            'creado': fila['creado'].strftime('%Y-%m-%d %H:%M')}


def listar():
    with db.conectar() as cx:
        return [_formato(f) for f in cx.execute('SELECT * FROM usuarios ORDER BY creado')]


def buscar(correo):
    correo = (correo or '').strip().lower()
    if not correo:
        return None
    with db.conectar() as cx:
        return _formato(cx.execute('SELECT * FROM usuarios WHERE correo = %s', (correo,)).fetchone())


def nombre_corto(nombres, apellidos=''):
    """Primer nombre y primer apellido: 'Juan David' + 'Sotelo Ramírez' -> 'Juan Sotelo'."""
    partes = [p.split()[0] for p in (nombres, apellidos) if p and p.split()]
    return ' '.join(partes)


def separar(usuario):
    """(nombres, apellidos) del usuario."""
    return usuario.get('nombres', ''), usuario.get('apellidos', '')


def validar_contrasena(contrasena, confirmacion):
    errores = {}
    if len(contrasena) < LARGO_MINIMO:
        errores['contrasena'] = f'La contraseña debe tener al menos {LARGO_MINIMO} caracteres.'
    elif contrasena != confirmacion:
        errores['confirmacion'] = 'Las contraseñas no coinciden.'
    return errores


def normalizar_celular(texto):
    """'300 123 4567' -> '+573001234567' (Colombia por defecto). Vacío -> ''. Devuelve None si no es válido."""
    limpio = re.sub(r'[\s().-]', '', texto or '')
    if not limpio:
        return ''
    if re.fullmatch(r'3\d{9}', limpio):          # celular colombiano sin indicativo
        limpio = '+57' + limpio
    elif re.fullmatch(r'57\d{10}', limpio):
        limpio = '+' + limpio
    return limpio if re.fullmatch(r'\+[1-9]\d{7,14}', limpio) else None


def validar(datos, roles_validos, usuario_id=None, contrasena='', confirmacion='', exigir_clave=True):
    """datos: nombres, apellidos, correo, celular, rol. Devuelve (datos limpios, errores)."""
    errores = {}
    limpio = {
        'nombres': ' '.join(datos.get('nombres', '').split()),
        'apellidos': ' '.join(datos.get('apellidos', '').split()),
        'correo': datos.get('correo', '').strip().lower(),
        'celular': normalizar_celular(datos.get('celular', '')),
        'rol': datos.get('rol', ''),
    }
    if len(limpio['nombres']) < 2:
        errores['nombres'] = 'Escribe el nombre.'
    if len(limpio['apellidos']) < 2:
        errores['apellidos'] = 'Escribe el apellido.'
    if not PATRON_CORREO.match(limpio['correo']):
        errores['correo'] = 'Escribe un correo válido.'
    else:
        otro = buscar(limpio['correo'])
        if otro and otro['id'] != usuario_id:
            errores['correo'] = 'Ya existe un usuario con ese correo.'
    if limpio['celular'] is None:
        errores['celular'] = 'Celular no válido. Ejemplo: 300 123 4567 o +57 300 123 4567.'
        limpio['celular'] = datos.get('celular', '')
    if limpio['rol'] not in roles_validos:
        errores['rol'] = 'Elige un rol.'
    if exigir_clave or contrasena or confirmacion:
        errores.update(validar_contrasena(contrasena, confirmacion))
    return limpio, errores


def obtener(usuario_id):
    with db.conectar() as cx:
        return _formato(cx.execute('SELECT * FROM usuarios WHERE id = %s', (usuario_id,)).fetchone())


def crear(datos, contrasena):
    with db.conectar() as cx:
        fila = cx.execute(
            'INSERT INTO usuarios (nombres, apellidos, correo, celular, rol, hash) VALUES (%s, %s, %s, %s, %s, %s) RETURNING *',
            (datos['nombres'], datos['apellidos'], datos['correo'], datos['celular'], datos['rol'],
             generate_password_hash(contrasena))).fetchone()
    return _formato(fila)


def actualizar(usuario_id, datos, activo=True, contrasena=''):
    """Cambia los datos del usuario; la contraseña solo si se escribió una nueva."""
    with db.conectar() as cx:
        fila = cx.execute(
            'UPDATE usuarios SET nombres = %s, apellidos = %s, correo = %s, celular = %s, rol = %s, activo = %s'
            + (', hash = %s' if contrasena else '') + ' WHERE id = %s RETURNING *',
            (datos['nombres'], datos['apellidos'], datos['correo'], datos['celular'], datos['rol'], activo,
             *([generate_password_hash(contrasena)] if contrasena else []), usuario_id)).fetchone()
    return _formato(fila)


def para_formulario(usuario):
    """Datos para precargar el formulario de edición (sin la contraseña cifrada)."""
    return {k: usuario[k] for k in ('id', 'nombres', 'apellidos', 'correo', 'celular', 'rol')} | {
        'activo': '1' if usuario['activo'] else '0'}


def autenticar(correo, contrasena):
    usuario = buscar(correo)
    if usuario and usuario['activo'] and check_password_hash(usuario['hash'], contrasena):
        return usuario
    return None


# ---------------------------------------------------------------- Recuperar la contraseña

def _cifrar_codigo(correo, codigo):
    # HMAC con la SECRET_KEY: aunque alguien lea la tabla, no puede sacar el código
    clave = os.environ['SECRET_KEY'].encode()
    return hmac.new(clave, f'{correo.strip().lower()}:{codigo}'.encode(), hashlib.sha256).hexdigest()


def solicitar_codigo(correo, ip=''):
    """Devuelve (estado, código). El código solo viene cuando estado == 'enviar'."""
    codigo = f'{secrets.randbelow(10 ** 6):06d}'
    with db.conectar() as cx:
        estado = cx.execute('SELECT solicitar_recuperacion(%s, %s, %s) AS estado',
                            (correo, _cifrar_codigo(correo, codigo), ip)).fetchone()['estado']
    return estado, (codigo if estado == 'enviar' else None)


def cambiar_con_codigo(correo, codigo, contrasena_nueva):
    """Si el código es correcto y vigente, cambia la contraseña. Devuelve True o False."""
    with db.conectar() as cx:
        usuario_id = cx.execute('SELECT validar_recuperacion(%s, %s) AS id',
                                (correo, _cifrar_codigo(correo, codigo))).fetchone()['id']
        if usuario_id is None:
            return False
        cx.execute('UPDATE usuarios SET hash = %s WHERE id = %s', (generate_password_hash(contrasena_nueva), usuario_id))
    return True
