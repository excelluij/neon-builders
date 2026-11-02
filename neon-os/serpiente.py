"""Motor de la Serpiente de la Arena de Neon OS. Sin pantalla (no usa tkinter).

La ventana está en juegos.py (SerpienteGame); aquí solo viven las reglas, para poder probarlas a fondo.
"""
import random

DELTAS = {"arriba": (0, -1), "abajo": (0, 1), "izq": (-1, 0), "der": (1, 0)}
OPUESTA = {"arriba": "abajo", "abajo": "arriba", "izq": "der", "der": "izq"}
MAX_GIROS = 2  # giros pendientes que se recuerdan entre paso y paso


class Serpiente:
    """Cuadrícula de ancho × alto con una serpiente de 3 segmentos avanzando a la derecha. `rng` necesita choice(seq)."""

    def __init__(self, ancho=20, alto=20, rng=None):
        self.ancho, self.alto = ancho, alto
        self._rng = rng or random.Random()
        cx, cy = ancho // 2, alto // 2
        self.cuerpo = [(cx, cy), (cx - 1, cy), (cx - 2, cy)]    # la cabeza va primero
        self.direccion = "der"
        self.puntaje = 0                                          # frutas comidas
        self.viva = True
        self._cola = []                                           # giros pedidos y aún no aplicados
        self.comida = self._nueva_comida()

    def _nueva_comida(self):
        ocupadas = set(self.cuerpo)
        libres = [(x, y) for y in range(self.alto) for x in range(self.ancho) if (x, y) not in ocupadas]
        return self._rng.choice(libres) if libres else None

    def girar(self, direccion):
        """Pide un giro. Ignora direcciones desconocidas, la misma y la opuesta a la última pedida (o a la actual
        si no hay ninguna): así dos pulsaciones rápidas nunca hacen un giro en U sobre sí misma."""
        if direccion not in DELTAS or len(self._cola) >= MAX_GIROS:
            return
        ultima = self._cola[-1] if self._cola else self.direccion
        if direccion == ultima or direccion == OPUESTA[ultima]:
            return
        self._cola.append(direccion)

    def paso(self):
        """Avanza una celda. Devuelve "mov", "comio" o "choque" (pared o cuerpo)."""
        if not self.viva:
            return "choque"
        if self._cola:
            self.direccion = self._cola.pop(0)
        dx, dy = DELTAS[self.direccion]
        nueva = (self.cuerpo[0][0] + dx, self.cuerpo[0][1] + dy)
        come = nueva == self.comida
        # al comer la cola no se mueve (cuenta como ocupada); si no come, la cola libera su celda
        ocupadas = self.cuerpo if come else self.cuerpo[:-1]
        if not (0 <= nueva[0] < self.ancho and 0 <= nueva[1] < self.alto) or nueva in ocupadas:
            self.viva = False
            return "choque"
        self.cuerpo.insert(0, nueva)
        if come:
            self.puntaje += 1
            self.comida = self._nueva_comida()
            if self.comida is None:                               # el tablero se llenó
                self.viva = False
            return "comio"
        self.cuerpo.pop()
        return "mov"
