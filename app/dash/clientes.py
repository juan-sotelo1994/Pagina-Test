"""Clientes (empresas) y su inventario de equipos.

- Clientes: app/data/clientes.json; los contratos en PDF en app/data/contratos/
- Equipos de clientes (activos): app/data/activos.json. Cada activo tiene el
  número de serie del equipo y de sus discos. Si un equipo con agente reporta
  ese mismo número de serie, queda agrupado bajo ese cliente en Soporte > Equipos.
Cuando conectemos la base de datos, solo cambian las funciones de este archivo.
"""
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path

import almacen

ARCHIVO_CLIENTES = 'clientes.json'
ARCHIVO_ACTIVOS = 'activos.json'
CARPETA_CONTRATOS = almacen.CARPETA / 'contratos'
TAMANO_CONTRATO = 10 * 1024 * 1024  # 10 MB

TIPOS_EQUIPO = ['Portátil', 'Escritorio', 'Servidor', 'Todo en uno', 'Mac', 'Otro']
PATRON_NIT = re.compile(r'^\d{6,10}(-\d)?$')       # 900123456 o 900123456-7 (sin puntos)
PATRON_CORREO = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
PATRON_SERIAL = re.compile(r'^[A-Za-z0-9._/\- ]{3,60}$')

_lock = threading.Lock()


def _ahora():
    return datetime.now().strftime('%Y-%m-%d %H:%M')


def normalizar_serial(serial):
    # Para comparar: sin espacios y en mayúsculas
    return re.sub(r'\s+', '', str(serial or '')).upper()


def normalizar_nit(nit):
    # Se guarda sin puntos ni espacios: 900.123.456-7 -> 900123456-7
    return re.sub(r'[.\s]', '', str(nit or ''))


# ---------------------------------------------------------------- clientes

def listar_clientes():
    return sorted(almacen.leer(ARCHIVO_CLIENTES, []), key=lambda c: c['nombre'].lower())


def obtener_cliente(cliente_id):
    return next((c for c in almacen.leer(ARCHIVO_CLIENTES, []) if c['id'] == cliente_id), None)


def validar_cliente(datos, cliente_id=None):
    errores = {}
    if len(datos['nombre'].strip()) < 3:
        errores['nombre'] = 'Escribe el nombre de la empresa.'
    nit = normalizar_nit(datos['nit'])
    if not PATRON_NIT.match(nit):
        errores['nit'] = 'NIT no válido. Ejemplo: 900.123.456-7'
    elif any(normalizar_nit(c['nit']) == nit and c['id'] != cliente_id for c in almacen.leer(ARCHIVO_CLIENTES, [])):
        errores['nit'] = 'Ya existe un cliente con ese NIT.'
    if len(datos['representante_legal'].strip()) < 3:
        errores['representante_legal'] = 'Escribe el nombre del representante legal.'
    if len(datos['representante_ti'].strip()) < 3:
        errores['representante_ti'] = 'Escribe el nombre del representante de TI.'
    if datos['ti_correo'].strip() and not PATRON_CORREO.match(datos['ti_correo'].strip()):
        errores['ti_correo'] = 'Correo no válido.'
    return errores


def validar_contrato(archivo):
    """Revisa el PDF subido. Devuelve (contenido, error)."""
    if not archivo or not archivo.filename:
        return None, None
    if not archivo.filename.lower().endswith('.pdf'):
        return None, 'El contrato debe ser un archivo PDF.'
    contenido = archivo.read(TAMANO_CONTRATO + 1)
    if len(contenido) > TAMANO_CONTRATO:
        return None, 'El PDF supera los 10 MB.'
    if not contenido.startswith(b'%PDF'):
        return None, 'El archivo no parece un PDF válido.'
    return contenido, None


def _guardar_contrato(cliente_id, contenido):
    CARPETA_CONTRATOS.mkdir(parents=True, exist_ok=True)
    nombre = f'{cliente_id}-{uuid.uuid4().hex[:8]}.pdf'
    (CARPETA_CONTRATOS / nombre).write_bytes(contenido)
    return nombre


def ruta_contrato(cliente):
    if not cliente or not cliente.get('contrato_archivo'):
        return None
    ruta = (CARPETA_CONTRATOS / cliente['contrato_archivo']).resolve()
    # Nunca se sirve algo fuera de la carpeta de contratos
    if ruta.parent != CARPETA_CONTRATOS.resolve() or not ruta.exists():
        return None
    return ruta


def guardar_cliente(datos, contrato=None, cliente_id=None, usuario=''):
    """Crea (cliente_id=None) o actualiza un cliente. Devuelve el cliente."""
    campos = {
        'nombre': datos['nombre'].strip(),
        'nit': normalizar_nit(datos['nit']),
        'representante_legal': datos['representante_legal'].strip(),
        'representante_ti': datos['representante_ti'].strip(),
        'ti_correo': datos['ti_correo'].strip().lower(),
        'ti_telefono': datos['ti_telefono'].strip(),
        'contrato_numero': datos['contrato_numero'].strip(),
        'contrato_inicio': datos['contrato_inicio'].strip(),
        'contrato_fin': datos['contrato_fin'].strip(),
    }
    with _lock:
        lista = almacen.leer(ARCHIVO_CLIENTES, [])
        if cliente_id:
            cliente = next((c for c in lista if c['id'] == cliente_id), None)
            if cliente is None:
                return None
            cliente.update(campos, actualizado=_ahora(), actualizado_por=usuario)
        else:
            cliente = {'id': uuid.uuid4().hex[:12], **campos, 'contrato_archivo': '', 'contrato_nombre': '',
                       'creado': _ahora(), 'creado_por': usuario}
            lista.append(cliente)
        if contrato is not None:
            anterior = ruta_contrato(cliente)
            cliente['contrato_archivo'] = _guardar_contrato(cliente['id'], contrato['contenido'])
            cliente['contrato_nombre'] = contrato['nombre'][:120]
            if anterior:
                anterior.unlink(missing_ok=True)
        almacen.escribir(ARCHIVO_CLIENTES, lista)
    return cliente


def eliminar_cliente(cliente_id):
    """Solo se elimina si no tiene equipos registrados. Devuelve (cliente, error)."""
    with _lock:
        if any(a['cliente_id'] == cliente_id for a in almacen.leer(ARCHIVO_ACTIVOS, [])):
            return None, 'El cliente tiene equipos registrados: muévelos o elimínalos primero.'
        lista = almacen.leer(ARCHIVO_CLIENTES, [])
        cliente = next((c for c in lista if c['id'] == cliente_id), None)
        if cliente is None:
            return None, 'Ese cliente ya no existe.'
        archivo = ruta_contrato(cliente)
        almacen.escribir(ARCHIVO_CLIENTES, [c for c in lista if c['id'] != cliente_id])
    if archivo:
        archivo.unlink(missing_ok=True)
    return cliente, None


# ---------------------------------------------------------------- equipos de clientes (activos)

def listar_activos(cliente_id=None):
    activos = almacen.leer(ARCHIVO_ACTIVOS, [])
    if cliente_id:
        activos = [a for a in activos if a['cliente_id'] == cliente_id]
    return sorted(activos, key=lambda a: (a['cliente_id'], a['serial']))


def _seriales_discos(texto):
    # Un serial por línea (o separados por coma)
    return [s.strip() for s in re.split(r'[\n,;]+', texto or '') if s.strip()]


def validar_activo(datos, activo_id=None):
    errores = {}
    if not obtener_cliente(datos['cliente_id']):
        errores['cliente_id'] = 'Elige la empresa.'
    if datos['tipo'] not in TIPOS_EQUIPO:
        errores['tipo'] = 'Elige el tipo de equipo.'
    serial = datos['serial'].strip()
    if not PATRON_SERIAL.match(serial):
        errores['serial'] = 'Número de serie no válido (3 a 60 letras, números o guiones).'
    else:
        repetido = next((a for a in almacen.leer(ARCHIVO_ACTIVOS, [])
                         if normalizar_serial(a['serial']) == normalizar_serial(serial) and a['id'] != activo_id), None)
        if repetido:
            cliente = obtener_cliente(repetido['cliente_id'])
            errores['serial'] = f"Ese serial ya está registrado ({cliente['nombre'] if cliente else 'otro cliente'})."
    discos = _seriales_discos(datos['discos'])
    if len(discos) > 12:
        errores['discos'] = 'Máximo 12 discos por equipo.'
    elif any(not PATRON_SERIAL.match(d) for d in discos):
        errores['discos'] = 'Algún serial de disco no es válido.'
    return errores


def guardar_activo(datos, activo_id=None, usuario=''):
    campos = {
        'cliente_id': datos['cliente_id'],
        'tipo': datos['tipo'],
        'marca_modelo': datos['marca_modelo'].strip()[:80],
        'serial': datos['serial'].strip(),
        'discos': _seriales_discos(datos['discos']),
        'responsable': datos['responsable'].strip()[:80],
        'notas': datos['notas'].strip()[:500],
    }
    with _lock:
        lista = almacen.leer(ARCHIVO_ACTIVOS, [])
        if activo_id:
            activo = next((a for a in lista if a['id'] == activo_id), None)
            if activo is None:
                return None
            activo.update(campos, actualizado=_ahora(), actualizado_por=usuario)
        else:
            activo = {'id': uuid.uuid4().hex[:12], **campos, 'creado': _ahora(), 'creado_por': usuario}
            lista.append(activo)
        almacen.escribir(ARCHIVO_ACTIVOS, lista)
    return activo


def eliminar_activo(activo_id):
    with _lock:
        lista = almacen.leer(ARCHIVO_ACTIVOS, [])
        activo = next((a for a in lista if a['id'] == activo_id), None)
        if activo:
            almacen.escribir(ARCHIVO_ACTIVOS, [a for a in lista if a['id'] != activo_id])
    return activo


# ---------------------------------------------------------------- relación con los equipos del agente

def serial_de_equipo(equipo):
    # El serial que reporta el agente (Mac) o el del inventario (Windows / Linux)
    return normalizar_serial(equipo.get('serial') or (equipo.get('inventario') or {}).get('serial'))


def mapa_seriales():
    """{serial normalizado: (activo, cliente)} para agrupar los equipos del agente."""
    clientes = {c['id']: c for c in almacen.leer(ARCHIVO_CLIENTES, [])}
    return {normalizar_serial(a['serial']): (a, clientes.get(a['cliente_id'])) for a in almacen.leer(ARCHIVO_ACTIVOS, [])}


def verificar_discos(activo, equipo):
    """Compara los seriales de disco registrados con los que reportó el inventario del agente.

    Devuelve {serial registrado: True (encontrado) / False (no está) / None (sin datos del agente)}.
    """
    reportados = {normalizar_serial(d.get('serial')) for d in ((equipo or {}).get('inventario') or {}).get('discos', [])
                  if d.get('serial')}
    return {d: (normalizar_serial(d) in reportados) if reportados else None for d in activo['discos']}
