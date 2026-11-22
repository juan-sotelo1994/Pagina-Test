"""Catálogos: productos para la venta (con stock), servicios y productos en renta.

Los tres comparten la misma lógica; cada uno se describe en CATALOGOS:
campos del formulario y prefijo del código. Se guardan en
app/data/productos.json, servicios.json y renta.json.

Los productos en renta se registran uno por uno (cada equipo con su serial)
porque cada unidad puede estar con un cliente distinto.
"""
import re
import threading
import uuid
from datetime import date, datetime

from nucleo import almacen

IVAS = ['19', '5', '0']

# Precios de venta de un producto, de mayor a menor, para negociar en la cotización
NIVELES_PRECIO = [('precio', 'Lista'), ('precio2', 'Preferencial'), ('precio3', 'Mínimo')]
ESTADOS_RENTA = ['Disponible', 'Rentado', 'En mantenimiento', 'De baja']

# (nombre, etiqueta, tipo, opciones, obligatorio, ayuda)
CATALOGOS = {
    'productos': {
        'archivo': 'productos.json', 'titulo': 'Productos', 'singular': 'producto', 'icono': 'fa-box-open',
        'prefijo': 'PROD', 'codigo_auto': True, 'tres_precios': True, 'grupo': 'Inventario', 'tipo_item': 'producto',
        'campos': [
            ('nombre', 'Nombre', 'text', None, True, ''),
            ('codigo', 'Código interno', 'auto', None, False, 'Se asigna solo y no se repite.'),
            ('sku', 'Referencia del fabricante (SKU)', 'text', None, False, 'El código del fabricante o del proveedor.'),
            ('categoria', 'Categoría', 'select', ['Computadores', 'Servidores', 'Redes', 'Almacenamiento', 'Periféricos',
                                                  'Licencias', 'Seguridad', 'Repuestos', 'Otros'], True, ''),
            ('marca', 'Marca', 'text', None, False, ''),
            ('unidad', 'Unidad', 'select', ['Unidad', 'Licencia', 'Caja', 'Metro', 'Kit'], True, ''),
            ('descripcion', 'Descripción', 'textarea', None, False, 'Aparece en la cotización debajo del nombre.'),
            # Compra: lo que le pagamos al proveedor. Venta: lo que le cobramos al cliente
            ('proveedor_id', 'Proveedor', 'proveedor', None, False, 'A quién se le compra.'),
            ('costo', 'Precio de compra (sin IVA)', 'money', None, False, 'Lo que le pagamos al proveedor. No se muestra al cliente.'),
            ('precio', 'Precio 1 · Lista (sin IVA)', 'money', None, True, 'El precio normal al público.'),
            ('precio2', 'Precio 2 · Preferencial (sin IVA)', 'money', None, False, 'Clientes frecuentes o por volumen. Vacío = igual al de lista.'),
            ('precio3', 'Precio 3 · Mínimo (sin IVA)', 'money', None, False, 'El piso de negociación. Vacío = igual al preferencial.'),
            ('iva', 'IVA', 'iva', IVAS, True, ''),
            ('stock', 'Stock disponible', 'int', None, False, ''),
            ('stock_minimo', 'Stock mínimo', 'int', None, False, 'Por debajo de este número se marca en rojo.'),
        ],
    },
    'servicios': {
        'archivo': 'servicios.json', 'titulo': 'Servicios', 'singular': 'servicio', 'icono': 'fa-layer-group',
        'prefijo': 'SER', 'codigo_auto': True, 'tres_precios': True, 'grupo': 'Inventario', 'tipo_item': 'servicio',
        'campos': [
            ('codigo', 'Código interno', 'auto', None, False, 'Se asigna solo y no se repite.'),
            ('nombre', 'Nombre', 'text', None, True, ''),
            ('categoria', 'Categoría', 'select', ['Mesa de ayuda', 'Nube', 'Infraestructura', 'Redes', 'Ciberseguridad',
                                                  'Consultoría', 'Soporte en sitio', 'Licenciamiento', 'Otros'], True, ''),
            ('unidad', 'Se cobra por', 'select', ['Servicio', 'Hora', 'Mes', 'Año', 'Usuario/mes', 'Equipo/mes', 'Visita'], True, ''),
            ('descripcion', 'Descripción y alcance', 'textarea', None, False, 'Aparece en la cotización debajo del nombre.'),
            # Tres precios para negociar, igual que en productos
            ('precio', 'Precio 1 · Lista (sin IVA)', 'money', None, True, 'El precio normal al público.'),
            ('precio2', 'Precio 2 · Preferencial (sin IVA)', 'money', None, False, 'Clientes frecuentes o contratos largos. Vacío = igual al de lista.'),
            ('precio3', 'Precio 3 · Mínimo (sin IVA)', 'money', None, False, 'El piso de negociación. Vacío = igual al preferencial.'),
            ('iva', 'IVA', 'iva', IVAS, True, ''),
        ],
    },
    'renta': {
        'archivo': 'renta.json', 'titulo': 'Productos en renta', 'singular': 'equipo en renta', 'icono': 'fa-box-archive',
        'prefijo': 'REN', 'grupo': 'Renta', 'tipo_item': 'renta',
        'campos': [
            ('codigo', 'Código', 'text', None, False, 'Si lo dejas vacío se genera solo.'),
            ('nombre', 'Nombre', 'text', None, True, ''),
            ('categoria', 'Categoría', 'select', ['Portátiles', 'Computadores de escritorio', 'Servidores', 'Impresoras',
                                                  'Monitores', 'Redes', 'Proyectores', 'Otros'], True, ''),
            ('marca', 'Marca y modelo', 'text', None, False, ''),
            ('proveedor_id', 'Proveedor', 'proveedor', None, False, 'A quién se le compró el equipo.'),
            ('serial', 'Número de serie', 'text', None, False, 'Identifica la unidad exacta que se entrega.'),
            ('descripcion', 'Descripción', 'textarea', None, False, 'Aparece en la cotización debajo del nombre.'),
            ('unidad', 'Tarifa por', 'select', ['Mes', 'Semana', 'Día'], True, ''),
            ('precio', 'Valor de la renta (sin IVA)', 'money', None, True, ''),
            ('iva', 'IVA', 'iva', IVAS, True, ''),
            ('costo', 'Precio de compra (sin IVA)', 'money', None, False, 'Lo que se le pagó al proveedor; sirve para saber en cuánto tiempo se paga el equipo.'),
            ('estado', 'Estado', 'select', ESTADOS_RENTA, True, ''),
            ('cliente_id', 'Cliente que lo tiene', 'cliente', None, False, ''),
            ('renta_inicio', 'Inicio de la renta', 'date', None, False, ''),
            ('renta_fin', 'Fin de la renta', 'date', None, False, 'Vacío si es indefinida.'),
        ],
    },
}

# Días antes del fin de una renta en que se empieza a avisar
DIAS_AVISO_RENTA = 15

_lock = threading.Lock()


def _numero(texto, entero=False):
    # Acepta "1.250.000", "1250000" o "1250000,50"
    limpio = str(texto or '').strip().replace('$', '').replace(' ', '')
    if not limpio:
        return 0
    if re.fullmatch(r'\d{1,3}(\.\d{3})+(,\d+)?', limpio):
        limpio = limpio.replace('.', '')
    limpio = limpio.replace(',', '.')
    valor = float(limpio)
    return int(valor) if entero else round(valor, 2)


def listar(tipo, solo_activos=False):
    lista = almacen.leer(CATALOGOS[tipo]['archivo'], [])
    if solo_activos:
        lista = [x for x in lista if x.get('activo', True)]
    return sorted(lista, key=lambda x: (x.get('categoria', ''), x['nombre'].lower()))


def obtener(tipo, item_id):
    return next((x for x in almacen.leer(CATALOGOS[tipo]['archivo'], []) if x['id'] == item_id), None)


def validar(tipo, form, item_id=None):
    """Devuelve (datos limpios, errores)."""
    datos, errores = {}, {}
    for nombre, etiqueta, clase, opciones, obligatorio, _ in CATALOGOS[tipo]['campos']:
        if clase == 'auto':
            continue  # lo pone guardar(); no se puede escribir desde el formulario
        valor = str(form.get(nombre, '')).strip()
        if clase in ('money', 'int'):
            try:
                numero = _numero(valor, entero=(clase == 'int'))
                if numero < 0:
                    raise ValueError
                datos[nombre] = numero
            except ValueError:
                errores[nombre] = 'Escribe un número válido.'
            if obligatorio and not valor:
                errores[nombre] = f'{etiqueta} es obligatorio.'
            continue
        if clase == 'date' and valor:
            try:
                valor = date.fromisoformat(valor).isoformat()
            except ValueError:
                errores[nombre] = 'Fecha no válida.'
        if clase == 'proveedor' and valor:
            from . import proveedores  # aquí para evitar importaciones circulares
            if proveedores.obtener(valor) is None:
                errores[nombre] = 'Ese proveedor ya no existe.'
        if clase in ('select', 'iva') and valor and valor not in opciones:
            errores[nombre] = 'Elige una opción de la lista.'
        if obligatorio and not valor:
            errores[nombre] = f'{etiqueta} es obligatorio.'
        datos[nombre] = valor[:1000 if clase == 'textarea' else 120]
    datos['activo'] = form.get('activo', '1') == '1'

    if 'sku' in datos:
        datos['sku'] = datos['sku'].upper()[:40]
    codigo = datos.get('codigo', '').upper()
    datos['codigo'] = codigo
    if not codigo:
        datos.pop('codigo')
    if codigo and not re.fullmatch(r'[A-Z0-9._\-]{2,30}', codigo):
        errores['codigo'] = 'Usa letras, números, guiones o puntos (2 a 30).'
    elif codigo and any(x['codigo'] == codigo and x['id'] != item_id for x in almacen.leer(CATALOGOS[tipo]['archivo'], [])):
        errores['codigo'] = 'Ya existe un registro con ese código.'
    if tipo == 'renta':
        _validar_renta(datos, errores, item_id)
    if CATALOGOS[tipo].get('tres_precios'):
        _validar_precios(datos, errores)
    return datos, errores


def _validar_precios(datos, errores):
    # Los tres precios van de mayor a menor y ninguno por debajo del precio de compra
    lista, pref, minimo, costo = (datos.get(k) or 0 for k in ('precio', 'precio2', 'precio3', 'costo'))
    if pref and lista and pref > lista:
        errores['precio2'] = 'No puede ser mayor que el precio de lista.'
    if minimo and minimo > (pref or lista):
        errores['precio3'] = 'No puede ser mayor que el precio preferencial.'
    if costo:
        for campo, valor in (('precio', lista), ('precio2', pref), ('precio3', minimo)):
            if valor and valor < costo and campo not in errores:
                errores[campo] = 'Queda por debajo del precio de compra.'


def _precios_distintos(producto):
    vistos, resultado = set(), []
    for nivel, etiqueta, valor in precios_de(producto):
        if valor not in vistos:
            vistos.add(valor)
            resultado.append({'nivel': nivel, 'etiqueta': etiqueta, 'valor': valor})
    return resultado


def precios_de(producto):
    """[(nivel, etiqueta, valor)] con los vacíos llenados por el nivel anterior."""
    resultado, anterior = [], 0
    for campo, etiqueta in NIVELES_PRECIO:
        valor = producto.get(campo) or anterior
        resultado.append((campo, etiqueta, valor))
        anterior = valor
    return resultado


def _validar_renta(datos, errores, item_id):
    from . import clientes  # aquí para evitar importaciones circulares
    serial = re.sub(r'\s+', '', datos.get('serial', '')).upper()
    datos['serial'] = serial
    if serial and any(re.sub(r'\s+', '', x.get('serial', '')).upper() == serial and x['id'] != item_id
                      for x in almacen.leer(CATALOGOS['renta']['archivo'], [])):
        errores['serial'] = 'Ya hay un equipo en renta con ese número de serie.'
    if datos.get('estado') != 'Rentado':
        # Solo un equipo rentado tiene cliente y fechas
        datos['cliente_id'] = datos['renta_inicio'] = datos['renta_fin'] = ''
        for campo in ('cliente_id', 'renta_inicio', 'renta_fin'):
            errores.pop(campo, None)
        return
    if not datos.get('cliente_id'):
        errores['cliente_id'] = 'Elige el cliente que tiene el equipo.'
    elif clientes.obtener_cliente(datos['cliente_id']) is None:
        errores['cliente_id'] = 'Ese cliente ya no existe.'
    if not datos.get('renta_inicio') and 'renta_inicio' not in errores:
        errores['renta_inicio'] = 'Indica desde cuándo está rentado.'
    if datos.get('renta_fin') and datos.get('renta_inicio') and datos['renta_fin'] < datos['renta_inicio']:
        errores['renta_fin'] = 'Debe ser posterior al inicio.'


def resumen_renta(lista):
    """Conteo por estado, ingreso de lo rentado y rentas que terminan pronto o ya vencieron."""
    hoy = date.today()
    conteo = {e: 0 for e in ESTADOS_RENTA}
    ingreso = {'Mes': 0, 'Semana': 0, 'Día': 0}
    por_vencer, vencidas = [], []
    for x in lista:
        estado = x.get('estado', 'Disponible')
        conteo[estado] = conteo.get(estado, 0) + 1
        if estado != 'Rentado':
            continue
        ingreso[x.get('unidad', 'Mes')] = ingreso.get(x.get('unidad', 'Mes'), 0) + x.get('precio', 0)
        if x.get('renta_fin'):
            dias = (date.fromisoformat(x['renta_fin']) - hoy).days
            if dias < 0:
                vencidas.append(x)
            elif dias <= DIAS_AVISO_RENTA:
                por_vencer.append(x)
    return {'conteo': conteo, 'ingreso': ingreso, 'por_vencer': por_vencer, 'vencidas': vencidas}


def mover_inventario(productos=None, rentas=None, revisar=True):
    """Aplica de una sola vez los cambios de una orden de compra.

    productos: {producto_id: cantidad a sumar (negativa para descontar)}
    rentas:    {renta_id: {'estado': ..., 'cliente_id': ..., 'renta_inicio': ..., 'renta_fin': ...}}
    Si revisar=True y falta stock o un equipo ya no está disponible, no cambia nada
    y devuelve la lista de problemas. Si todo sale bien devuelve ([], stock final por producto).
    """
    productos, rentas = productos or {}, rentas or {}
    with _lock:
        lista_p = almacen.leer(CATALOGOS['productos']['archivo'], [])
        lista_r = almacen.leer(CATALOGOS['renta']['archivo'], [])
        por_id_p = {x['id']: x for x in lista_p}
        por_id_r = {x['id']: x for x in lista_r}
        problemas = []
        if revisar:
            for pid, delta in productos.items():
                p = por_id_p.get(pid)
                if p and delta < 0 and (p.get('stock') or 0) + delta < 0:
                    problemas.append(f"{p['nombre']}: se necesitan {abs(delta):g} y hay {(p.get('stock') or 0):g} en stock")
            for rid, cambio in rentas.items():
                r = por_id_r.get(rid)
                if r and cambio.get('estado') == 'Rentado' and r.get('estado') != 'Disponible':
                    problemas.append(f"{r['nombre']} ({r.get('serial') or r['codigo']}) está «{r.get('estado')}»")
            if problemas:
                return problemas, {}
        stock_final = {}
        for pid, delta in productos.items():
            if pid in por_id_p:
                nuevo = (por_id_p[pid].get('stock') or 0) + delta
                # El stock se guarda entero cuando no hay fracción (5 y no 5.0)
                por_id_p[pid]['stock'] = int(nuevo) if float(nuevo).is_integer() else round(nuevo, 2)
                stock_final[pid] = por_id_p[pid]['stock']
        for rid, cambio in rentas.items():
            if rid in por_id_r:
                por_id_r[rid].update(cambio)
        if productos:
            almacen.escribir(CATALOGOS['productos']['archivo'], lista_p)
        if rentas:
            almacen.escribir(CATALOGOS['renta']['archivo'], lista_r)
    return [], stock_final


def usos_de_proveedor():
    """{proveedor_id: cantidad de productos y equipos de renta que tienen ese proveedor}"""
    usos = {}
    for tipo in ('productos', 'renta'):
        for x in almacen.leer(CATALOGOS[tipo]['archivo'], []):
            if x.get('proveedor_id'):
                usos[x['proveedor_id']] = usos.get(x['proveedor_id'], 0) + 1
    return usos


def rentas_de_cliente(cliente_id):
    return [x for x in almacen.leer(CATALOGOS['renta']['archivo'], []) if x.get('cliente_id') == cliente_id]


# ---------------------------------------------------------------- Código interno (PROD-001, SER-001)

CONSECUTIVOS = 'consecutivos.json'  # último número entregado por catálogo: no se reutiliza aunque se borre


def _formato_codigo(prefijo, numero):
    return f'{prefijo}-{numero:03d}'  # PROD-001 … PROD-999, PROD-1000…


def _siguiente_codigo(tipo, lista, reservar=False):
    """El próximo código interno. Con reservar=True lo marca como usado (se llama con _lock tomado)."""
    prefijo = CATALOGOS[tipo]['prefijo']
    consecutivos = almacen.leer(CONSECUTIVOS, {})
    usados = [int(m.group(1)) for x in lista if (m := re.fullmatch(rf'{prefijo}-(\d+)', x.get('codigo', '')))]
    numero = max([consecutivos.get(tipo, 0)] + usados) + 1
    if reservar:
        consecutivos[tipo] = numero
        almacen.escribir(CONSECUTIVOS, consecutivos)
    return _formato_codigo(prefijo, numero)


def siguiente_codigo(tipo):
    """Para mostrar en el formulario de «Nuevo» el código que va a recibir."""
    if not CATALOGOS[tipo].get('codigo_auto'):
        return ''
    return _siguiente_codigo(tipo, almacen.leer(CATALOGOS[tipo]['archivo'], []))


def asegurar_codigos():
    """Pasa los productos y servicios que tengan otro código (PRD-0001, SRV-0001 o escrito a mano)
    al código interno, en orden de creación. El código anterior queda en 'codigo_anterior'
    (y en productos, si era escrito a mano, como referencia del fabricante).
    Las cotizaciones y facturas ya hechas conservan el código con el que se emitieron."""
    cambios = {}
    with _lock:
        for tipo, cfg in CATALOGOS.items():
            if not cfg.get('codigo_auto'):
                continue
            lista = almacen.leer(cfg['archivo'], [])
            patron = rf"{cfg['prefijo']}-\d{{3,}}"
            pendientes = sorted((x for x in lista if not re.fullmatch(patron, x.get('codigo', ''))),
                                key=lambda x: x.get('creado', ''))
            if not pendientes:
                continue
            for x in pendientes:
                anterior = x.get('codigo', '')
                x['codigo'] = _siguiente_codigo(tipo, lista, reservar=True)
                if anterior:
                    x['codigo_anterior'] = anterior
                    hecho_a_mano = not re.fullmatch(r'(PRD|SRV)-\d+', anterior)
                    if tipo == 'productos' and hecho_a_mano and not x.get('sku'):
                        x['sku'] = anterior
                cambios[x['id']] = x['codigo']
            almacen.escribir(cfg['archivo'], lista)
    if cambios:
        # El historial de movimientos de inventario muestra el código nuevo
        from . import ventas  # aquí para evitar importaciones circulares
        ventas.actualizar_codigos_movimientos(cambios)
    return cambios


def guardar(tipo, datos, item_id=None, usuario=''):
    cfg = CATALOGOS[tipo]
    ahora = datetime.now().strftime('%Y-%m-%d %H:%M')
    with _lock:
        lista = almacen.leer(cfg['archivo'], [])
        if cfg.get('codigo_auto'):
            datos.pop('codigo', None)  # el código interno nunca cambia después de creado
            if not item_id:
                datos['codigo'] = _siguiente_codigo(tipo, lista, reservar=True)
        elif not datos.get('codigo'):
            # Código automático: REN-0001…
            usados = [int(m.group(1)) for x in lista if (m := re.fullmatch(rf"{cfg['prefijo']}-(\d+)", x['codigo']))]
            datos['codigo'] = f"{cfg['prefijo']}-{max(usados, default=0) + 1:04d}"
        if item_id:
            item = next((x for x in lista if x['id'] == item_id), None)
            if item is None:
                return None
            item.update(datos, actualizado=ahora, actualizado_por=usuario)
        else:
            item = {'id': uuid.uuid4().hex[:12], **datos, 'creado': ahora, 'creado_por': usuario}
            lista.append(item)
        almacen.escribir(cfg['archivo'], lista)
    return item


def eliminar(tipo, item_id):
    with _lock:
        lista = almacen.leer(CATALOGOS[tipo]['archivo'], [])
        item = next((x for x in lista if x['id'] == item_id), None)
        if item:
            almacen.escribir(CATALOGOS[tipo]['archivo'], [x for x in lista if x['id'] != item_id])
    return item


def para_cotizar():
    """Productos, servicios y equipos de renta disponibles, en el formato del editor de cotizaciones."""
    resultado = []
    for tipo, cfg in CATALOGOS.items():
        for x in listar(tipo, solo_activos=True):
            if tipo == 'renta' and x.get('estado') != 'Disponible':
                continue
            resultado.append({
                'tipo': cfg['tipo_item'], 'id': x['id'], 'codigo': x['codigo'], 'nombre': x['nombre'],
                'detalle': (x.get('descripcion', '') + (f"\nSerial: {x['serial']}" if x.get('serial') else '')).strip(), 'unidad': x.get('unidad', ''), 'precio': x.get('precio', 0),
                'iva': float(x.get('iva') or 0), 'stock': x.get('stock') if tipo == 'productos' else None,
                'categoria': x.get('categoria', ''),
                # Productos y servicios: los tres precios para elegir en el editor
                # (sin repetir: si el preferencial o el mínimo no están definidos, no se ofrecen)
                'precios': _precios_distintos(x) if cfg.get('tres_precios') else [],
            })
    return resultado


def por_tipo_item():
    """{'producto': {id: registro}, 'servicio': {...}, 'renta': {...}}"""
    return {cfg['tipo_item']: {x['id']: x for x in listar(t)} for t, cfg in CATALOGOS.items()}
