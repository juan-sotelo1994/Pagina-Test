"""Crea las tablas en PostgreSQL y copia los datos que hoy están en app/data/*.json.

Uso (desde la carpeta del proyecto):
    .venv\\Scripts\\python.exe db\\migrar.py            crea las tablas y copia los datos
    .venv\\Scripts\\python.exe db\\migrar.py --solo-tablas

Se puede ejecutar varias veces: las tablas que existen no se tocan y los registros
que ya se copiaron se saltan (no se duplican). Los archivos JSON no se borran.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import psycopg
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / 'app' / 'data'


def leer(nombre, por_defecto):
    ruta = DATOS / nombre
    if not ruta.exists():
        return por_defecto
    with open(ruta, encoding='utf-8') as archivo:
        return json.load(archivo)


def fecha(texto):
    """'2026-11-15 18:20' → datetime; vacío → ahora."""
    if not texto:
        return datetime.now()
    for formato in ('%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(texto, formato)
        except ValueError:
            pass
    return datetime.now()


def insertar(cur, tabla, fila, conflicto='id'):
    columnas = list(fila)
    sql = (f"INSERT INTO {tabla} ({', '.join(columnas)}) VALUES ({', '.join(['%s'] * len(columnas))}) "
           f"ON CONFLICT ({conflicto}) DO NOTHING")
    cur.execute(sql, [fila[c] for c in columnas])
    return cur.rowcount


def separar_nombre(u):
    if u.get('nombres'):
        return u['nombres'], u.get('apellidos', '')
    partes = u.get('nombre', '').split()
    return ' '.join(partes[:1]), ' '.join(partes[1:])


def items(cur, tabla, columna, documento_id, lista):
    for n, i in enumerate(lista, start=1):
        insertar(cur, tabla, {
            columna: documento_id, 'linea': n, 'tipo': i['tipo'], 'ref_id': i.get('ref_id', ''), 'codigo': i.get('codigo', ''),
            'nombre': i['nombre'], 'detalle': i.get('detalle', ''), 'unidad': i.get('unidad', 'Unidad'),
            'cantidad': i['cantidad'], 'precio': i['precio'], 'descuento_pct': i.get('descuento', 0),
            'iva_pct': int(i.get('iva', 19)), 'base': i['base'], 'valor_iva': i['valor_iva'], 'total': i['total'],
        }, conflicto=f'{columna}, linea')


def totales(t):
    return {'subtotal': t['bruto'], 'descuento': t['descuento'], 'base': t['base'], 'iva': t['iva'], 'total': t['total']}


def historial(cur, documento, documento_id, lista):
    cur.execute('SELECT count(*) FROM historial_documentos WHERE documento = %s AND documento_id = %s', (documento, documento_id))
    if cur.fetchone()[0]:
        return
    for h in lista:
        cur.execute('INSERT INTO historial_documentos (documento, documento_id, fecha, usuario, accion) VALUES (%s, %s, %s, %s, %s)',
                    (documento, documento_id, fecha(h['fecha']), h.get('usuario', ''), h['accion']))


def copiar_datos(cur):
    copiados = {}

    copiados['usuarios'] = sum(insertar(cur, 'usuarios', {
        'nombres': separar_nombre(u)[0], 'apellidos': separar_nombre(u)[1], 'correo': u['correo'].lower(),
        'rol': u['rol'], 'hash': u['hash'], 'activo': u.get('activo', True), 'creado': fecha(u.get('creado')),
    }, conflicto='correo') for u in leer('usuarios.json', []))

    comunes = lambda x: {'activo': x.get('activo', True), 'creado': fecha(x.get('creado')), 'creado_por': x.get('creado_por', ''),
                         'actualizado': fecha(x['actualizado']) if x.get('actualizado') else None,
                         'actualizado_por': x.get('actualizado_por')}

    copiados['proveedores'] = sum(insertar(cur, 'proveedores', {
        'id': p['id'], **{k: p.get(k, '') for k in ('nombre', 'nit', 'tipo', 'contacto', 'cargo', 'correo', 'telefono', 'ciudad',
                                                     'direccion', 'sitio_web', 'condiciones_pago', 'tiempo_entrega', 'notas')},
        'suministra': p.get('suministra', []), **comunes(p),
    }) for p in leer('proveedores.json', []))

    copiados['productos'] = sum(insertar(cur, 'productos', {
        'id': p['id'], 'codigo': p['codigo'], 'nombre': p['nombre'], 'categoria': p.get('categoria', 'Otros'),
        'marca': p.get('marca', ''), 'unidad': p.get('unidad', 'Unidad'), 'descripcion': p.get('descripcion', ''),
        'proveedor_id': p.get('proveedor_id') or None, 'costo': p.get('costo') or 0, 'precio': p.get('precio') or 0,
        'precio2': p.get('precio2') or 0, 'precio3': p.get('precio3') or 0,
        'iva': int(p.get('iva') or 0), 'stock': p.get('stock') or 0, 'stock_minimo': p.get('stock_minimo') or 0, **comunes(p),
    }) for p in leer('productos.json', []))

    copiados['servicios'] = sum(insertar(cur, 'servicios', {
        'id': s['id'], 'codigo': s['codigo'], 'nombre': s['nombre'], 'categoria': s.get('categoria', 'Otros'),
        'unidad': s.get('unidad', 'Servicio'), 'descripcion': s.get('descripcion', ''), 'precio': s.get('precio') or 0,
        'iva': int(s.get('iva') or 0), **comunes(s),
    }) for s in leer('servicios.json', []))

    copiados['productos_renta'] = sum(insertar(cur, 'productos_renta', {
        'id': r['id'], 'codigo': r['codigo'], 'nombre': r['nombre'], 'categoria': r.get('categoria', 'Otros'),
        'marca': r.get('marca', ''), 'serial': r.get('serial', ''), 'descripcion': r.get('descripcion', ''),
        'proveedor_id': r.get('proveedor_id') or None, 'unidad': r.get('unidad', 'Mes'), 'precio': r.get('precio') or 0,
        'iva': int(r.get('iva') or 0), 'costo': r.get('costo') or 0, 'estado': r.get('estado', 'Disponible'),
        'cliente_id': r.get('cliente_id') or None, 'renta_inicio': r.get('renta_inicio') or None,
        'renta_fin': r.get('renta_fin') or None, **comunes(r),
    }) for r in leer('renta.json', []))

    ids_productos = {p['id'] for p in leer('productos.json', [])}
    copiados['movimientos_inventario'] = sum(insertar(cur, 'movimientos_inventario', {
        'id': m['id'], 'fecha': fecha(m['fecha']), 'producto_id': m['producto_id'] if m['producto_id'] in ids_productos else None,
        'codigo': m.get('codigo', ''), 'nombre': m.get('nombre', ''), 'cantidad': m['cantidad'], 'stock_resultante': m['stock'],
        'motivo': m['motivo'], 'referencia': m.get('referencia', ''), 'usuario': m.get('usuario', ''),
    }) for m in leer('movimientos_inventario.json', []))

    copiados['ordenes_compra'] = 0
    for o in leer('ordenes.json', []):
        nueva = insertar(cur, 'ordenes_compra', {
            'id': o['id'], 'numero': o['numero'], 'fecha': o['fecha'], 'cotizacion_id': o['cotizacion_id'],
            'cotizacion_numero': o['cotizacion_numero'], 'cliente_id': o['cliente'].get('id') or None,
            'cliente_nombre': o['cliente']['nombre'], 'cliente_documento': o['cliente'].get('documento', ''),
            **{k: o.get(k, '') for k in ('contacto', 'contacto_correo', 'contacto_telefono', 'asunto', 'forma_pago',
                                          'tiempo_entrega', 'garantia')},
            'estado': o['estado'], **totales(o['totales']), 'creado': fecha(o.get('creado')), 'creado_por': o.get('creado_por', ''),
        })
        copiados['ordenes_compra'] += nueva
        items(cur, 'orden_items', 'orden_id', o['id'], o['items'])
        for s in o.get('servicios', []):
            insertar(cur, 'orden_servicios', {
                'orden_id': o['id'], 'linea': s['linea'] + 1, 'nombre': s['nombre'], 'detalle': s.get('detalle', ''),
                'cantidad': s['cantidad'], 'unidad': s.get('unidad', 'Servicio'), 'estado': s['estado'],
                'realizado': fecha(s['realizado']) if s.get('realizado') else None, 'realizado_por': s.get('realizado_por') or None,
            }, conflicto='orden_id, linea')
        for pid, cantidad in o.get('productos_descontados', {}).items():
            insertar(cur, 'orden_inventario', {'orden_id': o['id'], 'tipo': 'producto', 'ref_id': pid, 'cantidad': cantidad},
                     conflicto='orden_id, tipo, ref_id')
        for rid in o.get('rentas', []):
            insertar(cur, 'orden_inventario', {'orden_id': o['id'], 'tipo': 'renta', 'ref_id': rid, 'cantidad': 1},
                     conflicto='orden_id, tipo, ref_id')
        historial(cur, 'orden', o['id'], o.get('historial', []))

    copiados['facturas'] = 0
    for f in leer('facturas.json', []):
        pago = f.get('pago') or {}
        copiados['facturas'] += insertar(cur, 'facturas', {
            'id': f['id'], 'numero': f['numero'], 'fecha': f['fecha'], 'vence': f['vence'], 'orden_id': f['orden_id'],
            'orden_numero': f['orden_numero'], 'cotizacion_numero': f.get('cotizacion_numero', ''),
            'cliente_id': f['cliente'].get('id') or None, 'cliente_nombre': f['cliente']['nombre'],
            'cliente_documento': f['cliente'].get('documento', ''),
            **{k: f.get(k, '') for k in ('contacto', 'contacto_correo', 'contacto_telefono', 'asunto', 'forma_pago')},
            'estado': f['estado'], **totales(f['totales']),
            'pago_fecha': pago.get('fecha'), 'pago_medio': pago.get('medio'), 'pago_referencia': pago.get('referencia'),
            'pago_usuario': pago.get('usuario'), 'creado': fecha(f.get('creado')), 'creado_por': f.get('creado_por', ''),
        })
        items(cur, 'factura_items', 'factura_id', f['id'], f['items'])
        historial(cur, 'factura', f['id'], f.get('historial', []))
    return copiados


def main():
    load_dotenv(RAIZ / '.env')
    url = os.environ.get('DATABASE_URL')
    if not url:
        sys.exit('Falta DATABASE_URL en el archivo .env.')
    with psycopg.connect(url) as conexion:
        with conexion.cursor() as cur:
            cur.execute((Path(__file__).parent / 'esquema.sql').read_text(encoding='utf-8'))
            cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' "
                        "AND table_type = 'BASE TABLE' ORDER BY table_name")
            print('Tablas:', ', '.join(t for (t,) in cur.fetchall()))
            if '--solo-tablas' not in sys.argv:
                for tabla, cantidad in copiar_datos(cur).items():
                    print(f'  {tabla:24} {cantidad} copiados')
        conexion.commit()  # todo o nada: si algo falla, no queda nada a medias
    print('Listo.')


if __name__ == '__main__':
    main()
