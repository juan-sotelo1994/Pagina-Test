"""Comandos remotos que el panel envía a los agentes.

Flujo:
  1. Alguien con permiso escribe un script en el panel  -> estado 'pendiente'
  2. El agente pregunta cada pocos segundos y lo recibe  -> 'enviado'
  3. El agente lo ejecuta en segundo plano (SYSTEM / root) y devuelve la salida
                                                         -> 'terminado' o 'error'
  Si el agente no responde a tiempo                      -> 'sin respuesta'

Todo queda guardado en app/data/comandos.json como registro de auditoría:
quién envió qué, a qué equipo, cuándo y qué respondió.
"""
import threading
import time
import uuid

import almacen

ARCHIVO = 'comandos.json'
LARGO_SCRIPT = 20_000        # caracteres
LARGO_SALIDA = 64_000        # caracteres que se guardan de la salida
TIEMPOS = [60, 300, 900, 3600]  # segundos que puede tardar un comando
MAXIMO_REGISTROS = 2000

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


def crear(equipo_id, script, tiempo, usuario, descripcion=''):
    comando = {
        'id': uuid.uuid4().hex,
        'equipo': equipo_id,
        'script': script[:LARGO_SCRIPT],
        'descripcion': descripcion[:120],
        'tiempo': tiempo if tiempo in TIEMPOS else 300,
        'usuario': usuario,
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


def registrar_resultado(comando_id, equipo_id, codigo, salida):
    with _lock:
        lista = _leer()
        c = next((c for c in lista if c['id'] == comando_id and c['equipo'] == equipo_id), None)
        if c is None or c['estado'] != 'enviado':
            return False
        try:
            codigo = int(codigo)
        except (TypeError, ValueError):
            codigo = -1
        c.update(estado='terminado' if codigo == 0 else 'error', codigo=codigo,
                 salida=str(salida or '')[:LARGO_SALIDA], terminado=time.time())
        _escribir(lista)
    return True


def historial(equipo_id, cantidad=20):
    with _lock:
        lista = _leer()
        if _vencer(lista, time.time()):
            _escribir(lista)
    propios = [c for c in lista if c['equipo'] == equipo_id]
    return list(reversed(propios[-cantidad:]))
