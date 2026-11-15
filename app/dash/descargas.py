"""Paquetes del agente de soporte para descargar desde Soporte > Equipos.

Cada paquete es un .zip con el agente, el instalador de su sistema y un
config.json con la dirección del panel y el token, para instalar con un
solo comando. El token es secreto: solo pueden descargar los roles con
permiso para crear en Equipos.
"""
import io
import json
import os
import socket
import zipfile
from pathlib import Path
from urllib.parse import urlparse

CARPETA_AGENTE = Path(__file__).resolve().parents[2] / 'agente'

PLATAFORMAS = {
    'macos': {
        'nombre': 'macOS', 'icono': 'fa-brands fa-apple', 'carpeta': 'macos',
        'archivos': ['instalar.sh', 'desinstalar.sh'],
        'requisitos': 'macOS 11 o superior',
        'pasos': ['Descomprime el .zip y abre Terminal en la carpeta', 'cd macos && sudo ./instalar.sh'],
    },
    'windows': {
        'nombre': 'Windows', 'icono': 'fa-brands fa-windows', 'carpeta': 'windows',
        'archivos': ['instalar.bat', 'instalar.ps1', 'desinstalar.bat', 'desinstalar.ps1'],
        'requisitos': 'Windows 10 / 11 · Server 2019+',
        'pasos': ['Descomprime el .zip (clic derecho → Extraer todo)', 'Doble clic en windows\\instalar.bat'],
    },
    'debian': {
        'nombre': 'Debian', 'icono': 'fa-brands fa-linux', 'carpeta': 'linux',
        'archivos': ['instalar.sh', 'desinstalar.sh'],
        'requisitos': 'Debian 11 / 12',
        'pasos': ['unzip agente-soporte-debian.zip -d agente && cd agente/linux', 'sudo ./instalar.sh'],
    },
    'ubuntu': {
        'nombre': 'Ubuntu', 'icono': 'fa-brands fa-ubuntu', 'carpeta': 'linux',
        'archivos': ['instalar.sh', 'desinstalar.sh'],
        'requisitos': 'Ubuntu 20.04 / 22.04 / 24.04',
        'pasos': ['unzip agente-soporte-ubuntu.zip -d agente && cd agente/linux', 'sudo ./instalar.sh'],
    },
}

LEEME = """Agente de soporte de {empresa} para {nombre}
==============================================

Requisitos: {requisitos}. El equipo debe poder llegar al panel en:
    {servidor}

Instalación:
{pasos}

El agente queda como servicio del sistema: arranca solo al encender el equipo
y en unos segundos aparece en el panel, en Soporte > Equipos.

config.json contiene el token del agente: no compartas este paquete fuera
de tu equipo de soporte. Para desinstalar, usa el script "desinstalar" de la
misma carpeta que el instalador.
"""


def token_configurado():
    return bool(os.environ.get('AGENT_TOKEN'))


def ip_local():
    # La IP de este servidor en la red local (no envía tráfico)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('10.255.255.255', 1))
            return s.getsockname()[0]
    except OSError:
        return '127.0.0.1'


def servidor_sugerido(url_actual):
    # Si el panel se abrió como localhost, los equipos no podrán llegar: se sugiere la IP de la red
    url = urlparse(url_actual)
    if url.hostname in ('localhost', '127.0.0.1', '::1'):
        return f'{url.scheme}://{ip_local()}:{url.port or 5711}'
    return f'{url.scheme}://{url.netloc}'


def validar_servidor(servidor):
    url = urlparse(servidor.strip())
    if url.scheme not in ('http', 'https') or not url.hostname:
        return 'Escribe la dirección completa del panel, por ejemplo http://192.168.1.10:5711'
    if url.hostname in ('localhost', '127.0.0.1', '::1'):
        return 'Con localhost los otros equipos no llegan al panel: usa la IP de este servidor en la red.'
    return None


def _agregar(zipf, ruta_zip, contenido, ejecutable=False):
    info = zipfile.ZipInfo(ruta_zip)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3  # Unix: si no, unzip y el Mac ignoran los permisos
    # Permisos Unix dentro del zip (los .sh deben quedar ejecutables)
    info.external_attr = (0o755 if ejecutable else 0o644) << 16
    zipf.writestr(info, contenido)


def construir_zip(plataforma, servidor, empresa):
    datos = PLATAFORMAS[plataforma]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as zipf:
        _agregar(zipf, 'agente.py', (CARPETA_AGENTE / 'agente.py').read_bytes())
        _agregar(zipf, 'requirements.txt', (CARPETA_AGENTE / 'requirements.txt').read_bytes())

        for nombre in datos['archivos']:
            texto = (CARPETA_AGENTE / datos['carpeta'] / nombre).read_text(encoding='utf-8')
            if nombre.endswith('.sh'):
                # bash falla con saltos de línea de Windows
                contenido = texto.replace('\r\n', '\n').encode('utf-8')
            elif nombre.endswith('.ps1'):
                # PowerShell 5 necesita el BOM para leer bien las tildes
                contenido = b'\xef\xbb\xbf' + texto.replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8')
            else:
                contenido = texto.replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8')
            _agregar(zipf, f"{datos['carpeta']}/{nombre}", contenido, ejecutable=nombre.endswith('.sh'))

        config = {'servidor': servidor.rstrip('/'), 'token': os.environ.get('AGENT_TOKEN', ''), 'intervalo': 5}
        _agregar(zipf, 'config.json', json.dumps(config, indent=2))

        pasos = '\n'.join(f'  {i}. {p}' for i, p in enumerate(datos['pasos'], 1))
        leeme = LEEME.format(empresa=empresa, nombre=datos['nombre'], requisitos=datos['requisitos'],
                             servidor=servidor, pasos=pasos)
        if plataforma == 'windows':
            leeme = leeme.replace('\n', '\r\n')
        _agregar(zipf, 'LEEME.txt', leeme)
    return buffer.getvalue()
