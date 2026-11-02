"""Reglas de la Arena de Neon OS: el duelo de preguntas y sus premios. Sin pantalla (no usa tkinter).

La ventana del duelo está en juegos.py (DueloGame) y la pestaña en APP_final.py (ViewArena);
aquí solo viven las reglas, para poder probarlas a fondo. Los números se ajustan en las constantes.
"""
import random

PV_INICIAL = 100        # puntos de vida de cada lado
DANO = 20               # daño de un golpe
BONO_RAPIDEZ = 5        # daño extra si el jugador responde en menos de UMBRAL_RAPIDO segundos
UMBRAL_RAPIDO = 4.0
TIEMPO_RONDA = 10       # segundos para responder cada pregunta
TIEMPO_DUELO = 120      # segundos de tiempo activo (solo corre con una pregunta abierta)
RONDAS_MAX = 12         # preguntas por duelo, como máximo
MIN_PREGUNTAS = 4       # con menos preguntas no se puede armar un duelo
ACIERTO_ROBOT = 0.6     # probabilidad de que el robot acierte cada ronda
ROBOT_MIN_T = 3.0       # el robot responde entre estos dos tiempos (segundos)
ROBOT_MAX_T = 8.0
PREMIOS = {"victoria": 10, "empate": 5, "derrota": 2, "abandono": 0}  # monedas


# Juegos clásicos puros (serpiente y Tetris): partida corta, premio menor que el duelo.
ARCADE_TIEMPO = 120                                          # segundos de reloj corrido
ARCADE_UMBRALES = {"serpiente": (6, 12), "tetris": (4, 8)}   # puntaje (frutas / líneas) para ganar 2 y 3 monedas


def premio_arcade(juego, puntaje):
    """1 moneda por terminar la partida, más 1 por cada umbral alcanzado (2 y 3 monedas en total)."""
    return 1 + sum(puntaje >= umbral for umbral in ARCADE_UMBRALES[juego])


def armar_pool(bancos, grado, materia=None):
    """Preguntas de opción múltiple del grado: de una materia, o de todas si materia es None."""
    materias = bancos.get(grado, {})
    if materia is not None:
        materias = {materia: materias[materia]} if materia in materias else {}
    return [p for temas in materias.values() for banco in temas.values() for p in banco.get("preguntas", [])]


def premio(resultado):
    return PREMIOS[resultado]


def corazones_texto(n, maximo=5):
    n = max(0, min(n, maximo))
    return "❤️" * n + "🤍" * (maximo - n) + f" {n}/{maximo}"


class Duelo:
    """Estado de un duelo entre el jugador y el robot. `rng` necesita random(), uniform(a, b) y sample(seq, k)."""

    def __init__(self, preguntas, rng=None):
        self._rng = rng or random.Random()
        preguntas = list(preguntas)
        self.preguntas = self._rng.sample(preguntas, min(RONDAS_MAX, len(preguntas)))
        self.pv_jugador = self.pv_robot = PV_INICIAL
        self.tiempo_restante = float(TIEMPO_DUELO)
        self.ronda = 0            # preguntas ya entregadas
        self._abierta = False     # hay una pregunta entregada y sin resolver

    @property
    def terminado(self):
        return (self.pv_jugador <= 0 or self.pv_robot <= 0 or self.tiempo_restante <= 0
                or (not self._abierta and self.ronda >= len(self.preguntas)))

    def siguiente_pregunta(self):
        if self.terminado or self.ronda >= len(self.preguntas):
            return None
        pregunta = self.preguntas[self.ronda]
        self.ronda += 1
        self._abierta = True
        return pregunta

    def jugada_robot(self):
        """(acierta, segundos que tarda): se sortea al empezar la ronda y el jugador no lo ve."""
        return self._rng.random() < ACIERTO_ROBOT, self._rng.uniform(ROBOT_MIN_T, ROBOT_MAX_T)

    def resolver(self, correcta, tiempo, robot):
        """Aplica el golpe de la ronda. Devuelve (quién golpea, daño): ("jugador"|"robot"|None, int)."""
        robot_acierta, robot_tiempo = robot
        self._abierta = False
        if correcta and (not robot_acierta or tiempo <= robot_tiempo):
            dano = DANO + (BONO_RAPIDEZ if tiempo < UMBRAL_RAPIDO else 0)
            self.pv_robot = max(0, self.pv_robot - dano)
            return "jugador", dano
        if robot_acierta:
            self.pv_jugador = max(0, self.pv_jugador - DANO)
            return "robot", DANO
        return None, 0

    def gastar_tiempo(self, segundos):
        self.tiempo_restante = max(0.0, self.tiempo_restante - segundos)

    def resultado(self):
        if self.pv_jugador > self.pv_robot:
            return "victoria"
        if self.pv_jugador < self.pv_robot:
            return "derrota"
        return "empate"
