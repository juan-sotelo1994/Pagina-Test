import csv
import io
import re
from collections import Counter
from datetime import date, datetime

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from markupsafe import Markup

from auth import correo_admin, login_requerido, nombre_admin, nombre_de, usuarios
from nucleo import correo as correos
from nucleo import mensajes
from web import EMPRESA
from . import (agentes, catalogo, clientes, comandos, cotizaciones, descargas, equipos, favoritos, glpi, indicadores,
               pdf_cotizacion, permisos, proveedores, ventas)

# Blueprint del panel administrativo
dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')


# Menú lateral: (clave, texto, icono de Font Awesome)
# 'inicio' es la vista general; las demás claves son secciones del panel.
# Cada usuario arma sus Favoritos con la estrella de cada opción (dash/favoritos.py)
MENU = [
    {'grupo': 'Dashboard', 'icono': 'fa-gauge-high', 'items': [
        ('inicio', 'Vista general', 'fa-chart-pie'),
        ('agentes', 'Agentes', 'fa-building-user'),
    ]},
    {'grupo': 'Comercial', 'icono': 'fa-briefcase', 'items': [
        ('clientes', 'Clientes', 'fa-users'),
        ('cotizaciones', 'Cotizaciones', 'fa-file-signature'),
        ('ventas', 'Órdenes de compra', 'fa-cart-shopping'),
    ]},
    {'grupo': 'Facturación', 'icono': 'fa-file-invoice-dollar', 'items': [
        ('facturas', 'Facturas', 'fa-file-invoice'),
    ]},
    {'grupo': 'Inventario', 'icono': 'fa-boxes-stacked', 'items': [
        ('productos', 'Productos', 'fa-box-open'),
        ('servicios', 'Servicios', 'fa-layer-group'),
        ('proveedores', 'Proveedores', 'fa-truck-field'),
        ('activos', 'Equipos de inventario', 'fa-laptop-file'),
    ]},
    {'grupo': 'Renta', 'icono': 'fa-handshake', 'items': [
        ('renta', 'Productos en renta', 'fa-box-archive'),
    ]},
    {'grupo': 'Soporte', 'icono': 'fa-headset', 'items': [
        ('tickets', 'Tickets (GLPI)', 'fa-ticket'),
        ('equipos', 'Equipos con agente', 'fa-laptop'),
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
OPCIONES = {clave: (clave, texto, icono) for g in MENU for clave, texto, icono in g['items']}


def enlace_menu(clave):
    return url_for('dashboard.dash_view') if clave == 'inicio' else url_for('dashboard.seccion', nombre=clave)


def menu_visible(rol, usuario=None):
    # Solo muestra las opciones que el rol puede ver ('inicio' siempre se ve)
    visible = lambda clave: clave == 'inicio' or permisos.puede(rol, clave, 'ver')
    grupos = []
    for g in MENU:
        items = [i for i in g['items'] if visible(i[0])]
        if items:
            grupos.append({**g, 'items': items})
    favs = [OPCIONES[c] for c in favoritos.de_usuario(usuario) if c in OPCIONES and visible(c)]
    return grupos, favs


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

def facturas_panel():
    """Facturas reales; mientras no exista ninguna se muestran las de ejemplo."""
    reales = ventas.para_panel()
    return (reales, False) if reales else (FACTURAS, True)


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


@dashboard_bp.app_template_filter('fecha_hora')
def formato_fecha_hora(segundos):
    return datetime.fromtimestamp(segundos).strftime('%Y-%m-%d %H:%M:%S') if segundos else ''


@dashboard_bp.context_processor
def datos_panel():
    rol = session.get('rol')
    menu, favs = menu_visible(rol, session.get('usuario'))
    alertas_tickets = 0
    if permisos.puede(rol, 'tickets', 'ver'):
        alertas_tickets = glpi.resumen(glpi.obtener()[0])['alertas']
    nombre_completo, nombre_corto = nombre_de(session.get('usuario'))
    return {
        'menu': menu,
        'favoritos': favs,
        'nombre_usuario': nombre_completo,
        'nombre_corto': nombre_corto,
        'claves_favoritas': [f[0] for f in favs],
        'usuario': session.get('usuario'),
        'rol_nombre': permisos.NOMBRES_ROL.get(rol, ''),
        'puede': lambda modulo, accion='ver': permisos.puede(rol, modulo, accion),
        'alertas': sum(1 for f in facturas_panel()[0] if f['estado'] == 'Vencida'),
        'alertas_tickets': alertas_tickets,
        'documento_de': clientes.documento_de,  # "NIT 900123456-7" / "CC 1020304050"
    }


@dashboard_bp.errorhandler(403)
def sin_permiso(error):
    return render_template('dash/seccion.html', activo=None, titulo='Acceso denegado',
                           icono='fa-lock', mensaje='Tu rol no tiene permiso para ver esta sección.'), 403


# Áreas de la vista general de cada perfil (en este orden). Los perfiles que no están
# aquí (o no tienen permiso para ninguna área) ven accesos directos a sus secciones.
INICIO_POR_ROL = {
    'superadmin': ['facturacion', 'ventas', 'soporte', 'inventario'],
    'admin': ['facturacion', 'ventas', 'soporte', 'inventario'],
    'vendedor': ['ventas'],
    'preventa': ['ventas'],
    'tecnico': ['soporte'],
    'auxiliar': ['inventario'],
}
# Permiso que se necesita para ver cada área
PERMISO_AREA = {'facturacion': ('facturas',), 'ventas': ('cotizaciones', 'ventas'),
                'soporte': ('tickets', 'equipos'), 'inventario': ('productos',)}
DIAS_SEMANA = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']
MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre',
         'noviembre', 'diciembre']


@dashboard_bp.route('/')
@login_requerido
def dash_view():
    rol, usuario = session['rol'], session['usuario']
    secciones = [a for a in INICIO_POR_ROL.get(rol, [])
                 if any(permisos.puede(rol, m) for m in PERMISO_AREA[a])]
    hoy = date.today()
    datos = {'activo': 'inicio', 'secciones': secciones,
             'hoy_texto': f'{DIAS_SEMANA[hoy.weekday()]} {hoy.day} de {MESES[hoy.month - 1]}'}

    if 'facturacion' in secciones:
        facturas, de_ejemplo = facturas_panel()
        datos.update({
            'graficos': [
                resumen('Estado de facturas', Counter(f['estado'] for f in facturas), COLORES_ESTADO),
                resumen('Servicios facturados', Counter(f['servicio'] for f in facturas)),
                resumen('Facturas por vendedor', Counter(f['vendedor'] for f in facturas)),
            ],
            'facturas': facturas, 'facturas_ejemplo': de_ejemplo, 'colores_estado': COLORES_ESTADO,
            'valor_max': max([f['valor'] for f in facturas] + [1]),
            'por_cobrar': sum(f['valor'] for f in facturas if f['estado'] in ('Pendiente', 'Vencida')),
            'facturas_vencidas': sum(1 for f in facturas if f['estado'] == 'Vencida'),
        })
    if 'ventas' in secciones:
        # El perfil Ventas ve solo lo suyo; el administrador ve el total de la empresa
        datos['ventas_propias'] = rol in ('vendedor', 'preventa')
        datos['ventas_ind'] = indicadores.de_ventas(usuario if datos['ventas_propias'] else None)
    if 'soporte' in secciones:
        datos['soporte_ind'] = indicadores.de_soporte()
    if 'inventario' in secciones:
        datos['inventario_ind'] = indicadores.de_inventario()

    # Un rol puede tener una vista propia en templates/dash/inicio/<rol>.html
    return render_template([f'dash/inicio/{rol}.html', 'dash/inicio/panel.html'], **datos)


@dashboard_bp.route('/favoritos', methods=['POST'])
@login_requerido
def favoritos_alternar():
    """Agrega o quita una opción de los favoritos del usuario. Devuelve la lista para redibujar el menú."""
    rol = session['rol']
    clave = str((request.get_json(silent=True) or {}).get('clave', ''))
    if clave not in OPCIONES or not (clave == 'inicio' or permisos.puede(rol, clave, 'ver')):
        return jsonify(ok=False, error='Esa opción no existe en tu menú.'), 400
    _, error = favoritos.alternar(session['usuario'], clave)
    _, favs = menu_visible(rol, session['usuario'])
    return jsonify(ok=error is None, error=error,
                   favoritos=[{'clave': c, 'texto': t, 'icono': i, 'url': enlace_menu(c)} for c, t, i in favs])


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
    puede_editar = permisos.puede(rol_actual, 'usuarios', 'editar')

    # Solo el superadministrador puede crear, editar o nombrar superadministradores
    roles_asignables = [r for r in permisos.ROLES if r[0] != 'superadmin' or rol_actual == 'superadmin']
    errores, formulario = {}, {}

    if request.method == 'POST':
        usuario_id = request.form.get('id', type=int)
        actual = usuarios.obtener(usuario_id) if usuario_id else None
        if (usuario_id and (not puede_editar or actual is None)) or (not usuario_id and not puede_crear):
            abort(403)
        if actual and actual['rol'] == 'superadmin' and rol_actual != 'superadmin':
            abort(403)
        contrasena = request.form.get('contrasena', '')
        datos, errores = usuarios.validar(
            request.form, {r[0] for r in roles_asignables}, usuario_id,
            contrasena, request.form.get('confirmacion', ''), exigir_clave=not usuario_id)
        activo = request.form.get('activo', '1') == '1'
        # Nadie se quita a sí mismo el acceso por error
        if actual and actual['correo'] == session['usuario']:
            if not activo:
                errores['activo'] = 'No puedes desactivar tu propia cuenta.'
            if actual['rol'] == 'superadmin' and datos['rol'] != 'superadmin':
                errores['rol'] = 'No puedes quitarte el rol de Superadministrador.'
        formulario = {**datos, 'id': usuario_id or '', 'activo': '1' if activo else '0'}
        if not errores:
            if usuario_id:
                guardado = usuarios.actualizar(usuario_id, datos, activo, contrasena)
                if actual['correo'] == session['usuario']:
                    session['usuario'] = guardado['correo']  # si cambió su propio correo
                flash(f"Usuario {guardado['nombre']} actualizado"
                      f"{' y con contraseña nueva' if contrasena else ''}.", 'ok')
            else:
                guardado = usuarios.crear(datos, contrasena)
                flash(f"Usuario {guardado['nombre']} creado como {permisos.NOMBRES_ROL[guardado['rol']]}.", 'ok')
            return redirect(url_for('dashboard.usuarios_view'))

    lista = usuarios.listar()
    return render_template('dash/usuarios.html', activo='usuarios', lista=lista,
                           admin_correo=correo_admin(), admin_nombre=nombre_admin(), separar=usuarios.separar,
                           nombres_rol=permisos.NOMBRES_ROL, para_formulario=usuarios.para_formulario,
                           roles_asignables=roles_asignables, puede_crear=puede_crear, puede_editar=puede_editar,
                           rol_actual=rol_actual, errores=errores, formulario=formulario,
                           largo_minimo=usuarios.LARGO_MINIMO, canal_mensajes=mensajes.proveedor())


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


def _exigir(modulo, accion='ver'):
    if not permisos.puede(session['rol'], modulo, accion):
        abort(403)


def _pagina_agentes(**extra):
    tickets_glpi, origen, _ = glpi.obtener()
    oficina = agentes.construir(tickets_glpi, origen)
    rol = session['rol']
    datos = {
        'activo': 'agentes', 'oficina': oficina,
        'tareas': [t for t in agentes.listar_tareas() if t['estado'] == 'abierta'],
        'especialidades': agentes.ESPECIALIDADES, 'prioridades_tarea': agentes.PRIORIDADES_TAREA,
        'puede_crear': permisos.puede(rol, 'agentes', 'crear'),
        'puede_eliminar': permisos.puede(rol, 'agentes', 'eliminar'),
        'puede_asignar': permisos.puede(rol, 'agentes', 'editar'),
        'hoy': date.today().isoformat(),
        'errores_agente': {}, 'form_agente': {}, 'errores_tarea': {}, 'form_tarea': {},
    }
    datos.update(extra)
    return render_template('dash/agentes.html', **datos)


@dashboard_bp.route('/agentes')
@login_requerido
def agentes_view():
    _exigir('agentes', 'ver')
    return _pagina_agentes()


@dashboard_bp.route('/agentes/nuevo', methods=['POST'])
@login_requerido
def agentes_nuevo():
    _exigir('agentes', 'crear')
    form = {k: request.form.get(k, '') for k in ('nombre', 'correo', 'especialidad')}
    tickets_glpi, origen, _ = glpi.obtener()
    existentes = {a['nombre'].lower() for a in agentes.construir(tickets_glpi, origen)['agentes'] if a['origen'] != 'ejemplo'}
    errores = agentes.validar_agente(form['nombre'], form['correo'], form['especialidad'], existentes)
    if errores:
        return _pagina_agentes(errores_agente=errores, form_agente=form), 400
    nuevo = agentes.crear_agente(form['nombre'], form['correo'], form['especialidad'])
    flash(f"Agente {nuevo['nombre']} agregado a la oficina.", 'ok')
    return redirect(url_for('dashboard.agentes_view'))


@dashboard_bp.route('/agentes/<int:agente_id>/eliminar', methods=['POST'])
@login_requerido
def agentes_eliminar(agente_id):
    _exigir('agentes', 'eliminar')
    eliminado = agentes.eliminar_agente(agente_id)
    if eliminado:
        flash(f"Agente {eliminado['nombre']} eliminado junto con sus tareas.", 'ok')
    else:
        flash('Ese agente ya no existe.', 'error')
    return redirect(url_for('dashboard.agentes_view'))


@dashboard_bp.route('/agentes/tareas/nueva', methods=['POST'])
@login_requerido
def tareas_nueva():
    _exigir('agentes', 'editar')
    form = {k: request.form.get(k, '') for k in ('agente', 'titulo', 'descripcion', 'prioridad', 'fecha_limite')}
    tickets_glpi, origen, _ = glpi.obtener()
    nombres = {a['nombre'].lower() for a in agentes.construir(tickets_glpi, origen)['agentes']}
    errores = agentes.validar_tarea(form['agente'], form['titulo'], form['prioridad'], form['fecha_limite'], nombres)
    if errores:
        return _pagina_agentes(errores_tarea=errores, form_tarea=form), 400
    tarea = agentes.crear_tarea(form['agente'], form['titulo'], form['descripcion'], form['prioridad'],
                                form['fecha_limite'], session['usuario'])
    flash(f"Tarea asignada a {tarea['agente']}.", 'ok')
    return redirect(url_for('dashboard.agentes_view'))


@dashboard_bp.route('/agentes/tareas/<int:tarea_id>/completar', methods=['POST'])
@login_requerido
def tareas_completar(tarea_id):
    _exigir('agentes', 'editar')
    tarea = agentes.completar_tarea(tarea_id)
    flash(f"Tarea “{tarea['titulo']}” completada." if tarea else 'Esa tarea ya no existe.', 'ok' if tarea else 'error')
    return redirect(url_for('dashboard.agentes_view'))


@dashboard_bp.route('/agentes/tareas/<int:tarea_id>/eliminar', methods=['POST'])
@login_requerido
def tareas_eliminar(tarea_id):
    _exigir('agentes', 'eliminar')
    tarea = agentes.eliminar_tarea(tarea_id)
    flash(f"Tarea “{tarea['titulo']}” eliminada." if tarea else 'Esa tarea ya no existe.', 'ok' if tarea else 'error')
    return redirect(url_for('dashboard.agentes_view'))


@dashboard_bp.route('/tickets/resumen.json')
@login_requerido
def tickets_resumen():
    # Lo consulta el navegador cada minuto para mostrar alertas nuevas
    if not permisos.puede(session['rol'], 'tickets', 'ver'):
        abort(403)
    return jsonify(glpi.resumen(glpi.obtener()[0]))


# ---------------------------------------------------------------- Equipos (agente de soporte)

@dashboard_bp.route('/equipos')
@login_requerido
def equipos_view(error_descarga=None, servidor=None):
    _exigir('equipos')
    return render_template('dash/equipos.html', activo='equipos', equipos=equipos.listar(),
                           en_linea=equipos.SEGUNDOS_EN_LINEA,
                           plataformas=descargas.PLATAFORMAS, token_agente=descargas.token_configurado(),
                           puede_descargar=permisos.puede(session['rol'], 'equipos', 'crear'),
                           servidor_agente=servidor or descargas.servidor_sugerido(request.host_url),
                           error_descarga=error_descarga,
                           # Grupos por cliente (según el número de serie registrado en el inventario)
                           ver_grupos=permisos.puede(session['rol'], 'clientes', 'ver') or permisos.puede(session['rol'], 'activos', 'ver'),
                           clientes_lista=clientes.listar_clientes(),
                           puede_asignar=permisos.puede(session['rol'], 'activos', 'crear') and permisos.puede(session['rol'], 'activos', 'editar'),
                           puede_masivo=permisos.puede(session['rol'], 'equipos', 'editar'),
                           grupo=request.args.get('cliente', ''))


@dashboard_bp.route('/equipos/agente')
@login_requerido
def equipos_descargar_agente():
    # El paquete lleva el token del agente: solo para quien puede agregar equipos
    _exigir('equipos', 'crear')
    plataforma = request.args.get('plataforma', '')
    servidor = request.args.get('servidor', '').strip()
    if plataforma not in descargas.PLATAFORMAS:
        abort(404)
    error = descargas.validar_servidor(servidor)
    if error:
        return equipos_view(error_descarga=error, servidor=servidor), 400
    contenido = descargas.construir_zip(plataforma, servidor, EMPRESA['nombre'])
    return send_file(io.BytesIO(contenido), mimetype='application/zip', as_attachment=True,
                     download_name=f'agente-soporte-{plataforma}.zip')


@dashboard_bp.route('/equipos/datos')
@login_requerido
def equipos_datos():
    # La página consulta esta ruta cada pocos segundos para actualizarse sola
    _exigir('equipos')
    return jsonify(equipos.listar())


@dashboard_bp.route('/equipos/<equipo_id>')
@login_requerido
def equipo_view(equipo_id):
    _exigir('equipos')
    equipo = equipos.obtener(equipo_id)
    if equipo is None:
        abort(404)
    puede_asignar = permisos.puede(session['rol'], 'activos', 'crear')
    return render_template('dash/equipo.html', activo='equipos', equipo=equipo,
                           puede_asignar=puede_asignar, tipos=clientes.TIPOS_EQUIPO,
                           clientes_lista=clientes.listar_clientes() if puede_asignar else [])


@dashboard_bp.route('/equipos/<equipo_id>/datos')
@login_requerido
def equipo_datos(equipo_id):
    _exigir('equipos')
    equipo = equipos.obtener(equipo_id)
    if equipo is None:
        abort(404)
    return jsonify(equipo)


@dashboard_bp.route('/equipos/<equipo_id>/rdp')
@login_requerido
def equipo_rdp(equipo_id):
    # Archivo .rdp: al abrirlo, Windows lanza Conexión a Escritorio remoto contra el equipo
    _exigir('equipos')
    equipo = equipos.obtener(equipo_id)
    if equipo is None:
        abort(404)
    contenido = equipos.archivo_rdp(equipo, usuario=request.args.get('usuario', ''),
                                    pantalla=request.args.get('pantalla', 'completa'))
    if contenido is None:
        abort(409, 'El equipo no tiene una IP válida para conectarse.')
    nombre = re.sub(r'[^A-Za-z0-9_-]', '_', equipo['nombre']) or 'equipo'
    return send_file(io.BytesIO(contenido.encode('utf-8')), mimetype='application/x-rdp',
                     as_attachment=True, download_name=f'{nombre}.rdp')


@dashboard_bp.route('/equipos/<equipo_id>/comandos', methods=['GET', 'POST'])
@login_requerido
def equipo_comandos(equipo_id):
    # Consola remota: ejecuta scripts como SYSTEM/root en el equipo. Exige permiso de editar Equipos
    _exigir('equipos', 'editar')
    equipo = equipos.obtener(equipo_id)
    if equipo is None:
        abort(404)
    if request.method == 'POST':
        datos = request.get_json(silent=True) or {}
        script = str(datos.get('script', '')).strip()
        if not script:
            return jsonify(error='Escribe el comando a ejecutar.'), 400
        if len(script) > comandos.LARGO_SCRIPT:
            return jsonify(error='El script es demasiado largo.'), 400
        try:
            tiempo = int(datos.get('tiempo') or 300)
        except (TypeError, ValueError):
            tiempo = 300
        comandos.crear(equipo_id, equipo['nombre'], script, tiempo, session['usuario'],
                       permisos.NOMBRES_ROL.get(session['rol'], session['rol']), request.remote_addr,
                       str(datos.get('descripcion', '')))
    return jsonify(comandos=comandos.historial(equipo_id, 20))


def paginar(lista, por_pagina=25):
    """Una página de la lista según ?pagina=N, con los enlaces para la plantilla parciales/paginacion.html."""
    total = len(lista)
    paginas = max(1, -(-total // por_pagina))
    pagina = min(max(request.args.get('pagina', 1, type=int), 1), paginas)
    inicio = (pagina - 1) * por_pagina
    numeros = sorted({n for n in (1, paginas, pagina - 1, pagina, pagina + 1) if 1 <= n <= paginas})
    otros = {k: v for k, v in request.args.items() if k != 'pagina'}
    urls = {n: url_for(request.endpoint, **(request.view_args or {}), **otros, pagina=n)
            for n in set(numeros) | {pagina - 1, pagina + 1} if 1 <= n <= paginas}
    return {'items': lista[inicio:inicio + por_pagina], 'pagina': pagina, 'paginas': paginas, 'total': total,
            'desde': inicio + 1 if total else 0, 'hasta': min(inicio + por_pagina, total), 'numeros': numeros, 'urls': urls}


def _filtrar_historial():
    lista = comandos.historial()
    equipo_id = request.args.get('equipo', '')
    texto = request.args.get('q', '').strip().lower()
    if equipo_id:
        lista = [c for c in lista if c['equipo'] == equipo_id]
    if texto:
        campos = ('equipo_nombre', 'usuario', 'rol', 'ip_panel', 'cuenta_equipo', 'sesion_equipo', 'descripcion', 'script', 'estado')
        lista = [c for c in lista if any(texto in str(c.get(k, '')).lower() for k in campos)]
    return lista


@dashboard_bp.route('/equipos/historial')
@login_requerido
def comandos_historial():
    # Auditoría: quién ejecutó qué comando, en qué equipo y con qué cuenta
    _exigir('equipos', 'editar')
    paginado = paginar(_filtrar_historial())
    return render_template('dash/comandos_historial.html', activo='equipos', comandos=paginado['items'],
                           paginado=paginado, total=paginado['total'], equipos_lista=equipos.listar(),
                           filtro_equipo=request.args.get('equipo', ''), filtro_texto=request.args.get('q', ''))


@dashboard_bp.route('/equipos/historial.csv')
@login_requerido
def comandos_historial_csv():
    _exigir('equipos', 'editar')
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=';')
    escritor.writerow(['Fecha', 'Equipo', 'Usuario de la plataforma', 'Rol', 'IP del panel', 'Cuenta en el equipo',
                       'Sesión abierta en el equipo', 'Descripción', 'Comando', 'Estado', 'Código', 'Duración (s)'])
    for c in _filtrar_historial():
        duracion = round(c['terminado'] - c['enviado'], 1) if c.get('terminado') and c.get('enviado') else ''
        escritor.writerow([datetime.fromtimestamp(c['creado']).strftime('%Y-%m-%d %H:%M:%S'), c.get('equipo_nombre', c['equipo']),
                           c['usuario'], c.get('rol', ''), c.get('ip_panel', ''), c.get('cuenta_equipo', ''),
                           c.get('sesion_equipo', ''), c.get('descripcion', ''), c['script'], c['estado'],
                           '' if c.get('codigo') is None else c['codigo'], duracion])
    # BOM para que Excel abra bien las tildes
    contenido = '﻿' + salida.getvalue()
    return send_file(io.BytesIO(contenido.encode('utf-8')), mimetype='text/csv', as_attachment=True,
                     download_name=f"historial-comandos-{date.today().isoformat()}.csv")


def _equipos_por_ids(ids):
    lista = [equipos.obtener(str(i)) for i in (ids or [])[:500]]
    return [e for e in lista if e]


@dashboard_bp.route('/equipos/asignar', methods=['POST'])
@login_requerido
def equipos_asignar():
    # Asigna (o mueve) varios equipos a la empresa elegida
    _exigir('activos', 'crear')
    _exigir('activos', 'editar')
    datos = request.get_json(silent=True) or {}
    seleccion = _equipos_por_ids(datos.get('equipos'))
    if not seleccion:
        return jsonify(error='Selecciona al menos un equipo.'), 400
    cliente = clientes.obtener_cliente(str(datos.get('cliente_id', '')))
    if cliente is None:
        return jsonify(error='Elige la empresa.'), 400
    n = clientes.asignar_equipos(cliente['id'], seleccion, session['usuario'])
    return jsonify(ok=True, asignados=n, cliente=cliente['nombre'])


SISTEMAS_CONSOLA = {
    'windows': lambda e: (e.get('sistema') or '').startswith('Windows'),
    'unix': lambda e: not (e.get('sistema') or '').startswith('Windows'),
}


@dashboard_bp.route('/equipos/masivo', methods=['POST'])
@login_requerido
def equipos_masivo():
    # El mismo comando para varios equipos (un grupo o una selección). Queda como un lote
    _exigir('equipos', 'editar')
    datos = request.get_json(silent=True) or {}
    script = str(datos.get('script', '')).strip()
    if not script:
        return jsonify(error='Escribe el comando a ejecutar.'), 400
    if len(script) > comandos.LARGO_SCRIPT:
        return jsonify(error='El script es demasiado largo.'), 400
    sistema = datos.get('sistema')
    if sistema not in SISTEMAS_CONSOLA:
        return jsonify(error='Elige el tipo de consola.'), 400
    seleccion = _equipos_por_ids(datos.get('equipos'))
    # PowerShell solo va a equipos Windows y bash a Mac / Linux: los demás se omiten
    destino = [e for e in seleccion if SISTEMAS_CONSOLA[sistema](e)]
    if not destino:
        return jsonify(error='Ninguno de los equipos elegidos usa ese sistema.'), 400
    try:
        tiempo = int(datos.get('tiempo') or 300)
    except (TypeError, ValueError):
        tiempo = 300
    lote = comandos.crear_lote(destino, script, tiempo, session['usuario'],
                               permisos.NOMBRES_ROL.get(session['rol'], session['rol']), request.remote_addr,
                               str(datos.get('descripcion', '')))
    return jsonify(ok=True, lote=lote, enviados=len(destino), omitidos=[e['nombre'] for e in seleccion if e not in destino])


@dashboard_bp.route('/equipos/masivo/<lote>')
@login_requerido
def equipos_masivo_estado(lote):
    _exigir('equipos', 'editar')
    return jsonify(comandos=[{k: c.get(k) for k in ('equipo', 'equipo_nombre', 'estado', 'codigo', 'salida', 'cuenta_equipo')}
                             for c in comandos.del_lote(lote)])


@dashboard_bp.route('/equipos/<equipo_id>/ubicacion', methods=['POST'])
@login_requerido
def equipo_ubicacion(equipo_id):
    # Activa o desactiva el rastreo de ubicación (queda registrado quién y cuándo)
    _exigir('equipos', 'editar')
    activo = request.form.get('activo') == '1'
    if not equipos.cambiar_rastreo(equipo_id, activo, session['usuario']):
        abort(404)
    flash('Ubicación activada: el equipo la enviará en su próximo reporte (unos 20 a 40 segundos).' if activo
          else 'Ubicación desactivada y última posición borrada.', 'ok')
    return redirect(url_for('dashboard.equipo_view', equipo_id=equipo_id))


@dashboard_bp.route('/equipos/<equipo_id>/eliminar', methods=['POST'])
@login_requerido
def equipo_eliminar(equipo_id):
    # Solo quita el equipo de la lista; si el agente sigue instalado, vuelve a aparecer
    _exigir('equipos', 'eliminar')
    equipos.eliminar(equipo_id)
    flash('Equipo eliminado de la lista.', 'ok')
    return redirect(url_for('dashboard.equipos_view'))


# ---------------------------------------------------------------- Clientes y sus equipos

CAMPOS_CLIENTE = ('tipo_persona', 'nombre', 'tipo_documento', 'documento', 'representante_legal', 'representante_ti',
                  'ti_correo', 'ti_telefono', 'relacion', 'contrato_numero', 'contrato_inicio', 'contrato_fin',
                  'compra_referencia', 'compra_fecha')
CAMPOS_ACTIVO = ('cliente_id', 'tipo', 'marca_modelo', 'serial', 'discos', 'responsable', 'notas')


def _resumen_clientes():
    """Por cliente: equipos registrados, equipos con agente y cuántos están en línea."""
    por_cliente = {}
    for a in clientes.listar_activos():
        por_cliente.setdefault(a['cliente_id'], {'registrados': 0, 'agente': 0, 'en_linea': 0})['registrados'] += 1
    for e in equipos.listar():
        if e.get('cliente'):
            r = por_cliente.setdefault(e['cliente']['id'], {'registrados': 0, 'agente': 0, 'en_linea': 0})
            r['agente'] += 1
            r['en_linea'] += 1 if e['en_linea'] else 0
    return por_cliente


def _pagina_clientes(**extra):
    rol = session['rol']
    filtro_tipo = request.args.get('tipo', '')
    filtro_relacion = request.args.get('relacion', '')
    lista = [c for c in clientes.listar_clientes()
             if (not filtro_tipo or c.get('tipo_persona', 'juridica') == filtro_tipo)
             and (not filtro_relacion or c.get('relacion', 'contrato') == filtro_relacion)]
    datos = {
        'activo': 'clientes', 'lista': lista, 'resumen': _resumen_clientes(),
        'total_clientes': len(clientes.listar_clientes()),
        'filtro_tipo': filtro_tipo, 'filtro_relacion': filtro_relacion,
        'tipos_persona': clientes.TIPOS_PERSONA, 'tipos_documento': clientes.TIPOS_DOCUMENTO,
        'relaciones': clientes.RELACIONES,
        'puede_crear': permisos.puede(rol, 'clientes', 'crear'),
        'puede_editar': permisos.puede(rol, 'clientes', 'editar'),
        'puede_eliminar': permisos.puede(rol, 'clientes', 'eliminar'),
        'errores': {}, 'formulario': {},
    }
    datos.update(extra)
    return render_template('dash/clientes.html', **datos)


@dashboard_bp.route('/clientes')
@login_requerido
def clientes_view():
    _exigir('clientes')
    return _pagina_clientes()


@dashboard_bp.route('/clientes/guardar', methods=['POST'])
@login_requerido
def clientes_guardar():
    cliente_id = request.form.get('id') or None
    _exigir('clientes', 'editar' if cliente_id else 'crear')
    formulario = {k: request.form.get(k, '') for k in CAMPOS_CLIENTE}
    formulario['id'] = cliente_id or ''
    errores = clientes.validar_cliente(formulario, cliente_id)
    archivo = request.files.get('contrato')
    contenido, error_pdf = clientes.validar_contrato(archivo)
    if error_pdf:
        errores['contrato'] = error_pdf
    if errores:
        return _pagina_clientes(errores=errores, formulario=formulario), 400

    contrato = {'contenido': contenido, 'nombre': archivo.filename} if contenido else None
    cliente = clientes.guardar_cliente(formulario, contrato, cliente_id, session['usuario'])
    if cliente is None:
        abort(404)
    flash(f"Cliente {cliente['nombre']} {'actualizado' if cliente_id else 'creado'}.", 'ok')
    return redirect(url_for('dashboard.clientes_view'))


@dashboard_bp.route('/clientes/<cliente_id>/eliminar', methods=['POST'])
@login_requerido
def clientes_eliminar(cliente_id):
    _exigir('clientes', 'eliminar')
    rentados = catalogo.rentas_de_cliente(cliente_id)
    if rentados:
        flash(f'No se puede eliminar: tiene {len(rentados)} equipo(s) en renta. Primero márcalos como devueltos.', 'error')
        return redirect(url_for('dashboard.clientes_view'))
    cliente, error = clientes.eliminar_cliente(cliente_id)
    flash(error or f"Cliente {cliente['nombre']} eliminado.", 'error' if error else 'ok')
    return redirect(url_for('dashboard.clientes_view'))


@dashboard_bp.route('/clientes/<cliente_id>/contrato')
@login_requerido
def clientes_contrato(cliente_id):
    _exigir('clientes')
    cliente = clientes.obtener_cliente(cliente_id)
    ruta = clientes.ruta_contrato(cliente)
    if ruta is None:
        abort(404)
    nombre = re.sub(r'[^\w.\- ]', '_', cliente.get('contrato_nombre') or 'contrato.pdf')
    return send_file(ruta, mimetype='application/pdf', download_name=nombre)


def _pagina_activos(**extra):
    rol = session['rol']
    filtro = request.args.get('cliente', '')
    # Equipos del agente ya unidos a cada registro (por serial o por ID), para mostrar si reporta
    por_activo = {e['activo_id']: e for e in equipos.listar() if e.get('activo_id')}
    lista = clientes.listar_activos(filtro or None)
    for a in lista:
        e = por_activo.get(a['id'])
        a['equipo'] = {'id': e['id'], 'nombre': e['nombre'], 'en_linea': e['en_linea']} if e else None
    datos = {
        'activo': 'activos', 'activos_lista': lista, 'clientes_lista': clientes.listar_clientes(),
        'nombres_cliente': {c['id']: c['nombre'] for c in clientes.listar_clientes()},
        'filtro_cliente': filtro, 'tipos': clientes.TIPOS_EQUIPO,
        'puede_crear': permisos.puede(rol, 'activos', 'crear'),
        'puede_editar': permisos.puede(rol, 'activos', 'editar'),
        'puede_eliminar': permisos.puede(rol, 'activos', 'eliminar'),
        'errores': {}, 'formulario': {},
    }
    datos.update(extra)
    return render_template('dash/activos.html', **datos)


@dashboard_bp.route('/activos')
@login_requerido
def activos_view():
    _exigir('activos')
    return _pagina_activos()


@dashboard_bp.route('/activos/guardar', methods=['POST'])
@login_requerido
def activos_guardar():
    activo_id = request.form.get('id') or None
    _exigir('activos', 'editar' if activo_id else 'crear')
    formulario = {k: request.form.get(k, '') for k in CAMPOS_ACTIVO}
    formulario['id'] = activo_id or ''
    errores = clientes.validar_activo(formulario, activo_id)
    if errores:
        return _pagina_activos(errores=errores, formulario=formulario), 400
    activo = clientes.guardar_activo(formulario, activo_id, session['usuario'])
    if activo is None:
        abort(404)
    flash(f"Equipo {activo['serial']} {'actualizado' if activo_id else 'registrado'}.", 'ok')
    destino = request.form.get('volver') or url_for('dashboard.activos_view', cliente=activo['cliente_id'])
    # Solo se permite volver a páginas del propio panel
    return redirect(destino if destino.startswith('/dashboard/') else url_for('dashboard.activos_view'))


@dashboard_bp.route('/activos/<activo_id>/eliminar', methods=['POST'])
@login_requerido
def activos_eliminar(activo_id):
    _exigir('activos', 'eliminar')
    activo = clientes.eliminar_activo(activo_id)
    flash(f"Equipo {activo['serial']} eliminado del inventario." if activo else 'Ese equipo ya no existe.',
          'ok' if activo else 'error')
    return redirect(url_for('dashboard.activos_view'))


# ---------------------------------------------------------------- Productos, servicios y productos en renta

def _pagina_catalogo(tipo, **extra):
    rol = session['rol']
    cfg = catalogo.CATALOGOS[tipo]
    filtro = request.args.get('categoria', '')
    filtro_estado = request.args.get('estado', '') if tipo == 'renta' else ''
    filtro_cliente = request.args.get('cliente', '') if tipo == 'renta' else ''
    filtro_proveedor = request.args.get('proveedor', '')
    todos = catalogo.listar(tipo)
    lista = [x for x in todos if (not filtro or x.get('categoria') == filtro)
             and (not filtro_estado or x.get('estado') == filtro_estado)
             and (not filtro_cliente or x.get('cliente_id') == filtro_cliente)
             and (not filtro_proveedor or x.get('proveedor_id') == filtro_proveedor)]
    lista_proveedores = proveedores.listar() if tipo != 'servicios' else []
    lista_clientes = clientes.listar_clientes() if tipo == 'renta' else []
    datos = {
        'activo': tipo, 'tipo': tipo, 'cfg': cfg, 'lista': lista, 'filtro_categoria': filtro,
        'filtro_estado': filtro_estado, 'filtro_cliente': filtro_cliente, 'filtro_proveedor': filtro_proveedor,
        'proveedores_lista': lista_proveedores, 'nombres_proveedor': {p['id']: p['nombre'] for p in lista_proveedores},
        'clientes_lista': lista_clientes, 'nombres_cliente': {c['id']: c['nombre'] for c in lista_clientes},
        'estados_renta': catalogo.ESTADOS_RENTA, 'hoy': date.today().isoformat(),
        'renta': catalogo.resumen_renta(todos) if tipo == 'renta' else None,
        'categorias': next(c[3] for c in cfg['campos'] if c[0] == 'categoria'),
        'total': len(todos), 'inactivos': sum(1 for x in todos if not x.get('activo', True)),
        'stock_bajo': [x for x in todos if tipo == 'productos' and x.get('activo', True)
                       and x.get('stock_minimo') and x.get('stock', 0) <= x['stock_minimo']],
        'ver_costo': permisos.puede(rol, tipo, 'editar'),
        'puede_crear': permisos.puede(rol, tipo, 'crear'),
        'puede_editar': permisos.puede(rol, tipo, 'editar'),
        'puede_eliminar': permisos.puede(rol, tipo, 'eliminar'),
        'errores': {}, 'formulario': {}, 'errores_entrada': {}, 'entrada': {},
        'todos_productos': todos if tipo == 'productos' else [], 'precios_de': catalogo.precios_de,
    }
    datos.update(extra)
    return render_template('dash/catalogo.html', **datos)


@dashboard_bp.route('/<any(productos, servicios, renta):tipo>')
@login_requerido
def catalogo_view(tipo):
    _exigir(tipo)
    return _pagina_catalogo(tipo)


@dashboard_bp.route('/<any(productos, servicios, renta):tipo>/guardar', methods=['POST'])
@login_requerido
def catalogo_guardar(tipo):
    item_id = request.form.get('id') or None
    _exigir(tipo, 'editar' if item_id else 'crear')
    datos, errores = catalogo.validar(tipo, request.form, item_id)
    if errores:
        formulario = {**request.form.to_dict(), 'id': item_id or ''}
        return _pagina_catalogo(tipo, errores=errores, formulario=formulario), 400
    anterior = catalogo.obtener(tipo, item_id) if item_id else None
    item = catalogo.guardar(tipo, datos, item_id, session['usuario'])
    if item is None:
        abort(404)
    if tipo == 'productos':
        # Los cambios de stock hechos a mano también quedan en los movimientos
        ventas.registrar_ajuste(item['id'], (anterior or {}).get('stock', 0) or 0, item.get('stock', 0) or 0, session['usuario'],
                                nuevo=anterior is None)
    flash(f"{catalogo.CATALOGOS[tipo]['singular'].capitalize()} {item['codigo']} {'actualizado' if item_id else 'creado'}.", 'ok')
    return redirect(url_for('dashboard.catalogo_view', tipo=tipo))


@dashboard_bp.route('/<any(productos, servicios, renta):tipo>/<item_id>/eliminar', methods=['POST'])
@login_requerido
def catalogo_eliminar(tipo, item_id):
    _exigir(tipo, 'eliminar')
    item = catalogo.eliminar(tipo, item_id)
    # Las cotizaciones ya hechas guardan su propia copia del nombre y el precio
    flash(f"{item['nombre']} eliminado del catálogo." if item else 'Ese registro ya no existe.', 'ok' if item else 'error')
    return redirect(url_for('dashboard.catalogo_view', tipo=tipo))


# ---------------------------------------------------------------- Cotizaciones

def _cotizacion(cot_id):
    cot = cotizaciones.obtener(cot_id)
    if cot is None:
        abort(404)
    return cot


@dashboard_bp.route('/cotizaciones')
@login_requerido
def cotizaciones_view():
    _exigir('cotizaciones')
    filtro = request.args.get('estado', '')
    todas = cotizaciones.listar()
    rol = session['rol']
    return render_template(
        'dash/cotizaciones.html', activo='cotizaciones', filtro=filtro, estados=cotizaciones.ESTADOS,
        lista=[c for c in todas if not filtro or c['estado_actual'] == filtro], resumen=cotizaciones.resumen(todas),
        puede_crear=permisos.puede(rol, 'cotizaciones', 'crear'),
        puede_editar=permisos.puede(rol, 'cotizaciones', 'editar'),
        puede_eliminar=permisos.puede(rol, 'cotizaciones', 'eliminar'))


def _editor(formulario, cot=None, errores=None):
    lista = clientes.listar_clientes()
    # Al elegir un cliente, el editor sugiere su contacto de TI como "Atención"
    contactos = {c['id']: {'contacto': c.get('representante_ti') or (c['nombre'] if c.get('tipo_persona') == 'natural' else ''),
                           'contacto_correo': c.get('ti_correo', ''), 'contacto_telefono': c.get('ti_telefono', '')}
                 for c in lista}
    return render_template(
        'dash/cotizacion_editor.html', activo='cotizaciones', formulario=formulario, cot=cot, contactos=contactos,
        errores=errores or {}, clientes_lista=lista, catalogo_items=catalogo.para_cotizar(),
        formas_pago=cotizaciones.FORMAS_PAGO,
        puede_catalogo=permisos.puede(session['rol'], 'productos', 'crear'))


def _guardar_cotizacion(cot=None):
    datos, errores = cotizaciones.validar(request.form, request.form.get('items_json'))
    if errores:
        return _editor(datos, cot, errores), 400
    guardada = cotizaciones.guardar(datos, cot['id'] if cot else None, session['usuario'])
    if guardada is None:
        abort(409)
    flash(f"Cotización {guardada['numero']} {'actualizada' if cot else 'creada'}.", 'ok')
    return redirect(url_for('dashboard.cotizacion_detalle', cot_id=guardada['id']))


@dashboard_bp.route('/cotizaciones/nueva', methods=['GET', 'POST'])
@login_requerido
def cotizacion_nueva():
    _exigir('cotizaciones', 'crear')
    if request.method == 'POST':
        return _guardar_cotizacion()
    return _editor(cotizaciones.formulario_nuevo(request.args.get('cliente', '')))


@dashboard_bp.route('/cotizaciones/<cot_id>/editar', methods=['GET', 'POST'])
@login_requerido
def cotizacion_editar(cot_id):
    _exigir('cotizaciones', 'editar')
    cot = _cotizacion(cot_id)
    if not cot['editable']:
        flash('Una cotización aprobada o rechazada no se puede editar. Duplícala para hacer una nueva versión.', 'error')
        return redirect(url_for('dashboard.cotizacion_detalle', cot_id=cot_id))
    if request.method == 'POST':
        return _guardar_cotizacion(cot)
    return _editor(cotizaciones.formulario_desde(cot), cot)


@dashboard_bp.route('/cotizaciones/<cot_id>')
@login_requerido
def cotizacion_detalle(cot_id):
    _exigir('cotizaciones')
    rol = session['rol']
    cot = _cotizacion(cot_id)
    return render_template(
        'dash/cotizacion.html', activo='cotizaciones', cot=cot, estados=cotizaciones.ESTADOS,
        envio=_correo_cotizacion(cot), smtp_listo=correos.configurado(),
        puede_crear=permisos.puede(rol, 'cotizaciones', 'crear'),
        puede_editar=permisos.puede(rol, 'cotizaciones', 'editar'),
        puede_eliminar=permisos.puede(rol, 'cotizaciones', 'eliminar'))


@dashboard_bp.route('/cotizaciones/<cot_id>/pdf')
@login_requerido
def cotizacion_pdf(cot_id):
    _exigir('cotizaciones')
    cot = _cotizacion(cot_id)
    contenido = pdf_cotizacion.generar(cot, EMPRESA)
    # ?descargar=1 baja el archivo; sin él se abre en el navegador
    return send_file(io.BytesIO(contenido), mimetype='application/pdf', download_name=_nombre_pdf(cot),
                     as_attachment=request.args.get('descargar') == '1')


def _nombre_pdf(cot):
    return re.sub(r'[^\w\-]+', '_', f"{cot['numero']}_{cot['cliente']['nombre']}").strip('_')[:80] + '.pdf'


def _correo_cotizacion(cot):
    """Destinatario, asunto y mensaje sugeridos para enviar la cotización."""
    cliente = clientes.obtener_cliente(cot['cliente_id']) if cot.get('cliente_id') else None
    para = cot.get('contacto_correo') or (cliente or {}).get('ti_correo', '')
    saludo = cot.get('contacto') or cot['cliente']['nombre']
    firma = nombre_de(session.get('usuario'))[0]
    mensaje = (f"Hola, {saludo}:\n\n"
               f"Adjunto encontrará la cotización {cot['numero']} «{cot['asunto']}» por un total de "
               f"{formato_pesos(cot['totales']['total'])} (IVA incluido). Es válida hasta el {cot['vence']}.\n\n"
               "Quedamos atentos a sus comentarios o a cualquier ajuste que necesite.\n\n"
               f"Cordialmente,\n{firma}\n{EMPRESA['nombre']}\n{EMPRESA.get('telefono', '')}")
    return {'para': para, 'asunto': f"Cotización {cot['numero']} · {cot['asunto']} · {EMPRESA['nombre']}", 'mensaje': mensaje}


def _lista_correos(texto):
    correos_lista = [c.strip().lower() for c in re.split(r'[,;\s]+', texto or '') if c.strip()]
    malos = [c for c in correos_lista if not usuarios.PATRON_CORREO.match(c)]
    return correos_lista, malos


@dashboard_bp.route('/cotizaciones/<cot_id>/enviar-correo', methods=['POST'])
@login_requerido
def cotizacion_enviar_correo(cot_id):
    """Envía la cotización en PDF por correo al cliente."""
    _exigir('cotizaciones', 'editar')
    cot = _cotizacion(cot_id)
    volver = redirect(url_for('dashboard.cotizacion_detalle', cot_id=cot_id))
    para, malos_para = _lista_correos(request.form.get('para'))
    copia, malos_cc = _lista_correos(request.form.get('cc'))
    asunto = ' '.join(request.form.get('asunto', '').split())[:200]
    mensaje = request.form.get('mensaje', '').strip()[:5000]
    if not para or malos_para or malos_cc or len(para) + len(copia) > 10:
        flash('Revisa los correos: ' + (', '.join(malos_para + malos_cc) if malos_para or malos_cc
                                        else 'escribe al menos un destinatario (máximo 10 en total).'), 'error')
        return volver
    if not asunto or not mensaje:
        flash('Escribe el asunto y el mensaje del correo.', 'error')
        return volver

    pdf = pdf_cotizacion.generar(cot, EMPRESA)
    html = '<div style="font-family:Arial,sans-serif;font-size:14px;line-height:1.5">' + \
           ''.join(f'<p>{linea}</p>' if linea else '' for linea in
                   (Markup.escape(b).replace('\n', Markup('<br>')) for b in mensaje.split('\n\n'))) + '</div>'
    try:
        canal = correos.enviar(para, asunto, mensaje, html, adjuntos=[(_nombre_pdf(cot), pdf, 'application/pdf')],
                               cc=copia, responder_a=session['usuario'])
    except Exception as error:
        flash(f'No se pudo enviar el correo: {error}. Revisa la configuración SMTP del archivo .env.', 'error')
        return volver

    destino = ', '.join(para) + (f' (copia: {", ".join(copia)})' if copia else '')
    accion = f'Enviada por correo a {destino}' + (' (prueba: quedó en el archivo, sin SMTP)' if canal == 'archivo' else '')
    if request.form.get('marcar_enviada') == '1' and cot['estado'] == 'borrador' and not cot.get('orden_id'):
        cotizaciones.cambiar_estado(cot_id, 'enviada', session['usuario'], accion=accion)
    else:
        cotizaciones.anotar(cot_id, accion, session['usuario'])
    if canal == 'archivo':
        flash('Aún no hay correo configurado (falta SMTP_CLAVE en .env): el envío quedó en '
              'app/data/correos_salientes.log como prueba, con el PDF listado como adjunto.', 'info')
    else:
        flash(f"Cotización {cot['numero']} enviada a {destino} con el PDF adjunto.", 'ok')
    return volver


@dashboard_bp.route('/cotizaciones/<cot_id>/estado', methods=['POST'])
@login_requerido
def cotizacion_estado(cot_id):
    _exigir('cotizaciones', 'editar')
    actual, estado = _cotizacion(cot_id), request.form.get('estado', '')
    volver = redirect(url_for('dashboard.cotizacion_detalle', cot_id=cot_id))
    if estado not in cotizaciones.ESTADOS or estado == 'vencida':
        abort(400)
    orden = ventas.orden_activa_de(cot_id)
    if orden:
        flash(f"Esta cotización ya generó la orden {orden['numero']}. Para cambiarla, anula primero la orden.", 'error')
        return volver
    if estado != 'aprobada':
        cot = cotizaciones.cambiar_estado(cot_id, estado, session['usuario'])
        flash(f"Cotización {cot['numero']}: {cotizaciones.ESTADOS[estado].lower()}.", 'ok')
        return volver

    # Aprobar dispara la orden de compra, la salida de inventario y la factura
    orden, factura, problemas = ventas.aprobar(actual, session['usuario'])
    if problemas:
        flash('No se pudo aprobar: ' + '; '.join(problemas) + '.', 'error')
        return volver
    cotizaciones.cambiar_estado(cot_id, 'aprobada', session['usuario'],
                                extra={'orden_id': orden['id'], 'orden_numero': orden['numero'],
                                       'factura_id': factura['id'], 'factura_numero': factura['numero']},
                                accion=f"Aprobada: se generó la orden {orden['numero']} y la factura {factura['numero']}")
    flash(f"Cotización aprobada. Se generó la orden {orden['numero']}, se descontó el inventario y se emitió la factura {factura['numero']}.", 'ok')
    return redirect(url_for('dashboard.orden_detalle', orden_id=orden['id']))


@dashboard_bp.route('/cotizaciones/<cot_id>/duplicar', methods=['POST'])
@login_requerido
def cotizacion_duplicar(cot_id):
    _exigir('cotizaciones', 'crear')
    nueva = cotizaciones.duplicar(cot_id, session['usuario'])
    if nueva is None:
        abort(404)
    flash(f"Se creó {nueva['numero']} como copia. Revísala antes de enviarla.", 'ok')
    return redirect(url_for('dashboard.cotizacion_editar', cot_id=nueva['id']))


@dashboard_bp.route('/cotizaciones/<cot_id>/eliminar', methods=['POST'])
@login_requerido
def cotizacion_eliminar(cot_id):
    _exigir('cotizaciones', 'eliminar')
    cot = cotizaciones.eliminar(cot_id)
    flash(f"Cotización {cot['numero']} eliminada." if cot else 'Esa cotización ya no existe.', 'ok' if cot else 'error')
    return redirect(url_for('dashboard.cotizaciones_view'))


# ---------------------------------------------------------------- Proveedores

def _pagina_proveedores(**extra):
    rol = session['rol']
    filtro_tipo = request.args.get('tipo', '')
    filtro_suministra = request.args.get('suministra', '')
    todos = proveedores.listar()
    lista = [p for p in todos if (not filtro_tipo or p['tipo'] == filtro_tipo)
             and (not filtro_suministra or filtro_suministra in p.get('suministra', []))]
    datos = {
        'activo': 'proveedores', 'lista': lista, 'total': len(todos), 'usos': catalogo.usos_de_proveedor(),
        'filtro_tipo': filtro_tipo, 'filtro_suministra': filtro_suministra,
        'tipos': proveedores.TIPOS, 'suministra': proveedores.SUMINISTRA, 'condiciones': proveedores.CONDICIONES_PAGO,
        'puede_crear': permisos.puede(rol, 'proveedores', 'crear'),
        'puede_editar': permisos.puede(rol, 'proveedores', 'editar'),
        'puede_eliminar': permisos.puede(rol, 'proveedores', 'eliminar'),
        'errores': {}, 'formulario': {},
    }
    datos.update(extra)
    return render_template('dash/proveedores.html', **datos)


@dashboard_bp.route('/proveedores')
@login_requerido
def proveedores_view():
    _exigir('proveedores')
    return _pagina_proveedores()


@dashboard_bp.route('/proveedores/guardar', methods=['POST'])
@login_requerido
def proveedores_guardar():
    proveedor_id = request.form.get('id') or None
    _exigir('proveedores', 'editar' if proveedor_id else 'crear')
    datos, errores = proveedores.validar(request.form, proveedor_id)
    if errores:
        return _pagina_proveedores(errores=errores, formulario={**datos, 'id': proveedor_id or ''}), 400
    proveedor = proveedores.guardar(datos, proveedor_id, session['usuario'])
    if proveedor is None:
        abort(404)
    flash(f"Proveedor {proveedor['nombre']} {'actualizado' if proveedor_id else 'creado'}.", 'ok')
    return redirect(url_for('dashboard.proveedores_view'))


@dashboard_bp.route('/proveedores/<proveedor_id>/eliminar', methods=['POST'])
@login_requerido
def proveedores_eliminar(proveedor_id):
    _exigir('proveedores', 'eliminar')
    proveedor, error = proveedores.eliminar(proveedor_id, catalogo.usos_de_proveedor().get(proveedor_id, 0))
    flash(error or f"Proveedor {proveedor['nombre']} eliminado.", 'error' if error else 'ok')
    return redirect(url_for('dashboard.proveedores_view'))


# ---------------------------------------------------------------- Órdenes de compra

@dashboard_bp.route('/ventas')
@login_requerido
def ordenes_view():
    _exigir('ventas')
    filtro = request.args.get('estado', '')
    todas = ventas.listar_ordenes()
    conteo = Counter(o['estado'] for o in todas)
    return render_template('dash/ordenes.html', activo='ventas', lista=[o for o in todas if not filtro or o['estado'] == filtro],
                           filtro=filtro, estados=ventas.ESTADOS_ORDEN, conteo=conteo,
                           pendientes=sum(1 for o in todas for s in o['servicios'] if o['estado'] == 'abierta' and s['estado'] == 'pendiente'))


def _orden(orden_id):
    orden = ventas.obtener_orden(orden_id)
    if orden is None:
        abort(404)
    return orden


@dashboard_bp.route('/ventas/<orden_id>')
@login_requerido
def orden_detalle(orden_id):
    _exigir('ventas')
    rol = session['rol']
    orden = _orden(orden_id)
    return render_template('dash/orden.html', activo='ventas', orden=orden, estados=ventas.ESTADOS_ORDEN,
                           factura=ventas.obtener_factura(orden['factura_id']),
                           puede_editar=permisos.puede(rol, 'ventas', 'editar'),
                           puede_anular=permisos.puede(rol, 'ventas', 'eliminar'))


@dashboard_bp.route('/ventas/<orden_id>/servicio', methods=['POST'])
@login_requerido
def orden_servicio(orden_id):
    _exigir('ventas', 'editar')
    try:
        linea = int(request.form.get('linea', ''))
    except ValueError:
        abort(400)
    if ventas.marcar_servicio(orden_id, linea, request.form.get('hecho') == '1', session['usuario']) is None:
        abort(400)
    return redirect(url_for('dashboard.orden_detalle', orden_id=orden_id))


@dashboard_bp.route('/ventas/<orden_id>/anular', methods=['POST'])
@login_requerido
def orden_anular(orden_id):
    _exigir('ventas', 'eliminar')
    orden, error = ventas.anular(orden_id, session['usuario'], request.form.get('motivo', '').strip()[:200])
    if error:
        flash(error, 'error')
        return redirect(url_for('dashboard.orden_detalle', orden_id=orden_id))
    # La cotización vuelve a «Enviada» para poder corregirla y aprobarla otra vez
    if cotizaciones.obtener(orden['cotizacion_id']):
        cotizaciones.cambiar_estado(orden['cotizacion_id'], 'enviada', session['usuario'],
                                    extra={'orden_id': '', 'orden_numero': '', 'factura_id': '', 'factura_numero': ''},
                                    accion=f"Orden {orden['numero']} anulada; vuelve a enviada")
    flash(f"Orden {orden['numero']} anulada: se devolvió el inventario y la factura {orden['factura_numero']} quedó anulada.", 'ok')
    return redirect(url_for('dashboard.orden_detalle', orden_id=orden_id))


# ---------------------------------------------------------------- Facturas

@dashboard_bp.route('/facturas')
@login_requerido
def facturas_view():
    _exigir('facturas')
    filtro = request.args.get('estado', '')
    todas = ventas.listar_facturas()
    return render_template('dash/facturas.html', activo='facturas', filtro=filtro, estados=ventas.ESTADOS_FACTURA,
                           lista=[f for f in todas if not filtro or f['estado_actual'] == filtro],
                           resumen=ventas.resumen_facturas(todas))


def _factura(factura_id):
    factura = ventas.obtener_factura(factura_id)
    if factura is None:
        abort(404)
    return factura


@dashboard_bp.route('/facturas/<factura_id>')
@login_requerido
def factura_detalle(factura_id):
    _exigir('facturas')
    return render_template('dash/factura.html', activo='facturas', factura=_factura(factura_id),
                           medios=ventas.MEDIOS_PAGO, hoy=date.today().isoformat(),
                           puede_pagar=permisos.puede(session['rol'], 'facturas', 'editar'))


@dashboard_bp.route('/facturas/<factura_id>/pdf')
@login_requerido
def factura_pdf(factura_id):
    _exigir('facturas')
    factura = _factura(factura_id)
    nombre = re.sub(r'[^\w\-]+', '_', f"{factura['numero']}_{factura['cliente']['nombre']}").strip('_')[:80]
    contenido = pdf_cotizacion.generar(factura, EMPRESA, tipo='factura')
    return send_file(io.BytesIO(contenido), mimetype='application/pdf', download_name=f'{nombre}.pdf',
                     as_attachment=request.args.get('descargar') == '1')


@dashboard_bp.route('/facturas/<factura_id>/pago', methods=['POST'])
@login_requerido
def factura_pago(factura_id):
    _exigir('facturas', 'editar')
    factura, error = ventas.registrar_pago(factura_id, request.form.get('fecha', ''), request.form.get('medio', ''),
                                           request.form.get('referencia', ''), session['usuario'])
    flash(error or f"Pago de la factura {factura['numero']} registrado.", 'error' if error else 'ok')
    return redirect(url_for('dashboard.factura_detalle', factura_id=factura_id))


# ---------------------------------------------------------------- Movimientos de inventario

@dashboard_bp.route('/productos/entrada', methods=['POST'])
@login_requerido
def productos_entrada():
    """Mercancía que llega: suma al stock del producto y queda en los movimientos."""
    _exigir('productos', 'editar')
    producto_id = request.form.get('producto_id', '')
    producto, errores = ventas.registrar_entrada(producto_id, request.form, session['usuario'])
    if errores:
        return _pagina_catalogo('productos', errores_entrada=errores, entrada=request.form.to_dict()), 400
    flash(f"Entrada registrada: {request.form.get('cantidad')} × {producto['nombre']}. Stock actual: {producto['stock']}.", 'ok')
    return redirect(url_for('dashboard.catalogo_view', tipo='productos'))


@dashboard_bp.route('/productos/movimientos')
@login_requerido
def movimientos_view():
    _exigir('productos')
    filtro = request.args.get('producto', '')
    return render_template('dash/movimientos.html', activo='productos', lista=ventas.listar_movimientos(filtro or None),
                           productos=catalogo.listar('productos'), filtro=filtro)


@dashboard_bp.route('/<nombre>')
@login_requerido
def seccion(nombre):
    if nombre not in SECCIONES:
        abort(404)
    if not permisos.puede(session['rol'], nombre, 'ver'):
        abort(403)
    return render_template('dash/seccion.html', activo=nombre, titulo=SECCIONES[nombre])
