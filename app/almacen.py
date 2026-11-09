"""Lectura y escritura de los archivos JSON en app/data/.

Es el almacenamiento temporal hasta conectar la base de datos.
"""
import json
import os
from pathlib import Path

CARPETA = Path(__file__).resolve().parent / 'data'


def leer(nombre, por_defecto):
    archivo = CARPETA / nombre
    if not archivo.exists():
        return por_defecto
    return json.loads(archivo.read_text(encoding='utf-8'))


def escribir(nombre, datos):
    # Escribe en un archivo temporal y luego lo reemplaza: si algo falla
    # a mitad de camino, el archivo anterior queda intacto
    CARPETA.mkdir(parents=True, exist_ok=True)
    archivo = CARPETA / nombre
    temporal = archivo.with_suffix('.tmp')
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporal, archivo)
