"""Mensajes al celular (SMS o WhatsApp) con el código para recuperar la contraseña.

Se elige el proveedor en .env con MENSAJES_PROVEEDOR:

  twilio     SMS o WhatsApp por Twilio (https://www.twilio.com)
             TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN y TWILIO_DESDE:
               - SMS:      el número de Twilio, ej. +15017122661
               - WhatsApp: whatsapp:+14155238886 (sandbox) o tu número aprobado
  whatsapp   WhatsApp Cloud API de Meta (https://developers.facebook.com/docs/whatsapp)
             WHATSAPP_TOKEN, WHATSAPP_TELEFONO_ID y WHATSAPP_PLANTILLA: nombre de una plantilla
             de categoría «Autenticación» aprobada por Meta (con botón «Copiar código»).
             WHATSAPP_IDIOMA (por defecto es)

Sin proveedor, el mensaje se escribe en app/data/mensajes_salientes.log para poder probar.
"""
import base64
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime

from . import almacen

TIEMPO_ESPERA = 15
VERSION_GRAPH = 'v21.0'


class ErrorMensaje(Exception):
    pass


def proveedor():
    nombre = (os.environ.get('MENSAJES_PROVEEDOR') or '').strip().lower()
    requeridos = {'twilio': ('TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_DESDE'),
                  'whatsapp': ('WHATSAPP_TOKEN', 'WHATSAPP_TELEFONO_ID', 'WHATSAPP_PLANTILLA')}
    if nombre in requeridos and all(os.environ.get(k) for k in requeridos[nombre]):
        return nombre
    return None


def _pedir(url, datos, encabezados):
    peticion = urllib.request.Request(url, data=datos, headers=encabezados, method='POST')
    try:
        with urllib.request.urlopen(peticion, timeout=TIEMPO_ESPERA) as respuesta:
            return json.loads(respuesta.read() or b'{}')
    except urllib.error.HTTPError as error:
        detalle = error.read().decode('utf-8', 'replace')[:300]
        raise ErrorMensaje(f'El proveedor respondió {error.code}: {detalle}') from None
    except OSError as error:
        raise ErrorMensaje(f'No se pudo conectar con el proveedor: {error}') from None


def _twilio(celular, texto):
    sid = os.environ['TWILIO_ACCOUNT_SID']
    desde = os.environ['TWILIO_DESDE'].strip()
    destino = f'whatsapp:{celular}' if desde.startswith('whatsapp:') else celular
    credencial = base64.b64encode(f"{sid}:{os.environ['TWILIO_AUTH_TOKEN']}".encode()).decode()
    _pedir(f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json',
           urllib.parse.urlencode({'To': destino, 'From': desde, 'Body': texto}).encode(),
           {'Authorization': f'Basic {credencial}', 'Content-Type': 'application/x-www-form-urlencoded'})


def _whatsapp(celular, codigo):
    # Las plantillas de autenticación llevan el código en el cuerpo y en el botón «Copiar código»
    cuerpo = {
        'messaging_product': 'whatsapp',
        'to': celular.lstrip('+'),
        'type': 'template',
        'template': {
            'name': os.environ['WHATSAPP_PLANTILLA'],
            'language': {'code': os.environ.get('WHATSAPP_IDIOMA') or 'es'},
            'components': [
                {'type': 'body', 'parameters': [{'type': 'text', 'text': codigo}]},
                {'type': 'button', 'sub_type': 'url', 'index': '0', 'parameters': [{'type': 'text', 'text': codigo}]},
            ],
        },
    }
    _pedir(f"https://graph.facebook.com/{VERSION_GRAPH}/{os.environ['WHATSAPP_TELEFONO_ID']}/messages",
           json.dumps(cuerpo).encode(),
           {'Authorization': f"Bearer {os.environ['WHATSAPP_TOKEN']}", 'Content-Type': 'application/json'})


def enviar_codigo(celular, codigo, empresa='Test-Lab', minutos=2):
    """Envía el código al celular. Devuelve el canal usado: 'twilio', 'whatsapp' o 'archivo'."""
    texto = (f'{empresa}: tu código para recuperar la contraseña es {codigo}. '
             f'Vence en {minutos} minutos. Si no lo pediste, ignora este mensaje.')
    canal = proveedor()
    if canal == 'twilio':
        _twilio(celular, texto)
    elif canal == 'whatsapp':
        _whatsapp(celular, codigo)
    else:
        almacen.CARPETA.mkdir(parents=True, exist_ok=True)
        with open(almacen.CARPETA / 'mensajes_salientes.log', 'a', encoding='utf-8') as archivo:
            archivo.write(f'\n===== {datetime.now():%Y-%m-%d %H:%M:%S} · Para: {celular}\n{texto}\n')
        canal = 'archivo'
    return canal
