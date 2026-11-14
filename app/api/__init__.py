import hmac
import os

from flask import Blueprint, jsonify, request

from dash import equipos

# API que usan los agentes instalados en los equipos (no usa la sesión del panel)
api_bp = Blueprint('api', __name__, url_prefix='/api/agente')

TAMANO_MAXIMO = 64 * 1024  # un reporte normal pesa ~2 KB


def token_valido():
    esperado = os.environ.get('AGENT_TOKEN', '')
    recibido = request.headers.get('Authorization', '').removeprefix('Bearer ').strip()
    # compare_digest evita que se pueda adivinar el token midiendo tiempos
    return bool(esperado) and hmac.compare_digest(recibido.encode(), esperado.encode())


@api_bp.route('/reporte', methods=['POST'])
def reporte():
    if not os.environ.get('AGENT_TOKEN'):
        return jsonify(error='El panel no tiene AGENT_TOKEN configurado'), 503
    if not token_valido():
        return jsonify(error='Token inválido'), 401
    if (request.content_length or 0) > TAMANO_MAXIMO:
        return jsonify(error='Reporte demasiado grande'), 413

    datos = request.get_json(silent=True)
    if not equipos.registrar(datos, request.remote_addr):
        return jsonify(error='Reporte inválido'), 400
    return jsonify(ok=True)
