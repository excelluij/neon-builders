"""Pruebas de la retroalimentación de los juegos: explicación al fallar, felicitación al acertar.

Ejecutar desde esta carpeta:   python pruebas_feedback.py -v
Necesita customtkinter: los juegos se abren de verdad en ventanas por unos segundos.
"""
import copy
import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import customtkinter as ctk

import ia_local
import juegos
from banco_grado11 import BANCOS

LARGO_MIN = 15  # una explicación real tiene al menos una frase corta

# Banco de prueba con explicaciones (formato nuevo) y su versión sin ellas (misiones ya publicadas).
BANCO = {
    "preguntas": [
        ("2 + 2 =", "4", ["3", "5", "6"], "Sumar dos y dos da cuatro."),
        ("3 + 3 =", "6", ["5", "7", "9"], "Tres más tres es seis."),
        ("5 + 3 =", "8", ["7", "9", "6"], "Cinco más tres es ocho."),
        ("7 + 1 =", "8", ["7", "9", "6"], "Siete más uno es ocho."),
    ],
    "vf": [
        ("El Sol es una estrella", True, "El Sol es la estrella más cercana a la Tierra."),
        ("Marte es el planeta rojo", True, "Marte se ve rojizo por el óxido de hierro."),
        ("La Tierra gira alrededor del Sol", True, "La Tierra orbita al Sol una vez al año."),
        ("La Luna es un planeta", False, "La Luna es un satélite natural de la Tierra."),
        ("Venus es el planeta más frío", False, "Venus es el más caliente por su efecto invernadero."),
        ("Júpiter es un planeta sólido", False, "Júpiter es un gigante gaseoso."),
    ],
    "parejas": [
        ("Sol", "Estrella central"), ("Luna", "Satélite natural"), ("Marte", "Planeta rojo"),
        ("Venus", "Planeta más caliente"), ("Tierra", "Nuestro planeta"),
    ],
    "palabras": [("SOL", "Estrella central"), ("LUNA", "Satélite natural"), ("MARTE", "Planeta rojo")],
    "secuencias": [
        ("Hacer té", ["Hervir agua", "Poner la bolsita", "Verter el agua", "Esperar"]),
        ("Lavarse las manos", ["Mojar", "Echar jabón", "Frotar", "Enjuagar"]),
        ("Plantar una semilla", ["Cavar", "Sembrar", "Tapar", "Regar"]),
    ],
}
BANCO_VIEJO = copy.deepcopy(BANCO)
BANCO_VIEJO["preguntas"] = [q[:3] for q in BANCO["preguntas"]]
BANCO_VIEJO["vf"] = [v[:2] for v in BANCO["vf"]]


# ==============================================================================
# LÓGICA PURA
# ==============================================================================
class TestTextosYEmpaque(unittest.TestCase):
    def test_felicitacion_sin_racha_larga(self):
        for _ in range(40):
            for racha in (1, 2):
                self.assertNotIn("seguidas", juegos.felicitacion(racha))

    def test_felicitacion_con_racha(self):
        self.assertIn("3 seguidas", juegos.felicitacion(3))
        self.assertIn("7 seguidas", juegos.felicitacion(7))

    def test_felicitaciones_no_se_repiten_seguidas(self):
        previa = juegos.felicitacion(1)
        for _ in range(60):
            actual = juegos.felicitacion(1)
            self.assertNotEqual(actual, previa)
            previa = actual

    def test_animo_no_vacio(self):
        for _ in range(10):
            self.assertTrue(juegos.animo().strip())

    def test_desempacar_pregunta(self):
        self.assertEqual(juegos.desempacar_pregunta(("p", "ok", ["a", "b", "c"])), ("p", "ok", ["a", "b", "c"], ""))
        self.assertEqual(juegos.desempacar_pregunta(["p", "ok", ["a", "b", "c"], "porque sí"]), ("p", "ok", ["a", "b", "c"], "porque sí"))

    def test_desempacar_vf(self):
        self.assertEqual(juegos.desempacar_vf(("x", True)), ("x", True, ""))
        self.assertEqual(juegos.desempacar_vf(["x", False, "porque no"]), ("x", False, "porque no"))


class TestBancoGrado11(unittest.TestCase):
    def test_cada_pregunta_y_afirmacion_tiene_explicacion(self):
        faltan = []
        for grado, materias in BANCOS.items():
            for materia, temas in materias.items():
                for tema, b in temas.items():
                    for q in b["preguntas"]:
                        if len(q) != 4 or not isinstance(q[3], str) or len(q[3].strip()) < LARGO_MIN:
                            faltan.append(f"{materia}/{tema}: {q[0]}")
                    for v in b["vf"]:
                        if len(v) != 3 or not isinstance(v[2], str) or len(v[2].strip()) < LARGO_MIN:
                            faltan.append(f"{materia}/{tema}: {v[0]}")
        self.assertEqual(faltan, [], f"{len(faltan)} sin explicación, p. ej. {faltan[:3]}")

    def test_no_hay_explicaciones_repetidas_en_un_tema(self):
        for materia, temas in BANCOS["11"].items():
            for tema, b in temas.items():
                expl = [q[3] for q in b["preguntas"] if len(q) > 3] + [v[2] for v in b["vf"] if len(v) > 2]
                self.assertEqual(len(expl), len(set(expl)), f"explicaciones repetidas en {materia}/{tema}")

    def test_todos_los_bancos_siguen_siendo_validos(self):
        for materia, temas in BANCOS["11"].items():
            for tema, b in temas.items():
                self.assertEqual(ia_local.validar_banco(b), [], f"{materia}/{tema}")


class TestIaLocal(unittest.TestCase):
    def test_validar_acepta_formato_viejo_y_nuevo(self):
        self.assertEqual(ia_local.validar_banco(BANCO), [])
        self.assertEqual(ia_local.validar_banco(BANCO_VIEJO), [])

    def test_validar_rechaza_explicacion_que_no_es_texto(self):
        malo = copy.deepcopy(BANCO)
        malo["preguntas"][0] = ("2 + 2 =", "4", ["3", "5", "6"], 5)
        self.assertTrue(ia_local.validar_banco(malo))
        malo = copy.deepcopy(BANCO)
        malo["vf"][0] = ("El Sol es una estrella", True, ["no", "texto"])
        self.assertTrue(ia_local.validar_banco(malo))

    def test_agregar_pregunta_con_y_sin_explicacion(self):
        op = {"op": "agregar_pregunta", "pregunta": "¿1 + 1?", "correcta": "2", "incorrectas": ["3", "4", "5"]}
        nuevo, inf = ia_local.aplicar_operaciones(BANCO, [dict(op, explicacion="Uno más uno es dos.")])
        self.assertEqual(list(nuevo["preguntas"][-1]), ["¿1 + 1?", "2", ["3", "4", "5"], "Uno más uno es dos."], inf)
        nuevo, inf = ia_local.aplicar_operaciones(BANCO, [op])
        self.assertEqual(len(nuevo["preguntas"][-1]), 3, inf)

    def test_agregar_vf_con_explicacion(self):
        op = {"op": "agregar_vf", "afirmacion": "El agua hierve a 100 °C", "verdadera": True, "explicacion": "A nivel del mar."}
        nuevo, inf = ia_local.aplicar_operaciones(BANCO, [op])
        self.assertEqual(list(nuevo["vf"][-1]), ["El agua hierve a 100 °C", True, "A nivel del mar."], inf)

    def test_comando_basico_pregunta_con_explicacion(self):
        ops, avisos = ia_local.interpretar_basico("agrega pregunta: ¿1+1? | 2 | 3 | 4 | 5 | Uno más uno es dos")
        self.assertEqual(avisos, [])
        self.assertEqual(ops[0]["explicacion"], "Uno más uno es dos")
        ops, avisos = ia_local.interpretar_basico("agrega pregunta: ¿1+1? | 2 | 3 | 4 | 5")
        self.assertEqual(avisos, [])
        self.assertNotIn("explicacion", ops[0])

    def test_comando_basico_afirmacion_con_explicacion(self):
        ops, avisos = ia_local.interpretar_basico("agrega afirmación: El agua hierve a 100 °C | verdadero | A nivel del mar")
        self.assertEqual(avisos, [])
        self.assertEqual((ops[0]["verdadera"], ops[0]["explicacion"]), ("verdadero", "A nivel del mar"))
        ops, avisos = ia_local.interpretar_basico("agrega afirmación: El agua hierve a 100 °C | verdadero")
        self.assertEqual(avisos, [])
        self.assertNotIn("explicacion", ops[0])

    def test_tutor_busca_apuntes_con_preguntas_de_cuatro_elementos(self):
        res = ia_local._buscar_apuntes("derivada", BANCOS["11"]["Matemáticas"])
        self.assertTrue(res)


# ==============================================================================
# JUEGOS REALES (se abren ventanas)
# ==============================================================================
class JuegoTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ctk.CTk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        for _ in range(10):  # deja correr los after() pendientes de customtkinter antes de cerrar
            cls.root.update()
            time.sleep(0.02)
        cls.root.destroy()

    def setUp(self):
        self.finales, self.abiertos = [], []

    def tearDown(self):
        for g in self.abiertos:
            try:
                g.finalizado = True
                g.destroy()
            except Exception:
                pass

    # -- ayudas --
    def abrir(self, tipo, banco=None):
        g = juegos.TIPOS[tipo][3](self.root, "Matemáticas", f"{tipo}: Tema", "#38bdf8", self.finales.append, copy.deepcopy(banco or BANCO))
        self.abiertos.append(g)
        self.bombear(40)
        return g

    def bombear(self, ms):
        fin = time.time() + ms / 1000
        while time.time() < fin:
            self.root.update()
            time.sleep(0.01)

    def esperar(self, cond, seg=3.0):
        fin = time.time() + seg
        while time.time() < fin:
            self.root.update()
            if cond():
                return True
            time.sleep(0.01)
        return cond()

    def hijos(self, w):
        for h in w.winfo_children():
            yield h
            yield from self.hijos(h)

    def textos(self, w):
        out = []
        for h in [w, *self.hijos(w)]:
            try:
                t = h.cget("text")
            except Exception:
                continue
            if isinstance(t, str):
                out.append(t)
        return "\n".join(out)

    def tarjeta(self, g):
        self.bombear(40)
        return g.tarjeta.winfo_ismapped(), self.textos(g.tarjeta)

    def continuar(self, g):
        for h in self.hijos(g.tarjeta):
            if isinstance(h, ctk.CTkButton) and "Continuar" in h.cget("text"):
                h.invoke()
                self.bombear(40)
                return True
        return False

    def assertFelicita(self, texto):
        self.assertTrue(any(f in texto for f in juegos.FELICITACIONES), texto)

    def hay_explicacion(self, texto):
        """La línea de explicación empieza con 💡 (el título de aliento también lo usa de adorno al final)."""
        return any(linea.startswith("💡") for linea in texto.split("\n"))


class TestVentana(JuegoTestCase):
    def test_la_ventana_cabe_en_la_pantalla(self):
        g = self.abrir("quiz")
        self.bombear(100)
        self.assertLessEqual(g.winfo_height(), g.winfo_screenheight() - 40)  # deja sitio a la barra de tareas

    def test_en_un_portatil_de_768_de_alto_tambien_cabe(self):
        with mock.patch.object(ctk.CTkToplevel, "winfo_screenheight", lambda self: 768):
            g = self.abrir("quiz")
        self.bombear(100)
        self.assertLessEqual(g.winfo_height(), 768 - 40)

    def test_la_tarjeta_queda_dentro_de_la_ventana(self):
        g = self.abrir("quiz")
        ok = g.preg[g.i][1]
        g.responder(next(b for b in g.botones if b.cget("text") != ok), "x")
        self.bombear(100)
        self.assertLessEqual(g.tarjeta.winfo_rooty() + g.tarjeta.winfo_height(), g.winfo_rooty() + g.winfo_height())
        self.assertGreaterEqual(g.tarjeta.winfo_rooty(), g.winfo_rooty())


class TestCerrarPartida(JuegoTestCase):
    def test_cerrar_partida_limpia_y_solo_funciona_una_vez(self):
        g = self.abrir("quiz")
        ok = g.preg[g.i][1]
        g.responder(next(b for b in g.botones if b.cget("text") != ok), "x")     # deja la tarjeta visible
        self.bombear(60)
        self.assertTrue(g._cerrar_partida())
        self.assertTrue(g.finalizado)
        self.assertFalse(g.tarjeta.winfo_ismapped())
        self.assertEqual(g.cuerpo.winfo_children(), [])
        self.assertFalse(g._cerrar_partida())


class TestQuiz(JuegoTestCase):
    def test_fallo_muestra_explicacion_y_espera_a_continuar(self):
        g = self.abrir("quiz")
        _, ok, _, expl = juegos.desempacar_pregunta(g.preg[g.i])
        mala = next(b for b in g.botones if b.cget("text") != ok)
        g.responder(mala, mala.cget("text"))
        visible, t = self.tarjeta(g)
        self.assertTrue(visible)
        self.assertIn(expl, t)
        self.assertIn(ok, t)
        self.assertEqual((g.vidas, g.racha), (2, 0))
        self.bombear(1400)  # ya no avanza solo: hay que leer
        self.assertEqual(g.i, 0)
        self.assertTrue(self.continuar(g))
        self.assertEqual(g.i, 1)
        self.assertFalse(g.tarjeta.winfo_ismapped())

    def test_fallo_sin_explicacion_dice_la_correcta(self):
        g = self.abrir("quiz", BANCO_VIEJO)
        ok = g.preg[g.i][1]
        mala = next(b for b in g.botones if b.cget("text") != ok)
        g.responder(mala, mala.cget("text"))
        visible, t = self.tarjeta(g)
        self.assertTrue(visible)
        self.assertIn(ok, t)
        self.assertFalse(self.hay_explicacion(t), t)
        self.assertTrue(self.continuar(g))

    def test_acierto_felicita_y_avanza_solo(self):
        g = self.abrir("quiz")
        ok = g.preg[g.i][1]
        g.responder(next(b for b in g.botones if b.cget("text") == ok), ok)
        visible, t = self.tarjeta(g)
        self.assertTrue(visible)
        self.assertFelicita(t)
        self.assertNotIn("Continuar", t)
        self.assertTrue(self.esperar(lambda: g.i == 1))
        self.assertFalse(g.tarjeta.winfo_ismapped())

    def test_racha_de_tres_y_reinicio_al_fallar(self):
        g = self.abrir("quiz")
        for n in range(3):
            ok = g.preg[g.i][1]
            g.responder(next(b for b in g.botones if b.cget("text") == ok), ok)
            _, t = self.tarjeta(g)
            if n < 2:
                self.assertNotIn("seguidas", t)
            self.assertTrue(self.esperar(lambda n=n: g.i == n + 1))
        self.assertIn("3 seguidas", t)
        ok = g.preg[g.i][1]
        mala = next(b for b in g.botones if b.cget("text") != ok)
        g.responder(mala, mala.cget("text"))
        self.assertEqual(g.racha, 0)

    def test_pantalla_final_con_detalle_y_sin_tarjeta(self):
        g = self.abrir("quiz")
        ok = g.preg[g.i][1]
        mala = next(b for b in g.botones if b.cget("text") != ok)
        g.responder(mala, mala.cget("text"))
        self.bombear(40)
        g.terminar(0.5, "Acertaste 4 de 8")
        self.bombear(40)
        self.assertFalse(g.tarjeta.winfo_ismapped())
        t = self.textos(g.cuerpo)
        self.assertIn("Acertaste 4 de 8", t)
        self.assertIn("50%", t)
        self.assertEqual(self.finales, [0.5])

    def test_mensajes_finales_por_nivel(self):
        for fraccion, esperado in ((1.0, "Excelente"), (0.7, "Muy bien"), (0.3, "Buen intento"), (0.0, "sí se puede")):
            g = self.abrir("quiz")
            g.terminar(fraccion)
            self.assertIn(esperado, self.textos(g.cuerpo), fraccion)


class TestCiertoFalso(JuegoTestCase):
    def test_fallo_con_explicacion(self):
        g = self.abrir("vf")
        _, correcta, expl = juegos.desempacar_vf(g.items[g.i])
        g.responder(not correcta)
        visible, t = self.tarjeta(g)
        self.assertTrue(visible)
        self.assertIn(expl, t)
        self.assertIn("Cierto" if correcta else "Falso", t)
        self.assertTrue(self.continuar(g))
        self.assertEqual(g.i, 1)

    def test_tiempo_agotado(self):
        g = self.abrir("vf")
        g.responder(None)
        visible, t = self.tarjeta(g)
        self.assertTrue(visible)
        self.assertIn("tiempo", t.lower())
        self.assertTrue(self.hay_explicacion(t), t)

    def test_acierto(self):
        g = self.abrir("vf")
        g.responder(g.items[g.i][1])
        visible, t = self.tarjeta(g)
        self.assertTrue(visible)
        self.assertFelicita(t)
        self.assertTrue(self.esperar(lambda: g.i == 1))

    def test_banco_viejo_no_se_rompe(self):
        g = self.abrir("vf", BANCO_VIEJO)
        g.responder(not g.items[g.i][1])
        visible, t = self.tarjeta(g)
        self.assertTrue(visible)
        self.assertFalse(self.hay_explicacion(t), t)


class TestBurbujas(JuegoTestCase):
    def test_reventar_la_incorrecta(self):
        g = self.abrir("burbujas")
        _, ok, _, expl = juegos.desempacar_pregunta(g.preg[g.i])
        g.click(next(k for k, b in enumerate(g.burbujas) if not b["ok"]))
        visible, t = self.tarjeta(g)
        self.assertTrue(visible)
        self.assertIn(expl, t)
        self.assertIn(ok, t)
        self.assertTrue(self.continuar(g))
        self.assertEqual(g.i, 1)

    def test_reventar_la_correcta(self):
        g = self.abrir("burbujas")
        g.click(next(k for k, b in enumerate(g.burbujas) if b["ok"]))
        visible, t = self.tarjeta(g)
        self.assertTrue(visible)
        self.assertFelicita(t)
        self.assertTrue(self.esperar(lambda: g.i == 1))

    def test_se_escapa_la_correcta(self):
        g = self.abrir("burbujas")
        _, ok, _, expl = juegos.desempacar_pregunta(g.preg[g.i])
        next(b for b in g.burbujas if b["ok"])["y"] = -500
        self.assertTrue(self.esperar(lambda: g.tarjeta.winfo_ismapped()))
        t = self.textos(g.tarjeta)
        self.assertIn("escap", t.lower())
        self.assertIn(ok, t)
        self.assertIn(expl, t)
        self.assertEqual(g.vidas, 2)


class TestAdivina(JuegoTestCase):
    def test_fallo_muestra_termino_y_definicion(self):
        g = self.abrir("adivina")
        q, ok, _, expl = juegos.desempacar_pregunta(g.preg[g.i])
        mala = next(b for b in g.botones if b.cget("text") != ok)
        g.responder(mala, mala.cget("text"))
        visible, t = self.tarjeta(g)
        self.assertTrue(visible)
        self.assertIn(expl, t)
        definicion = dict(BANCO["parejas"])[ok]
        self.assertIn(definicion, t)


class TestMemoria(JuegoTestCase):
    def test_pareja_felicita_y_muestra_el_significado(self):
        g = self.abrir("memoria")
        k = g.cartas[0][0]
        j = next(n for n, (kk, _) in enumerate(g.cartas) if kk == k and n != 0)
        g.voltear(0)
        g.voltear(j)
        visible, t = self.tarjeta(g)
        self.assertTrue(visible)
        termino, definicion = g.pares[k]
        self.assertIn(termino, t)
        self.assertIn(definicion, t)

    def test_error_no_revela_nada(self):
        g = self.abrir("memoria")
        k = g.cartas[0][0]
        m = next(n for n, (kk, _) in enumerate(g.cartas) if kk != k)
        g.voltear(0)
        g.voltear(m)
        visible, _ = self.tarjeta(g)
        self.assertFalse(visible)
        self.assertEqual(g.fallos, 1)


class TestAhorcado(JuegoTestCase):
    def test_perder_la_palabra_la_revela_con_su_pista(self):
        g = self.abrir("ahorcado")
        palabra, pista = g.palabra, g.pista
        malas = [l for l in g.LETRAS if not any(juegos._base(c) == l for c in palabra)]
        for letra in malas[:g.MAX_ERRORES]:
            g.letra(letra)
        visible, t = self.tarjeta(g)
        self.assertTrue(visible)
        self.assertIn(palabra, t)
        self.assertIn(pista, t)
        self.assertTrue(self.continuar(g))
        self.assertEqual(g.r, 1)

    def test_ganar_la_palabra(self):
        g = self.abrir("ahorcado")
        for letra in {juegos._base(c) for c in g.palabra}:
            g.letra(letra)
        visible, t = self.tarjeta(g)
        self.assertTrue(visible)
        self.assertFelicita(t)
        self.assertTrue(self.esperar(lambda: g.r == 1))


class TestSecuencia(JuegoTestCase):
    def test_orden_correcto_felicita(self):
        g = self.abrir("secuencia")
        for paso in list(g.pasos):
            g.elegir(next(b for b in g.botones if b.cget("text") == paso), paso)
        visible, t = self.tarjeta(g)
        self.assertTrue(visible)
        self.assertFelicita(t)
        self.assertTrue(self.esperar(lambda: g.r == 1))

    def test_paso_equivocado_no_abre_tarjeta_pero_corta_la_racha(self):
        g = self.abrir("secuencia")
        g.racha = 2
        otro = next(p for p in g.pasos if p != g.pasos[0])
        g.elegir(next(b for b in g.botones if b.cget("text") == otro), otro)
        visible, _ = self.tarjeta(g)
        self.assertFalse(visible)
        self.assertEqual(g.racha, 0)


class TestCazador(JuegoTestCase):
    def test_revisar_con_fallos_y_tocar_para_ver_por_que(self):
        g = self.abrir("cazador")
        for i, item in enumerate(g.items):
            if item[1]:  # marca las verdaderas: todo mal
                g.alternar(i)
        g.revisar()
        visible, t = self.tarjeta(g)
        self.assertTrue(visible)
        self.assertIn("Toca", t)
        i_mala = next(i for i, item in enumerate(g.items) if item[1])
        g.alternar(i_mala)
        visible, t = self.tarjeta(g)
        self.assertTrue(visible)
        self.assertIn(g.items[i_mala][2], t)

    def test_revisar_perfecto_felicita(self):
        g = self.abrir("cazador")
        for i, item in enumerate(g.items):
            if not item[1]:
                g.alternar(i)
        g.revisar()
        visible, t = self.tarjeta(g)
        self.assertTrue(visible)
        self.assertFelicita(t)

    def test_banco_viejo_no_se_rompe(self):
        g = self.abrir("cazador", BANCO_VIEJO)
        g.revisar()
        g.alternar(0)
        self.bombear(40)


if __name__ == "__main__":
    unittest.main()
