"""Equipos monitoreados por el agente de soporte.

El último reporte de cada equipo vive en memoria y se guarda en
app/data/equipos.json cada cierto tiempo, para no perder el inventario al
reiniciar el panel. El historial de los gráficos solo vive en memoria.
Cuando conectemos la base de datos, solo cambian cargar() y guardar().
"""
import json
import os
import re
import threading
import time
from collections import deque
from pathlib import Path

ARCHIVO = Path(__file__).resolve().parent.parent / 'data' / 'equipos.json'

SEGUNDOS_EN_LINEA = 20     # sin reportes en este tiempo = desconectado
GUARDAR_CADA = 30          # segundos entre escrituras al archivo
PUNTOS_HISTORIAL = 120     # 10 minutos con reportes cada 5 s

_lock = threading.Lock()
_equipos = None
_historial = {}
_ultimo_guardado = 0.0

ID_VALIDO = re.compile(r'^[A-Za-z0-9-]{8,64}$')


# ---------------------------------------------------------------- limpieza

def _texto(valor, largo=120):
    return str(valor)[:largo] if valor is not None else ''


def _numero(valor, minimo=0.0, maximo=float('inf')):
    try:
        n = float(valor)
    except (TypeError, ValueError):
        return 0.0
    return min(max(n, minimo), maximo) if n == n else 0.0  # n != n es NaN


def limpiar(datos):
    """Convierte el JSON del agente en un registro con tipos y tamaños seguros.

    Devuelve None si el reporte no es válido.
    """
    if not isinstance(datos, dict) or not ID_VALIDO.match(str(datos.get('id', ''))):
        return None

    memoria = datos.get('memoria') if isinstance(datos.get('memoria'), dict) else {}
    red = datos.get('red') if isinstance(datos.get('red'), dict) else {}
    remoto = datos.get('remoto') if isinstance(datos.get('remoto'), dict) else {}
    bateria = datos.get('bateria') if isinstance(datos.get('bateria'), dict) else None

    discos = []
    for d in (datos.get('discos') or [])[:20]:
        if isinstance(d, dict):
            discos.append({
                'nombre': _texto(d.get('nombre'), 80),
                'punto': _texto(d.get('punto'), 200),
                'total': _numero(d.get('total')),
                'usado': _numero(d.get('usado')),
                'porcentaje': _numero(d.get('porcentaje'), 0, 100),
            })

    interfaces = []
    for i in (red.get('interfaces') or [])[:20]:
        if isinstance(i, dict):
            interfaces.append({
                'nombre': _texto(i.get('nombre'), 40),
                'ip': _texto(i.get('ip'), 45),
                'bajada': _numero(i.get('bajada')),
                'subida': _numero(i.get('subida')),
                'total_bajada': _numero(i.get('total_bajada')),
                'total_subida': _numero(i.get('total_subida')),
            })

    return {
        'id': str(datos['id']).lower(),
        'nombre': _texto(datos.get('nombre'), 80) or 'Sin nombre',
        'hostname': _texto(datos.get('hostname'), 120),
        'sistema': _texto(datos.get('sistema'), 80),
        'modelo': _texto(datos.get('modelo'), 80),
        'serial': _texto(datos.get('serial'), 40),
        'usuario': _texto(datos.get('usuario'), 60),
        'ip': _texto(datos.get('ip'), 45),
        'agente': _texto(datos.get('agente'), 20),
        'nucleos': int(_numero(datos.get('nucleos'), 0, 1024)),
        'arranque': int(_numero(datos.get('arranque'))),
        'cpu': _numero(datos.get('cpu'), 0, 100),
        'memoria': {
            'total': _numero(memoria.get('total')),
            'usada': _numero(memoria.get('usada')),
            'porcentaje': _numero(memoria.get('porcentaje'), 0, 100),
        },
        'discos': discos,
        'red': {
            'bajada': _numero(red.get('bajada')),
            'subida': _numero(red.get('subida')),
            'interfaces': interfaces,
        },
        'bateria': {
            'porcentaje': _numero(bateria.get('porcentaje'), 0, 100),
            'cargando': bool(bateria.get('cargando')),
        } if bateria else None,
        'remoto': {
            'pantalla': bool(remoto.get('pantalla')),
            'ssh': bool(remoto.get('ssh')),
        },
    }


# ---------------------------------------------------------------- almacenamiento

def cargar():
    global _equipos
    if _equipos is None:
        _equipos = {}
        if ARCHIVO.exists():
            _equipos = json.loads(ARCHIVO.read_text(encoding='utf-8'))
    return _equipos


def guardar():
    # Igual que en permisos.py: archivo temporal + reemplazo
    global _ultimo_guardado
    ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
    temporal = ARCHIVO.with_suffix('.tmp')
    temporal.write_text(json.dumps(cargar(), ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporal, ARCHIVO)
    _ultimo_guardado = time.time()


def registrar(datos, ip_origen):
    """Guarda un reporte del agente. Devuelve False si no es válido."""
    equipo = limpiar(datos)
    if equipo is None:
        return False

    ahora = time.time()
    with _lock:
        equipos = cargar()
        nuevo = equipo['id'] not in equipos
        equipo['visto'] = ahora
        equipo['primera_vez'] = equipos.get(equipo['id'], {}).get('primera_vez', ahora)
        equipo['ip_origen'] = _texto(ip_origen, 45)
        equipos[equipo['id']] = equipo

        _historial.setdefault(equipo['id'], deque(maxlen=PUNTOS_HISTORIAL)).append({
            't': ahora,
            'cpu': equipo['cpu'],
            'memoria': equipo['memoria']['porcentaje'],
            'bajada': equipo['red']['bajada'],
            'subida': equipo['red']['subida'],
        })

        if nuevo or ahora - _ultimo_guardado > GUARDAR_CADA:
            guardar()
    return True


def en_linea(equipo, ahora=None):
    return (ahora or time.time()) - equipo.get('visto', 0) < SEGUNDOS_EN_LINEA


def ip_conexion(equipo):
    # La IP con la que el equipo llega al panel; sirve para Compartir pantalla / SSH
    return equipo.get('ip') or equipo.get('ip_origen', '')


def listar():
    ahora = time.time()
    with _lock:
        equipos = [dict(e) for e in cargar().values()]
    for e in equipos:
        e['en_linea'] = en_linea(e, ahora)
        e['ip_conexion'] = ip_conexion(e)
    # Primero los conectados, luego por nombre
    return sorted(equipos, key=lambda e: (not e['en_linea'], e['nombre'].lower()))


def obtener(equipo_id):
    with _lock:
        equipo = cargar().get(equipo_id)
        if equipo is None:
            return None
        equipo = dict(equipo)
        equipo['historial'] = list(_historial.get(equipo_id, []))
    equipo['en_linea'] = en_linea(equipo)
    equipo['ip_conexion'] = ip_conexion(equipo)
    return equipo


def eliminar(equipo_id):
    with _lock:
        if cargar().pop(equipo_id, None) is not None:
            _historial.pop(equipo_id, None)
            guardar()
