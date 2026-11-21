"""Proveedores: a quienes les compramos insumos, productos, equipos o licencias.

Se guardan en app/data/proveedores.json. Los productos y equipos de renta
pueden tener un proveedor (proveedor_id) para saber a quién volver a pedir.
"""
import re
import threading
import uuid
from datetime import datetime

from nucleo import almacen
from .clientes import PATRON_CORREO, PATRON_NIT, normalizar_nit

ARCHIVO = 'proveedores.json'

TIPOS = ['Mayorista', 'Distribuidor', 'Fabricante', 'Software y licencias', 'Servicios', 'Otro']
SUMINISTRA = ['Computadores', 'Servidores', 'Redes', 'Almacenamiento', 'Periféricos', 'Licencias',
              'Seguridad', 'Repuestos', 'Nube', 'Servicios técnicos', 'Otros']
CONDICIONES_PAGO = ['Contado', 'Anticipo', 'Crédito 30 días', 'Crédito 45 días', 'Crédito 60 días', 'Crédito 90 días']

CAMPOS = ('nombre', 'nit', 'tipo', 'contacto', 'cargo', 'correo', 'telefono', 'ciudad', 'direccion', 'sitio_web',
          'condiciones_pago', 'tiempo_entrega', 'notas')
_lock = threading.Lock()


def listar(solo_activos=False):
    lista = sorted(almacen.leer(ARCHIVO, []), key=lambda p: p['nombre'].lower())
    return [p for p in lista if p.get('activo', True)] if solo_activos else lista


def obtener(proveedor_id):
    return next((p for p in almacen.leer(ARCHIVO, []) if p['id'] == proveedor_id), None)


def validar(form, proveedor_id=None):
    """Devuelve (datos limpios, errores)."""
    datos = {k: str(form.get(k, '')).strip() for k in CAMPOS}
    datos['suministra'] = [s for s in form.getlist('suministra') if s in SUMINISTRA] if hasattr(form, 'getlist') \
        else [s for s in form.get('suministra', []) if s in SUMINISTRA]
    datos['activo'] = form.get('activo', '1') == '1'
    errores = {}

    if len(datos['nombre']) < 3:
        errores['nombre'] = 'Escribe la razón social.'
    datos['nit'] = normalizar_nit(datos['nit'])
    if not PATRON_NIT.match(datos['nit']):
        errores['nit'] = 'NIT no válido. Ejemplo: 900.123.456-7'
    elif any(p['nit'] == datos['nit'] and p['id'] != proveedor_id for p in almacen.leer(ARCHIVO, [])):
        errores['nit'] = 'Ya existe un proveedor con ese NIT.'
    if datos['tipo'] not in TIPOS:
        errores['tipo'] = 'Elige el tipo de proveedor.'
    if datos['correo'] and not PATRON_CORREO.match(datos['correo']):
        errores['correo'] = 'Correo no válido.'
    if datos['telefono'] and not re.fullmatch(r'[\d\s+()\-]{7,20}', datos['telefono']):
        errores['telefono'] = 'Teléfono no válido.'
    if datos['sitio_web']:
        if not re.match(r'^https?://', datos['sitio_web'], re.I):
            datos['sitio_web'] = 'https://' + datos['sitio_web']
        if not re.fullmatch(r'https?://[\w.\-]+\.[a-z]{2,}(/\S*)?', datos['sitio_web'], re.I):
            errores['sitio_web'] = 'Dirección web no válida.'
    if datos['condiciones_pago'] and datos['condiciones_pago'] not in CONDICIONES_PAGO:
        errores['condiciones_pago'] = 'Elige una opción de la lista.'
    for campo, limite in (('notas', 1000), ('direccion', 160)):
        datos[campo] = datos[campo][:limite]
    for campo in ('nombre', 'contacto', 'cargo', 'correo', 'ciudad', 'tiempo_entrega'):
        datos[campo] = datos[campo][:120]
    return datos, errores


def guardar(datos, proveedor_id=None, usuario=''):
    ahora = datetime.now().strftime('%Y-%m-%d %H:%M')
    with _lock:
        lista = almacen.leer(ARCHIVO, [])
        if proveedor_id:
            p = next((p for p in lista if p['id'] == proveedor_id), None)
            if p is None:
                return None
            p.update(datos, actualizado=ahora, actualizado_por=usuario)
        else:
            p = {'id': uuid.uuid4().hex[:12], **datos, 'creado': ahora, 'creado_por': usuario}
            lista.append(p)
        almacen.escribir(ARCHIVO, lista)
    return p


def eliminar(proveedor_id, en_uso=0):
    """Devuelve (proveedor, error). No se borra si tiene productos o equipos asociados."""
    if en_uso:
        return None, f'Tiene {en_uso} producto(s) o equipo(s) de renta asociados: cámbialos de proveedor o márcalo como inactivo.'
    with _lock:
        lista = almacen.leer(ARCHIVO, [])
        p = next((p for p in lista if p['id'] == proveedor_id), None)
        if p is None:
            return None, 'Ese proveedor ya no existe.'
        almacen.escribir(ARCHIVO, [x for x in lista if x['id'] != proveedor_id])
    return p, None
