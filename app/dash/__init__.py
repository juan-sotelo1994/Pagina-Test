from collections import Counter

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, session, url_for

from auth import correo_admin, login_requerido, usuarios
from . import glpi, permisos

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
    {'grupo': 'Soporte', 'icono': 'fa-headset', 'items': [
        ('tickets', 'Tickets (GLPI)', 'fa-ticket'),
    ]},
    {'grupo': 'Usuarios y accesos', 'icono': 'fa-user-shield', 'items': [
        ('usuarios', 'Usuarios', 'fa-user-gear'),
    ]},
    {'grupo': 'Configuración', 'icono': 'fa-gear', 'items': [
        ('roles', 'Roles y permisos', 'fa-user-lock'),
        ('configuracion', 'General', 'fa-sliders'),
    ]},
]

SECCIONES = {clave: texto for g in MENU for clave, texto, _ in g['items']}


def menu_visible(rol):
    # Solo muestra las opciones que el rol puede ver ('inicio' siempre se ve)
    visible = lambda clave: clave == 'inicio' or permisos.puede(rol, clave, 'ver')
    grupos = []
    for g in MENU:
        items = [i for i in g['items'] if visible(i[0])]
        if items:
            grupos.append({**g, 'items': items})
    return grupos, [f for f in FAVORITOS if visible(f[0])]


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
    rol = session.get('rol')
    menu, favoritos = menu_visible(rol)
    alertas_tickets = 0
    if permisos.puede(rol, 'tickets', 'ver'):
        alertas_tickets = glpi.resumen(glpi.obtener()[0])['alertas']
    return {
        'menu': menu,
        'favoritos': favoritos,
        'usuario': session.get('usuario'),
        'rol_nombre': permisos.NOMBRES_ROL.get(rol, ''),
        'puede': lambda modulo, accion='ver': permisos.puede(rol, modulo, accion),
        'alertas': sum(1 for f in FACTURAS if f['estado'] == 'Vencida'),
        'alertas_tickets': alertas_tickets,
    }


@dashboard_bp.errorhandler(403)
def sin_permiso(error):
    return render_template('dash/seccion.html', activo=None, titulo='Acceso denegado',
                           icono='fa-lock', mensaje='Tu rol no tiene permiso para ver esta sección.'), 403


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


@dashboard_bp.route('/roles', methods=['GET', 'POST'])
@login_requerido
def roles():
    rol_actual = session['rol']
    if not permisos.puede(rol_actual, 'roles', 'ver'):
        abort(403)

    seleccionado = request.values.get('rol', 'admin')
    if seleccionado not in permisos.NOMBRES_ROL:
        seleccionado = 'admin'

    if request.method == 'POST':
        if not permisos.puede(rol_actual, 'roles', 'editar'):
            abort(403)
        nombre = permisos.NOMBRES_ROL[seleccionado]
        if seleccionado == 'superadmin':
            flash('Los permisos del Superadministrador no se pueden modificar.', 'error')
        elif request.form.get('accion') == 'restablecer':
            permisos.restablecer_rol(seleccionado)
            flash(f'Se restablecieron los permisos iniciales de {nombre}.', 'ok')
        else:
            # Los checkbox llegan como "modulo:accion"
            nuevos = {}
            for valor in request.form.getlist('permiso'):
                modulo, _, accion = valor.partition(':')
                nuevos.setdefault(modulo, []).append(accion)
            permisos.actualizar_rol(seleccionado, nuevos)
            flash(f'Permisos de {nombre} guardados.', 'ok')
        return redirect(url_for('dashboard.roles', rol=seleccionado))

    resumen_roles = {clave: permisos.permisos_de(clave) for clave, _, _ in permisos.ROLES}
    return render_template('dash/roles.html', activo='roles',
                           roles=permisos.ROLES, acciones=permisos.ACCIONES, modulos=permisos.MODULOS,
                           seleccionado=seleccionado, permisos_rol=resumen_roles[seleccionado],
                           resumen_roles=resumen_roles,
                           puede_editar=permisos.puede(rol_actual, 'roles', 'editar') and seleccionado != 'superadmin')


@dashboard_bp.route('/usuarios', methods=['GET', 'POST'])
@login_requerido
def usuarios_view():
    rol_actual = session['rol']
    if not permisos.puede(rol_actual, 'usuarios', 'ver'):
        abort(403)
    puede_crear = permisos.puede(rol_actual, 'usuarios', 'crear')

    # Solo el superadministrador puede crear otros superadministradores
    roles_asignables = [r for r in permisos.ROLES if r[0] != 'superadmin' or rol_actual == 'superadmin']
    errores, formulario = {}, {}

    if request.method == 'POST':
        if not puede_crear:
            abort(403)
        formulario = {k: request.form.get(k, '') for k in ('nombre', 'correo', 'rol')}
        errores = usuarios.validar(
            formulario['nombre'], formulario['correo'], formulario['rol'],
            request.form.get('contrasena', ''), request.form.get('confirmacion', ''),
            roles_validos={r[0] for r in roles_asignables},
            correos_reservados={correo_admin()},
        )
        if not errores:
            nuevo = usuarios.crear(formulario['nombre'], formulario['correo'], formulario['rol'],
                                   request.form['contrasena'])
            flash(f"Usuario {nuevo['nombre']} creado como {permisos.NOMBRES_ROL[nuevo['rol']]}.", 'ok')
            return redirect(url_for('dashboard.usuarios_view'))

    return render_template('dash/usuarios.html', activo='usuarios', lista=usuarios.listar(),
                           admin_correo=correo_admin(), nombres_rol=permisos.NOMBRES_ROL,
                           roles_asignables=roles_asignables, puede_crear=puede_crear,
                           errores=errores, formulario=formulario, largo_minimo=usuarios.LARGO_MINIMO)


@dashboard_bp.route('/tickets', methods=['GET', 'POST'])
@login_requerido
def tickets():
    if not permisos.puede(session['rol'], 'tickets', 'ver'):
        abort(403)
    puede_crear = permisos.puede(session['rol'], 'tickets', 'crear')
    errores, formulario = {}, {}

    if request.method == 'POST':
        if not puede_crear:
            abort(403)
        formulario = {k: request.form.get(k, '') for k in ('titulo', 'descripcion', 'cliente', 'tipo', 'urgencia')}
        tipo = request.form.get('tipo', type=int)
        urgencia = request.form.get('urgencia', type=int)
        errores = glpi.validar_ticket(formulario['titulo'], formulario['descripcion'], tipo, urgencia)
        if not errores and not glpi.configurado():
            errores['general'] = 'GLPI no está configurado: el ticket no se puede enviar todavía.'
        if not errores:
            try:
                numero = glpi.crear_ticket(formulario['titulo'], formulario['descripcion'], tipo, urgencia,
                                           formulario['cliente'], session['usuario'])
            except RuntimeError as error:
                errores['general'] = str(error)
            else:
                flash(f'Ticket #{numero} creado en GLPI.', 'ok')
                return redirect(url_for('dashboard.tickets', estado='nuevos'))

    lista, origen, error = glpi.obtener()
    filtro = request.args.get('estado', 'alertas')
    filtros = {
        'alertas': lambda t: t['estado'] in (glpi.NUEVO, glpi.PENDIENTE),
        'nuevos': lambda t: t['estado'] == glpi.NUEVO,
        'pendientes': lambda t: t['estado'] == glpi.PENDIENTE,
        'en_curso': lambda t: t['estado'] in (glpi.ASIGNADO, glpi.PLANIFICADO),
        'todos': lambda t: True,
    }
    visibles = [t for t in lista if filtros.get(filtro, filtros['alertas'])(t)]
    return render_template('dash/tickets.html', activo='tickets', tickets=visibles,
                           resumen=glpi.resumen(lista), origen=origen, error=error, filtro=filtro,
                           ultimo_nuevo=max((t['id'] for t in lista if t['estado'] == glpi.NUEVO), default=0),
                           estados=glpi.ESTADOS, prioridades=glpi.PRIORIDADES, url_ticket=glpi.url_ticket,
                           puede_crear=puede_crear, glpi_configurado=glpi.configurado(),
                           tipos=glpi.TIPOS, urgencias=glpi.URGENCIAS, errores=errores, formulario=formulario)


@dashboard_bp.route('/tickets/resumen.json')
@login_requerido
def tickets_resumen():
    # Lo consulta el navegador cada minuto para mostrar alertas nuevas
    if not permisos.puede(session['rol'], 'tickets', 'ver'):
        abort(403)
    return jsonify(glpi.resumen(glpi.obtener()[0]))


@dashboard_bp.route('/<nombre>')
@login_requerido
def seccion(nombre):
    if nombre not in SECCIONES:
        abort(404)
    if not permisos.puede(session['rol'], nombre, 'ver'):
        abort(403)
    return render_template('dash/seccion.html', activo=nombre, titulo=SECCIONES[nombre])
