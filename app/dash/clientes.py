"""Clientes (empresas) y su inventario de equipos.

- Clientes: app/data/clientes.json; los contratos en PDF en app/data/contratos/
- Equipos de inventario (activos): app/data/activos.json. Cada activo tiene el
  número de serie del equipo y de sus discos. Si un equipo con agente reporta
  ese mismo número de serie, queda agrupado bajo ese cliente en Soporte > Equipos.
Cuando conectemos la base de datos, solo cambian las funciones de este archivo.
"""
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path

from nucleo import almacen

ARCHIVO_CLIENTES = 'clientes.json'
ARCHIVO_ACTIVOS = 'activos.json'
CARPETA_CONTRATOS = almacen.CARPETA / 'contratos'
TAMANO_CONTRATO = 10 * 1024 * 1024  # 10 MB

TIPOS_EQUIPO = ['Portátil', 'Escritorio', 'Servidor', 'Todo en uno', 'Mac', 'Otro']

TIPOS_PERSONA = {'juridica': 'Empresa', 'natural': 'Persona natural'}
TIPOS_DOCUMENTO = {'NIT': 'NIT', 'CC': 'Cédula de ciudadanía', 'CE': 'Cédula de extranjería', 'PA': 'Pasaporte'}
RELACIONES = {'contrato': 'Contrato', 'compra': 'Compra', 'soporte': 'Soporte por demanda'}

PATRON_NIT = re.compile(r'^\d{6,10}(-\d)?$')       # 900123456 o 900123456-7 (sin puntos)
PATRONES_DOCUMENTO = {
    'NIT': PATRON_NIT,
    'CC': re.compile(r'^\d{5,10}$'),
    'CE': re.compile(r'^[A-Za-z0-9]{5,12}$'),
    'PA': re.compile(r'^[A-Za-z0-9]{5,15}$'),
}
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


def documento_de(cliente):
    """'NIT 900123456-7' o 'CC 1020304050' (también para clientes guardados con el formato anterior)."""
    return f"{cliente.get('tipo_documento') or 'NIT'} {cliente.get('documento') or cliente.get('nit', '')}".strip()


def validar_cliente(datos, cliente_id=None):
    errores = {}
    juridica = datos['tipo_persona'] == 'juridica'
    if datos['tipo_persona'] not in TIPOS_PERSONA:
        errores['tipo_persona'] = 'Elige si es empresa o persona natural.'
    if len(datos['nombre'].strip()) < 3:
        errores['nombre'] = 'Escribe la razón social.' if juridica else 'Escribe el nombre completo.'

    # Documento: las empresas siempre se identifican con NIT
    tipo_doc = 'NIT' if juridica else datos['tipo_documento']
    documento = normalizar_nit(datos['documento'])
    if tipo_doc not in TIPOS_DOCUMENTO:
        errores['tipo_documento'] = 'Elige el tipo de documento.'
    elif not PATRONES_DOCUMENTO[tipo_doc].match(documento):
        errores['documento'] = 'NIT no válido. Ejemplo: 900.123.456-7' if tipo_doc == 'NIT' else 'Número de documento no válido.'
    elif any(documento_de(c) == f'{tipo_doc} {documento}' and c['id'] != cliente_id
             for c in almacen.leer(ARCHIVO_CLIENTES, [])):
        errores['documento'] = 'Ya existe un cliente con ese documento.'

    if juridica:
        if len(datos['representante_legal'].strip()) < 3:
            errores['representante_legal'] = 'Escribe el nombre del representante legal.'
        if len(datos['representante_ti'].strip()) < 3:
            errores['representante_ti'] = 'Escribe el nombre del representante de TI.'
    if datos['ti_correo'].strip() and not PATRON_CORREO.match(datos['ti_correo'].strip()):
        errores['ti_correo'] = 'Correo no válido.'

    if datos['relacion'] not in RELACIONES:
        errores['relacion'] = 'Elige el tipo de relación con el cliente.'
    elif datos['relacion'] == 'contrato':
        if not datos['contrato_numero'].strip():
            errores['contrato_numero'] = 'Escribe el número del contrato.'
        if datos['contrato_inicio'] and datos['contrato_fin'] and datos['contrato_fin'] < datos['contrato_inicio']:
            errores['contrato_fin'] = 'La fecha de fin es anterior al inicio.'
    elif datos['relacion'] == 'compra' and not datos['compra_referencia'].strip():
        errores['compra_referencia'] = 'Escribe el número de factura u orden de compra.'
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
    juridica = datos['tipo_persona'] == 'juridica'
    relacion = datos['relacion']
    campos = {
        'tipo_persona': datos['tipo_persona'],
        'nombre': datos['nombre'].strip(),
        'tipo_documento': 'NIT' if juridica else datos['tipo_documento'],
        'documento': normalizar_nit(datos['documento']),
        'representante_legal': datos['representante_legal'].strip() if juridica else '',
        'representante_ti': datos['representante_ti'].strip(),
        'ti_correo': datos['ti_correo'].strip().lower(),
        'ti_telefono': datos['ti_telefono'].strip(),
        'relacion': relacion,
        # Solo se guardan los datos de la relación elegida
        'contrato_numero': datos['contrato_numero'].strip() if relacion == 'contrato' else '',
        'contrato_inicio': datos['contrato_inicio'].strip() if relacion == 'contrato' else '',
        'contrato_fin': datos['contrato_fin'].strip() if relacion == 'contrato' else '',
        'compra_referencia': datos['compra_referencia'].strip() if relacion != 'contrato' else '',
        'compra_fecha': datos['compra_fecha'].strip() if relacion != 'contrato' else '',
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
    # Un equipo asignado desde el agente puede no tener serial todavía: queda unido por su ID
    if not serial and datos.get('equipo_id'):
        pass
    elif not PATRON_SERIAL.match(serial):
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
        'equipo_id': (datos.get('equipo_id') or '').strip()[:64],
    }
    with _lock:
        lista = almacen.leer(ARCHIVO_ACTIVOS, [])
        if activo_id:
            activo = next((a for a in lista if a['id'] == activo_id), None)
            if activo is None:
                return None
            if not campos['equipo_id']:
                campos['equipo_id'] = activo.get('equipo_id', '')  # el formulario no lo trae: se conserva
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
    """Índice para agrupar los equipos del agente: por serial normalizado y por ID del equipo.

    {'serial:<SERIAL>': (activo, cliente), 'equipo:<id>': (activo, cliente)}
    """
    clientes = {c['id']: c for c in almacen.leer(ARCHIVO_CLIENTES, [])}
    indice = {}
    for a in almacen.leer(ARCHIVO_ACTIVOS, []):
        par = (a, clientes.get(a['cliente_id']))
        if a.get('serial'):
            indice[f"serial:{normalizar_serial(a['serial'])}"] = par
        if a.get('equipo_id'):
            indice[f"equipo:{a['equipo_id']}"] = par
    return indice


def buscar_activo(equipo, indice):
    """El activo del inventario que corresponde a un equipo del agente: por serial o por ID."""
    serial = serial_de_equipo(equipo)
    return (indice.get(f'serial:{serial}') if serial else None) or indice.get(f"equipo:{equipo.get('id')}") or (None, None)


def tipo_sugerido(equipo):
    if (equipo.get('sistema') or '').startswith('macOS'):
        return 'Mac'
    return 'Portátil' if equipo.get('bateria') else 'Escritorio'


def asignar_equipos(cliente_id, lista_equipos, usuario):
    """Asigna (o mueve) varios equipos del agente a un cliente. Devuelve cuántos se asignaron."""
    if not obtener_cliente(cliente_id):
        return 0
    with _lock:
        activos = almacen.leer(ARCHIVO_ACTIVOS, [])
        for equipo in lista_equipos:
            serial = serial_de_equipo(equipo)
            existente = next((a for a in activos if (serial and normalizar_serial(a['serial']) == serial)
                              or a.get('equipo_id') == equipo['id']), None)
            if existente:
                existente.update(cliente_id=cliente_id, equipo_id=equipo['id'], actualizado=_ahora(), actualizado_por=usuario)
                continue
            inv = equipo.get('inventario') or {}
            activos.append({
                'id': uuid.uuid4().hex[:12], 'cliente_id': cliente_id, 'tipo': tipo_sugerido(equipo),
                'marca_modelo': f"{inv.get('fabricante', '')} {inv.get('modelo', '')}".strip()[:80],
                'serial': (equipo.get('serial') or inv.get('serial') or '').strip(),
                'discos': [d['serial'] for d in inv.get('discos', []) if d.get('serial')],
                'responsable': (equipo.get('usuario') or '')[:80],
                'notas': f"Asignado desde Soporte › Equipos con agente ({equipo.get('nombre', '')})",
                'equipo_id': equipo['id'], 'creado': _ahora(), 'creado_por': usuario,
            })
        almacen.escribir(ARCHIVO_ACTIVOS, activos)
    return len(lista_equipos)


def verificar_discos(activo, equipo):
    """Compara los seriales de disco registrados con los que reportó el inventario del agente.

    Devuelve {serial registrado: True (encontrado) / False (no está) / None (sin datos del agente)}.
    """
    reportados = {normalizar_serial(d.get('serial')) for d in ((equipo or {}).get('inventario') or {}).get('discos', [])
                  if d.get('serial')}
    return {d: (normalizar_serial(d) in reportados) if reportados else None for d in activo['discos']}
