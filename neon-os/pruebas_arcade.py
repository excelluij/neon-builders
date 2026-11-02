"""Pruebas de los motores de los juegos clásicos de la Arena: Serpiente y Tetris (sin pantalla).

Ejecutar desde esta carpeta:   python pruebas_arcade.py -v
No abre ventanas ni toca ninguna base de datos.
"""
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pruebas_arena import RngFijo
from serpiente import Serpiente
from tetris import ALTO, ANCHO, PIEZAS, Tetris


class TestSerpiente(unittest.TestCase):
    def nueva(self):
        return Serpiente(20, 20, RngFijo())

    def test_estado_inicial(self):
        s = self.nueva()
        self.assertEqual((s.cuerpo, s.direccion, s.puntaje, s.viva), ([(10, 10), (9, 10), (8, 10)], "der", 0, True))
        self.assertEqual(s.comida, (0, 0))                      # la primera celda libre (RngFijo.choice toma la primera)

    def test_paso_avanza_y_conserva_el_largo(self):
        s = self.nueva()
        s.comida = (0, 0)
        self.assertEqual(s.paso(), "mov")
        self.assertEqual(s.cuerpo, [(11, 10), (10, 10), (9, 10)])

    def test_giros_reversa_y_cola_de_dos(self):
        s = self.nueva()
        s.girar("izq")                                          # reversa respecto de "der": ignorada
        s.paso()
        self.assertEqual(s.cuerpo[0], (11, 10))
        s = self.nueva()
        s.girar("arriba")
        s.girar("izq")
        s.girar("abajo")                                        # el 3.º no cabe en la cola de 2
        s.paso()
        s.paso()
        s.paso()
        self.assertEqual((s.cuerpo[0], s.direccion), ((8, 9), "izq"))

    def test_dos_giros_rapidos_no_dan_un_giro_en_u(self):        # enfoque de revisión 4
        s = self.nueva()
        s.girar("arriba")
        s.girar("abajo")                                        # abajo es opuesta a la última en cola: ignorada
        s.paso()
        s.paso()
        self.assertTrue(s.viva)
        self.assertEqual(s.cuerpo[0], (10, 8))

    def test_direccion_desconocida_se_ignora(self):
        s = self.nueva()
        s.girar("diagonal")
        s.paso()
        self.assertEqual((s.cuerpo[0], s.direccion), ((11, 10), "der"))

    def test_comer_suma_crece_y_pone_comida_libre(self):
        s = self.nueva()
        s.comida = (11, 10)
        self.assertEqual(s.paso(), "comio")
        self.assertEqual((s.puntaje, len(s.cuerpo)), (1, 4))
        self.assertNotIn(s.comida, s.cuerpo)
        self.assertTrue(0 <= s.comida[0] < 20 and 0 <= s.comida[1] < 20)

    def test_choques(self):
        s = self.nueva()
        s.cuerpo = [(19, 5), (18, 5), (17, 5)]
        self.assertEqual(s.paso(), "choque")
        self.assertFalse(s.viva)
        s = self.nueva()
        s.cuerpo = [(5, 5), (4, 5), (4, 6), (5, 6), (6, 6), (6, 5)]
        s.direccion = "abajo"
        self.assertEqual(s.paso(), "choque")                    # (5,6) es parte del cuerpo y no la cola

    def test_avanzar_hacia_la_cola_no_es_choque_si_no_come(self):
        s = self.nueva()
        s.cuerpo = [(5, 5), (5, 6), (6, 6), (6, 5)]
        s.direccion = "der"
        s.comida = (0, 0)
        self.assertEqual(s.paso(), "mov")
        self.assertTrue(s.viva)

    def test_tablero_lleno_termina(self):
        s = Serpiente(2, 2, RngFijo())
        s.cuerpo = [(0, 0), (0, 1), (1, 1)]
        s.direccion = "der"
        s.comida = (1, 0)
        self.assertEqual(s.paso(), "comio")
        self.assertFalse(s.viva)
        self.assertIsNone(s.comida)


class TestTetris(unittest.TestCase):
    def nuevo(self):
        return Tetris(RngFijo())                                  # piezas en orden: I, O, T, S, Z, J, L

    def test_estado_inicial_y_siguiente(self):
        t = self.nuevo()
        self.assertEqual((t.pieza.tipo, t.siguiente, t.lineas, t.terminado), ("I", "O", 0, False))
        self.assertEqual(sorted(t.celdas_pieza()), [(3, 1), (4, 1), (5, 1), (6, 1)])

    def test_mover_respeta_las_paredes(self):                    # enfoque de revisión 3
        t = self.nuevo()
        for _ in range(3):
            self.assertTrue(t.mover(-1))
        self.assertFalse(t.mover(-1))
        self.assertEqual(min(x for x, _ in t.celdas_pieza()), 0)
        for _ in range(6):
            t.mover(1)
        self.assertFalse(t.mover(1))
        self.assertEqual(max(x for x, _ in t.celdas_pieza()), 9)

    def test_rotar_y_patada_contra_la_pared(self):
        t = self.nuevo()
        self.assertTrue(t.rotar())
        self.assertEqual(len({x for x, _ in t.celdas_pieza()}), 1)   # I vertical
        t = self.nuevo()
        t.pieza.rot, t.pieza.x = 1, 7                              # vertical en la última columna
        self.assertTrue(t.rotar())                                 # horizontal: necesita la patada −1
        self.assertEqual((t.pieza.rot, t.pieza.x, max(x for x, _ in t.celdas_pieza())), (2, 6, 9))

    def test_no_rota_si_no_cabe_ni_con_patadas(self):             # enfoque de revisión 3
        t = self.nuevo()
        for y in range(ALTO):
            for x in range(ANCHO):
                if x != 4:
                    t.tablero[y][x] = "X"
        t.pieza.rot, t.pieza.x, t.pieza.y = 1, 2, 0                # I vertical dentro del pozo de la columna 4
        self.assertFalse(t.rotar())
        self.assertEqual(t.pieza.rot, 1)

    def test_bajar_fija_la_pieza_y_trae_la_siguiente(self):
        t = self.nuevo()
        for _ in range(18):
            self.assertTrue(t.bajar())
        self.assertFalse(t.bajar())
        self.assertEqual([t.tablero[19][x] for x in range(3, 7)], ["I"] * 4)
        self.assertEqual((t.pieza.tipo, t.siguiente), ("O", "T"))

    def test_lineas_de_1_y_de_4(self):
        t = self.nuevo()
        for x in range(10):
            if x not in (3, 4, 5, 6):
                t.tablero[19][x] = "X"
        t.caida_instantanea()
        self.assertEqual(t.lineas, 1)
        self.assertTrue(all(c is None for c in t.tablero[19]))
        t = self.nuevo()
        for y in range(16, 20):
            for x in range(9):
                t.tablero[y][x] = "X"
        t.pieza.rot, t.pieza.x, t.pieza.y = 1, 7, 0                # I vertical en la columna 9
        self.assertEqual(t.caida_instantanea(), 16)
        self.assertEqual(t.lineas, 4)
        self.assertTrue(all(c is None for fila in t.tablero for c in fila))

    def test_termina_si_la_pieza_nueva_no_cabe(self):
        t = self.nuevo()
        t.tablero[0][4] = "X"                                      # estorba donde aparece la "O"
        t.caida_instantanea()
        self.assertTrue(t.terminado)

    def test_terminado_no_acepta_mas_movimientos(self):
        t = self.nuevo()
        t.terminado = True
        self.assertEqual((t.mover(1), t.rotar(), t.bajar(), t.caida_instantanea()), (False, False, False, 0))

    def test_la_bolsa_reparte_las_7_piezas_cada_7(self):
        t = Tetris(random.Random(3))
        vistas = []
        for _ in range(14):
            vistas.append(t.pieza.tipo)
            t.caida_instantanea()
            t.tablero = [[None] * ANCHO for _ in range(ALTO)]      # vaciar para no topar con el techo
            t.terminado = False
        self.assertEqual((set(vistas[:7]), set(vistas[7:])), (set(PIEZAS), set(PIEZAS)))

    def test_intervalo_acelera_cada_dos_lineas(self):
        t = self.nuevo()
        for lineas, esperado in ((0, 0.8), (1, 0.8), (2, 0.72), (3, 0.72), (6, 0.56), (20, 0.2), (50, 0.2)):
            t.lineas = lineas
            self.assertAlmostEqual(t.intervalo(), esperado)

    def test_ninguna_celda_sale_del_tablero_con_movimientos_al_azar(self):   # enfoque de revisión 3
        rng = random.Random(7)
        t = Tetris(random.Random(11))
        for _ in range(600):
            if t.terminado:
                t = Tetris(random.Random(rng.randint(0, 99)))
            rng.choice((lambda: t.mover(-1), lambda: t.mover(1), t.rotar, t.bajar, t.rotar))()
            for x, y in t.celdas_pieza():
                self.assertTrue(0 <= x < ANCHO and 0 <= y < ALTO, (x, y))


if __name__ == "__main__":
    unittest.main()
