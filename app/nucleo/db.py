"""Conexión a PostgreSQL (DATABASE_URL en el archivo .env).

Uso:
    with db.conectar() as cx:
        fila = cx.execute('SELECT ... WHERE id = %s', (id,)).fetchone()   # dict
Al salir del with se confirma (commit) o, si hubo un error, se deshace todo.
"""
import os

import psycopg
from psycopg.rows import dict_row

Error = psycopg.Error


def conectar():
    url = os.environ.get('DATABASE_URL')
    if not url:
        raise RuntimeError('Falta DATABASE_URL en el archivo .env.')
    return psycopg.connect(url, row_factory=dict_row, connect_timeout=5)
