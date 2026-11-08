from collections import Counter

from flask import Blueprint, abort, render_template, session

from auth import login_requerido

# Blueprint del panel administrativo
dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')


# Menú lateral: (clave, texto, icono de Font Awesome)
# 'inicio' es la vista general; las demás claves son secciones del panel
FAVORITOS = [
    ('inicio', 'Vista general', 'fa-gauge-high'),
    ('cotizaciones', 'Cotizaciones', 'fa-file-signature'),
]

MENU = [
    {'grupo': 'Dashboard', 'icono': 'fa-gauge-high', 'items': [
        ('inicio', 'Vista general', 'fa-chart-pie'),
    ]},
    {'grupo': 'Comercial', 'icono': 'fa-briefcase', 'items': [
        ('clientes', 'Clientes', 'fa-users'),
        ('cotizaciones', 'Cotizaciones', 'fa-file-signature'),
        ('ventas', 'Ventas', 'fa-chart-line'),
        ('vendedores', 'Vendedores', 'fa-user-tie'),
    ]},
    {'grupo': 'Facturación', 'icono': 'fa-file-invoice-dollar', 'items': [
        ('facturas', 'Facturas', 'fa-file-invoice'),
    ]},
    {'grupo': 'Inventario', 'icono': 'fa-boxes-stacked', 'items': [
        ('productos', 'Productos', 'fa-box-open'),
        ('servicios', 'Servicios', 'fa-layer-group'),
        ('proveedores', 'Proveedores', 'fa-truck-field'),
    ]},
    {'grupo': 'Usuarios y accesos', 'icono': 'fa-user-shield', 'items': [
        ('usuarios', 'Usuarios', 'fa-user-gear'),
    ]},
    {'grupo': 'Sistema', 'icono': 'fa-gear', 'items': [
        ('configuracion', 'Configuración', 'fa-sliders'),
    ]},
]

SECCIONES = {clave: texto for g in MENU for clave, texto, _ in g['items']}


# Datos de ejemplo mientras no exista la base de datos
FACTURAS = [
    {'numero': 'FV-1048', 'cliente': 'Comercial Andina S.A.S.', 'nit': '900.456.112-3', 'servicio': 'Mesa de ayuda', 'fecha': '2026-11-07', 'vendedor': 'Laura Gómez', 'valor': 4850000, 'estado': 'Pagada'},
    {'numero': 'FV-1047', 'cliente': 'Logística del Valle', 'nit': '901.223.874-1', 'servicio': 'Nube', 'fecha': '2026-11-06', 'vendedor': 'Andrés Ruiz', 'valor': 7200000, 'estado': 'Pendiente'},
    {'numero': 'FV-1046', 'cliente': 'Clínica San Rafael', 'nit': '800.918.330-5', 'servicio': 'Ciberseguridad', 'fecha': '2026-11-05', 'vendedor': 'Laura Gómez', 'valor': 12400000, 'estado': 'Pagada'},
    {'numero': 'FV-1045', 'cliente': 'Agroindustrias El Llano', 'nit': '900.774.501-8', 'servicio': 'Redes', 'fecha': '2026-11-03', 'vendedor': 'Camilo Pérez', 'valor': 3150000, 'estado': 'Vencida'},
    {'numero': 'FV-1044', 'cliente': 'Colegio Nueva Esperanza', 'nit': '860.115.442-0', 'servicio': 'Mesa de ayuda', 'fecha': '2026-11-01', 'vendedor': 'Andrés Ruiz', 'valor': 2600000, 'estado': 'Pagada'},
    {'numero': 'FV-1043', 'cliente': 'Constructora Altamira', 'nit': '901.330.096-2', 'servicio': 'Nube', 'fecha': '2026-10-29', 'vendedor': 'Camilo Pérez', 'valor': 9800000, 'estado': 'Pendiente'},
    {'numero': 'FV-1042', 'cliente': 'Farmacias Vida', 'nit': '900.612.778-4', 'servicio': 'Ciberseguridad', 'fecha': '2026-10-27', 'vendedor': 'Laura Gómez', 'valor': 6300000, 'estado': 'Vencida'},
    {'numero': 'FV-1041', 'cliente': 'Hotel Mirador', 'nit': '800.207.665-9', 'servicio': 'Redes', 'fecha': '2026-10-24', 'vendedor': 'Andrés Ruiz', 'valor': 4100000, 'estado': 'Pagada'},
]

# Colores de los gráficos (en el mismo orden en que aparecen las categorías)
COLORES = ['#2bb3a3', '#3b82f6', '#b5f04a', '#f59e0b', '#ef6351', '#a78bfa']
COLORES_ESTADO = {'Pagada': '#4caf6e', 'Pendiente': '#f59e0b', 'Vencida': '#ef6351'}


def resumen(titulo, conteo, colores=None):
    # Convierte un Counter en los datos que necesita el gráfico de dona
    total = sum(conteo.values())
    partes = []
    for i, (nombre, cantidad) in enumerate(conteo.most_common()):
        color = (colores or {}).get(nombre, COLORES[i % len(COLORES)])
        partes.append({'nombre': nombre, 'cantidad': cantidad, 'color': color,
                       'porcentaje': cantidad * 100 / total})
    return {'titulo': titulo, 'total': total, 'partes': partes}


@dashboard_bp.app_template_filter('pesos')
def formato_pesos(valor):
    return '$ ' + f'{valor:,.0f}'.replace(',', '.')


@dashboard_bp.context_processor
def datos_panel():
    return {
        'menu': MENU,
        'favoritos': FAVORITOS,
        'usuario': session.get('usuario'),
        'alertas': sum(1 for f in FACTURAS if f['estado'] == 'Vencida'),
    }


@dashboard_bp.route('/')
@login_requerido
def dash_view():
    graficos = [
        resumen('Estado de facturas', Counter(f['estado'] for f in FACTURAS), COLORES_ESTADO),
        resumen('Servicios facturados', Counter(f['servicio'] for f in FACTURAS)),
        resumen('Facturas por vendedor', Counter(f['vendedor'] for f in FACTURAS)),
    ]
    valor_max = max(f['valor'] for f in FACTURAS)
    return render_template('dash/inicio.html', activo='inicio', graficos=graficos,
                           facturas=FACTURAS, valor_max=valor_max, colores_estado=COLORES_ESTADO)


@dashboard_bp.route('/<nombre>')
@login_requerido
def seccion(nombre):
    if nombre not in SECCIONES:
        abort(404)
    return render_template('dash/seccion.html', activo=nombre, titulo=SECCIONES[nombre])
