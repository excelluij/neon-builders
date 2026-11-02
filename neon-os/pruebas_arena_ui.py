"""Pruebas de la Arena con pantalla: corazones en BovedaCore, ventana del duelo, pestaña y HUD.

Ejecutar desde esta carpeta:   python pruebas_arena_ui.py -v
Usa una base de datos temporal (nunca toca neon_os.db) y MainApp como raíz oculta compartida.
"""
import atexit
import os
import shutil
import sys
import tempfile
import time
import types
import unittest
from datetime import date, timedelta
from unittest import mock

_TMP = tempfile.mkdtemp(prefix="neon_arena_")
atexit.register(shutil.rmtree, _TMP, ignore_errors=True)
os.environ["NEON_DB"] = os.path.join(_TMP, "import.db")  # antes de importar almacen / APP_final
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import customtkinter as ctk

import almacen
import APP_final
import arena
import juegos
from pruebas_arena import RngFijo

HOY = date(2026, 10, 18)
ROOT = None
REAL_LANZAR_TETRIS = juegos.lanzar_tetris   # el real, antes de que TestViewArena lo reemplace por un doble


def setUpModule():
    global ROOT
    almacen.iniciar()
    ROOT = APP_final.MainApp()
    ROOT.cargar_avatar_en_hilo = lambda: None   # sin descargas ni hilos de avatar
    ROOT.withdraw()


def tearDownModule():
    for _ in range(10):
        ROOT.update()
        time.sleep(0.02)
    ROOT.destroy()


# ==============================================================================
# TAREA 2: corazones de la Arena
# ==============================================================================
class TestCorazonesArena(unittest.TestCase):
    def test_arrancan_en_5_y_cada_gasto_resta_1(self):
        b = APP_final.BovedaCore("ana", "11")
        self.assertEqual(b.corazones_arena_disponibles(HOY), 5)
        self.assertEqual(b.gastar_corazon_arena(HOY)[0], True)
        self.assertEqual(b.corazones_arena, 4)

    def test_sin_corazones_bloquea_y_no_resta(self):
        b = APP_final.BovedaCore("ana", "11")
        b.corazones_arena, b.arena_fecha = 0, HOY.isoformat()
        self.assertEqual(b.gastar_corazon_arena(HOY), (False, "Sin corazones: vuelven mañana"))
        self.assertEqual(b.corazones_arena, 0)

    def test_recarga_al_consultar_en_un_dia_nuevo_sin_reiniciar_sesion(self):   # enfoque de revisión 4
        b = APP_final.BovedaCore("ana", "11")
        for _ in range(5):
            b.gastar_corazon_arena(HOY)
        self.assertEqual(b.corazones_arena_disponibles(HOY), 0)
        self.assertEqual(b.corazones_arena_disponibles(HOY + timedelta(days=1)), 5)

    def test_exportar_importar_y_progreso_viejo(self):
        b = APP_final.BovedaCore("ana", "11")
        b.gastar_corazon_arena(HOY)
        b.gastar_corazon_arena(HOY)
        otro = APP_final.BovedaCore("ana", "11")
        otro.importar(b.exportar())
        self.assertEqual((otro.corazones_arena, otro.arena_fecha), (3, HOY.isoformat()))
        viejo = APP_final.BovedaCore("beto", "11")
        viejo.importar({"coins": 10})
        self.assertEqual(viejo.corazones_arena_disponibles(HOY), 5)

    def test_las_vidas_no_se_tocan(self):
        b = APP_final.BovedaCore("ana", "11")
        b.gastar_corazon_arena(HOY)
        self.assertEqual(b.hearts, 5)


# ==============================================================================
# 3b, TAREA 4: récords por juego y devolver un corazón
# ==============================================================================
class TestRecords(unittest.TestCase):
    def test_registrar_record(self):
        b = APP_final.BovedaCore("ana", "11")
        self.assertFalse(b.registrar_record("tetris", 0))
        self.assertTrue(b.registrar_record("tetris", 5))
        self.assertEqual(b.records, {"tetris": 5})
        self.assertFalse(b.registrar_record("tetris", 5))
        self.assertFalse(b.registrar_record("tetris", 3))
        self.assertTrue(b.registrar_record("serpiente", 2))
        self.assertEqual(b.records, {"tetris": 5, "serpiente": 2})

    def test_records_en_exportar_importar_y_progreso_viejo(self):
        b = APP_final.BovedaCore("ana", "11")
        b.registrar_record("serpiente", 9)
        otro = APP_final.BovedaCore("ana", "11")
        otro.importar(b.exportar())
        self.assertEqual(otro.records, {"serpiente": 9})
        viejo = APP_final.BovedaCore("beto", "11")
        viejo.importar({"coins": 3})
        self.assertEqual(viejo.records, {})

    def test_los_records_de_un_jugador_no_se_comparten_con_otro_objeto(self):
        a, b = APP_final.BovedaCore("ana", "11"), APP_final.BovedaCore("beto", "11")
        a.registrar_record("tetris", 4)
        self.assertEqual(b.records, {})

    def test_devolver_corazon_no_pasa_del_maximo(self):
        b = APP_final.BovedaCore("ana", "11")
        b.gastar_corazon_arena(HOY)
        b.devolver_corazon_arena()
        self.assertEqual(b.corazones_arena, 5)
        b.devolver_corazon_arena()
        self.assertEqual(b.corazones_arena, 5)


# ==============================================================================
# AYUDAS PARA LAS PRUEBAS CON PANTALLA
# ==============================================================================
class UITestCase(unittest.TestCase):
    def setUp(self):
        self.finales, self.abiertos = [], []

    def tearDown(self):
        for g in self.abiertos:
            try:
                g.finalizado = True
                g.destroy()
            except Exception:
                pass

    def bombear(self, ms):
        fin = time.time() + ms / 1000
        while time.time() < fin:
            ROOT.update()
            time.sleep(0.01)

    def esperar(self, cond, seg=4.0):
        fin = time.time() + seg
        while time.time() < fin:
            ROOT.update()
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

    def boton_con(self, w, texto):
        return [h for h in self.hijos(w) if isinstance(h, ctk.CTkButton) and texto in h.cget("text")]


# ==============================================================================
# TAREA 4: ventana del duelo
# ==============================================================================
class TestPartidaArena(UITestCase):
    def test_alto_ventana_guardado_y_coherente(self):
        pool = [(f"P{i}", "ok", ["a", "b", "c"], f"expl {i}") for i in range(12)]
        g = juegos.lanzar_duelo(ROOT, "Física", pool, "#3b82f6", self.finales.append)
        self.abiertos.append(g)
        self.assertTrue(520 <= g.alto_ventana <= 760)

    def test_si_construir_falla_no_queda_ninguna_ventana_y_nadie_recibe_on_finish(self):   # hallazgo de la revisión final
        antes = len([w for w in ROOT.winfo_children() if isinstance(w, ctk.CTkToplevel)])
        with mock.patch.object(juegos.tetris, "Tetris", side_effect=RuntimeError("falló construir")):
            with self.assertRaises(RuntimeError):
                juegos.lanzar_tetris(ROOT, "#8b5cf6", self.finales.append)
        self.bombear(400)
        self.assertEqual(len([w for w in ROOT.winfo_children() if isinstance(w, ctk.CTkToplevel)]), antes)
        self.assertEqual(self.finales, [])

    def test_duelo_hereda_de_partida_arena_y_su_autotick(self):
        self.assertTrue(issubclass(juegos.DueloGame, juegos.PartidaArena))
        self.assertTrue(juegos.PartidaArena.AUTOTICK)
        self.assertNotIn("AUTOTICK", vars(juegos.DueloGame))

    def _prueba(self, **kw):
        class Prueba(juegos.PartidaArena):
            def construir(self):
                pass
        g = Prueba(ROOT, "x", "Prueba", "#3b82f6", self.finales.append, {}, **kw)
        self.abiertos.append(g)
        return g

    def test_pantalla_final_generica(self):
        g = self._prueba(on_revancha=lambda: None, corazones=lambda: 2)
        g._pantalla_final("Titulo", "mensaje", [("Puntaje: 7", 20, None)], "Jugar otra (−1 ❤️)", 7)
        t = self.textos(g.cuerpo)
        for texto in ("Titulo", "Puntaje: 7", "mensaje", "Jugar otra (−1 ❤️)", "Cambiar de dinámica", "❤️❤️🤍🤍🤍 2/5"):
            self.assertIn(texto, t)
        self.assertEqual(self.finales, [7])
        g._pantalla_final("de nuevo", "x", [], "x", 9)                  # ya cerrada: no hace nada
        self.assertEqual(self.finales, [7])

    def test_abandonar_entrega_none_por_defecto(self):
        g = self._prueba()
        g.cerrar()
        self.assertEqual(self.finales, [None])

    def test_sin_corazones_o_sin_revancha_el_boton_queda_desactivado(self):
        g = self._prueba(on_revancha=lambda: None, corazones=lambda: 0)
        g._pantalla_final("T", "m", [], "Jugar otra (−1 ❤️)", 1)
        self.assertEqual(str(self.boton_con(g.cuerpo, "Jugar otra")[0].cget("state")), "disabled")
        self.assertIn("Sin corazones: vuelven mañana", self.textos(g.cuerpo))
        g = self._prueba(corazones=lambda: 3)                            # sin on_revancha
        g._pantalla_final("T", "m", [], "Jugar otra (−1 ❤️)", 1)
        self.assertEqual(str(self.boton_con(g.cuerpo, "Jugar otra")[0].cget("state")), "disabled")


class TestDuelo(UITestCase):
    def abrir_duelo(self, robot_acierta, n=12, corazones=None, on_revancha=None, autotick=False, guarda=0.0):
        pool = [(f"P{i}", "ok", ["a", "b", "c"], f"expl {i}") for i in range(12)]
        rng = RngFijo(randoms=[0.0 if robot_acierta else 0.99] * n, uniforms=[3.0] * n)
        with mock.patch.object(juegos.DueloGame, "AUTOTICK", autotick), mock.patch.object(juegos.DueloGame, "GUARDA_CLIC", guarda):
            g = juegos.lanzar_duelo(ROOT, "Física", pool, "#3b82f6", self.finales.append, on_revancha, corazones, rng)
        self.abiertos.append(g)
        self.bombear(40)
        return g

    def boton(self, g, correcta):
        return next(b for b in g.botones if (b.cget("text") == "ok") == correcta)

    def continuar(self, g):
        botones = self.boton_con(g.tarjeta, "Continuar")
        if botones:
            botones[0].invoke()
            self.bombear(40)
        return bool(botones)

    def test_acierto_golpea_al_robot_y_felicita(self):
        g = self.abrir_duelo(robot_acierta=False)
        g.responder(self.boton(g, True), "ok")
        self.bombear(60)
        self.assertEqual((g.duelo.pv_robot, g.duelo.pv_jugador), (75, 100))      # respuesta inmediata: bono de rapidez
        self.assertTrue(g.tarjeta.winfo_ismapped())
        self.assertIn("−25 PV", self.textos(g.tarjeta))

    def test_fallo_muestra_explicacion_y_el_reloj_no_corre_mientras_se_lee(self):
        g = self.abrir_duelo(robot_acierta=False)
        g.responder(self.boton(g, False), "x")
        self.bombear(60)
        self.assertIn("expl", self.textos(g.tarjeta))
        antes = g.duelo.tiempo_restante
        for _ in range(5):
            g._tick()
        self.assertEqual(g.duelo.tiempo_restante, antes)
        self.assertTrue(self.continuar(g))
        g._tick()
        self.assertEqual(g.duelo.tiempo_restante, antes - 1)

    def test_el_robot_golpea_si_fallas(self):
        g = self.abrir_duelo(robot_acierta=True)
        g.responder(self.boton(g, False), "x")
        self.bombear(60)
        self.assertEqual(g.duelo.pv_jugador, 80)
        self.assertIn("te golpea", self.textos(g.tarjeta))

    def test_sin_responder_en_10_segundos_se_resuelve_como_fallo(self):
        g = self.abrir_duelo(robot_acierta=False)
        for _ in range(10):
            g._tick()
        self.bombear(60)
        self.assertIn("Se acabó el tiempo", self.textos(g.tarjeta))
        self.assertEqual(g.duelo.pv_robot, 100)

    def test_victoria_derrota_y_empate_entregan_el_resultado_y_la_pantalla_final(self):
        g = self.abrir_duelo(robot_acierta=False)
        for _ in range(5):                                   # t = 4 s: sin bono, 5 golpes de 20
            for _ in range(4):
                g._tick()
            g.responder(self.boton(g, True), "ok")
            self.esperar(lambda: g.pregunta_abierta or g.finalizado)
        self.assertEqual(self.finales, ["victoria"])
        t = self.textos(g.cuerpo)
        self.assertIn("+10", t)
        self.assertIn("Revancha", t)
        self.assertIn("Cambiar de dinámica", t)
        g2 = self.abrir_duelo(robot_acierta=True)
        for _ in range(5):
            g2.responder(self.boton(g2, False), "x")
            self.continuar(g2)
        self.assertEqual(self.finales[-1], "derrota")
        g3 = self.abrir_duelo(robot_acierta=False)
        g3.duelo.gastar_tiempo(120)
        g3._tick()
        self.assertEqual(self.finales[-1], "empate")

    def test_cerrar_con_pregunta_abierta_es_abandono_sin_errores(self):          # enfoque de revisión 2
        with mock.patch.object(juegos.DueloGame, "_tick") as tick:               # el temporizador real de 1 s
            g = self.abrir_duelo(robot_acierta=False, autotick=True)
            g.cerrar()
            self.bombear(1300)
        self.assertEqual(tick.call_count, 0)
        self.assertEqual(self.finales, ["abandono"])
        self.assertFalse(g.winfo_exists())

    def test_doble_clic_no_cuenta_dos_veces(self):                              # enfoque de revisión 3
        g = self.abrir_duelo(robot_acierta=True)
        b = self.boton(g, False)
        g.responder(b, "x")
        g.responder(b, "x")
        self.assertEqual(g.duelo.pv_jugador, 80)
        self.continuar(g)
        self.continuar(g)
        self.assertEqual(g.duelo.ronda, 2)

    def test_revancha_segun_corazones_y_cambiar_de_dinamica(self):
        llamadas = []
        g = self.abrir_duelo(robot_acierta=False, corazones=lambda: 0, on_revancha=lambda: llamadas.append(1))
        g.duelo.gastar_tiempo(120)
        g._tick()
        rev = self.boton_con(g.cuerpo, "Revancha")[0]
        self.assertEqual(str(rev.cget("state")), "disabled")
        self.assertIn("Sin corazones: vuelven mañana", self.textos(g.cuerpo))
        g2 = self.abrir_duelo(robot_acierta=False, corazones=lambda: 3, on_revancha=lambda: llamadas.append(1))
        g2.duelo.gastar_tiempo(120)
        g2._tick()
        self.boton_con(g2.cuerpo, "Revancha")[0].invoke()
        self.assertEqual(llamadas, [1])
        self.boton_con(g2.cuerpo, "Cambiar de dinámica")[0].invoke()
        self.assertFalse(g2.winfo_exists())

    def test_el_duelo_no_aparece_en_el_menu_de_misiones(self):
        self.assertNotIn("duelo", juegos.TIPOS)

    # -- hallazgos de la revisión final ----------------------------------------------------
    def test_cerrar_con_el_duelo_ya_ganado_entrega_victoria_y_no_abandono(self):
        g = self.abrir_duelo(robot_acierta=False)
        for _ in range(4):
            for _ in range(4):
                g._tick()
            g.responder(self.boton(g, True), "ok")
            self.esperar(lambda: g.pregunta_abierta or g.finalizado)
        for _ in range(4):
            g._tick()
        g.responder(self.boton(g, True), "ok")                 # 5.º golpe: ya está decidido, falta la pantalla final
        self.assertTrue(g.duelo.terminado)
        self.assertFalse(g.finalizado)
        g.cerrar()
        self.assertEqual(self.finales, ["victoria"])

    def test_cerrar_con_el_duelo_ya_perdido_entrega_derrota_y_no_abandono(self):
        g = self.abrir_duelo(robot_acierta=True)
        for n in range(5):
            g.responder(self.boton(g, False), "x")
            if n < 4:
                self.continuar(g)
        self.assertTrue(g.duelo.terminado)
        self.assertFalse(g.finalizado)
        g.cerrar()
        self.assertEqual(self.finales, ["derrota"])

    def test_el_segundo_clic_de_un_doble_clic_en_continuar_no_responde_la_siguiente(self):
        # Guarda larga y reloj de la guarda movido a mano: así la prueba no depende de lo rápido que abra las ventanas el equipo
        # (con 0.3 s reales fallaba de forma intermitente cuando la máquina iba cargada).
        g = self.abrir_duelo(robot_acierta=True, guarda=30.0)
        g._no_antes_de = 0.0                                   # 1.ª ronda: la guarda ya pasó
        g.responder(self.boton(g, False), "x")
        self.continuar(g)                                      # abre la ronda 2 (su guarda de 30 s corre desde que se abrió)
        g.responder(self.boton(g, False), "x")                 # el segundo clic del doble clic cae sobre una opción
        self.assertTrue(g.pregunta_abierta)
        self.assertEqual((g.duelo.ronda, g.duelo.pv_jugador), (2, 80))
        g._no_antes_de = 0.0                                   # pasada la guarda, el clic ya cuenta
        g.responder(self.boton(g, False), "x")
        self.assertEqual(g.duelo.pv_jugador, 60)


# ==============================================================================
# 3b, TAREA 6: ventana de la Serpiente
# ==============================================================================
class TestSerpienteGame(UITestCase):
    def abrir(self, record=0, autotick=False):
        with mock.patch.object(juegos.PartidaArena, "AUTOTICK", autotick):
            g = juegos.lanzar_serpiente(ROOT, "#10b981", self.finales.append, record=record, rng=RngFijo())
        self.abiertos.append(g)
        self.bombear(40)
        return g

    def test_arranca_con_120_s_y_una_serpiente_de_3_segmentos(self):
        g = self.abrir()
        self.assertEqual((g.tiempo_restante, len(g.juego.cuerpo), g.finalizado), (120, 3, False))
        self.assertIn("120", g.lbl_estado.cget("text"))

    def test_una_partida_completa_hasta_el_choque(self):
        g = self.abrir()
        for _ in range(10):                                        # de (10,10) a la pared en 10 pasos
            g._paso()
        self.assertTrue(g.finalizado)
        self.assertEqual(self.finales, [0])
        t = self.textos(g.cuerpo)
        self.assertIn("Chocaste", t)
        self.assertIn("+1", t)
        self.assertIn("Jugar otra", t)

    def test_teclas_giran_y_wasd_tambien(self):
        g = self.abrir()
        g.tecla("Up")
        g._paso()
        self.assertEqual(g.juego.direccion, "arriba")
        g.tecla("A")
        g._paso()
        self.assertEqual(g.juego.direccion, "izq")

    def test_fin_por_tiempo(self):
        g = self.abrir()
        for _ in range(120):
            g._tick()
        self.assertEqual(self.finales, [0])
        self.assertIn("Se acabó el tiempo", self.textos(g.cuerpo))

    def test_premio_y_record_en_la_pantalla_final(self):
        g = self.abrir(record=3)
        g.juego.puntaje, g.juego.cuerpo = 8, [(19, 5), (18, 5), (17, 5)]
        g._paso()
        t = self.textos(g.cuerpo)
        self.assertIn("+2", t)
        self.assertIn("¡Nuevo récord!", t)
        self.assertEqual(self.finales, [8])
        g = self.abrir(record=10)
        g.juego.puntaje, g.juego.cuerpo = 8, [(19, 5), (18, 5), (17, 5)]
        g._paso()
        t = self.textos(g.cuerpo)
        self.assertIn("Récord: 10", t)
        self.assertNotIn("Nuevo récord", t)

    def test_teclas_y_pasos_tras_el_final_no_hacen_nada(self):      # enfoque de revisión 1
        g = self.abrir()
        for _ in range(10):
            g._paso()
        cuerpo = list(g.juego.cuerpo)
        g.tecla("Up")
        g._paso()
        g._tick()
        self.assertEqual((g.juego.cuerpo, self.finales), (cuerpo, [0]))

    def test_cerrar_a_mitad_es_abandono_y_los_temporizadores_se_cancelan(self):   # enfoque de revisión 2
        with mock.patch.object(juegos.SerpienteGame, "_paso") as paso, mock.patch.object(juegos.SerpienteGame, "_tick") as tick:
            g = self.abrir(autotick=True)
            g.cerrar()
            paso.reset_mock()                                      # abrir la ventana tarda: algún paso pudo ocurrir antes de cerrar
            tick.reset_mock()
            self.bombear(1300)                                     # lo que cuenta es que tras cerrar no se dispare ninguno
        self.assertEqual((paso.call_count, tick.call_count), (0, 0))
        self.assertEqual(self.finales, [None])

    def test_el_tablero_cabe_en_una_ventana_pequena(self):          # enfoque de revisión 5
        with mock.patch.object(ctk.CTkToplevel, "winfo_screenheight", lambda self: 768):
            g = self.abrir()
        self.assertEqual(g.celda, max(12, min(24, (g.alto_ventana - 150) // 20)))
        self.assertLessEqual(g.celda * 20, g.alto_ventana - 130)

    def test_el_tablero_aprovecha_la_escala_de_pantalla(self):      # hallazgo de la verificación visual
        g = self.abrir()
        self.assertEqual(g.celda_px, max(1, int(g.celda * g.escala)))
        self.assertEqual(int(g.canvas.cget("height")), g.celda_px * 20)
        self.assertLessEqual(g.celda_px * 20, int((g.alto_ventana - 130) * g.escala))

    def test_con_los_temporizadores_reales_la_serpiente_se_mueve_sola(self):
        g = self.abrir(autotick=True)
        cabeza = g.juego.cuerpo[0]
        self.assertTrue(self.esperar(lambda: g.juego.cuerpo[0] != cabeza, seg=2.0))


# ==============================================================================
# 3b, TAREA 7: ventana del Tetris
# ==============================================================================
class TestTetrisGame(UITestCase):
    def abrir(self, record=0, autotick=False):
        with mock.patch.object(juegos.PartidaArena, "AUTOTICK", autotick):
            g = juegos.lanzar_tetris(ROOT, "#8b5cf6", self.finales.append, record=record, rng=RngFijo())
        self.abiertos.append(g)
        self.bombear(40)
        return g

    def test_teclas_mueven_rotan_y_caen(self):
        g = self.abrir()
        x0 = min(x for x, _ in g.juego.celdas_pieza())
        g.tecla("Left")
        self.assertEqual(min(x for x, _ in g.juego.celdas_pieza()), x0 - 1)
        g.tecla("Up")
        self.assertEqual(g.juego.pieza.rot, 1)
        g.tecla("space")
        self.assertEqual(g.juego.pieza.tipo, "O")                    # cayó y trajo la siguiente

    def test_la_gravedad_baja_la_pieza(self):
        g = self.abrir()
        y0 = g.juego.pieza.y
        g._paso()
        self.assertEqual(g.juego.pieza.y, y0 + 1)

    def test_bajar_con_la_flecha_reinicia_la_gravedad(self):
        g = self.abrir()
        with mock.patch.object(juegos.TetrisGame, "_reiniciar_gravedad") as reinicia:
            g.tecla("Down")
        self.assertEqual(reinicia.call_count, 1)

    def test_fin_por_pila_llena_entrega_las_lineas(self):
        g = self.abrir()
        for _ in range(60):
            if g.finalizado:
                break
            g.tecla("space")
        self.assertTrue(g.finalizado)
        self.assertEqual(self.finales, [0])
        t = self.textos(g.cuerpo)
        self.assertIn("Te quedaste sin espacio", t)
        self.assertIn("+1", t)

    def test_lineas_premio_y_record(self):
        g = self.abrir(record=1)
        for y in range(16, 20):
            for x in range(9):
                g.juego.tablero[y][x] = "X"
        g.juego.pieza.rot, g.juego.pieza.x, g.juego.pieza.y = 1, 7, 0
        g.tecla("space")                                             # 4 líneas de golpe
        self.assertEqual(g.juego.lineas, 4)
        g.juego.terminado = True
        g._paso()
        t = self.textos(g.cuerpo)
        self.assertIn("+2", t)
        self.assertIn("¡Nuevo récord!", t)
        self.assertEqual(self.finales, [4])

    def test_fin_por_tiempo(self):
        g = self.abrir()
        for _ in range(120):
            g._tick()
        self.assertEqual(self.finales, [0])
        self.assertIn("Se acabó el tiempo", self.textos(g.cuerpo))

    def test_teclas_y_pasos_tras_el_final_no_hacen_nada(self):      # enfoque de revisión 1
        g = self.abrir()
        for _ in range(120):
            g._tick()
        tablero = [list(f) for f in g.juego.tablero]
        g.tecla("space")
        g.tecla("Left")
        g._paso()
        g._tick()
        self.assertEqual((g.juego.tablero, self.finales), (tablero, [0]))

    def test_cerrar_a_mitad_es_abandono_y_los_temporizadores_se_cancelan(self):   # enfoque de revisión 2
        with mock.patch.object(juegos.TetrisGame, "_paso") as paso, mock.patch.object(juegos.TetrisGame, "_tick") as tick:
            g = self.abrir(autotick=True)
            g.cerrar()
            paso.reset_mock()                                      # abrir la ventana tarda: algún paso pudo ocurrir antes de cerrar
            tick.reset_mock()
            self.bombear(1300)
        self.assertEqual((paso.call_count, tick.call_count), (0, 0))
        self.assertEqual(self.finales, [None])

    def test_el_tablero_cabe_en_una_ventana_pequena(self):          # enfoque de revisión 5
        with mock.patch.object(ctk.CTkToplevel, "winfo_screenheight", lambda self: 768):
            g = self.abrir()
        self.assertEqual(g.celda, max(12, min(28, (g.alto_ventana - 150) // 20)))
        self.assertLessEqual(g.celda * 20, g.alto_ventana - 130)

    def test_el_tablero_aprovecha_la_escala_de_pantalla(self):      # hallazgo de la verificación visual
        g = self.abrir()
        self.assertEqual(g.celda_px, max(1, int(g.celda * g.escala)))
        self.assertEqual(int(g.canvas.cget("height")), g.celda_px * 20)
        self.assertEqual(int(g.canvas_sig.cget("width")), g.celda_px * 4)
        self.assertLessEqual(g.celda_px * 20, int((g.alto_ventana - 130) * g.escala))

    def test_con_los_temporizadores_reales_la_pieza_baja_sola(self):
        g = self.abrir(autotick=True)
        y0 = g.juego.pieza.y
        self.assertTrue(self.esperar(lambda: g.juego.pieza.y > y0, seg=3.0))


# ==============================================================================
# TAREA 5: pestaña Arena y HUD
# ==============================================================================
class TestViewArena(UITestCase):
    def setUp(self):
        super().setUp()
        self.lanzamientos, self.huds, self.boveda = [], 0, None
        self._parches = [mock.patch.object(juegos, "lanzar_duelo", self._falso_lanzar_duelo),
                         mock.patch.object(juegos, "lanzar_serpiente", self._falso_arcade("serpiente")),
                         mock.patch.object(juegos, "lanzar_tetris", self._falso_arcade("tetris"))]
        for parche in self._parches:
            parche.start()

    def tearDown(self):
        for parche in self._parches:
            parche.stop()
        super().tearDown()

    def _ventana_falsa(self):
        v = types.SimpleNamespace(vivo=True, alzadas=0, estado="normal", restauradas=0)
        v.winfo_exists = lambda: v.vivo
        v.destroy = lambda: setattr(v, "vivo", False)
        v.lift = lambda: setattr(v, "alzadas", v.alzadas + 1)
        v.focus_force = lambda: None
        v.state = lambda: v.estado
        v.deiconify = lambda: (setattr(v, "restauradas", v.restauradas + 1), setattr(v, "estado", "normal"))
        return v

    def _falso_lanzar_duelo(self, master, materia, pool, color, on_finish, on_revancha=None, corazones=None, rng=None):
        self.lanzamientos.append({"juego": "duelo", "materia": materia, "pool": pool, "corazones_al_lanzar": self.boveda.corazones_arena})
        return self._ventana_falsa()

    def _falso_arcade(self, juego):
        def falso(master, color, on_finish, on_revancha=None, corazones=None, record=0, rng=None):
            self.lanzamientos.append({"juego": juego, "record": record, "corazones_al_lanzar": self.boveda.corazones_arena})
            return self._ventana_falsa()
        return falso

    def vista(self, corazones, grado="11"):
        self.lanzamientos, self.huds = [], 0
        b = APP_final.BovedaCore("ana", grado)
        b.corazones_arena, b.arena_fecha = corazones, date.today().isoformat()
        self.boveda = b
        v = APP_final.ViewArena(ctk.CTkFrame(ROOT), b, self._hud)
        ROOT.update()
        return v

    def _hud(self):
        self.huds += 1

    def test_corazones_en_pantalla(self):
        v = self.vista(corazones=3)
        self.assertEqual(v.lbl_corazones.cget("text"), "❤️❤️❤️🤍🤍 3/5")

    def test_jugar_gasta_el_corazon_antes_de_abrir_el_duelo(self):
        v = self.vista(corazones=5)
        v.combo_materia.set("Física")
        v.jugar()
        self.assertEqual(self.lanzamientos[0]["corazones_al_lanzar"], 4)
        self.assertEqual(self.lanzamientos[0]["materia"], "Física")
        self.assertTrue(all(len(p) == 4 for p in self.lanzamientos[0]["pool"]))
        self.assertGreaterEqual(self.huds, 1)                                    # guardó el progreso al gastar

    def test_sin_corazones_no_se_puede_jugar(self):
        v = self.vista(corazones=0)
        v.jugar()
        self.assertEqual(self.lanzamientos, [])
        self.assertEqual(str(v.btn_jugar.cget("state")), "disabled")
        self.assertIn("Sin corazones: vuelven mañana", v.lbl_resultado.cget("text") + v.lbl_corazones.cget("text"))

    def test_banco_pequeno_no_gasta_el_corazon(self):                           # enfoque de revisión 1
        v = self.vista(corazones=5, grado="7")                                   # el grado 7 no tiene contenido
        v.jugar()
        self.assertEqual((self.lanzamientos, v.boveda.corazones_arena), ([], 5))
        self.assertIn("preguntas", v.lbl_resultado.cget("text"))

    def test_no_abre_dos_duelos_ni_gasta_dos_corazones(self):                   # enfoque de revisión 5
        v = self.vista(corazones=5)
        v.jugar()
        v.jugar()
        self.assertEqual((len(self.lanzamientos), v.boveda.corazones_arena), (1, 4))

    def test_despues_de_terminar_se_puede_jugar_otro_y_se_cierra_la_ventana_vieja(self):
        v = self.vista(corazones=5)
        v.jugar()
        vieja = v.ventana
        v._al_terminar("victoria")
        v.jugar()
        self.assertFalse(vieja.winfo_exists())
        self.assertEqual(len(self.lanzamientos), 2)

    def test_premios_suman_monedas_y_puntos_y_el_abandono_no(self):
        for resultado, monedas in (("victoria", 10), ("empate", 5), ("derrota", 2), ("abandono", 0)):
            v = self.vista(corazones=5)
            v._al_terminar(resultado)
            self.assertEqual((v.boveda.coins, v.boveda.puntos), (monedas, monedas))
            self.assertEqual(self.huds, 1)
            if monedas:
                self.assertIn(f"+{monedas}", v.lbl_resultado.cget("text"))

    def test_sin_grado_usa_el_ultimo_grado_y_ofrece_mezcla(self):
        v = self.vista(corazones=5, grado=None)
        valores = v.combo_materia.cget("values")
        self.assertEqual(valores[0], "Mezcla")
        self.assertIn("Física", valores)
        v.jugar()
        self.assertEqual(len(self.lanzamientos), 1)

    def test_revancha_cierra_el_duelo_y_gasta_otro_corazon(self):
        v = self.vista(corazones=5)
        v.jugar()
        v._revancha()
        self.assertEqual((len(self.lanzamientos), v.boveda.corazones_arena), (2, 3))

    def test_el_refresco_recarga_corazones_de_un_dia_nuevo_sin_reiniciar_sesion(self):   # hallazgo de la revisión final
        v = self.vista(corazones=0)
        self.assertEqual(str(v.btn_jugar.cget("state")), "disabled")
        self.boveda.arena_fecha = (date.today() - timedelta(days=1)).isoformat()         # pasó la medianoche con la app abierta
        v._refresco_periodico()
        self.assertEqual(str(v.btn_jugar.cget("state")), "normal")
        self.assertEqual(v.lbl_corazones.cget("text"), "❤️❤️❤️❤️❤️ 5/5")

    # -- 3b: serpiente y Tetris desde la pestaña -----------------------------------------------
    def test_jugar_arcade_gasta_el_corazon_antes_de_abrir_y_pasa_el_record(self):
        v = self.vista(corazones=5)
        v.boveda.records["tetris"] = 4
        v.jugar_tetris()
        lanzamiento = self.lanzamientos[0]
        self.assertEqual((lanzamiento["juego"], lanzamiento["corazones_al_lanzar"], lanzamiento["record"]), ("tetris", 4, 4))
        self.assertGreaterEqual(self.huds, 1)

    def test_sin_corazones_desactiva_los_tres_botones(self):
        v = self.vista(corazones=0)
        for boton in (v.btn_jugar, v.btn_serpiente, v.btn_tetris):
            self.assertEqual(str(boton.cget("state")), "disabled")
        v.jugar_serpiente()
        v.jugar_tetris()
        self.assertEqual(self.lanzamientos, [])
        self.assertIn("Sin corazones: vuelven mañana", v.lbl_resultado.cget("text"))

    def test_premio_y_record_arcade(self):
        v = self.vista(corazones=5)
        v._al_terminar_arcade("serpiente", 8)
        self.assertEqual((v.boveda.coins, v.boveda.puntos, v.boveda.records), (2, 2, {"serpiente": 8}))
        self.assertIn("+2", v.lbl_resultado.cget("text"))
        self.assertIn("¡Nuevo récord!", v.lbl_resultado.cget("text"))
        v._al_terminar_arcade("serpiente", 3)
        self.assertEqual((v.boveda.coins, v.boveda.records["serpiente"]), (3, 8))
        self.assertNotIn("récord", v.lbl_resultado.cget("text"))
        v._al_terminar_arcade("tetris", 9)
        self.assertEqual(v.boveda.coins, 6)                                   # 2 + 1 + 3

    def test_abandono_arcade_sin_premio_ni_record(self):
        v = self.vista(corazones=5)
        v._al_terminar_arcade("tetris", None)
        self.assertEqual((v.boveda.coins, v.boveda.records), (0, {}))
        self.assertIn("Abandonaste la partida: sin premio, el corazón ya estaba gastado.", v.lbl_resultado.cget("text"))

    def test_la_revancha_repite_el_mismo_juego(self):
        v = self.vista(corazones=5)
        v.jugar_tetris()
        v._revancha()
        self.assertEqual([l["juego"] for l in self.lanzamientos], ["tetris", "tetris"])
        self.assertEqual(v.boveda.corazones_arena, 3)
        v._al_terminar_arcade("tetris", 1)                                    # la partida terminó
        v.jugar()
        v._revancha()
        self.assertEqual(self.lanzamientos[-1]["juego"], "duelo")

    def test_si_falla_la_apertura_se_devuelve_el_corazon(self):
        v = self.vista(corazones=5)
        with mock.patch.object(juegos, "lanzar_tetris", side_effect=RuntimeError("falló")):
            v.jugar_tetris()
        self.assertEqual(v.boveda.corazones_arena, 5)
        self.assertFalse(v._en_curso)
        self.assertIn("Te devolvimos el corazón", v.lbl_resultado.cget("text"))
        v.jugar_serpiente()
        self.assertEqual(len(self.lanzamientos), 1)                           # la pestaña sigue viva
        with mock.patch.object(juegos, "lanzar_duelo", side_effect=RuntimeError("falló")):
            v._al_terminar_arcade("serpiente", 1)
            v.jugar()
        self.assertEqual(v.boveda.corazones_arena, 4)                         # el del duelo fallido también volvió

    def test_pulsar_con_una_partida_abierta_la_trae_al_frente(self):
        v = self.vista(corazones=5)
        v.jugar_serpiente()
        v.jugar_tetris()
        self.assertEqual((len(self.lanzamientos), v.boveda.corazones_arena), (1, 4))
        self.assertEqual(v.ventana.alzadas, 1)

    def test_pulsar_con_la_partida_minimizada_la_restaura(self):           # hallazgo de la revisión final
        v = self.vista(corazones=5)
        v.jugar_serpiente()
        v.ventana.estado = "iconic"
        v.jugar_tetris()
        self.assertEqual((v.ventana.restauradas, v.ventana.estado, v.ventana.alzadas), (1, "normal", 1))
        self.assertEqual((len(self.lanzamientos), v.boveda.corazones_arena), (1, 4))

    def test_si_la_ventana_falla_a_medio_construir_no_queda_abierta_y_se_devuelve_el_corazon(self):   # hallazgo
        v = self.vista(corazones=5)
        antes = len([w for w in ROOT.winfo_children() if isinstance(w, ctk.CTkToplevel)])
        with mock.patch.object(juegos, "lanzar_tetris", REAL_LANZAR_TETRIS), \
                mock.patch.object(juegos.tetris, "Tetris", side_effect=RuntimeError("falló construir")):
            v.jugar_tetris()
        self.bombear(400)
        self.assertEqual((v.boveda.corazones_arena, v._en_curso, v.ventana), (5, False, None))
        self.assertIn("Te devolvimos el corazón", v.lbl_resultado.cget("text"))
        self.assertNotIn("Abandonaste", v.lbl_resultado.cget("text"))
        self.assertEqual(len([w for w in ROOT.winfo_children() if isinstance(w, ctk.CTkToplevel)]), antes)


class TestPestanaYHud(UITestCase):
    def setUp(self):
        super().setUp()
        almacen.RUTA = os.path.join(_TMP, f"pestana_{time.time_ns()}.db")
        almacen.iniciar()
        with almacen._con() as con:
            con.execute("DELETE FROM usuarios")
        almacen.crear_usuario("ana", "a@edu.co", "clave", "Estudiante", None, "11")
        almacen.crear_usuario("profe", "p@edu.co", "clave", "Profesor", "Física", None)
        self._sin_red = mock.patch.object(APP_final, "generar_avatar_2d", side_effect=RuntimeError("sin red en las pruebas"))
        self._sin_red.start()

    def tearDown(self):
        ROOT.mostrar_auth()
        self._sin_red.stop()
        super().tearDown()

    def buscar(self, w, clase):
        return [h for h in self.hijos(w) if isinstance(h, clase)]

    def test_el_estudiante_tiene_pestana_arena_y_linea_en_el_hud(self):
        ROOT.iniciar_sesion("ana", almacen.obtener_usuario("ana"))
        ROOT.update()
        self.assertTrue(self.buscar(ROOT, APP_final.ViewArena))
        self.assertEqual(ROOT.lbl_arena.cget("text"), "⚔️ Arena: 5/5")
        ROOT.boveda.gastar_corazon_arena()
        ROOT.actualizar_hud()
        self.assertEqual(ROOT.lbl_arena.cget("text"), "⚔️ Arena: 4/5")

    def test_profesor_y_administrador_no_tienen_arena(self):
        ROOT.iniciar_sesion("profe", almacen.obtener_usuario("profe"))
        ROOT.update()
        self.assertFalse(self.buscar(ROOT, APP_final.ViewArena))
        self.assertIsNone(ROOT.lbl_arena)
        ROOT.iniciar_sesion("luix", {"role": "Administrador", "materia": None, "correo": "x", "grado": None})
        ROOT.update()
        self.assertFalse(self.buscar(ROOT, APP_final.ViewArena))
        self.assertIsNone(ROOT.lbl_arena)


if __name__ == "__main__":
    unittest.main()
