from flask import Blueprint, render_template

# Blueprint del sitio público (la página que ven los clientes)
web_bp = Blueprint('web', __name__)


# Datos de la empresa: se editan aquí y se usan en todas las plantillas
EMPRESA = {
    'nombre': 'Test-Lab',
    'lema': 'Asesoría y soluciones',
    # Pendiente: reemplazar por el teléfono y correo reales de Test-Lab
    'telefono': '(+57) 300 000 0000',
    'telefono_link': '+573000000000',
    'correo': 'contacto@test-lab.com',
}

# Palabras de la franja animada debajo del hero
FRENTES = ['ERP', 'Nube', 'Infraestructura', 'Mesa de ayuda', 'Redes', 'Ciberseguridad', 'Servidores']


@web_bp.app_context_processor
def datos_empresa():
    return {'empresa': EMPRESA}


@web_bp.route('/')
def inicio():
    return render_template('web/index.html', frentes=FRENTES)
