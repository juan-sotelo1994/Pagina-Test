"""Crea un superadministrador en la base de datos (para la primera vez o si se pierde el acceso).

Uso (desde la carpeta del proyecto):
    .venv\\Scripts\\python.exe db\\crear_superadmin.py

Pide nombres, apellidos, correo y la contraseña (que no se ve al escribirla).
Si el correo ya existe, le cambia la contraseña y lo deja como superadministrador activo.
"""
import getpass
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / 'app'))

from dotenv import load_dotenv  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

load_dotenv(RAIZ / '.env')
from nucleo import db  # noqa: E402
from auth import usuarios  # noqa: E402


def main():
    correo = input('Correo: ').strip().lower()
    if not usuarios.PATRON_CORREO.match(correo):
        sys.exit('Correo no válido.')
    existente = usuarios.buscar(correo)
    nombres = existente['nombres'] if existente else input('Nombres: ').strip()
    apellidos = existente['apellidos'] if existente else input('Apellidos: ').strip()
    clave = getpass.getpass(f'Contraseña (mínimo {usuarios.LARGO_MINIMO} caracteres): ')
    errores = usuarios.validar_contrasena(clave, getpass.getpass('Repite la contraseña: '))
    if errores:
        sys.exit(next(iter(errores.values())))
    with db.conectar() as cx:
        cx.execute("""
            INSERT INTO usuarios (nombres, apellidos, correo, rol, hash) VALUES (%s, %s, %s, 'superadmin', %s)
            ON CONFLICT (correo) DO UPDATE SET rol = 'superadmin', activo = true, hash = EXCLUDED.hash
        """, (nombres, apellidos, correo, generate_password_hash(clave)))
    print(f"{'Actualizado' if existente else 'Creado'}: {correo} es superadministrador.")


if __name__ == '__main__':
    main()
