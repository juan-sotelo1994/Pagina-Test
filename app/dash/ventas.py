"""Órdenes de compra, facturas y movimientos de inventario.

Cuando una cotización pasa a «Aprobada» se dispara aprobar():
  1. Crea la orden de compra (ORD-AAAA-0001) con todas las líneas.
  2. Descuenta del stock los productos y deja un movimiento por cada uno.
  3. Pasa los equipos de renta a «Rentado» con el cliente y las fechas.
  4. Emite la factura (FV-0001) con productos, servicios y renta.
  5. Los servicios (configuración, asesoría…) quedan en la orden como
     pendientes de prestar, para marcarlos a medida que se hacen.
anular() deshace todo: devuelve el stock, libera los equipos y anula la factura.

Se guarda en app/data/ordenes.json, facturas.json y movimientos_inventario.json.
"""
import calendar
import math
import re
import threading
import uuid
from datetime import date, datetime, timedelta

from nucleo import almacen
from . import catalogo

ORDENES = 'ordenes.json'
FACTURAS = 'facturas.json'
MOVIMIENTOS = 'movimientos_inventario.json'

ESTADOS_ORDEN = {'abierta': 'Servicios pendientes', 'completada': 'Completada', 'anulada': 'Anulada'}
ESTADOS_FACTURA = ['Pendiente', 'Vencida', 'Pagada', 'Anulada']  # Vencida se calcula
MEDIOS_PAGO = ['Transferencia', 'Consignación', 'Efectivo', 'Tarjeta', 'Cheque']

_lock = threading.Lock()


def _ahora():
    return datetime.now().strftime('%Y-%m-%d %H:%M')


def _consecutivo(lista, prefijo):
    usados = [int(m.group(1)) for x in lista if (m := re.fullmatch(rf'{prefijo}(\d+)', x['numero']))]
    return f'{prefijo}{max(usados, default=0) + 1:04d}'


def dias_de_pago(forma_pago):
    """'Crédito 30 días' → 30; contado o anticipo → 0."""
    m = re.search(r'(\d+)\s*d[ií]as', forma_pago or '')
    return int(m.group(1)) if m else 0


def _sumar_periodos(inicio, unidad, cantidad):
    n = max(1, math.ceil(cantidad))
    if unidad == 'Día':
        return inicio + timedelta(days=n - 1)
    if unidad == 'Semana':
        return inicio + timedelta(weeks=n) - timedelta(days=1)
    mes = inicio.month - 1 + n
    anio, mes = inicio.year + mes // 12, mes % 12 + 1
    return date(anio, mes, min(inicio.day, calendar.monthrange(anio, mes)[1])) - timedelta(days=1)


# ---------------------------------------------------------------- Aprobación

def aprobar(cot, usuario):
    """Devuelve (orden, factura, problemas). Si hay problemas no se cambia nada."""
    if cot.get('orden_id'):
        return None, None, ['Esta cotización ya tiene una orden de compra.']
    hoy = date.today()
    productos, rentas, problemas = {}, {}, []
    for i in cot['items']:
        if i['tipo'] == 'producto' and i.get('ref_id'):
            productos[i['ref_id']] = productos.get(i['ref_id'], 0) - i['cantidad']
        elif i['tipo'] == 'renta' and i.get('ref_id'):
            if not cot.get('cliente_id'):
                problemas.append('Para rentar equipos el cliente debe estar registrado en Comercial › Clientes.')
                break
            if i['ref_id'] in rentas:
                problemas.append(f"{i['nombre']} aparece dos veces; un equipo solo se puede rentar una vez.")
                continue
            rentas[i['ref_id']] = {
                'estado': 'Rentado', 'cliente_id': cot['cliente_id'], 'renta_inicio': hoy.isoformat(),
                'renta_fin': _sumar_periodos(hoy, i.get('unidad', 'Mes'), i['cantidad']).isoformat(),
            }
    if problemas:
        return None, None, problemas

    with _lock:
        problemas, stock_final = catalogo.mover_inventario(productos, rentas)
        if problemas:
            return None, None, problemas
        ordenes = almacen.leer(ORDENES, [])
        facturas = almacen.leer(FACTURAS, [])
        orden_id, factura_id = uuid.uuid4().hex[:12], uuid.uuid4().hex[:12]
        numero_orden = _consecutivo(ordenes, f'ORD-{hoy.year}-')
        numero_factura = _consecutivo(facturas, 'FV-')
        cliente = {**cot['cliente'], 'id': cot.get('cliente_id', '')}
        comunes = {
            'cotizacion_id': cot['id'], 'cotizacion_numero': cot['numero'], 'cliente': cliente,
            'contacto': cot.get('contacto', ''), 'contacto_correo': cot.get('contacto_correo', ''),
            'contacto_telefono': cot.get('contacto_telefono', ''), 'asunto': cot['asunto'],
            'items': cot['items'], 'totales': cot['totales'], 'forma_pago': cot.get('forma_pago', ''),
            'creado': _ahora(), 'creado_por': usuario,
        }
        servicios = [{'linea': n, 'nombre': i['nombre'], 'detalle': i.get('detalle', ''), 'cantidad': i['cantidad'],
                      'unidad': i['unidad'], 'estado': 'pendiente', 'realizado': '', 'realizado_por': ''}
                     for n, i in enumerate(cot['items']) if i['tipo'] == 'servicio']
        orden = {
            'id': orden_id, 'numero': numero_orden, 'fecha': hoy.isoformat(), **comunes,
            'tiempo_entrega': cot.get('tiempo_entrega', ''), 'garantia': cot.get('garantia', ''),
            'estado': 'abierta' if servicios else 'completada', 'servicios': servicios,
            'productos_descontados': {pid: -d for pid, d in productos.items() if pid in stock_final},
            'rentas': list(rentas), 'factura_id': factura_id, 'factura_numero': numero_factura,
            'historial': [{'fecha': _ahora(), 'usuario': usuario, 'accion': f"Generada al aprobar {cot['numero']}"}],
        }
        factura = {
            'id': factura_id, 'numero': numero_factura, 'fecha': hoy.isoformat(),
            'vence': (hoy + timedelta(days=dias_de_pago(cot.get('forma_pago')))).isoformat(), **comunes,
            'orden_id': orden_id, 'orden_numero': numero_orden, 'estado': 'Pendiente', 'pago': None,
            'historial': [{'fecha': _ahora(), 'usuario': usuario, 'accion': f'Emitida desde {numero_orden}'}],
        }
        ordenes.append(orden)
        facturas.append(factura)
        almacen.escribir(ORDENES, ordenes)
        almacen.escribir(FACTURAS, facturas)
        _registrar_movimientos([(pid, -cant, stock_final[pid]) for pid, cant in orden['productos_descontados'].items()],
                               f'Salida por {numero_orden}', numero_orden, usuario)
    return orden, factura, []


def anular(orden_id, usuario, motivo=''):
    """Devuelve (orden, error)."""
    with _lock:
        ordenes = almacen.leer(ORDENES, [])
        orden = next((o for o in ordenes if o['id'] == orden_id), None)
        if orden is None:
            return None, 'Esa orden no existe.'
        if orden['estado'] == 'anulada':
            return None, 'La orden ya está anulada.'
        facturas = almacen.leer(FACTURAS, [])
        factura = next((f for f in facturas if f['id'] == orden['factura_id']), None)
        if factura and factura['estado'] == 'Pagada':
            return None, f"La factura {factura['numero']} ya está pagada; no se puede anular la orden."

        # Solo se liberan los equipos que siguen rentados a este cliente
        renta = {x['id']: x for x in catalogo.listar('renta')}
        liberar = {rid: {'estado': 'Disponible', 'cliente_id': '', 'renta_inicio': '', 'renta_fin': ''}
                   for rid in orden['rentas']
                   if rid in renta and renta[rid].get('estado') == 'Rentado' and renta[rid].get('cliente_id') == orden['cliente']['id']}
        _, stock_final = catalogo.mover_inventario(orden['productos_descontados'], liberar, revisar=False)

        texto = 'Anulada' + (f': {motivo}' if motivo else '')
        orden['estado'] = 'anulada'
        orden['historial'].append({'fecha': _ahora(), 'usuario': usuario, 'accion': texto})
        if factura:
            factura['estado'] = 'Anulada'
            factura['historial'].append({'fecha': _ahora(), 'usuario': usuario, 'accion': f"{texto} (orden {orden['numero']})"})
        almacen.escribir(ORDENES, ordenes)
        almacen.escribir(FACTURAS, facturas)
        _registrar_movimientos([(pid, cant, stock_final[pid]) for pid, cant in orden['productos_descontados'].items()
                                if pid in stock_final], f"Devolución por anulación de {orden['numero']}", orden['numero'], usuario)
    return orden, None


# ---------------------------------------------------------------- Órdenes

def listar_ordenes(estado=None):
    lista = sorted(almacen.leer(ORDENES, []), key=lambda o: o['numero'], reverse=True)
    return [o for o in lista if not estado or o['estado'] == estado]


def obtener_orden(orden_id):
    return next((o for o in almacen.leer(ORDENES, []) if o['id'] == orden_id), None)


def orden_activa_de(cot_id):
    return next((o for o in almacen.leer(ORDENES, []) if o['cotizacion_id'] == cot_id and o['estado'] != 'anulada'), None)


def marcar_servicio(orden_id, linea, hecho, usuario):
    with _lock:
        ordenes = almacen.leer(ORDENES, [])
        orden = next((o for o in ordenes if o['id'] == orden_id), None)
        servicio = next((s for s in (orden or {}).get('servicios', []) if s['linea'] == linea), None)
        if servicio is None or orden['estado'] == 'anulada':
            return None
        servicio.update(estado='realizado' if hecho else 'pendiente', realizado=_ahora() if hecho else '',
                        realizado_por=usuario if hecho else '')
        orden['estado'] = 'completada' if all(s['estado'] == 'realizado' for s in orden['servicios']) else 'abierta'
        orden['historial'].append({'fecha': _ahora(), 'usuario': usuario,
                                   'accion': f"{servicio['nombre']}: {'realizado' if hecho else 'vuelve a pendiente'}"})
        almacen.escribir(ORDENES, ordenes)
    return orden


# ---------------------------------------------------------------- Facturas

def _completar_factura(f):
    f['estado_actual'] = 'Vencida' if f['estado'] == 'Pendiente' and f['vence'] < date.today().isoformat() else f['estado']
    return f


def listar_facturas(estado=None):
    lista = [_completar_factura(f) for f in sorted(almacen.leer(FACTURAS, []), key=lambda f: f['numero'], reverse=True)]
    return [f for f in lista if not estado or f['estado_actual'] == estado]


def obtener_factura(factura_id):
    f = next((f for f in almacen.leer(FACTURAS, []) if f['id'] == factura_id), None)
    return _completar_factura(f) if f else None


def registrar_pago(factura_id, fecha, medio, referencia, usuario):
    """Devuelve (factura, error)."""
    try:
        fecha = date.fromisoformat(fecha).isoformat()
    except ValueError:
        return None, 'Fecha de pago no válida.'
    if medio not in MEDIOS_PAGO:
        return None, 'Elige el medio de pago.'
    with _lock:
        facturas = almacen.leer(FACTURAS, [])
        f = next((f for f in facturas if f['id'] == factura_id), None)
        if f is None or f['estado'] != 'Pendiente':
            return None, 'Solo se registra el pago de una factura pendiente.'
        f['estado'] = 'Pagada'
        f['pago'] = {'fecha': fecha, 'medio': medio, 'referencia': referencia.strip()[:80], 'usuario': usuario}
        f['historial'].append({'fecha': _ahora(), 'usuario': usuario, 'accion': f'Pago registrado ({medio})'})
        almacen.escribir(FACTURAS, facturas)
    return _completar_factura(f), None


def resumen_facturas(lista):
    conteo = {e: 0 for e in ESTADOS_FACTURA}
    valor = {e: 0 for e in ESTADOS_FACTURA}
    for f in lista:
        conteo[f['estado_actual']] += 1
        valor[f['estado_actual']] += f['totales']['total']
    return {'conteo': conteo, 'valor': valor, 'por_cobrar': valor['Pendiente'] + valor['Vencida']}


def para_panel():
    """Facturas reales en el formato de los gráficos de la vista general."""
    nombres = {'producto': 'Productos', 'servicio': 'Servicios', 'renta': 'Renta', 'libre': 'Otros'}
    resultado = []
    for f in listar_facturas():
        if f['estado'] == 'Anulada':
            continue
        # La categoría que más pesa en la factura
        pesos = {}
        for i in f['items']:
            pesos[i['tipo']] = pesos.get(i['tipo'], 0) + i['total']
        principal = max(pesos, key=pesos.get) if pesos else 'libre'
        resultado.append({
            'id': f['id'], 'numero': f['numero'], 'cliente': f['cliente']['nombre'], 'nit': f['cliente'].get('documento', ''),
            'servicio': nombres[principal], 'fecha': f['fecha'], 'vendedor': f['creado_por'],
            'valor': f['totales']['total'], 'estado': f['estado_actual'],
        })
    return resultado


# ---------------------------------------------------------------- Movimientos de inventario

def _registrar_movimientos(cambios, motivo, referencia, usuario):
    """cambios: [(producto_id, cantidad con signo, stock resultante)]. Se llama con _lock tomado."""
    if not cambios:
        return
    productos = {x['id']: x for x in catalogo.listar('productos')}
    movimientos = almacen.leer(MOVIMIENTOS, [])
    for pid, cantidad, stock in cambios:
        p = productos.get(pid, {})
        movimientos.append({'id': uuid.uuid4().hex[:12], 'fecha': _ahora(), 'producto_id': pid,
                            'codigo': p.get('codigo', ''), 'nombre': p.get('nombre', '(eliminado)'),
                            'cantidad': cantidad, 'stock': stock, 'motivo': motivo, 'referencia': referencia,
                            'usuario': usuario})
    almacen.escribir(MOVIMIENTOS, movimientos)


def actualizar_codigos_movimientos(cambios):
    """cambios: {producto_id: código nuevo}."""
    with _lock:
        movimientos = almacen.leer(MOVIMIENTOS, [])
        for m in movimientos:
            if m.get('producto_id') in cambios:
                m['codigo'] = cambios[m['producto_id']]
        almacen.escribir(MOVIMIENTOS, movimientos)


def registrar_ajuste(producto_id, stock_anterior, stock_nuevo, usuario, nuevo=False):
    """Cuando alguien crea un producto con stock o lo cambia a mano desde el catálogo."""
    if stock_anterior != stock_nuevo:
        with _lock:
            _registrar_movimientos([(producto_id, stock_nuevo - stock_anterior, stock_nuevo)],
                                   'Stock inicial' if nuevo else 'Ajuste manual', '', usuario)


def registrar_entrada(producto_id, form, usuario):
    """Mercancía que llega del proveedor: suma al stock y deja el movimiento. Devuelve (producto, errores)."""
    from . import proveedores  # aquí para evitar importaciones circulares
    errores = {}
    producto = catalogo.obtener('productos', producto_id)
    if producto is None:
        errores['producto_id'] = 'Elige el producto que llegó.'
    try:
        cantidad = int(str(form.get('cantidad', '')).strip())
        if not 1 <= cantidad <= 100000:
            raise ValueError
    except ValueError:
        errores['cantidad'] = 'Escribe cuántas unidades llegaron (número entero).'
    proveedor = None
    if form.get('proveedor_id'):
        proveedor = proveedores.obtener(form['proveedor_id'])
        if proveedor is None:
            errores['proveedor_id'] = 'Ese proveedor ya no existe.'
    costo = None
    if str(form.get('costo', '')).strip():
        try:
            costo = catalogo._numero(form['costo'])
            if costo < 0:
                raise ValueError
        except ValueError:
            errores['costo'] = 'Escribe un precio válido.'
    documento = str(form.get('documento', '')).strip()[:60]
    if errores:
        return None, errores

    cambios_producto = {'proveedor_id': proveedor['id']} if proveedor else {}
    if costo:
        cambios_producto['costo'] = costo  # el precio de compra queda al día con lo último que llegó
    with _lock:
        _, stock_final = catalogo.mover_inventario({producto_id: cantidad}, revisar=False)
        if cambios_producto:
            # Se manda el código actual para que guardar() no genere uno nuevo
            catalogo.guardar('productos', {**cambios_producto, 'codigo': producto['codigo']}, producto_id, usuario)
        detalle = ' · '.join(x for x in (proveedor['nombre'] if proveedor else '', f'doc. {documento}' if documento else '') if x)
        _registrar_movimientos([(producto_id, cantidad, stock_final[producto_id])],
                               'Entrada de mercancía' + (f' ({detalle})' if detalle else ''), documento, usuario)
    return catalogo.obtener('productos', producto_id), {}


def listar_movimientos(producto_id=None):
    lista = almacen.leer(MOVIMIENTOS, [])
    return [m for m in reversed(lista) if not producto_id or m['producto_id'] == producto_id]
