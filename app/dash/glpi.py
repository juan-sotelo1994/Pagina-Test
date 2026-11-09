"""Consulta de tickets en GLPI por medio de su API REST.

Configuración en .env:
    GLPI_URL         dirección de GLPI, por ejemplo https://soporte.test-lab.com
    GLPI_APP_TOKEN   Configuración > General > API > cliente de la API
    GLPI_USER_TOKEN  Preferencias del usuario > Token de la API remota

Si GLPI no está configurado o no responde, se muestran datos de ejemplo.
"""
import json
import os
import time
import urllib.parse
import urllib.request

# Estados de ticket en GLPI
NUEVO, ASIGNADO, PLANIFICADO, PENDIENTE, RESUELTO, CERRADO = 1, 2, 3, 4, 5, 6
ESTADOS = {
    NUEVO: 'Nuevo', ASIGNADO: 'En curso (asignado)', PLANIFICADO: 'En curso (planificado)',
    PENDIENTE: 'Pendiente', RESUELTO: 'Resuelto', CERRADO: 'Cerrado',
}
PRIORIDADES = {1: 'Muy baja', 2: 'Baja', 3: 'Media', 4: 'Alta', 5: 'Muy alta', 6: 'Mayor'}

# Campos de la búsqueda de tickets en GLPI
CAMPOS = {'id': 2, 'titulo': 1, 'prioridad': 3, 'solicitante': 4, 'tecnico': 5, 'estado': 12, 'fecha': 15}

CACHE_SEGUNDOS = 60
TIEMPO_ESPERA = 6

EJEMPLO = [
    {'id': 1287, 'titulo': 'No hay internet en la sede norte', 'estado': NUEVO, 'prioridad': 5, 'solicitante': 'Clínica San Rafael', 'tecnico': '', 'fecha': '2026-11-08 09:42'},
    {'id': 1286, 'titulo': 'Instalar antivirus en 3 equipos nuevos', 'estado': NUEVO, 'prioridad': 3, 'solicitante': 'Farmacias Vida', 'tecnico': '', 'fecha': '2026-11-08 08:15'},
    {'id': 1284, 'titulo': 'Impresora de contabilidad no imprime', 'estado': PENDIENTE, 'prioridad': 2, 'solicitante': 'Comercial Andina S.A.S.', 'tecnico': 'Juan Mora', 'fecha': '2026-11-07 16:20'},
    {'id': 1281, 'titulo': 'Renovar certificado SSL del portal', 'estado': PENDIENTE, 'prioridad': 4, 'solicitante': 'Hotel Mirador', 'tecnico': 'Diana Ríos', 'fecha': '2026-11-07 11:05'},
    {'id': 1279, 'titulo': 'Lentitud en el servidor de archivos', 'estado': ASIGNADO, 'prioridad': 4, 'solicitante': 'Constructora Altamira', 'tecnico': 'Juan Mora', 'fecha': '2026-11-06 14:30'},
    {'id': 1276, 'titulo': 'Crear cuentas de correo para nuevos empleados', 'estado': PLANIFICADO, 'prioridad': 3, 'solicitante': 'Logística del Valle', 'tecnico': 'Diana Ríos', 'fecha': '2026-11-05 10:12'},
]

_cache = {'momento': 0, 'tickets': None}


def configurado():
    return all(os.environ.get(k) for k in ('GLPI_URL', 'GLPI_APP_TOKEN', 'GLPI_USER_TOKEN'))


def url_ticket(ticket_id):
    if not configurado():
        return None
    return f"{os.environ['GLPI_URL'].rstrip('/')}/front/ticket.form.php?id={ticket_id}"


def _pedir(ruta, encabezados, parametros=None):
    url = f"{os.environ['GLPI_URL'].rstrip('/')}/apirest.php/{ruta}"
    if parametros:
        url += '?' + urllib.parse.urlencode(parametros)
    peticion = urllib.request.Request(url, headers=encabezados)
    with urllib.request.urlopen(peticion, timeout=TIEMPO_ESPERA) as respuesta:
        cuerpo = respuesta.read().decode('utf-8')
    return json.loads(cuerpo) if cuerpo else None


def _texto(valor):
    # GLPI separa varios valores con "$#$" (por ejemplo, varios técnicos)
    if valor is None:
        return ''
    if isinstance(valor, list):
        return ', '.join(str(v) for v in valor if v)
    return str(valor).replace('$#$', ', ')


def _consultar():
    base = {'App-Token': os.environ['GLPI_APP_TOKEN'], 'Content-Type': 'application/json'}
    sesion = _pedir('initSession', {**base, 'Authorization': f"user_token {os.environ['GLPI_USER_TOKEN']}"})
    encabezados = {**base, 'Session-Token': sesion['session_token']}
    try:
        parametros = {
            # 'notold' = todos los tickets que no están resueltos ni cerrados
            'criteria[0][field]': CAMPOS['estado'],
            'criteria[0][searchtype]': 'equals',
            'criteria[0][value]': 'notold',
            'sort': CAMPOS['id'],
            'order': 'DESC',
            'range': '0-199',
        }
        for i, campo in enumerate(CAMPOS.values()):
            parametros[f'forcedisplay[{i}]'] = campo
        resultado = _pedir('search/Ticket', encabezados, parametros) or {}
    finally:
        try:
            _pedir('killSession', encabezados)
        except Exception:
            pass

    tickets = []
    for fila in resultado.get('data', []):
        tickets.append({
            'id': int(fila.get(str(CAMPOS['id']), 0)),
            'titulo': _texto(fila.get(str(CAMPOS['titulo']))),
            'estado': int(fila.get(str(CAMPOS['estado'])) or 0),
            'prioridad': int(fila.get(str(CAMPOS['prioridad'])) or 0),
            'solicitante': _texto(fila.get(str(CAMPOS['solicitante']))),
            'tecnico': _texto(fila.get(str(CAMPOS['tecnico']))),
            'fecha': _texto(fila.get(str(CAMPOS['fecha'])))[:16],
        })
    return tickets


def obtener():
    """Devuelve (tickets, origen, error). origen es 'glpi' o 'ejemplo'."""
    if not configurado():
        return EJEMPLO, 'ejemplo', None

    if _cache['tickets'] is not None and time.time() - _cache['momento'] < CACHE_SEGUNDOS:
        return _cache['tickets'], 'glpi', None

    try:
        tickets = _consultar()
    except Exception as error:
        # Si GLPI no responde, se muestran los últimos datos conocidos
        if _cache['tickets'] is not None:
            return _cache['tickets'], 'glpi', f'No se pudo actualizar desde GLPI ({error}).'
        return [], 'glpi', f'No se pudo conectar con GLPI ({error}).'

    _cache.update(momento=time.time(), tickets=tickets)
    return tickets, 'glpi', None


def resumen(tickets):
    nuevos = [t for t in tickets if t['estado'] == NUEVO]
    pendientes = [t for t in tickets if t['estado'] == PENDIENTE]
    en_curso = [t for t in tickets if t['estado'] in (ASIGNADO, PLANIFICADO)]
    return {
        'nuevos': len(nuevos),
        'pendientes': len(pendientes),
        'en_curso': len(en_curso),
        'alertas': len(nuevos) + len(pendientes),
        'ultimos_nuevos': [{'id': t['id'], 'titulo': t['titulo']}
                           for t in sorted(nuevos, key=lambda t: t['id'], reverse=True)[:5]],
    }
