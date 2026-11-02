"""Pruebas de las reglas puras de la Arena (arena.py): duelo, premios, banco de preguntas.

Ejecutar desde esta carpeta:   python pruebas_arena.py -v
No abre ventanas ni toca ninguna base de datos.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import arena
from arena import Duelo

PREGS = [(f"P{i}", "ok", ["a", "b", "c"], f"expl {i}") for i in range(12)]


class RngFijo:
    """Generador aleatorio de prueba: devuelve en orden los valores dados; sample() toma las primeras k."""

    def __init__(self, randoms=(), uniforms=()):
        self._r, self._u = list(randoms), list(uniforms)

    def random(self):
        return self._r.pop(0)

    def uniform(self, a, b):
        return self._u.pop(0)

    def sample(self, seq, k):
        return list(seq)[:k]

    def choice(self, seq):
        return list(seq)[0]

    def shuffle(self, lista):
        pass                       # el orden no cambia: las piezas salen I, O, T, S, Z, J, L


class TestArena(unittest.TestCase):
    def test_constantes_y_premios_de_la_especificacion(self):
        self.assertEqual((arena.PV_INICIAL, arena.DANO, arena.BONO_RAPIDEZ, arena.UMBRAL_RAPIDO), (100, 20, 5, 4.0))
        self.assertEqual((arena.TIEMPO_RONDA, arena.TIEMPO_DUELO, arena.RONDAS_MAX, arena.MIN_PREGUNTAS), (10, 120, 12, 4))
        self.assertEqual((arena.ACIERTO_ROBOT, arena.ROBOT_MIN_T, arena.ROBOT_MAX_T), (0.6, 3.0, 8.0))
        self.assertEqual(arena.PREMIOS, {"victoria": 10, "empate": 5, "derrota": 2, "abandono": 0})
        self.assertEqual([arena.premio(r) for r in ("victoria", "empate", "derrota", "abandono")], [10, 5, 2, 0])

    def test_tabla_de_resolucion(self):
        casos = [  # (acierta jugador, t jugador, (acierta robot, t robot), (quién golpea, daño))
            (True, 6.0, (False, 5.0), ("jugador", 20)), (True, 2.0, (False, 5.0), ("jugador", 25)),
            (True, 4.0, (False, 5.0), ("jugador", 20)), (True, 5.0, (True, 5.0), ("jugador", 20)),
            (True, 6.0, (True, 5.0), ("robot", 20)), (True, 3.0, (True, 5.0), ("jugador", 25)),
            (False, 7.0, (True, 5.0), ("robot", 20)), (False, 10.0, (True, 3.0), ("robot", 20)),
            (False, 7.0, (False, 5.0), (None, 0)), (False, 10.0, (False, 5.0), (None, 0))]
        for c, t, r, esperado in casos:
            with self.subTest(c=c, t=t, r=r):
                d = Duelo(PREGS)
                d.siguiente_pregunta()
                self.assertEqual(d.resolver(c, t, r), esperado)
                self.assertEqual((d.pv_jugador, d.pv_robot),
                                 (100 - (esperado[1] if esperado[0] == "robot" else 0), 100 - (esperado[1] if esperado[0] == "jugador" else 0)))

    def test_pv_no_bajan_de_cero_y_fin_por_pv(self):
        d = Duelo(PREGS)
        for _ in range(4):
            d.siguiente_pregunta()
            d.resolver(True, 1.0, (False, 5.0))   # 4 golpes rápidos = 100 PV
        self.assertEqual((d.pv_robot, d.terminado, d.resultado()), (0, True, "victoria"))
        d = Duelo(PREGS)                           # 3 rápidos (75) + 2 normales (40) = 115: se queda en 0
        for t in (1.0, 1.0, 1.0, 6.0, 6.0):
            d.siguiente_pregunta()
            d.resolver(True, t, (False, 5.0))
        self.assertEqual(d.pv_robot, 0)
        d = Duelo(PREGS)
        for _ in range(5):
            d.siguiente_pregunta()
            d.resolver(False, 10.0, (True, 3.0))
        self.assertEqual((d.pv_jugador, d.terminado, d.resultado()), (0, True, "derrota"))

    def test_fin_por_reloj_con_empate_y_con_ventaja(self):
        d = Duelo(PREGS)
        d.siguiente_pregunta()
        d.gastar_tiempo(999)
        self.assertEqual((d.tiempo_restante, d.terminado, d.resultado()), (0, True, "empate"))
        d = Duelo(PREGS)
        d.siguiente_pregunta()
        d.resolver(True, 6.0, (False, 5.0))
        d.siguiente_pregunta()
        d.gastar_tiempo(120)
        self.assertEqual(d.resultado(), "victoria")

    def test_fin_sin_preguntas(self):
        d = Duelo(PREGS[:4], RngFijo())
        for n in range(4):
            self.assertFalse(d.terminado)
            self.assertEqual(d.siguiente_pregunta(), PREGS[n])
            d.resolver(False, 7.0, (False, 5.0))
        self.assertTrue(d.terminado)
        self.assertIsNone(d.siguiente_pregunta())

    def test_limite_de_rondas_y_sin_repetir(self):
        d = Duelo([(f"Q{i}", "ok", ["a", "b", "c"]) for i in range(40)])
        vistas = []
        while (q := d.siguiente_pregunta()) is not None:
            vistas.append(q[0])
            d.resolver(False, 7.0, (False, 5.0))
        self.assertEqual((len(vistas), len(set(vistas))), (12, 12))

    def test_jugada_del_robot(self):
        d = Duelo(PREGS, RngFijo(randoms=[0.59, 0.6], uniforms=[3.0, 8.0]))
        self.assertEqual((d.jugada_robot(), d.jugada_robot()), ((True, 3.0), (False, 8.0)))
        d = Duelo(PREGS)
        self.assertTrue(all(3.0 <= d.jugada_robot()[1] <= 8.0 for _ in range(300)))

    def test_armar_pool(self):
        bancos = {"11": {"Física": {"T1": {"preguntas": ["a", "b"]}, "T2": {"preguntas": ["c"]}}, "Química": {"T": {"preguntas": ["d"]}}},
                  "10": {"Física": {"T": {"preguntas": ["z"]}}}}
        self.assertEqual(sorted(arena.armar_pool(bancos, "11")), ["a", "b", "c", "d"])
        self.assertEqual(sorted(arena.armar_pool(bancos, "11", "Física")), ["a", "b", "c"])
        self.assertEqual((arena.armar_pool(bancos, "9"), arena.armar_pool(bancos, "11", "Inglés")), ([], []))

    def test_el_banco_real_alcanza_para_duelos(self):
        from banco_grado11 import BANCOS
        for materia in BANCOS["11"]:
            self.assertGreaterEqual(len(arena.armar_pool(BANCOS, "11", materia)), arena.MIN_PREGUNTAS)
        self.assertGreaterEqual(len(arena.armar_pool(BANCOS, "11")), 200)

    def test_premio_arcade_por_umbrales(self):
        self.assertEqual(arena.ARCADE_TIEMPO, 120)
        casos = [("serpiente", 0, 1), ("serpiente", 5, 1), ("serpiente", 6, 2), ("serpiente", 11, 2), ("serpiente", 12, 3), ("serpiente", 40, 3),
                 ("tetris", 0, 1), ("tetris", 3, 1), ("tetris", 4, 2), ("tetris", 7, 2), ("tetris", 8, 3), ("tetris", 25, 3)]
        for juego, puntaje, esperado in casos:
            with self.subTest(juego=juego, puntaje=puntaje):
                self.assertEqual(arena.premio_arcade(juego, puntaje), esperado)
        with self.assertRaises(KeyError):
            arena.premio_arcade("ajedrez", 3)

    def test_corazones_texto(self):
        self.assertEqual(arena.corazones_texto(3), "❤️❤️❤️🤍🤍 3/5")
        self.assertEqual((arena.corazones_texto(0), arena.corazones_texto(5)), ("🤍🤍🤍🤍🤍 0/5", "❤️❤️❤️❤️❤️ 5/5"))


if __name__ == "__main__":
    unittest.main()
