"""Roles y permisos de acceso al panel.

Por ahora los permisos se guardan en app/data/roles.json. Cuando conectemos
la base de datos, solo hay que cambiar cargar() y guardar() por consultas;
el resto del panel usa puede() y no necesita cambios.
"""
import almacen

ARCHIVO = 'roles.json'

# (clave, nombre, descripción)
ROLES = [
    ('superadmin', 'Superadministrador', 'Control total del sistema. Sus permisos no se pueden modificar.'),
    ('admin', 'Administrador', 'Gestiona toda la operación de la empresa.'),
    ('vendedor', 'Vendedor', 'Atiende clientes, cotizaciones y ventas.'),
    ('preventa', 'Preventa', 'Prepara propuestas técnicas y cotizaciones.'),
    ('tecnico', 'Técnico', 'Consulta clientes y gestiona los servicios.'),
    ('auxiliar', 'Auxiliar administrativo', 'Apoya facturación, proveedores e inventario.'),
]
NOMBRES_ROL = {clave: nombre for clave, nombre, _ in ROLES}

ACCIONES = [('ver', 'Ver'), ('crear', 'Crear'), ('editar', 'Editar'), ('eliminar', 'Eliminar')]
TODAS = [clave for clave, _ in ACCIONES]

# (clave, nombre, grupo) — las claves coinciden con las del menú del panel
MODULOS = [
    ('clientes', 'Clientes', 'Comercial'),
    ('cotizaciones', 'Cotizaciones', 'Comercial'),
    ('ventas', 'Ventas', 'Comercial'),
    ('vendedores', 'Vendedores', 'Comercial'),
    ('facturas', 'Facturas', 'Facturación'),
    ('productos', 'Productos', 'Inventario'),
    ('servicios', 'Servicios', 'Inventario'),
    ('proveedores', 'Proveedores', 'Inventario'),
    ('tickets', 'Tickets (GLPI)', 'Soporte'),
    ('usuarios', 'Usuarios', 'Usuarios y accesos'),
    ('roles', 'Roles y permisos', 'Configuración'),
    ('configuracion', 'General', 'Configuración'),
]

VCE = ['ver', 'crear', 'editar']

PERMISOS_INICIALES = {
    'admin': {**{m: TODAS for m, _, _ in MODULOS}, 'roles': ['ver']},
    'vendedor': {
        'clientes': VCE, 'cotizaciones': VCE, 'ventas': ['ver', 'crear'],
        'productos': ['ver'], 'servicios': ['ver'],
    },
    'preventa': {
        'clientes': VCE, 'cotizaciones': VCE, 'productos': ['ver'],
        'servicios': ['ver'], 'proveedores': ['ver'], 'tickets': ['ver'],
    },
    'tecnico': {
        'clientes': ['ver'], 'servicios': ['ver', 'editar'], 'productos': ['ver'],
        'tickets': VCE,
    },
    'auxiliar': {
        'clientes': VCE, 'cotizaciones': ['ver'], 'facturas': VCE,
        'productos': VCE, 'proveedores': VCE, 'tickets': ['ver'],
    },
}

_cache = None


def cargar():
    global _cache
    if _cache is None:
        datos = {rol: dict(p) for rol, p in PERMISOS_INICIALES.items()}
        guardados = almacen.leer(ARCHIVO, {})
        # Módulos que existían cuando se guardó el archivo. Si después se
        # agrega un módulo nuevo, cada rol recibe su permiso inicial para él
        conocidos = set(guardados.pop('_modulos', [m for p in guardados.values() for m in p]))
        for rol, permisos_rol in guardados.items():
            nuevos = {m: a for m, a in PERMISOS_INICIALES.get(rol, {}).items() if m not in conocidos}
            datos[rol] = {**permisos_rol, **nuevos}
        _cache = datos
    return _cache


def guardar(datos):
    global _cache
    almacen.escribir(ARCHIVO, {'_modulos': [m for m, _, _ in MODULOS], **datos})
    _cache = datos


def permisos_de(rol):
    if rol == 'superadmin':
        return {m: list(TODAS) for m, _, _ in MODULOS}
    return cargar().get(rol, {})


def puede(rol, modulo, accion='ver'):
    return accion in permisos_de(rol).get(modulo, [])


def actualizar_rol(rol, permisos):
    if rol == 'superadmin' or rol not in NOMBRES_ROL:
        return
    validos = {m for m, _, _ in MODULOS}
    limpios = {}
    for modulo, acciones in permisos.items():
        acciones = [a for a in TODAS if a in acciones]
        # Crear, editar o eliminar sin poder ver no tiene sentido
        if acciones and 'ver' not in acciones:
            acciones.insert(0, 'ver')
        if modulo in validos and acciones:
            limpios[modulo] = acciones
    datos = dict(cargar())
    datos[rol] = limpios
    guardar(datos)


def restablecer_rol(rol):
    if rol in PERMISOS_INICIALES:
        datos = dict(cargar())
        datos[rol] = dict(PERMISOS_INICIALES[rol])
        guardar(datos)
