"""Comandos remotos que el panel envía a los agentes.

Flujo:
  1. Alguien con permiso escribe un script en el panel  -> estado 'pendiente'
  2. El agente pregunta cada pocos segundos y lo recibe  -> 'enviado'
  3. El agente lo ejecuta en segundo plano (SYSTEM / root) y devuelve la salida
                                                         -> 'terminado' o 'error'
  Si el agente no responde a tiempo                      -> 'sin respuesta'

Todo queda guardado en app/data/comandos.json como registro de auditoría:
  - quién lo envió en la plataforma (correo, rol, IP desde donde lo envió)
  - con qué cuenta corrió en el equipo (p. ej. nt authority\\system)
  - qué usuario tenía la sesión abierta en el equipo en ese momento
"""
import threading
import time
import uuid

import almacen

ARCHIVO = 'comandos.json'
LARGO_SCRIPT = 20_000        # caracteres
LARGO_SALIDA = 64_000        # caracteres que se guardan de la salida
TIEMPOS = [60, 300, 900, 3600]  # segundos que puede tardar un comando
MAXIMO_REGISTROS = 5000

_lock = threading.Lock()


def _leer():
    return almacen.leer(ARCHIVO, [])


def _escribir(lista):
    almacen.escribir(ARCHIVO, lista[-MAXIMO_REGISTROS:])


def _vencer(lista, ahora):
    # Marca como 'sin respuesta' lo que el agente no contestó a tiempo
    cambio = False
    for c in lista:
        if c['estado'] == 'pendiente' and ahora - c['creado'] > 600:
            c.update(estado='sin respuesta', salida='El equipo no recogió el comando en 10 minutos (¿está apagado?).')
            cambio = True
        elif c['estado'] == 'enviado' and ahora - c['enviado'] > c['tiempo'] + 120:
            c.update(estado='sin respuesta', salida='El agente no devolvió el resultado a tiempo.')
            cambio = True
    return cambio


def crear(equipo_id, equipo_nombre, script, tiempo, usuario, rol, ip_panel, descripcion=''):
    comando = {
        'id': uuid.uuid4().hex,
        'equipo': equipo_id,
        'equipo_nombre': equipo_nombre,
        'script': script[:LARGO_SCRIPT],
        'descripcion': descripcion[:120],
        'tiempo': tiempo if tiempo in TIEMPOS else 300,
        # Quién lo envió desde la plataforma
        'usuario': usuario,
        'rol': rol,
        'ip_panel': ip_panel,
        # Lo completa el agente al ejecutarlo
        'cuenta_equipo': '',
        'sesion_equipo': '',
        'estado': 'pendiente',
        'creado': time.time(),
        'enviado': None,
        'terminado': None,
        'codigo': None,
        'salida': '',
    }
    with _lock:
        lista = _leer()
        lista.append(comando)
        _escribir(lista)
    return comando


def para_agente(equipo_id):
    """Entrega al agente sus comandos pendientes y los marca como enviados."""
    ahora = time.time()
    with _lock:
        lista = _leer()
        cambio = _vencer(lista, ahora)
        entregar = []
        for c in lista:
            if c['equipo'] == equipo_id and c['estado'] == 'pendiente':
                c.update(estado='enviado', enviado=ahora)
                entregar.append({'id': c['id'], 'script': c['script'], 'tiempo': c['tiempo']})
        if entregar or cambio:
            _escribir(lista)
    return entregar


def registrar_resultado(comando_id, equipo_id, codigo, salida, cuenta='', sesion=''):
    """Guarda lo que devolvió el agente. Devuelve el comando actualizado o None."""
    with _lock:
        lista = _leer()
        c = next((c for c in lista if c['id'] == comando_id and c['equipo'] == equipo_id), None)
        if c is None or c['estado'] != 'enviado':
            return None
        try:
            codigo = int(codigo)
        except (TypeError, ValueError):
            codigo = -1
        c.update(estado='terminado' if codigo == 0 else 'error', codigo=codigo,
                 salida=str(salida or '')[:LARGO_SALIDA], terminado=time.time(),
                 cuenta_equipo=str(cuenta or '')[:120], sesion_equipo=str(sesion or '')[:120])
        _escribir(lista)
        return dict(c)


def historial(equipo_id=None, cantidad=None):
    """Comandos del más reciente al más antiguo; de un equipo o de todos."""
    with _lock:
        lista = _leer()
        if _vencer(lista, time.time()):
            _escribir(lista)
    if equipo_id:
        lista = [c for c in lista if c['equipo'] == equipo_id]
    lista = list(reversed(lista))
    return lista[:cantidad] if cantidad else lista
