"""Favoritos del menú lateral, guardados por usuario en app/data/favoritos.json.

{"correo@usuario": ["inicio", "cotizaciones", ...]}  (en el orden en que se agregaron)
Quien todavía no ha elegido los suyos ve los favoritos iniciales.
"""
import threading

import almacen

ARCHIVO = 'favoritos.json'
INICIALES = ['inicio', 'cotizaciones']
MAXIMO = 15

_lock = threading.Lock()


def de_usuario(usuario):
    guardados = almacen.leer(ARCHIVO, {})
    return list(guardados[usuario]) if usuario in guardados else list(INICIALES)


def alternar(usuario, clave):
    """Agrega la opción si no estaba o la quita si ya estaba. Devuelve (lista, error)."""
    with _lock:
        guardados = almacen.leer(ARCHIVO, {})
        lista = list(guardados[usuario]) if usuario in guardados else list(INICIALES)
        if clave in lista:
            lista.remove(clave)
        elif len(lista) >= MAXIMO:
            return lista, f'Puedes tener hasta {MAXIMO} favoritos.'
        else:
            lista.append(clave)
        guardados[usuario] = lista
        almacen.escribir(ARCHIVO, guardados)
    return lista, None
