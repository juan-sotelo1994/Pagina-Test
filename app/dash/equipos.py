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

from . import clientes

ARCHIVO = Path(__file__).resolve().parent.parent / 'data' / 'equipos.json'

SEGUNDOS_EN_LINEA = 60     # sin reportes en este tiempo = desconectado (3 reportes de 20 s)
GUARDAR_CADA = 30          # segundos entre escrituras al archivo
PUNTOS_HISTORIAL = 120     # 40 minutos con reportes cada 20 s

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


def _limpiar_ubicacion(u):
    """Coordenadas válidas o None. fuente: 'windows' (Wi-Fi/GPS), 'ip' (aproximada) o 'no disponible'."""
    if not isinstance(u, dict):
        return None
    limpia = {
        'fuente': _texto(u.get('fuente'), 20),
        'ciudad': _texto(u.get('ciudad'), 60),
        'region': _texto(u.get('region'), 60),
        'pais': _texto(u.get('pais'), 4),
        'momento': int(_numero(u.get('momento'))),
    }
    try:
        lat, lon = float(u.get('lat')), float(u.get('lon'))
    except (TypeError, ValueError):
        return limpia
    if -90 <= lat <= 90 and -180 <= lon <= 180:
        limpia.update(lat=round(lat, 6), lon=round(lon, 6), precision=round(_numero(u.get('precision'), 0, 1_000_000)))
    return limpia


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
    sensores = datos.get('sensores') if isinstance(datos.get('sensores'), dict) else {}
    temp = sensores.get('cpu_temp')
    try:
        temp = round(float(temp), 1) if temp is not None and -20 < float(temp) < 150 else None
    except (TypeError, ValueError):
        temp = None

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
        'sensores': {
            'cpu_temp': temp,  # None = el equipo no informa temperatura
            'fuente': _texto(sensores.get('fuente'), 60),
            'ventiladores': [
                {'nombre': _texto(v.get('nombre'), 60), 'rpm': int(_numero(v.get('rpm'), 0, 100_000))}
                for v in (sensores.get('ventiladores') or [])[:12] if isinstance(v, dict)
            ],
            'ventiladores_disponible': bool(sensores.get('ventiladores_disponible')),
        },
        'ubicacion': _limpiar_ubicacion(datos.get('ubicacion')),
        'remoto': {
            'pantalla': bool(remoto.get('pantalla')),
            'ssh': bool(remoto.get('ssh')),
            'rdp': bool(remoto.get('rdp')),
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
        anterior = equipos.get(equipo['id'], {})
        equipo['visto'] = ahora
        equipo['primera_vez'] = anterior.get('primera_vez', ahora)
        # El inventario llega por comandos, no con cada reporte: se conserva
        if anterior.get('inventario'):
            equipo['inventario'] = anterior['inventario']
        # Ubicación: solo se guarda si un administrador activó el rastreo en este equipo
        equipo['rastreo'] = anterior.get('rastreo') or {'activo': False}
        if not equipo['rastreo']['activo']:
            equipo['ubicacion'] = None
        elif not equipo['ubicacion']:
            equipo['ubicacion'] = anterior.get('ubicacion')
        equipo['ip_origen'] = _texto(ip_origen, 45)
        equipos[equipo['id']] = equipo

        _historial.setdefault(equipo['id'], deque(maxlen=PUNTOS_HISTORIAL)).append({
            't': ahora,
            'cpu': equipo['cpu'],
            'memoria': equipo['memoria']['porcentaje'],
            'bajada': equipo['red']['bajada'],
            'subida': equipo['red']['subida'],
            'temp': equipo['sensores']['cpu_temp'],
        })

        if nuevo or ahora - _ultimo_guardado > GUARDAR_CADA:
            guardar()
    return True


def rastreo_activo(equipo_id):
    with _lock:
        return bool((cargar().get(equipo_id, {}).get('rastreo') or {}).get('activo'))


def cambiar_rastreo(equipo_id, activo, usuario):
    """Activa o desactiva el envío de ubicación de un equipo. Al desactivarlo se borra la última."""
    with _lock:
        equipo = cargar().get(equipo_id)
        if equipo is None:
            return False
        equipo['rastreo'] = {'activo': bool(activo), 'por': usuario, 'desde': time.time()}
        if not activo:
            equipo['ubicacion'] = None
        guardar()
    return True


def en_linea(equipo, ahora=None):
    return (ahora or time.time()) - equipo.get('visto', 0) < SEGUNDOS_EN_LINEA


# ---------------------------------------------------------------- inventario

MARCA_INVENTARIO = '###INVENTARIO###'


def _lista(valor, maximo, convertir):
    if not isinstance(valor, list):
        valor = [valor] if isinstance(valor, dict) else []
    return [convertir(v) for v in valor[:maximo] if isinstance(v, dict)]


def limpiar_inventario(datos):
    """Deja solo campos conocidos, con tipos y tamaños seguros."""
    if not isinstance(datos, dict):
        return None
    texto = lambda clave, largo=120: _texto(datos.get(clave), largo).strip()
    return {
        'fabricante': texto('fabricante'),
        'modelo': texto('modelo'),
        'serial': texto('serial', 60),
        'bios': texto('bios', 60),
        'bios_fecha': texto('bios_fecha', 20),
        'procesador': texto('procesador'),
        'nucleos': int(_numero(datos.get('nucleos'), 0, 1024)),
        'hilos': int(_numero(datos.get('hilos'), 0, 4096)),
        'ram_gb': round(_numero(datos.get('ram_gb'), 0, 1_000_000), 1),
        'ram_modulos': _lista(datos.get('ram_modulos'), 32, lambda m: {
            'capacidad_gb': _numero(m.get('capacidad_gb'), 0, 10_000),
            'velocidad': int(_numero(m.get('velocidad'), 0, 100_000)),
            'fabricante': _texto(m.get('fabricante'), 60).strip(),
            'ranura': _texto(m.get('ranura'), 40).strip(),
        }),
        'so': texto('so'),
        'so_version': texto('so_version', 40),
        'so_compilacion': texto('so_compilacion', 40),
        'so_instalado': texto('so_instalado', 20),
        'arquitectura': texto('arquitectura', 30),
        'dominio': texto('dominio', 120),
        'en_dominio': bool(datos.get('en_dominio')),
        'discos': _lista(datos.get('discos'), 20, lambda d: {
            'modelo': _texto(d.get('modelo'), 80).strip(),
            'tamano_gb': int(_numero(d.get('tamano_gb'), 0, 1_000_000)),
            'tipo': _texto(d.get('tipo'), 20).strip(),
            'interfaz': _texto(d.get('interfaz'), 20).strip(),
            'salud': _texto(d.get('salud'), 20).strip(),
            'serial': _texto(d.get('serial'), 60).strip(),
        }),
        'red': _lista(datos.get('red'), 20, lambda r: {
            'nombre': _texto(r.get('nombre'), 60).strip(),
            'descripcion': _texto(r.get('descripcion'), 120).strip(),
            'mac': _texto(r.get('mac'), 20).strip(),
            'velocidad': _texto(r.get('velocidad'), 20).strip(),
        }),
        'antivirus': [_texto(a, 80) for a in (datos.get('antivirus') or [])[:10] if isinstance(a, str)],
        'software': _lista(datos.get('software'), 500, lambda s: {
            'nombre': _texto(s.get('nombre'), 120).strip(),
            'version': _texto(s.get('version'), 40).strip(),
            'editor': _texto(s.get('editor'), 80).strip(),
        }),
    }


def quitar_inventario(salida):
    # Reemplaza la línea de datos del inventario por un aviso legible
    lineas = str(salida).splitlines()
    if not any(l.startswith(MARCA_INVENTARIO) for l in lineas):
        return salida
    lineas = [l for l in lineas if not l.startswith(MARCA_INVENTARIO)]
    return '\n'.join(lineas + ['', '[Inventario guardado en la ficha del equipo]'])


def actualizar_inventario(equipo_id, salida, comando):
    """Busca el bloque ###INVENTARIO### en la salida de un comando y lo guarda.

    Devuelve True si actualizó la ficha del equipo.
    """
    lineas = [l for l in str(salida).splitlines() if l.startswith(MARCA_INVENTARIO)]
    if not lineas:
        return False
    try:
        inventario = limpiar_inventario(json.loads(lineas[-1][len(MARCA_INVENTARIO):]))
    except ValueError:
        return False
    if inventario is None:
        return False
    inventario.update(actualizado=time.time(), por=comando.get('usuario', ''), comando=comando.get('id', ''))
    with _lock:
        equipo = cargar().get(equipo_id)
        if equipo is None:
            return False
        equipo['inventario'] = inventario
        guardar()
    return True


def _asignar_cliente(equipo, seriales):
    """Marca a qué cliente pertenece el equipo según su número de serie. Devuelve el activo."""
    activo, cliente = seriales.get(clientes.serial_de_equipo(equipo), (None, None))
    equipo['cliente'] = {'id': cliente['id'], 'nombre': cliente['nombre']} if cliente else None
    equipo['activo_id'] = activo['id'] if activo else None
    return activo


def _completar(equipo):
    # Datos calculados que la página necesita; el inventario completa serie y modelo
    inv = equipo.get('inventario') or {}
    equipo['serial'] = equipo.get('serial') or inv.get('serial', '')
    if inv.get('modelo'):
        equipo['modelo'] = f"{inv.get('fabricante', '')} {inv['modelo']}".strip()
    equipo['ip_conexion'] = ip_conexion(equipo)
    return equipo


def ip_conexion(equipo):
    # La IP con la que el equipo llega al panel; sirve para Compartir pantalla / SSH
    return equipo.get('ip') or equipo.get('ip_origen', '')


PANTALLAS_RDP = {'completa': None, '1920x1080': (1920, 1080), '1600x900': (1600, 900), '1280x720': (1280, 720)}


def archivo_rdp(equipo, usuario='', pantalla='completa'):
    """Contenido de un archivo .rdp para abrir Escritorio remoto contra el equipo.

    Devuelve None si la IP no es válida. La IP y el usuario se validan para
    que no se puedan colar otras líneas en el archivo.
    """
    ip = ip_conexion(equipo)
    if not ip or not re.fullmatch(r'[0-9A-Fa-f.:]{3,45}', ip):
        return None
    usuario = usuario.strip()
    if not re.fullmatch(r'[\w.\\@-]{0,104}', usuario):
        usuario = ''
    tamano = PANTALLAS_RDP.get(pantalla)

    lineas = [
        f'full address:s:{ip}:3389',
        'prompt for credentials:i:1',       # pide la contraseña al conectar (no se guarda)
        'authentication level:i:2',          # avisa si no puede verificar el certificado
        'use multimon:i:0',
        'redirectclipboard:i:1',
        'audiomode:i:0',
    ]
    if usuario:
        lineas.append(f'username:s:{usuario}')
    if tamano:
        lineas += ['screen mode id:i:1', f'desktopwidth:i:{tamano[0]}', f'desktopheight:i:{tamano[1]}']
    else:
        lineas.append('screen mode id:i:2')
    return '\r\n'.join(lineas) + '\r\n'


def listar():
    ahora = time.time()
    with _lock:
        equipos = [dict(e) for e in cargar().values()]
    seriales = clientes.mapa_seriales()
    for e in equipos:
        e['en_linea'] = en_linea(e, ahora)
        _asignar_cliente(e, seriales)
        _completar(e)
        e.pop('inventario', None)  # la lista no lo necesita y pesa (programas instalados)
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
    activo = _asignar_cliente(equipo, clientes.mapa_seriales())
    if activo:
        equipo['discos_verificados'] = clientes.verificar_discos(activo, equipo)
    return _completar(equipo)


def eliminar(equipo_id):
    with _lock:
        if cargar().pop(equipo_id, None) is not None:
            _historial.pop(equipo_id, None)
            guardar()
