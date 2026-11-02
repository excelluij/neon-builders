"""Carpeta donde viven los archivos de la app (neon_os.db, .env, materiales_neon).

Con el código normal es la carpeta de este archivo; empaquetada con PyInstaller (.exe) es la carpeta del .exe,
para que los datos queden junto al programa y no dentro de su carpeta interna."""
import os
import sys


def carpeta_app():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def recurso(nombre):
    """Ruta de un archivo que viaja con el programa (el logo): dentro del paquete del .exe (PyInstaller lo deja en sys._MEIPASS)
    o junto al código. A diferencia de carpeta_app(), no es una carpeta de datos del usuario."""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, nombre)


def poner_icono(ventana):
    """Pone el logo de Neon OS (logo.ico) como icono de la ventana y de la barra de tareas. Solo en Windows; si falta el archivo o
    el sistema no lo acepta, la ventana sigue con el icono por defecto y no pasa nada."""
    ruta = recurso("logo.ico")
    if sys.platform.startswith("win") and os.path.exists(ruta):
        try:
            ventana.iconbitmap(ruta)
        except Exception:  # noqa: BLE001 - un icono no justifica romper una ventana
            pass
