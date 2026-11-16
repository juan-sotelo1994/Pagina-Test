"""Cotizaciones: estudio preliminar de productos y servicios para un cliente.

Se guardan en app/data/cotizaciones.json. Los totales siempre se calculan
aquí (nunca se confía en lo que manda el navegador).
"""
import json
import threading
import uuid
from datetime import date, datetime, timedelta

import almacen
from . import catalogo, clientes

ARCHIVO = 'cotizaciones.json'

ESTADOS = {
    'borrador': 'Borrador',
    'enviada': 'Enviada',
    'aprobada': 'Aprobada',
    'rechazada': 'Rechazada',
    'vencida': 'Vencida',  # calculado: borrador/enviada que pasó su validez
}
EDITABLES = ('borrador', 'enviada')

FORMAS_PAGO = ['Contado', '50% anticipo y 50% contra entrega', 'Crédito 30 días', 'Crédito 60 días', 'Mensualidad anticipada']

CONDICIONES_INICIALES = {
    'forma_pago': 'Contado',
    'tiempo_entrega': '5 días hábiles después de aprobada',
    'garantia': '12 meses en equipos por defecto de fábrica; 30 días en servicios',
    'validez_dias': 15,
}

CAMPOS = ('cliente_id', 'prospecto_nombre', 'prospecto_documento', 'contacto', 'contacto_correo', 'contacto_telefono',
          'asunto', 'necesidad', 'propuesta', 'forma_pago', 'tiempo_entrega', 'garantia', 'validez_dias', 'notas', 'fecha')

_lock = threading.Lock()


def _numero(valor, por_defecto=0.0):
    try:
        return catalogo._numero(valor)
    except (TypeError, ValueError):
        return por_defecto


def limpiar_items(crudos):
    """Valida las líneas enviadas por el editor y calcula sus valores."""
    catalogos = catalogo.por_tipo_item()
    items = []
    for crudo in crudos if isinstance(crudos, list) else []:
        if not isinstance(crudo, dict):
            continue
        tipo = crudo.get('tipo') if crudo.get('tipo') in ('producto', 'servicio', 'renta') else 'libre'
        ref = catalogos.get(tipo, {}).get(str(crudo.get('ref_id', '')))
        if tipo != 'libre' and ref is None:
            tipo = 'libre'  # el producto se borró del catálogo: queda como línea libre
        nombre = str(crudo.get('nombre') or (ref or {}).get('nombre', '')).strip()[:160]
        if not nombre:
            continue
        cantidad = max(_numero(crudo.get('cantidad'), 1), 0)
        precio = max(_numero(crudo.get('precio')), 0)
        descuento = min(max(_numero(crudo.get('descuento')), 0), 100)
        iva = _numero(crudo.get('iva'))
        iva = iva if iva in (0, 5, 19) else 19
        bruto = cantidad * precio
        valor_descuento = round(bruto * descuento / 100, 2)
        base = bruto - valor_descuento
        valor_iva = round(base * iva / 100, 2)
        items.append({
            'tipo': tipo, 'ref_id': ref['id'] if ref else '', 'codigo': (ref or {}).get('codigo', str(crudo.get('codigo', ''))[:30]),
            'nombre': nombre, 'detalle': str(crudo.get('detalle', '')).strip()[:1000],
            'unidad': str(crudo.get('unidad') or (ref or {}).get('unidad', 'Unidad'))[:30],
            'cantidad': cantidad, 'precio': precio, 'descuento': descuento, 'iva': iva,
            'bruto': round(bruto, 2), 'valor_descuento': valor_descuento, 'base': round(base, 2),
            'valor_iva': valor_iva, 'total': round(base + valor_iva, 2),
        })
    return items


def totales(items):
    por_tarifa = {}
    for i in items:
        if i['iva']:
            por_tarifa[i['iva']] = por_tarifa.get(i['iva'], 0) + i['valor_iva']
    resultado = {
        'bruto': sum(i['bruto'] for i in items),
        'descuento': sum(i['valor_descuento'] for i in items),
        'base': sum(i['base'] for i in items),
        'iva': sum(i['valor_iva'] for i in items),
        'iva_por_tarifa': [{'tarifa': t, 'valor': round(v, 2)} for t, v in sorted(por_tarifa.items(), reverse=True)],
        'productos': sum(i['total'] for i in items if i['tipo'] == 'producto'),
        'servicios': sum(i['total'] for i in items if i['tipo'] == 'servicio'),
        'rentas': sum(i['total'] for i in items if i['tipo'] == 'renta'),
    }
    resultado['total'] = resultado['base'] + resultado['iva']
    return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in resultado.items()}


def validar(form, items_json):
    """Devuelve (datos limpios, errores)."""
    datos = {k: str(form.get(k, '')).strip() for k in CAMPOS}
    errores = {}
    try:
        crudos = json.loads(items_json or '[]')
    except ValueError:
        crudos = []
    datos['items'] = limpiar_items(crudos)

    if datos['cliente_id']:
        cliente = clientes.obtener_cliente(datos['cliente_id'])
        if cliente is None:
            errores['cliente_id'] = 'Ese cliente ya no existe.'
        datos['prospecto_nombre'] = datos['prospecto_documento'] = ''
    elif not datos['prospecto_nombre']:
        errores['cliente_id'] = 'Elige un cliente registrado o escribe el nombre del prospecto.'
    if not datos['asunto']:
        errores['asunto'] = 'Escribe el asunto de la cotización.'
    if not datos['items']:
        errores['items'] = 'Agrega al menos un producto o servicio.'
    try:
        datos['fecha'] = date.fromisoformat(datos['fecha']).isoformat() if datos['fecha'] else date.today().isoformat()
    except ValueError:
        errores['fecha'] = 'Fecha no válida.'
    try:
        datos['validez_dias'] = int(datos['validez_dias'] or CONDICIONES_INICIALES['validez_dias'])
        if not 1 <= datos['validez_dias'] <= 365:
            raise ValueError
    except ValueError:
        errores['validez_dias'] = 'Entre 1 y 365 días.'
    for campo, limite in (('asunto', 160), ('necesidad', 4000), ('propuesta', 4000), ('notas', 2000)):
        datos[campo] = datos[campo][:limite]
    return datos, errores


def _siguiente_numero(lista, fecha):
    anio = fecha[:4]
    usados = [int(c['numero'].rsplit('-', 1)[1]) for c in lista if c['numero'].startswith(f'COT-{anio}-')]
    return f'COT-{anio}-{max(usados, default=0) + 1:04d}'


def _completar(c):
    """Agrega los datos calculados que no se guardan: estado vigente, vencimiento y cliente."""
    vence = date.fromisoformat(c['fecha']) + timedelta(days=c.get('validez_dias', 15))
    c['vence'] = vence.isoformat()
    c['estado_actual'] = 'vencida' if c['estado'] in EDITABLES and vence < date.today() else c['estado']
    c['editable'] = c['estado'] in EDITABLES
    cliente = clientes.obtener_cliente(c['cliente_id']) if c.get('cliente_id') else None
    c['cliente'] = {
        'nombre': cliente['nombre'] if cliente else c.get('prospecto_nombre') or c.get('cliente_nombre', ''),
        'documento': clientes.documento_de(cliente) if cliente else c.get('prospecto_documento', ''),
        'registrado': cliente is not None,
    }
    return c


def listar(estado=None):
    lista = [_completar(c) for c in almacen.leer(ARCHIVO, [])]
    if estado:
        lista = [c for c in lista if c['estado_actual'] == estado]
    return sorted(lista, key=lambda c: c['numero'], reverse=True)


def obtener(cot_id):
    c = next((c for c in almacen.leer(ARCHIVO, []) if c['id'] == cot_id), None)
    return _completar(c) if c else None


def guardar(datos, cot_id=None, usuario=''):
    ahora = datetime.now().strftime('%Y-%m-%d %H:%M')
    datos = {**datos, 'totales': totales(datos['items'])}
    # Se guarda el nombre del cliente por si luego lo borran del módulo de clientes
    if datos['cliente_id']:
        cliente = clientes.obtener_cliente(datos['cliente_id'])
        datos['cliente_nombre'] = cliente['nombre'] if cliente else ''
    with _lock:
        lista = almacen.leer(ARCHIVO, [])
        if cot_id:
            c = next((c for c in lista if c['id'] == cot_id), None)
            if c is None or c['estado'] not in EDITABLES:
                return None
            c.update(datos, actualizado=ahora, actualizado_por=usuario)
            c['historial'].append({'fecha': ahora, 'usuario': usuario, 'accion': 'Editada'})
        else:
            c = {'id': uuid.uuid4().hex[:12], 'numero': _siguiente_numero(lista, datos['fecha']), **datos,
                 'estado': 'borrador', 'creado': ahora, 'creado_por': usuario,
                 'historial': [{'fecha': ahora, 'usuario': usuario, 'accion': 'Creada'}]}
            lista.append(c)
        almacen.escribir(ARCHIVO, lista)
    return _completar(dict(c))


def cambiar_estado(cot_id, estado, usuario='', extra=None, accion=None):
    if estado not in ('borrador', 'enviada', 'aprobada', 'rechazada'):
        return None
    ahora = datetime.now().strftime('%Y-%m-%d %H:%M')
    with _lock:
        lista = almacen.leer(ARCHIVO, [])
        c = next((c for c in lista if c['id'] == cot_id), None)
        if c is None:
            return None
        c['estado'] = estado
        c.update(extra or {})
        c['historial'].append({'fecha': ahora, 'usuario': usuario, 'accion': accion or f'Marcada como {ESTADOS[estado].lower()}'})
        almacen.escribir(ARCHIVO, lista)
    return _completar(dict(c))


def duplicar(cot_id, usuario=''):
    original = obtener(cot_id)
    if original is None:
        return None
    datos = {k: original.get(k, '') for k in CAMPOS}
    datos['fecha'] = date.today().isoformat()
    datos['items'] = original['items']
    return guardar(datos, usuario=usuario)


def eliminar(cot_id):
    with _lock:
        lista = almacen.leer(ARCHIVO, [])
        c = next((c for c in lista if c['id'] == cot_id), None)
        if c:
            almacen.escribir(ARCHIVO, [x for x in lista if x['id'] != cot_id])
    return c


def resumen(lista):
    conteo = {k: 0 for k in ESTADOS}
    valor = {k: 0 for k in ESTADOS}
    for c in lista:
        conteo[c['estado_actual']] += 1
        valor[c['estado_actual']] += c['totales']['total']
    return {'conteo': conteo, 'valor': valor}


def formulario_desde(c):
    """Datos para precargar el editor a partir de una cotización guardada."""
    datos = {k: c.get(k, '') for k in CAMPOS}
    datos['items'] = c['items']
    return datos


def formulario_nuevo(cliente_id=''):
    return {**{k: '' for k in CAMPOS}, **CONDICIONES_INICIALES, 'cliente_id': cliente_id,
            'fecha': date.today().isoformat(), 'items': []}
