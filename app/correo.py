"""Envío de correos del panel (códigos para recuperar la contraseña, cotizaciones en PDF…).

Con SMTP configurado en .env se envían de verdad:
    SMTP_SERVIDOR=smtp.gmail.com
    SMTP_PUERTO=587
    SMTP_USUARIO=cuenta@gmail.com
    SMTP_CLAVE=contraseña de aplicación (no la clave normal de la cuenta)
    SMTP_REMITENTE=Test-Lab <cuenta@gmail.com>     (opcional)
Sin SMTP, el correo se escribe en app/data/correos_salientes.log para poder probar
en este equipo (esa carpeta no se sube a GitHub).
"""
import os
import smtplib
from datetime import datetime
from email.message import EmailMessage

import almacen


def configurado():
    return all(os.environ.get(k) for k in ('SMTP_SERVIDOR', 'SMTP_USUARIO', 'SMTP_CLAVE'))


def enviar(destino, asunto, texto, html=None, adjuntos=(), cc=(), responder_a=None):
    """Envía el correo. destino y cc: un correo o una lista. adjuntos: [(nombre, bytes, tipo mime)].
    Devuelve 'smtp' si salió por correo o 'archivo' si quedó en correos_salientes.log."""
    para = [destino] if isinstance(destino, str) else list(destino)
    copia = [cc] if isinstance(cc, str) else list(cc)
    if not configurado():
        almacen.CARPETA.mkdir(parents=True, exist_ok=True)
        lineas = [f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} · Para: {', '.join(para)}"
                  + (f" · CC: {', '.join(copia)}" if copia else ''),
                  f'Asunto: {asunto}']
        lineas += [f'Adjunto: {nombre} ({len(datos) // 1024 + 1} KB)' for nombre, datos, _ in adjuntos]
        with open(almacen.CARPETA / 'correos_salientes.log', 'a', encoding='utf-8') as archivo:
            archivo.write('\n'.join(lineas) + f'\n\n{texto}\n')
        return 'archivo'

    mensaje = EmailMessage()
    mensaje['Subject'] = asunto
    mensaje['From'] = os.environ.get('SMTP_REMITENTE') or os.environ['SMTP_USUARIO']
    mensaje['To'] = ', '.join(para)
    if copia:
        mensaje['Cc'] = ', '.join(copia)
    if responder_a:
        mensaje['Reply-To'] = responder_a  # las respuestas del cliente le llegan a quien envió
    mensaje.set_content(texto)
    if html:
        mensaje.add_alternative(html, subtype='html')
    for nombre, datos, tipo in adjuntos:
        principal, _, secundario = tipo.partition('/')
        mensaje.add_attachment(datos, maintype=principal, subtype=secundario, filename=nombre)
    puerto = int(os.environ.get('SMTP_PUERTO') or 587)
    if puerto == 465:
        servidor = smtplib.SMTP_SSL(os.environ['SMTP_SERVIDOR'], puerto, timeout=30)
    else:
        servidor = smtplib.SMTP(os.environ['SMTP_SERVIDOR'], puerto, timeout=30)
        servidor.starttls()
    clave = os.environ['SMTP_CLAVE']
    if 'gmail.com' in os.environ['SMTP_SERVIDOR']:
        clave = clave.replace(' ', '')  # Google muestra la contraseña de aplicación en grupos de 4
    with servidor:
        servidor.login(os.environ['SMTP_USUARIO'], clave)
        servidor.send_message(mensaje, to_addrs=para + copia)
    return 'smtp'
