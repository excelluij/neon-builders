"""Lector sencillo de un archivo .env para Neon OS (sin dependencias).

El archivo se llama exactamente `.env` y va junto a la app (en la misma carpeta que APP_final.py y correo.py). Sirve para
poner ahí las variables NEON_* (claves de Brevo, clave del administrador...) en vez de definirlas en Windows. Reglas:

  * Una variable por línea:  NOMBRE=valor   (opcionalmente con «export » delante). Las líneas que empiezan por # son comentarios;
    NO hay comentarios al final de una línea, así que un valor puede llevar # o = sin problema.
  * Un valor entre comillas simples o dobles pierde las comillas (sirve para conservar espacios al principio o al final).
  * Solo se leen nombres que empiezan por NEON_ (mayúsculas, números y _): cualquier otro nombre del archivo se ignora, para que
    un .env nunca pueda cambiar PATH, PYTHONPATH u otras variables del sistema.
  * Lo que ya esté definido en las variables de entorno de Windows tiene prioridad: el .env solo rellena lo que falta.
  * Un valor vacío cuenta como no definido. Si una variable se repite, gana la última línea.
  * Nunca se muestra ningún valor: los avisos hablan de nombres y de números de línea.

Se carga solo al ARRANCAR como programa (APP_final.py, correo.py, almacen.py, app_movil.py), nunca al importar los módulos:
así las pruebas automáticas no leen el .env real. Ver docs/CORREO.md.
"""
import os
import re
import sys

import rutas

RUTA_POR_DEFECTO = os.path.join(rutas.carpeta_app(), ".env")
_LINEA = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_.-]*)\s*=(.*)$")
_NOMBRE_PROPIO = re.compile(r"NEON_[A-Z0-9_]+")


def parsear(texto):
    """(pares, invalidas): `pares` = [(nombre, valor, número_de_línea)]; `invalidas` = números de las líneas mal formadas.
    No filtra nombres (eso lo hace cargar_env)."""
    pares, invalidas = [], []
    if texto.startswith("﻿"):
        texto = texto[1:]
    for n, linea in enumerate(re.split(r"\r\n|\n|\r", texto), 1):
        if not linea.strip() or linea.lstrip().startswith("#"):
            continue
        m = _LINEA.match(linea)
        if not m:
            invalidas.append(n)
            continue
        valor = m.group(2).strip()
        if valor[:1] in ("'", '"'):
            if len(valor) >= 2 and valor[-1] == valor[0]:
                valor = valor[1:-1]
            else:                                         # comilla sin cerrar: mejor avisar que cargar un valor a medias
                invalidas.append(n)
                continue
        pares.append((m.group(1), valor, n))
    return pares, invalidas


def _advertencias(r):
    """Avisos sobre el archivo (solo nombres y números de línea; jamás valores)."""
    avisos = []
    if not r["existe"]:
        if r["aviso_txt"]:
            avisos.append("⚠️ Encontré .env.txt pero no .env: el archivo debe llamarse exactamente .env (Windows puede ocultar la extensión .txt).")
        return avisos
    if r["error"]:
        avisos.append(f"⚠️ No se pudo leer el archivo .env ({r['error']}); se ignora.")
        return avisos
    if r["invalidas"]:
        numeros = ", ".join(str(n) for n in r["invalidas"])
        avisos.append(f"⚠️ .env: la línea {numeros} no tiene el formato NOMBRE=valor (se ignora)." if len(r["invalidas"]) == 1 else
                      f"⚠️ .env: las líneas {numeros} no tienen el formato NOMBRE=valor (se ignoran).")
    if r["ignoradas"]:
        avisos.append("⚠️ .env: se ignoran las variables que no empiezan por NEON_ (solo se leen esas): " + ", ".join(sorted(r["ignoradas"])) + ".")
    return avisos


def describir(r):
    """Líneas para mostrar al usuario en las herramientas de consola (nombres y números, nunca valores). [] si no hay .env."""
    if not r["existe"] or r["error"]:
        return _advertencias(r)
    lineas = [f"Leído .env junto a la app: {len(r['cargadas'])} variable(s) cargada(s)"
              + (": " + ", ".join(sorted(r["cargadas"])) if r["cargadas"] else "") + "."]
    if r["ya_definidas"]:
        lineas.append("  Ya estaban definidas en el sistema y tienen prioridad (no se cambian): " + ", ".join(sorted(r["ya_definidas"])) + ".")
    if r["vacias"]:
        lineas.append("  Sin valor en el .env (se ignoran): " + ", ".join(sorted(r["vacias"])) + ".")
    return lineas + _advertencias(r)


def cargar_env(ruta=None, entorno=None, avisar=True):
    """Lee el .env y vuelca en `entorno` (por defecto os.environ) las variables NEON_* que falten. Nunca lanza una excepción
    por culpa del archivo. Devuelve un resumen con SOLO nombres: ruta, existe, cargadas, ya_definidas, vacias, ignoradas,
    invalidas (números de línea), error y aviso_txt. Con avisar=True escribe los avisos en stderr."""
    ruta = ruta or RUTA_POR_DEFECTO
    entorno = os.environ if entorno is None else entorno
    r = {"ruta": ruta, "existe": False, "cargadas": [], "ya_definidas": [], "vacias": [], "ignoradas": [],
         "invalidas": [], "error": None, "aviso_txt": False}
    if not os.path.exists(ruta):
        r["aviso_txt"] = os.path.isfile(ruta + ".txt")
    else:
        r["existe"] = True
        try:
            with open(ruta, "rb") as f:
                texto = f.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            r["error"] = "no está codificado en UTF-8: guárdalo como UTF-8"
        except OSError:
            r["error"] = "no se pudo abrir: permisos, o no es un archivo"
        else:
            pares, r["invalidas"] = parsear(texto)
            ultimos = {nombre: valor for nombre, valor, _ in pares}                 # la última línea de cada variable gana
            for nombre, valor in ultimos.items():
                if not _NOMBRE_PROPIO.fullmatch(nombre):
                    r["ignoradas"].append(nombre)
                elif not valor:
                    r["vacias"].append(nombre)
                elif str(entorno.get(nombre, "")).strip():
                    r["ya_definidas"].append(nombre)
                else:
                    entorno[nombre] = valor
                    r["cargadas"].append(nombre)
    if avisar:
        for aviso in _advertencias(r):
            print(f"[Neon OS] {aviso}", file=sys.stderr)
    return r
