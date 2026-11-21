"""Roles y permisos de acceso al panel.

Por ahora los permisos se guardan en app/data/roles.json. Cuando conectemos
la base de datos, solo hay que cambiar cargar() y guardar() por consultas;
el resto del panel usa puede() y no necesita cambios.
"""
from nucleo import almacen

ARCHIVO = 'roles.json'

# (clave, nombre, descripción)
ROLES = [
    ('superadmin', 'Superadministrador', 'Control total del sistema. Sus permisos no se pueden modificar.'),
    ('admin', 'Administrador', 'Gestiona toda la operación de la empresa, menos los agentes.'),
    ('vendedor', 'Ventas', 'Consulta los productos en existencia, hace cotizaciones y ve las órdenes de compra.'),
    ('preventa', 'Preventa', 'Prepara propuestas técnicas y cotizaciones.'),
    ('tecnico', 'Técnico', 'Consulta clientes y gestiona los servicios.'),
    ('auxiliar', 'Auxiliar de inventario', 'Ingresa al inventario los productos que llegan y gestiona los proveedores.'),
]
NOMBRES_ROL = {clave: nombre for clave, nombre, _ in ROLES}

ACCIONES = [('ver', 'Ver'), ('crear', 'Crear'), ('editar', 'Editar'), ('eliminar', 'Eliminar')]
TODAS = [clave for clave, _ in ACCIONES]

# (clave, nombre, grupo) — las claves coinciden con las del menú del panel
MODULOS = [
    ('agentes', 'Agentes', 'Dashboard'),
    ('clientes', 'Clientes', 'Comercial'),
    ('cotizaciones', 'Cotizaciones', 'Comercial'),
    ('ventas', 'Órdenes de compra', 'Comercial'),
    ('facturas', 'Facturas', 'Facturación'),
    ('productos', 'Productos', 'Inventario'),
    ('servicios', 'Servicios', 'Inventario'),
    ('proveedores', 'Proveedores', 'Inventario'),
    ('activos', 'Equipos de inventario', 'Inventario'),
    ('renta', 'Productos en renta', 'Renta'),
    ('tickets', 'Tickets (GLPI)', 'Soporte'),
    ('equipos', 'Equipos con agente', 'Soporte'),
    ('usuarios', 'Usuarios', 'Usuarios y accesos'),
    ('roles', 'Roles y permisos', 'Configuración'),
    ('configuracion', 'General', 'Configuración'),
]

VCE = ['ver', 'crear', 'editar']

# Perfiles: superadmin todo (no se configura); admin todo menos agentes y sin cambiar
# permisos; ventas cotiza y consulta; auxiliar recibe la mercancía
PERMISOS_INICIALES = {
    'admin': {**{m: TODAS for m, _, _ in MODULOS if m != 'agentes'}, 'roles': ['ver']},
    'vendedor': {
        'productos': ['ver'], 'cotizaciones': VCE, 'ventas': ['ver'],
    },
    'preventa': {
        'clientes': VCE, 'cotizaciones': VCE, 'productos': ['ver'],
        'servicios': ['ver'], 'proveedores': ['ver'], 'tickets': ['ver'], 'activos': ['ver'], 'renta': ['ver'],
    },
    'tecnico': {
        'clientes': ['ver'], 'servicios': ['ver', 'editar'], 'productos': ['ver'],
        'tickets': VCE, 'agentes': ['ver'], 'equipos': ['ver'], 'activos': VCE, 'renta': ['ver', 'editar'],
    },
    'auxiliar': {
        'productos': VCE, 'proveedores': VCE, 'renta': VCE,
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
