import csv
import io
import re
from collections import Counter
from datetime import date, datetime

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, send_file, session, url_for

from auth import correo_admin, login_requerido, usuarios
from web import EMPRESA
from . import agentes, clientes, comandos, descargas, equipos, glpi, permisos

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
        ('agentes', 'Agentes', 'fa-building-user'),
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
        ('activos', 'Equipos de clientes', 'fa-laptop-file'),
    ]},
    {'grupo': 'Soporte', 'icono': 'fa-headset', 'items': [
        ('tickets', 'Tickets (GLPI)', 'fa-ticket'),
        ('equipos', 'Equipos', 'fa-laptop'),
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


@dashboard_bp.app_template_filter('fecha_hora')
def formato_fecha_hora(segundos):
    return datetime.fromtimestamp(segundos).strftime('%Y-%m-%d %H:%M:%S') if segundos else ''


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
    datos = {
        'activo': 'inicio', 'graficos': graficos, 'facturas': FACTURAS,
        'valor_max': max(f['valor'] for f in FACTURAS), 'colores_estado': COLORES_ESTADO,
    }

    # Cada rol puede tener su propio inicio en templates/dash/inicio/<rol>.html
    rol = session['rol']
    return render_template([f'dash/inicio/{rol}.html', 'dash/inicio/general.html'], **datos)


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
                           clientes_lista=clientes.listar_clientes() if permisos.puede(session['rol'], 'clientes', 'ver') or permisos.puede(session['rol'], 'activos', 'ver') else [],
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
    lista = _filtrar_historial()
    return render_template('dash/comandos_historial.html', activo='equipos', comandos=lista[:300],
                           total=len(lista), equipos_lista=equipos.listar(),
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

CAMPOS_CLIENTE = ('nombre', 'nit', 'representante_legal', 'representante_ti', 'ti_correo', 'ti_telefono',
                  'contrato_numero', 'contrato_inicio', 'contrato_fin')
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
    datos = {
        'activo': 'clientes', 'lista': clientes.listar_clientes(), 'resumen': _resumen_clientes(),
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
    # Equipos del agente por serial, para mostrar si el registrado ya está reportando
    por_serial = {clientes.serial_de_equipo(e): e for e in equipos.listar()}
    lista = clientes.listar_activos(filtro or None)
    for a in lista:
        e = por_serial.get(clientes.normalizar_serial(a['serial']))
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


@dashboard_bp.route('/<nombre>')
@login_requerido
def seccion(nombre):
    if nombre not in SECCIONES:
        abort(404)
    if not permisos.puede(session['rol'], nombre, 'ver'):
        abort(403)
    return render_template('dash/seccion.html', activo=nombre, titulo=SECCIONES[nombre])
