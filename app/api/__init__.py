import hmac
import os

from flask import Blueprint, jsonify, request

from dash import comandos, equipos

# API que usan los agentes instalados en los equipos (no usa la sesión del panel)
api_bp = Blueprint('api', __name__, url_prefix='/api/agente')

TAMANO_MAXIMO = 64 * 1024  # un reporte normal pesa ~2 KB
TAMANO_RESULTADO = 256 * 1024


def token_valido():
    esperado = os.environ.get('AGENT_TOKEN', '')
    recibido = request.headers.get('Authorization', '').removeprefix('Bearer ').strip()
    # compare_digest evita que se pueda adivinar el token midiendo tiempos
    return bool(esperado) and hmac.compare_digest(recibido.encode(), esperado.encode())


@api_bp.before_request
def exigir_token():
    if not os.environ.get('AGENT_TOKEN'):
        return jsonify(error='El panel no tiene AGENT_TOKEN configurado'), 503
    if not token_valido():
        return jsonify(error='Token inválido'), 401


@api_bp.route('/reporte', methods=['POST'])
def reporte():
    if (request.content_length or 0) > TAMANO_MAXIMO:
        return jsonify(error='Reporte demasiado grande'), 413

    datos = request.get_json(silent=True)
    if not equipos.registrar(datos, request.remote_addr):
        return jsonify(error='Reporte inválido'), 400
    # El agente solo envía su ubicación si un administrador la activó para este equipo
    return jsonify(ok=True, ubicacion=equipos.rastreo_activo(str(datos.get('id', '')).lower()))


@api_bp.route('/comandos/<equipo_id>')
def comandos_pendientes(equipo_id):
    # El agente pregunta cada pocos segundos si hay algo que ejecutar
    equipo_id = equipo_id.lower()
    if equipos.obtener(equipo_id) is None:
        return jsonify(error='Equipo desconocido: primero debe enviar un reporte'), 404
    return jsonify(comandos=comandos.para_agente(equipo_id))


@api_bp.route('/comandos/<equipo_id>/<comando_id>', methods=['POST'])
def comando_resultado(equipo_id, comando_id):
    if (request.content_length or 0) > TAMANO_RESULTADO:
        return jsonify(error='Resultado demasiado grande'), 413
    datos = request.get_json(silent=True) or {}
    equipo_id = equipo_id.lower()
    salida = str(datos.get('salida') or '')

    # El bloque de inventario (JSON largo) no se guarda en el historial: va a la ficha del equipo
    comando = comandos.registrar_resultado(comando_id, equipo_id, datos.get('codigo'),
                                           equipos.quitar_inventario(salida),
                                           datos.get('cuenta'), datos.get('sesion'))
    if comando is None:
        return jsonify(error='Comando desconocido o ya terminado'), 404
    if comando['codigo'] == 0:
        equipos.actualizar_inventario(equipo_id, salida, comando)
    return jsonify(ok=True)
