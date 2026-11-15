"""Agentes de la mesa de ayuda y sus tareas.

Los agentes vienen de tres lugares:
  - 'panel':   agregados en Dashboard > Agentes (app/data/agentes.json)
  - 'usuario': usuarios con rol Técnico
  - 'glpi':    técnicos asignados en tickets de GLPI
Solo los agregados en el panel se pueden eliminar desde aquí.

Las tareas se guardan en app/data/tareas.json y suman a la carga del agente
junto con sus tickets abiertos de GLPI.
"""
import re
from datetime import date, datetime

import almacen
from auth import usuarios
from . import glpi

ARCHIVO_AGENTES = 'agentes.json'
ARCHIVO_TAREAS = 'tareas.json'

# Técnicos adicionales para la vista de ejemplo (sin GLPI configurado y sin agentes propios)
EJEMPLO_EXTRA = ['Camila Torres', 'Sergio Vega', 'Paula Andrade']

ESPECIALIDADES = ['Mesa de ayuda N1', 'Mesa de ayuda N2', 'Mesa de ayuda N3', 'Redes',
                  'Nube', 'Ciberseguridad', 'Servidores', 'Soporte en sitio']
PRIORIDADES_TAREA = {'baja': 'Baja', 'media': 'Media', 'alta': 'Alta', 'urgente': 'Urgente'}

LIMITE_SATURADO = 3       # tickets + tareas abiertas a partir de los cuales está saturado
PRIORIDAD_URGENTE = 5     # Muy alta o Mayor en GLPI
PATRON_CORREO = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


# ---------- Agentes agregados en el panel ----------

def listar_agentes():
    return almacen.leer(ARCHIVO_AGENTES, [])


def validar_agente(nombre, correo, especialidad, nombres_existentes):
    errores = {}
    if len(nombre.strip()) < 3:
        errores['nombre'] = 'Escribe el nombre completo.'
    elif nombre.strip().lower() in nombres_existentes:
        errores['nombre'] = 'Ya existe un agente con ese nombre.'
    if correo.strip() and not PATRON_CORREO.match(correo.strip()):
        errores['correo'] = 'Escribe un correo válido o déjalo vacío.'
    if especialidad not in ESPECIALIDADES:
        errores['especialidad'] = 'Elige una especialidad.'
    return errores


def crear_agente(nombre, correo, especialidad):
    lista = listar_agentes()
    agente = {
        'id': max((a['id'] for a in lista), default=0) + 1,
        'nombre': nombre.strip(),
        'correo': correo.strip().lower(),
        'especialidad': especialidad,
        'creado': datetime.now().strftime('%Y-%m-%d %H:%M'),
    }
    lista.append(agente)
    almacen.escribir(ARCHIVO_AGENTES, lista)
    return agente


def eliminar_agente(agente_id):
    """Elimina el agente y sus tareas. Devuelve el agente eliminado o None."""
    lista = listar_agentes()
    agente = next((a for a in lista if a['id'] == agente_id), None)
    if agente:
        almacen.escribir(ARCHIVO_AGENTES, [a for a in lista if a['id'] != agente_id])
        tareas = [t for t in listar_tareas() if t['agente'].lower() != agente['nombre'].lower()]
        almacen.escribir(ARCHIVO_TAREAS, tareas)
    return agente


# ---------- Tareas ----------

def listar_tareas():
    return almacen.leer(ARCHIVO_TAREAS, [])


def validar_tarea(agente, titulo, prioridad, fecha_limite, nombres_agentes):
    errores = {}
    if agente.strip().lower() not in nombres_agentes:
        errores['agente'] = 'Elige un agente.'
    if len(titulo.strip()) < 4:
        errores['titulo'] = 'Escribe la tarea (al menos 4 caracteres).'
    if prioridad not in PRIORIDADES_TAREA:
        errores['prioridad'] = 'Elige la prioridad.'
    if fecha_limite:
        try:
            if date.fromisoformat(fecha_limite) < date.today():
                errores['fecha_limite'] = 'La fecha límite no puede estar en el pasado.'
        except ValueError:
            errores['fecha_limite'] = 'Fecha no válida.'
    return errores


def crear_tarea(agente, titulo, descripcion, prioridad, fecha_limite, creado_por):
    tareas = listar_tareas()
    tarea = {
        'id': max((t['id'] for t in tareas), default=0) + 1,
        'agente': agente.strip(),
        'titulo': titulo.strip(),
        'descripcion': descripcion.strip(),
        'prioridad': prioridad,
        'fecha_limite': fecha_limite or '',
        'estado': 'abierta',
        'creado_por': creado_por,
        'creado': datetime.now().strftime('%Y-%m-%d %H:%M'),
    }
    tareas.append(tarea)
    almacen.escribir(ARCHIVO_TAREAS, tareas)
    return tarea


def completar_tarea(tarea_id):
    tareas = listar_tareas()
    tarea = next((t for t in tareas if t['id'] == tarea_id), None)
    if tarea:
        tarea['estado'] = 'completada'
        tarea['completada'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        almacen.escribir(ARCHIVO_TAREAS, tareas)
    return tarea


def eliminar_tarea(tarea_id):
    tareas = listar_tareas()
    tarea = next((t for t in tareas if t['id'] == tarea_id), None)
    if tarea:
        almacen.escribir(ARCHIVO_TAREAS, [t for t in tareas if t['id'] != tarea_id])
    return tarea


# ---------- Vista de la oficina ----------

def _tecnicos_de(ticket):
    return [n.strip() for n in ticket['tecnico'].split(',') if n.strip()]


def construir(tickets, origen):
    propios = listar_agentes()

    # (nombre, origen, datos extra) sin repetidos, conservando el orden
    candidatos = [(a['nombre'], 'panel', a) for a in propios]
    candidatos += [(u['nombre'], 'usuario', {}) for u in usuarios.listar() if u['rol'] == 'tecnico' and u['activo']]
    for t in tickets:
        candidatos += [(n, 'glpi', {}) for n in _tecnicos_de(t)]
    if origen == 'ejemplo' and not propios:
        candidatos += [(n, 'ejemplo', {}) for n in EJEMPLO_EXTRA]

    vistos, unicos = set(), []
    for nombre, fuente, extra in candidatos:
        if nombre.lower() not in vistos:
            vistos.add(nombre.lower())
            unicos.append((nombre, fuente, extra))

    tareas_abiertas = [t for t in listar_tareas() if t['estado'] == 'abierta']

    agentes = []
    for nombre, fuente, extra in unicos:
        asignados = [t for t in tickets if nombre.lower() in (x.lower() for x in _tecnicos_de(t))]
        tareas = [t for t in tareas_abiertas if t['agente'].lower() == nombre.lower()]
        urgentes = (sum(1 for t in asignados if t['prioridad'] >= PRIORIDAD_URGENTE)
                    + sum(1 for t in tareas if t['prioridad'] == 'urgente'))
        carga = len(asignados) + len(tareas)
        if not carga:
            estado = 'libre'
        elif carga >= LIMITE_SATURADO or urgentes:
            estado = 'saturado'
        else:
            estado = 'ocupado'
        agentes.append({
            'id': extra.get('id'),
            'nombre': nombre,
            'origen': fuente,
            'especialidad': extra.get('especialidad', ''),
            'correo': extra.get('correo', ''),
            'estado': estado,
            'asignados': len(asignados),
            'pendientes': sum(1 for t in asignados if t['estado'] == glpi.PENDIENTE),
            'urgentes': urgentes,
            'tareas': len(tareas),
            'tickets': [{'id': t['id'], 'titulo': t['titulo']} for t in asignados[:5]],
            'lista_tareas': [{'id': t['id'], 'titulo': t['titulo']} for t in tareas[:5]],
        })

    return {
        'agentes': agentes,
        'sin_asignar': sum(1 for t in tickets if not t['tecnico'] and t['estado'] == glpi.NUEVO),
        'conteo': {e: sum(1 for a in agentes if a['estado'] == e) for e in ('libre', 'ocupado', 'saturado')},
        'resumen': glpi.resumen(tickets),
        'origen': origen,
    }
