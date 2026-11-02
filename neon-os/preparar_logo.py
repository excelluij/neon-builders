"""Prepara el logo de Neon OS a partir de logo.png (el archivo original que entrega el diseñador).

    python preparar_logo.py

Genera, junto a este archivo:
  * logo_app.png  el logo recortado, sin el rótulo «LOGOTIPO PRINCIPAL» que trae la imagen original, con fondo transparente (se muestra
                  en la pantalla de acceso);
  * logo.ico      el icono de la ventana, de la barra de tareas y del .exe (varios tamaños, de 16 a 256 píxeles).
Si cambias logo.png, vuelve a ejecutarlo (y a construir el .exe). Necesita pillow (requirements.txt).
"""
import os

from PIL import Image

CARPETA = os.path.dirname(os.path.abspath(__file__))
TAMANOS_ICO = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
UMBRAL_ALFA = 40            # por debajo de esto un píxel cuenta como fondo (transparente)
MARGEN = 0.04               # aire alrededor del dibujo, como fracción del lado mayor


def _filas_con_dibujo(alfa, ancho, alto):
    pix = alfa.load()
    return [y for y in range(alto) if any(pix[x, y] > UMBRAL_ALFA for x in range(ancho))]


def _bloques(filas):
    """[(primera, última)] de tramos de filas consecutivas."""
    bloques, ini, prev = [], None, None
    for y in filas:
        if ini is None:
            ini = y
        elif y != prev + 1:
            bloques.append((ini, prev))
            ini = y
        prev = y
    if ini is not None:
        bloques.append((ini, prev))
    return bloques


def recortar_logo(imagen):
    """Se queda con el dibujo principal (el tramo de filas más alto) y descarta rótulos sueltos como «LOGOTIPO PRINCIPAL»;
    devuelve la imagen RGBA recortada a su contenido, con un margen."""
    rgba = imagen.convert("RGBA")
    ancho, alto = rgba.size
    alfa = rgba.getchannel("A")
    bloques = _bloques(_filas_con_dibujo(alfa, ancho, alto))
    if not bloques:
        return rgba
    arriba, abajo = max(bloques, key=lambda b: b[1] - b[0])
    franja = rgba.crop((0, arriba, ancho, abajo + 1))
    caja = franja.getchannel("A").point(lambda a: 255 if a > UMBRAL_ALFA else 0).getbbox()
    dibujo = franja.crop(caja)
    margen = round(max(dibujo.size) * MARGEN)
    lienzo = Image.new("RGBA", (dibujo.width + 2 * margen, dibujo.height + 2 * margen), (0, 0, 0, 0))
    lienzo.paste(dibujo, (margen, margen))
    return lienzo


def cuadrado(imagen, lado=256):
    """El logo centrado en un lienzo cuadrado transparente (los iconos son cuadrados)."""
    copia = imagen.copy()
    copia.thumbnail((lado, lado), Image.LANCZOS)
    lienzo = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    lienzo.paste(copia, ((lado - copia.width) // 2, (lado - copia.height) // 2))
    return lienzo


def preparar(origen=None, destino=None):
    origen = origen or os.path.join(CARPETA, "logo.png")
    destino = destino or CARPETA
    recortado = recortar_logo(Image.open(origen))
    recortado.save(os.path.join(destino, "logo_app.png"))
    cuadrado(recortado).save(os.path.join(destino, "logo.ico"), format="ICO", sizes=TAMANOS_ICO)
    return recortado.size


if __name__ == "__main__":
    ancho, alto = preparar()
    print(f"Listo: logo_app.png ({ancho}x{alto}) y logo.ico en {CARPETA}")
