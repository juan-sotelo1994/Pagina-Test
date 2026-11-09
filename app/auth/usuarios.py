"""Usuarios del panel.

Por ahora se guardan en app/data/usuarios.json con la contraseña cifrada.
Cuando conectemos la base de datos, solo cambian estas funciones.
"""
import re
from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

import almacen

ARCHIVO = 'usuarios.json'
LARGO_MINIMO = 8
PATRON_CORREO = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def listar():
    return almacen.leer(ARCHIVO, [])


def buscar(correo):
    correo = correo.strip().lower()
    return next((u for u in listar() if u['correo'] == correo), None)


def validar(nombre, correo, rol, contrasena, confirmacion, roles_validos, correos_reservados=()):
    # Devuelve un diccionario {campo: mensaje} con los errores encontrados
    errores = {}
    correo = correo.strip().lower()
    if len(nombre.strip()) < 3:
        errores['nombre'] = 'Escribe el nombre completo.'
    if not PATRON_CORREO.match(correo):
        errores['correo'] = 'Escribe un correo válido.'
    elif buscar(correo) or correo in correos_reservados:
        errores['correo'] = 'Ya existe un usuario con ese correo.'
    if rol not in roles_validos:
        errores['rol'] = 'Elige un rol.'
    if len(contrasena) < LARGO_MINIMO:
        errores['contrasena'] = f'La contraseña debe tener al menos {LARGO_MINIMO} caracteres.'
    elif contrasena != confirmacion:
        errores['confirmacion'] = 'Las contraseñas no coinciden.'
    return errores


def crear(nombre, correo, rol, contrasena):
    usuarios = listar()
    usuario = {
        'id': max((u['id'] for u in usuarios), default=0) + 1,
        'nombre': nombre.strip(),
        'correo': correo.strip().lower(),
        'rol': rol,
        'hash': generate_password_hash(contrasena),
        'activo': True,
        'creado': datetime.now().strftime('%Y-%m-%d %H:%M'),
    }
    usuarios.append(usuario)
    almacen.escribir(ARCHIVO, usuarios)
    return usuario


def autenticar(correo, contrasena):
    usuario = buscar(correo)
    if usuario and usuario['activo'] and check_password_hash(usuario['hash'], contrasena):
        return usuario
    return None
