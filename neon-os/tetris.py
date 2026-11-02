"""Motor del Tetris de la Arena de Neon OS. Sin pantalla (no usa tkinter).

La ventana está en juegos.py (TetrisGame); aquí solo viven las reglas, para poder probarlas a fondo.
"""
import random

ANCHO, ALTO = 10, 20
PIEZAS = ("I", "O", "T", "S", "Z", "J", "L")
# estado 0 de cada pieza: (lado de la caja, celdas (x, y) dentro de la caja)
FORMAS = {
    "I": (4, [(0, 1), (1, 1), (2, 1), (3, 1)]),
    "O": (2, [(0, 0), (1, 0), (0, 1), (1, 1)]),
    "T": (3, [(1, 0), (0, 1), (1, 1), (2, 1)]),
    "S": (3, [(1, 0), (2, 0), (0, 1), (1, 1)]),
    "Z": (3, [(0, 0), (1, 0), (1, 1), (2, 1)]),
    "J": (3, [(0, 0), (0, 1), (1, 1), (2, 1)]),
    "L": (3, [(2, 0), (0, 1), (1, 1), (2, 1)]),
}
PATADAS = (0, -1, 1, -2, 2)  # desplazamientos en x que se prueban al rotar


def celdas_de(tipo, rot, x, y):
    """Celdas absolutas (x, y) de una pieza con su rotación (giros horarios) y la esquina (x, y) de su caja."""
    lado, celdas = FORMAS[tipo]
    for _ in range(rot % 4):
        celdas = [(lado - 1 - cy, cx) for cx, cy in celdas]     # un giro horario
    return [(x + cx, y + cy) for cx, cy in celdas]


class Pieza:
    def __init__(self, tipo, rot, x, y):
        self.tipo, self.rot, self.x, self.y = tipo, rot, x, y


class Tetris:
    """Tablero de ANCHO × ALTO. `rng` necesita shuffle(lista). El puntaje son las líneas completadas."""

    def __init__(self, rng=None):
        self._rng = rng or random.Random()
        self.tablero = [[None] * ANCHO for _ in range(ALTO)]    # filas × columnas; letra de la pieza fijada o None
        self.lineas = 0
        self.terminado = False
        self._bolsa = []
        self.pieza = self._aparecer(self._de_la_bolsa())
        self.siguiente = self._de_la_bolsa()

    # -- piezas -------------------------------------------------------------------------
    def _de_la_bolsa(self):
        """Bolsa de 7: cada 7 piezas salen las 7, en orden aleatorio."""
        if not self._bolsa:
            self._bolsa = list(PIEZAS)
            self._rng.shuffle(self._bolsa)
        return self._bolsa.pop(0)

    def _aparecer(self, tipo):
        pieza = Pieza(tipo, 0, (ANCHO - FORMAS[tipo][0]) // 2, 0)
        if self._choca(pieza.tipo, pieza.rot, pieza.x, pieza.y):
            self.terminado = True
        return pieza

    def _choca(self, tipo, rot, x, y):
        """Verdadero si alguna celda queda fuera del tablero (paredes, suelo o techo) o sobre una celda ocupada."""
        for cx, cy in celdas_de(tipo, rot, x, y):
            if not (0 <= cx < ANCHO and 0 <= cy < ALTO) or self.tablero[cy][cx] is not None:
                return True
        return False

    def celdas_pieza(self):
        p = self.pieza
        return celdas_de(p.tipo, p.rot, p.x, p.y)

    # -- movimientos --------------------------------------------------------------------
    def mover(self, dx):
        p = self.pieza
        if self.terminado or self._choca(p.tipo, p.rot, p.x + dx, p.y):
            return False
        p.x += dx
        return True

    def rotar(self):
        """Giro horario; si choca prueba las patadas laterales de PATADAS. Devuelve False si no cabe."""
        p = self.pieza
        if self.terminado:
            return False
        rot = (p.rot + 1) % 4
        for dx in PATADAS:
            if not self._choca(p.tipo, rot, p.x + dx, p.y):
                p.rot, p.x = rot, p.x + dx
                return True
        return False

    def bajar(self):
        """Baja una fila. Si no puede, fija la pieza, borra líneas, trae la siguiente y devuelve False."""
        p = self.pieza
        if self.terminado:
            return False
        if not self._choca(p.tipo, p.rot, p.x, p.y + 1):
            p.y += 1
            return True
        self._fijar()
        return False

    def caida_instantanea(self):
        """Baja hasta el fondo y fija la pieza. Devuelve cuántas filas bajó."""
        p = self.pieza
        if self.terminado:
            return 0
        filas = 0
        while not self._choca(p.tipo, p.rot, p.x, p.y + 1):
            p.y += 1
            filas += 1
        self._fijar()
        return filas

    def _fijar(self):
        for x, y in self.celdas_pieza():
            self.tablero[y][x] = self.pieza.tipo
        quedan = [fila for fila in self.tablero if any(c is None for c in fila)]
        borradas = ALTO - len(quedan)
        self.tablero = [[None] * ANCHO for _ in range(borradas)] + quedan
        self.lineas += borradas
        self.pieza = self._aparecer(self.siguiente)
        self.siguiente = self._de_la_bolsa()

    def intervalo(self):
        """Segundos por fila de la gravedad: acelera cada 2 líneas, con piso de 0,2 s."""
        return max(0.2, 0.8 - 0.08 * (self.lineas // 2))
