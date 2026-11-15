#!/usr/bin/env python3
"""Agente de soporte.

Se instala en cada equipo (macOS, Windows o Linux) y cada pocos segundos
envía al panel: nombre, usuario, sistema, CPU, memoria, discos, red y si el
equipo acepta conexiones remotas (VNC / SSH / Escritorio remoto).

Uso:
    python3 agente.py                         # lee config.json
    python3 agente.py --servidor http://192.168.1.10:5711 --token XXXX
    python3 agente.py --una-vez --mostrar     # imprime un reporte y sale (prueba)
    python3 agente.py --log agente.log        # escribe el registro en un archivo
"""
import argparse
import json
import logging
import os
import platform
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import urlparse

import psutil

VERSION = '0.3.0'
INTERVALO = 20           # segundos entre reportes al panel
INTERVALO_COMANDOS = 5   # segundos entre consultas de comandos remotos
ES_MAC = sys.platform == 'darwin'
ES_WINDOWS = sys.platform == 'win32'
# En Windows y Linux el instalador copia el agente a su carpeta y config.json queda al lado
CARPETA = Path('/Library/Application Support/AgenteSoporte') if ES_MAC else Path(__file__).resolve().parent
CONFIG = Path(os.environ.get('AGENTE_CONFIG', CARPETA / 'config.json'))

log = logging.getLogger('agente')


# ---------------------------------------------------------------- utilidades

def comando(*args):
    # Ejecuta un comando del sistema y devuelve su salida, o '' si falla
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ''


def dato_ioreg(clave):
    # Lee un dato del hardware del Mac (UUID, número de serie)
    for linea in comando('ioreg', '-rd1', '-c', 'IOPlatformExpertDevice').splitlines():
        if f'"{clave}"' in linea:
            return linea.split('=', 1)[1].strip().strip('"')
    return ''


def puerto_abierto(puerto):
    # True si el equipo está escuchando en ese puerto (servicio activado)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(('127.0.0.1', puerto)) == 0


# ---------------------------------------------------------------- identidad

def guid_windows():
    # Identificador que Windows asigna a la instalación
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Cryptography',
                            0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as clave:
            return winreg.QueryValueEx(clave, 'MachineGuid')[0]
    except OSError:
        return ''


def nombre_linux():
    # "Ubuntu 24.04 LTS", "Debian GNU/Linux 12 (bookworm)", etc.
    try:
        return platform.freedesktop_os_release().get('PRETTY_NAME', '')
    except (OSError, AttributeError):
        return ''


def identificador():
    # Un ID estable por equipo: el UUID del hardware en Mac, el MachineGuid en Windows
    if ES_MAC:
        valor = dato_ioreg('IOPlatformUUID')
        if valor:
            return valor.lower()
    if ES_WINDOWS:
        valor = guid_windows()
        if valor:
            return valor.lower()
    machine_id = Path('/etc/machine-id')
    if machine_id.exists():
        return machine_id.read_text().strip()
    # Último recurso: un UUID guardado junto a la configuración
    archivo = CONFIG.with_name('equipo.id')
    if not archivo.exists():
        archivo.write_text(str(uuid.uuid4()))
    return archivo.read_text().strip()


def info_fija():
    # Datos que no cambian mientras el agente está corriendo
    if ES_MAC:
        nombre = comando('scutil', '--get', 'ComputerName') or socket.gethostname()
        sistema = f'macOS {platform.mac_ver()[0]}'
        modelo = comando('sysctl', '-n', 'hw.model')
        serial = dato_ioreg('IOPlatformSerialNumber')
    elif ES_WINDOWS:
        nombre = os.environ.get('COMPUTERNAME') or socket.gethostname()
        sistema = f'Windows {platform.release()} (compilación {platform.version()})'
        modelo = platform.machine()
        serial = ''
    else:
        nombre = socket.gethostname()
        sistema = nombre_linux() or platform.platform(terse=True)
        modelo = platform.machine()
        serial = ''
    return {
        'id': identificador(),
        'nombre': nombre,
        'hostname': socket.gethostname(),
        'sistema': sistema,
        'modelo': modelo,
        'serial': serial,
        'nucleos': psutil.cpu_count() or 0,
        'agente': VERSION,
    }


# ---------------------------------------------------------------- métricas

def usuario_activo():
    if ES_MAC:
        # Quien tiene la sesión gráfica abierta
        usuario = comando('stat', '-f', '%Su', '/dev/console')
        if usuario and usuario != 'root':
            return usuario
    usuarios = psutil.users()
    return usuarios[0].name if usuarios else ''


def discos():
    resultado = []
    for p in psutil.disk_partitions(all=False):
        if ES_MAC:
            # '/' es el disco principal; '/Volumes/...' son discos externos
            if p.mountpoint != '/' and not p.mountpoint.startswith('/Volumes/'):
                continue
            nombre = 'Macintosh HD' if p.mountpoint == '/' else p.mountpoint.removeprefix('/Volumes/')
        elif ES_WINDOWS:
            # Omite lectores de CD/DVD y unidades sin disco
            if 'cdrom' in p.opts or not p.fstype:
                continue
            nombre = p.mountpoint.rstrip('\\')
        else:
            if p.fstype in ('squashfs', 'tmpfs', 'overlay') or p.device.startswith('/dev/loop'):
                continue
            nombre = p.mountpoint
        try:
            uso = psutil.disk_usage(p.mountpoint)
        except OSError:
            continue
        # En APFS los volúmenes comparten espacio: lo usado real es total - libre
        usado = uso.total - uso.free if ES_MAC else uso.used
        resultado.append({
            'nombre': nombre,
            'punto': p.mountpoint,
            'total': uso.total,
            'usado': usado,
            'porcentaje': round(usado * 100 / uso.total, 1) if uso.total else 0,
        })
    return resultado


class Red:
    """Calcula la velocidad de red comparando con la lectura anterior."""

    def __init__(self):
        self.anterior = psutil.net_io_counters(pernic=True)
        self.momento = time.monotonic()

    def leer(self):
        ahora = time.monotonic()
        actual = psutil.net_io_counters(pernic=True)
        segundos = max(ahora - self.momento, 0.001)
        direcciones = psutil.net_if_addrs()
        estados = psutil.net_if_stats()

        interfaces = []
        for nombre, c in actual.items():
            ipv4 = [a.address for a in direcciones.get(nombre, []) if a.family == socket.AF_INET]
            estado = estados.get(nombre)
            # Solo interfaces activas con IP (omite loopback, puentes vacíos, etc.)
            if not ipv4 or ipv4[0].startswith('127.') or (estado and not estado.isup):
                continue
            previo = self.anterior.get(nombre, c)
            interfaces.append({
                'nombre': nombre,
                'ip': ipv4[0],
                'bajada': max(c.bytes_recv - previo.bytes_recv, 0) / segundos,
                'subida': max(c.bytes_sent - previo.bytes_sent, 0) / segundos,
                'total_bajada': c.bytes_recv,
                'total_subida': c.bytes_sent,
            })

        self.anterior, self.momento = actual, ahora
        return interfaces


def ip_hacia(servidor):
    # La IP local que usa el equipo para llegar al panel (la que sirve para conectarse)
    url = urlparse(servidor)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((url.hostname, url.port or 80))
            return s.getsockname()[0]
    except OSError:
        return ''


def reporte(fijo, red, servidor):
    memoria = psutil.virtual_memory()
    interfaces = red.leer()
    bateria = psutil.sensors_battery() if hasattr(psutil, 'sensors_battery') else None
    return {
        **fijo,
        'usuario': usuario_activo(),
        'ip': ip_hacia(servidor),
        'arranque': int(psutil.boot_time()),
        'cpu': psutil.cpu_percent(interval=None),
        'memoria': {
            'total': memoria.total,
            'usada': memoria.total - memoria.available,
            'porcentaje': memoria.percent,
        },
        'discos': discos(),
        'red': {
            'bajada': sum(i['bajada'] for i in interfaces),
            'subida': sum(i['subida'] for i in interfaces),
            'interfaces': interfaces,
        },
        'bateria': {'porcentaje': round(bateria.percent), 'cargando': bool(bateria.power_plugged)} if bateria else None,
        'remoto': {
            'pantalla': puerto_abierto(5900),  # Compartir pantalla / Gestión remota (VNC)
            'ssh': puerto_abierto(22),         # Sesión remota (SSH)
            'rdp': puerto_abierto(3389),       # Escritorio remoto de Windows
        },
    }


# ---------------------------------------------------------------- envío

def enviar(servidor, token, datos):
    peticion = urllib.request.Request(
        servidor.rstrip('/') + '/api/agente/reporte',
        data=json.dumps(datos).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'},
        method='POST',
    )
    with urllib.request.urlopen(peticion, timeout=5) as r:
        return r.status


# ---------------------------------------------------------------- comandos remotos

def pedir_json(servidor, token, ruta, datos=None, timeout=10):
    peticion = urllib.request.Request(
        servidor.rstrip('/') + ruta,
        data=json.dumps(datos).encode() if datos is not None else None,
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'},
        method='POST' if datos is not None else 'GET',
    )
    with urllib.request.urlopen(peticion, timeout=timeout) as r:
        return json.loads(r.read().decode() or 'null')


def ejecutar(script, tiempo):
    """Ejecuta un script en segundo plano y devuelve (código, salida).

    En Windows corre en PowerShell con la cuenta del agente (SYSTEM): no abre
    ventanas ni interrumpe al usuario. En macOS/Linux corre en bash como root.
    """
    if ES_WINDOWS:
        # Salida en UTF-8 y sin barras de progreso (ensucian el texto)
        preambulo = ("$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8\n"
                     "$ProgressPreference = 'SilentlyContinue'\n")
        sufijo, codificacion = '.ps1', 'utf-8-sig'  # PowerShell 5 necesita el BOM
    else:
        preambulo, sufijo, codificacion = '', '.sh', 'utf-8'

    with tempfile.NamedTemporaryFile('w', suffix=sufijo, delete=False, encoding=codificacion) as f:
        f.write(preambulo + script)
        ruta = f.name
    if ES_WINDOWS:
        orden = ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', ruta]
        extra = {'creationflags': 0x08000000}  # CREATE_NO_WINDOW
    else:
        orden, extra = ['/bin/bash', ruta], {}

    try:
        proceso = subprocess.run(orden, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 stdin=subprocess.DEVNULL, timeout=tiempo, **extra)
        return proceso.returncode, proceso.stdout.decode('utf-8', 'replace')
    except subprocess.TimeoutExpired as e:
        parcial = (e.stdout or b'').decode('utf-8', 'replace')
        return 124, parcial + f'\n[Detenido: superó el tiempo máximo de {tiempo} s]'
    except OSError as e:
        return 127, f'No se pudo ejecutar: {e}'
    finally:
        try:
            os.remove(ruta)
        except OSError:
            pass


def atender_comandos(servidor, token, equipo_id, permitir):
    # Hilo aparte: pregunta al panel cada pocos segundos si hay algo que ejecutar
    fallando = False
    while True:
        try:
            pendientes = pedir_json(servidor, token, f'/api/agente/comandos/{equipo_id}')['comandos']
            fallando = False
            for c in pendientes:
                tiempo = max(10, min(int(c.get('tiempo', 300)), 3600))
                if permitir:
                    log.info('Ejecutando comando %s del panel', c['id'])
                    codigo, salida = ejecutar(c['script'], tiempo)
                else:
                    codigo, salida = 126, 'Este equipo tiene desactivados los comandos remotos (permitir_comandos: false).'
                pedir_json(servidor, token, f"/api/agente/comandos/{equipo_id}/{c['id']}",
                           {'codigo': codigo, 'salida': salida[-60000:]}, timeout=30)
        except urllib.error.HTTPError as e:
            # 404 = el panel aún no conoce el equipo (llega con el primer reporte)
            if e.code != 404 and not fallando:
                log.warning('Comandos remotos: el panel respondió HTTP %s', e.code)
            fallando = True
        except Exception as e:
            if not fallando:
                log.warning('Comandos remotos: %s', e)
            fallando = True
        time.sleep(INTERVALO_COMANDOS)


def cargar_config(args):
    config = {}
    if CONFIG.exists():
        config = json.loads(CONFIG.read_text())
    servidor = args.servidor or config.get('servidor')
    token = args.token or config.get('token')
    intervalo = args.intervalo or config.get('intervalo', INTERVALO)
    permitir = bool(config.get('permitir_comandos', True))
    if not args.mostrar and (not servidor or not token):
        sys.exit(f'Falta "servidor" o "token". Revisa {CONFIG} o usa --servidor y --token.')
    return servidor or 'http://127.0.0.1', token, max(int(intervalo), 2), permitir


def main():
    parser = argparse.ArgumentParser(description='Agente de soporte')
    parser.add_argument('--servidor', help='URL del panel, p. ej. http://192.168.1.10:5711')
    parser.add_argument('--token', help='Token del agente (AGENT_TOKEN del panel)')
    parser.add_argument('--intervalo', type=int, help=f'Segundos entre reportes (por defecto {INTERVALO})')
    parser.add_argument('--una-vez', action='store_true', help='Envía un solo reporte y sale')
    parser.add_argument('--mostrar', action='store_true', help='Imprime el reporte en pantalla')
    parser.add_argument('--log', help='Archivo de registro (en Windows el servicio no tiene consola)')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
                        filename=args.log, encoding='utf-8')
    servidor, token, intervalo, permitir = cargar_config(args)

    fijo = info_fija()
    red = Red()
    psutil.cpu_percent(interval=None)  # la primera lectura de CPU siempre da 0
    time.sleep(1)

    log.info('Agente %s iniciado: equipo "%s", panel %s, cada %ss', VERSION, fijo['nombre'], servidor, intervalo)
    if token and not args.una_vez:
        threading.Thread(target=atender_comandos, args=(servidor, token, fijo['id'], permitir), daemon=True).start()
    fallando = False
    while True:
        try:
            datos = reporte(fijo, red, servidor)
        except Exception:
            # Un error leyendo un sensor no debe detener el agente
            log.exception('No se pudo leer el estado del equipo')
            time.sleep(intervalo)
            continue
        if args.mostrar:
            print(json.dumps(datos, indent=2, ensure_ascii=False))
        if token:
            try:
                enviar(servidor, token, datos)
                if fallando:
                    log.info('Conexión con el panel restablecida')
                fallando = False
            except urllib.error.HTTPError as e:
                log.error('El panel rechazó el reporte: HTTP %s', e.code)
                fallando = True
            except (urllib.error.URLError, OSError) as e:
                # Solo se registra el primer fallo para no llenar el log
                if not fallando:
                    log.warning('No se pudo contactar el panel: %s', e)
                fallando = True
        if args.una_vez:
            break
        time.sleep(intervalo)


if __name__ == '__main__':
    main()
