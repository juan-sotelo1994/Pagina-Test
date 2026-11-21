"""Envía un correo de prueba con la configuración SMTP del archivo .env.

Uso (desde la carpeta del proyecto):
    .venv\\Scripts\\python.exe db\\probar_correo.py destino@correo.com
"""
import smtplib
import socket
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / 'app'))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(RAIZ / '.env')
from nucleo import correo  # noqa: E402


def main():
    if len(sys.argv) < 2:
        sys.exit('Escribe a qué correo enviar la prueba:  db\\probar_correo.py destino@correo.com')
    if not correo.configurado():
        sys.exit('Falta SMTP_SERVIDOR, SMTP_USUARIO o SMTP_CLAVE en el archivo .env.')
    destino = sys.argv[1]
    try:
        correo.enviar(destino, 'Prueba del panel de Test-Lab',
                      'Si lees esto, el panel ya puede enviar los códigos para recuperar la contraseña.',
                      '<p>Si lees esto, el panel ya puede enviar los códigos para <b>recuperar la contraseña</b>.</p>')
    except smtplib.SMTPAuthenticationError:
        sys.exit('Gmail rechazó el usuario o la clave. Revisa que SMTP_CLAVE sea la contraseña de aplicación '
                 '(16 letras, sin espacios) y que la verificación en 2 pasos esté activa.')
    except (smtplib.SMTPException, socket.error) as error:
        sys.exit(f'No se pudo enviar: {error}')
    print(f'Enviado a {destino}. Revisa la bandeja de entrada (y la de spam).')


if __name__ == '__main__':
    main()
