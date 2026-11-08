from flask import Blueprint

# Blueprint del panel administrativo. Se llama 'dashboard' porque
# templates/base.html usa url_for('dashboard.<vista>')
dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')


@dashboard_bp.route('/')
def dash_view():
    # Pendiente: vistas del panel (clientes, cotizaciones, facturas...)
    return 'Panel en construcción'
