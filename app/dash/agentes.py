"""Agentes de la mesa de ayuda para la oficina 3D.

Un agente es un usuario con rol Técnico o un técnico que aparece asignado
en los tickets de GLPI. Su estado depende de la carga de tickets abiertos.
"""
from auth import usuarios
from . import glpi

# Técnicos adicionales para la vista de ejemplo (sin GLPI configurado)
EJEMPLO_EXTRA = ['Camila Torres', 'Sergio Vega', 'Paula Andrade']

LIMITE_SATURADO = 3       # tickets abiertos a partir de los cuales está saturado
PRIORIDAD_URGENTE = 5     # Muy alta o Mayor


def _tecnicos_de(ticket):
    return [n.strip() for n in ticket['tecnico'].split(',') if n.strip()]


def construir(tickets, origen):
    nombres = [u['nombre'] for u in usuarios.listar() if u['rol'] == 'tecnico' and u['activo']]
    for t in tickets:
        nombres.extend(_tecnicos_de(t))
    if origen == 'ejemplo':
        nombres.extend(EJEMPLO_EXTRA)

    # Sin repetidos, conservando el orden
    vistos, unicos = set(), []
    for n in nombres:
        if n.lower() not in vistos:
            vistos.add(n.lower())
            unicos.append(n)

    agentes = []
    for nombre in unicos:
        asignados = [t for t in tickets if nombre.lower() in (x.lower() for x in _tecnicos_de(t))]
        urgentes = sum(1 for t in asignados if t['prioridad'] >= PRIORIDAD_URGENTE)
        if not asignados:
            estado = 'libre'
        elif len(asignados) >= LIMITE_SATURADO or urgentes:
            estado = 'saturado'
        else:
            estado = 'ocupado'
        agentes.append({
            'nombre': nombre,
            'estado': estado,
            'asignados': len(asignados),
            'pendientes': sum(1 for t in asignados if t['estado'] == glpi.PENDIENTE),
            'urgentes': urgentes,
            'tickets': [{'id': t['id'], 'titulo': t['titulo']} for t in asignados[:5]],
        })

    return {
        'agentes': agentes,
        'sin_asignar': sum(1 for t in tickets if not t['tecnico'] and t['estado'] == glpi.NUEVO),
        'conteo': {e: sum(1 for a in agentes if a['estado'] == e) for e in ('libre', 'ocupado', 'saturado')},
        'resumen': glpi.resumen(tickets),
        'origen': origen,
    }
