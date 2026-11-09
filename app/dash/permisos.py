"""Roles y permisos de acceso al panel.

Por ahora los permisos se guardan en app/data/roles.json. Cuando conectemos
la base de datos, solo hay que cambiar cargar() y guardar() por consultas;
el resto del panel usa puede() y no necesita cambios.
"""
import json
import os
from pathlib import Path

ARCHIVO = Path(__file__).resolve().parent.parent / 'data' / 'roles.json'

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
        'servicios': ['ver'], 'proveedores': ['ver'],
    },
    'tecnico': {
        'clientes': ['ver'], 'servicios': ['ver', 'editar'], 'productos': ['ver'],
    },
    'auxiliar': {
        'clientes': VCE, 'cotizaciones': ['ver'], 'facturas': VCE,
        'productos': VCE, 'proveedores': VCE,
    },
}

_cache = None


def cargar():
    global _cache
    if _cache is None:
        datos = {rol: dict(p) for rol, p in PERMISOS_INICIALES.items()}
        if ARCHIVO.exists():
            datos.update(json.loads(ARCHIVO.read_text(encoding='utf-8')))
        _cache = datos
    return _cache


def guardar(datos):
    # Escribe en un archivo temporal y luego lo reemplaza: si algo falla
    # a mitad de camino, el archivo anterior queda intacto
    global _cache
    ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
    temporal = ARCHIVO.with_suffix('.tmp')
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporal, ARCHIVO)
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
