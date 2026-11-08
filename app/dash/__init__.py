from flask import Blueprint, render_template, session

from auth import login_requerido

# Blueprint del panel administrativo. Se llama 'dashboard' porque
# templates/base.html usa url_for('dashboard.<vista>')
dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')


@dashboard_bp.route('/')
@login_requerido
def dash_view():
    # Pendiente: vistas del panel (clientes, cotizaciones, facturas...)
    return render_template('dash/inicio.html', usuario=session['usuario'])
