"""Indicadores de la vista general, por área.

Cada perfil ve los suyos (ventas, soporte, inventario) y el administrador los
reúne todos. Se calculan con los mismos datos de los módulos del panel.
"""
from collections import Counter
from datetime import date, timedelta

from . import catalogo, cotizaciones, equipos, glpi, ventas

MESES_CORTOS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
TEMPERATURA_ALTA = 85  # °C de CPU a partir de la cual se avisa


def _ultimos_meses(n=6):
    """[(clave 'AAAA-MM', etiqueta 'nov'), ...] del más antiguo al actual."""
    hoy = date.today().replace(day=1)
    meses = []
    for i in range(n - 1, -1, -1):
        anio, mes = divmod(hoy.year * 12 + hoy.month - 1 - i, 12)
        meses.append((f'{anio}-{mes + 1:02d}', MESES_CORTOS[mes]))
    return meses


def _barras(valores_por_mes, n=6):
    meses = _ultimos_meses(n)
    maximo = max([valores_por_mes.get(c, 0) for c, _ in meses] + [1])
    return [{'mes': e, 'valor': valores_por_mes.get(c, 0), 'alto': valores_por_mes.get(c, 0) * 100 / maximo} for c, e in meses]


# ---------------------------------------------------------------- Ventas

def de_ventas(usuario=None):
    """Indicadores comerciales. Con usuario: solo sus cotizaciones y órdenes (perfil Ventas)."""
    hoy = date.today()
    mes = hoy.strftime('%Y-%m')
    cots = [c for c in cotizaciones.listar() if not usuario or c.get('creado_por') == usuario]
    ordenes = [o for o in ventas.listar_ordenes() if o['estado'] != 'anulada' and (not usuario or o.get('creado_por') == usuario)]

    estados = Counter(c['estado_actual'] for c in cots)
    cerradas = estados['aprobada'] + estados['rechazada']
    limite = (hoy + timedelta(days=3)).isoformat()
    por_mes = Counter()
    for o in ordenes:
        por_mes[o['fecha'][:7]] += o['totales']['total']

    return {
        'cotizaciones_mes': sum(1 for c in cots if c['fecha'][:7] == mes),
        'cotizado_mes': sum(c['totales']['total'] for c in cots if c['fecha'][:7] == mes),
        'vendido_mes': por_mes[mes],
        'ordenes_mes': sum(1 for o in ordenes if o['fecha'][:7] == mes),
        'en_negociacion': sum(c['totales']['total'] for c in cots if c['estado_actual'] == 'enviada'),
        'enviadas': estados['enviada'],
        'tasa_cierre': round(estados['aprobada'] * 100 / cerradas) if cerradas else None,
        'estados': {k: estados[k] for k in cotizaciones.ESTADOS},
        'por_vencer': [c for c in cots if c['estado_actual'] in ('borrador', 'enviada') and c['vence'] <= limite],
        'servicios_pendientes': sum(1 for o in ordenes if o['estado'] == 'abierta'),
        'ultimas': cots[:6],
        'barras': _barras(por_mes),
        'tiene_datos': bool(cots or ordenes),
    }


# ---------------------------------------------------------------- Soporte

def de_soporte():
    tickets, origen, error = glpi.obtener()
    resumen = glpi.resumen(tickets)
    lista_equipos = equipos.listar()
    calientes = [e for e in lista_equipos if e['en_linea']
                 and ((e.get('sensores') or {}).get('cpu_temp') or 0) >= TEMPERATURA_ALTA]
    servicios = [{'orden': o, 'servicio': s} for o in ventas.listar_ordenes('abierta')
                 for s in o['servicios'] if s['estado'] == 'pendiente']
    return {
        'nuevos': resumen['nuevos'], 'pendientes': resumen['pendientes'], 'en_curso': resumen['en_curso'],
        'cerrados': glpi.cerrados_recientes(),
        'urgentes': sorted([t for t in tickets if t['prioridad'] >= 4], key=lambda t: (-t['prioridad'], -t['id']))[:6],
        'origen': origen, 'error': error,
        'equipos_total': len(lista_equipos),
        'equipos_en_linea': sum(1 for e in lista_equipos if e['en_linea']),
        'calientes': calientes,
        'servicios': servicios[:6], 'servicios_total': len(servicios),
        'tickets_dona': [
            {'nombre': 'Nuevos', 'cantidad': resumen['nuevos'], 'color': '#3b82f6'},
            {'nombre': 'En curso', 'cantidad': resumen['en_curso'], 'color': '#2bb3a3'},
            {'nombre': 'Pendientes', 'cantidad': resumen['pendientes'], 'color': '#f59e0b'},
        ],
    }


# ---------------------------------------------------------------- Inventario

def de_inventario():
    productos = catalogo.listar('productos', solo_activos=True)
    mes = date.today().strftime('%Y-%m')
    movimientos = ventas.listar_movimientos()
    del_mes = [m for m in movimientos if m['fecha'][:7] == mes]
    entradas_por_mes = Counter()
    for m in movimientos:
        if m['cantidad'] > 0 and m['motivo'].startswith(('Entrada', 'Stock inicial')):
            entradas_por_mes[m['fecha'][:7]] += m['cantidad']
    renta = catalogo.resumen_renta(catalogo.listar('renta'))
    return {
        'productos': len(productos),
        'unidades': sum(p.get('stock') or 0 for p in productos),
        'valor_compra': sum((p.get('stock') or 0) * (p.get('costo') or 0) for p in productos),
        'valor_venta': sum((p.get('stock') or 0) * (p.get('precio') or 0) for p in productos),
        'stock_bajo': [p for p in productos if p.get('stock_minimo') and (p.get('stock') or 0) <= p['stock_minimo']],
        'sin_stock': sum(1 for p in productos if (p.get('stock') or 0) <= 0),
        'entradas_mes': sum(m['cantidad'] for m in del_mes if m['cantidad'] > 0 and m['motivo'].startswith('Entrada')),
        'salidas_mes': -sum(m['cantidad'] for m in del_mes if m['cantidad'] < 0),
        'movimientos': movimientos[:6],
        'barras': _barras(entradas_por_mes),
        'renta': renta,
        'renta_total': sum(renta['conteo'].values()),
    }
