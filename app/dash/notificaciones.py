"""Notificaciones de la campana del panel y del aviso al iniciar sesión.

Reúne lo que necesita atención (facturas vencidas o por vencer, tickets nuevos,
cotizaciones por vencer, servicios por entregar, stock bajo, rentas que terminan
y equipos calientes). Cada usuario ve solo lo de los módulos que su rol puede ver;
el perfil Ventas ve solo sus propias cotizaciones y órdenes.
"""
from datetime import date

from flask import url_for

from . import catalogo, cotizaciones, equipos, glpi, permisos, ventas
from .indicadores import TEMPERATURA_ALTA

DIAS_FACTURA = 5      # avisar las facturas que vencen en estos días
DIAS_COTIZACION = 3   # y las cotizaciones
MAXIMO_POR_TIPO = 5   # el resto se resume en «y N más»
NIVELES = {'alta': 0, 'media': 1, 'info': 2}
ROLES_SOLO_LO_SUYO = ('vendedor', 'preventa')


def _pesos(valor):
    return '$ ' + f'{valor:,.0f}'.replace(',', '.')


def _cuando(fecha_iso):
    """'2026-11-20' -> 'venció hace 2 días' / 'vence hoy' / 'vence mañana' / 'vence en 3 días'."""
    dias = (date.fromisoformat(fecha_iso) - date.today()).days
    if dias < -1:
        return f'venció hace {-dias} días'
    if dias == -1:
        return 'venció ayer'
    if dias == 0:
        return 'vence hoy'
    if dias == 1:
        return 'vence mañana'
    return f'vence en {dias} días'


def _dias(fecha_iso):
    return (date.fromisoformat(fecha_iso) - date.today()).days


def _aviso(area, nivel, icono, titulo, detalle, url):
    return {'area': area, 'nivel': nivel, 'icono': icono, 'titulo': titulo, 'detalle': detalle, 'url': url}


def _limitar(avisos, area, icono, url_todos, texto_mas):
    """Deja los primeros MAXIMO_POR_TIPO y resume el resto en un solo aviso."""
    if len(avisos) <= MAXIMO_POR_TIPO:
        return avisos
    resto = len(avisos) - MAXIMO_POR_TIPO
    mas = _aviso(area, avisos[MAXIMO_POR_TIPO]['nivel'], icono, f'y {resto} {texto_mas}', 'Ver la lista completa', url_todos)
    mas['cantidad'] = resto  # cuenta en el total como los avisos que resume
    return avisos[:MAXIMO_POR_TIPO] + [mas]


def _facturas():
    vencidas, por_vencer = [], []
    for f in ventas.listar_facturas():
        if f['estado_actual'] == 'Vencida':
            vencidas.append(f)
        elif f['estado_actual'] == 'Pendiente' and _dias(f['vence']) <= DIAS_FACTURA:
            por_vencer.append(f)
    vencidas.sort(key=lambda f: f['vence'])
    por_vencer.sort(key=lambda f: f['vence'])
    detalle = lambda f: f"{f['cliente']['nombre']} · {_pesos(f['totales']['total'])} · {_cuando(f['vence'])}"
    avisos = _limitar([_aviso('Facturas', 'alta', 'fa-file-invoice-dollar', f"Factura {f['numero']} vencida", detalle(f),
                              url_for('dashboard.factura_detalle', factura_id=f['id'])) for f in vencidas],
                      'Facturas', 'fa-file-invoice-dollar', url_for('dashboard.facturas_view', estado='Vencida'),
                      'facturas vencidas más')
    avisos += _limitar([_aviso('Facturas', 'media', 'fa-file-invoice', f"Factura {f['numero']} por vencer", detalle(f),
                               url_for('dashboard.factura_detalle', factura_id=f['id'])) for f in por_vencer],
                       'Facturas', 'fa-file-invoice', url_for('dashboard.facturas_view', estado='Pendiente'),
                       'facturas por vencer más')
    return avisos


def _tickets():
    resumen = glpi.resumen(glpi.obtener()[0])
    avisos = []
    if resumen['nuevos']:
        n = resumen['nuevos']
        ultimos = ', '.join(f"#{t['id']}" for t in resumen['ultimos_nuevos'][:3])
        avisos.append(_aviso('Soporte', 'alta', 'fa-ticket', f"{n} ticket{'s' if n > 1 else ''} nuevo{'s' if n > 1 else ''}",
                             f'Sin asignar: {ultimos}' if ultimos else 'Sin asignar',
                             url_for('dashboard.tickets', estado='nuevos')))
    if resumen['pendientes']:
        n = resumen['pendientes']
        avisos.append(_aviso('Soporte', 'media', 'fa-hourglass-half', f"{n} ticket{'s' if n > 1 else ''} pendiente{'s' if n > 1 else ''}",
                             'Esperando respuesta o una acción', url_for('dashboard.tickets', estado='pendientes')))
    return avisos


def _cotizaciones(usuario):
    lista = [c for c in cotizaciones.listar()
             if c['estado_actual'] in ('borrador', 'enviada') and _dias(c['vence']) <= DIAS_COTIZACION
             and (not usuario or c.get('creado_por') == usuario)]
    lista.sort(key=lambda c: c['vence'])
    return _limitar([_aviso('Ventas', 'media', 'fa-file-signature', f"Cotización {c['numero']} por vencer",
                            f"{c['cliente']['nombre']} · {_pesos(c['totales']['total'])} · {_cuando(c['vence'])}",
                            url_for('dashboard.cotizacion_detalle', cot_id=c['id'])) for c in lista],
                    'Ventas', 'fa-file-signature', url_for('dashboard.cotizaciones_view', estado='enviada'),
                    'cotizaciones por vencer más')


def _servicios(usuario):
    avisos = []
    for o in ventas.listar_ordenes('abierta'):
        if usuario and o.get('creado_por') != usuario:
            continue
        pendientes = [s['nombre'] for s in o['servicios'] if s['estado'] == 'pendiente']
        if pendientes:
            avisos.append(_aviso('Ventas', 'info', 'fa-screwdriver-wrench',
                                 f"Orden {o['numero']}: {len(pendientes)} servicio{'s' if len(pendientes) > 1 else ''} por entregar",
                                 f"{o['cliente']['nombre']} · {', '.join(pendientes)}",
                                 url_for('dashboard.orden_detalle', orden_id=o['id'])))
    return _limitar(avisos, 'Ventas', 'fa-screwdriver-wrench', url_for('dashboard.ordenes_view', estado='abierta'),
                    'órdenes con servicios pendientes más')


def _inventario():
    productos = catalogo.listar('productos', solo_activos=True)
    sin_stock = [p for p in productos if (p.get('stock') or 0) <= 0]
    bajo = [p for p in productos if (p.get('stock') or 0) > 0 and p.get('stock_minimo') and p['stock'] <= p['stock_minimo']]
    url = url_for('dashboard.catalogo_view', tipo='productos')
    avisos = _limitar([_aviso('Inventario', 'alta', 'fa-box-open', f"{p['nombre']} sin existencias",
                              f"{p.get('codigo', '')} · stock 0", url) for p in sin_stock],
                      'Inventario', 'fa-box-open', url, 'productos sin existencias más')
    avisos += _limitar([_aviso('Inventario', 'media', 'fa-boxes-stacked', f"{p['nombre']}: stock bajo",
                               f"{p.get('codigo', '')} · quedan {p['stock']} (mínimo {p['stock_minimo']})", url) for p in bajo],
                       'Inventario', 'fa-boxes-stacked', url, 'productos con stock bajo más')
    return avisos


def _renta():
    resumen = catalogo.resumen_renta(catalogo.listar('renta'))
    url = url_for('dashboard.catalogo_view', tipo='renta')
    avisos = [_aviso('Renta', 'alta', 'fa-calendar-xmark', f"Renta vencida: {x['nombre']}",
                     f"{x.get('codigo', '')} · {_cuando(x['renta_fin'])}", url) for x in resumen['vencidas']]
    avisos += [_aviso('Renta', 'media', 'fa-calendar-day', f"Renta por terminar: {x['nombre']}",
                      f"{x.get('codigo', '')} · {_cuando(x['renta_fin'])}", url) for x in resumen['por_vencer']]
    return _limitar(avisos, 'Renta', 'fa-calendar-day', url, 'rentas más')


def _equipos():
    calientes = [e for e in equipos.listar() if e['en_linea']
                 and ((e.get('sensores') or {}).get('cpu_temp') or 0) >= TEMPERATURA_ALTA]
    return [_aviso('Soporte', 'alta', 'fa-temperature-high', f"{e['nombre']}: CPU caliente",
                   f"{e['sensores']['cpu_temp']:.0f} °C", url_for('dashboard.equipo_view', equipo_id=e['id'])) for e in calientes]


# Módulo que hay que poder ver -> cómo se arman sus avisos
FUENTES = [
    ('facturas', lambda u: _facturas()),
    ('tickets', lambda u: _tickets()),
    ('equipos', lambda u: _equipos()),
    ('cotizaciones', _cotizaciones),
    ('ventas', _servicios),
    ('productos', lambda u: _inventario()),
    ('renta', lambda u: _renta()),
]


def para(rol, usuario):
    """{'total', 'alta', 'avisos': [...]} con lo que este usuario debe atender, lo más urgente primero."""
    solo_suyo = usuario if rol in ROLES_SOLO_LO_SUYO else None
    avisos = []
    for modulo, fuente in FUENTES:
        if permisos.puede(rol, modulo, 'ver'):
            try:
                avisos += fuente(solo_suyo)
            except Exception:  # una fuente con problemas (GLPI caído, etc.) no deja sin avisos al resto
                continue
    avisos.sort(key=lambda a: NIVELES[a['nivel']])  # sort estable: dentro de cada nivel se conserva el orden
    cuenta = lambda a: a.get('cantidad', 1)
    return {'total': sum(map(cuenta, avisos)), 'alta': sum(cuenta(a) for a in avisos if a['nivel'] == 'alta'),
            'avisos': avisos}
