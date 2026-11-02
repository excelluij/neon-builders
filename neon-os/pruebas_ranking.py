"""Pruebas de la pieza 2: ranking top 10 con puntaje acumulado (monedas ganadas, que no baja al comprar).

Ejecutar desde esta carpeta:   python pruebas_ranking.py -v
Usa una base de datos temporal: nunca toca el neon_os.db real.
"""
import atexit
import os
import shutil
import sys
import tempfile
import time
import types
import unittest

_TMP = tempfile.mkdtemp(prefix="neon_ranking_")
atexit.register(shutil.rmtree, _TMP, ignore_errors=True)
os.environ["NEON_DB"] = os.path.join(_TMP, "import.db")  # antes de importar almacen / APP_final
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import customtkinter as ctk

import almacen
import APP_final


def alumno(usuario, puntos, grado="11", rol="Estudiante"):
    """Crea un usuario y, si puntos no es None, su progreso guardado con ese puntaje."""
    almacen.crear_usuario(usuario, f"{usuario}@edu.co", "clave", rol, "Física" if rol == "Profesor" else None, None if rol == "Profesor" else grado)
    if puntos is not None:
        almacen.guardar_progreso(usuario, {"coins": 0, "puntos": puntos})


class BDTestCase(unittest.TestCase):
    def setUp(self):
        almacen.RUTA = os.path.join(_TMP, f"{self.id().split('.')[-1]}_{time.time_ns()}.db")
        almacen.iniciar()
        # iniciar() siembra cuentas de demostración en una base vacía; las quitamos para controlar el escenario
        with almacen._con() as con:
            con.execute("DELETE FROM usuarios")


# ==============================================================================
# REGLAS PURAS
# ==============================================================================
class TestArmarRanking(unittest.TestCase):
    def test_orden_y_puestos(self):
        self.assertEqual(almacen.armar_ranking([("b", 50), ("a", 80), ("c", 20)]), [(1, "a", 80), (2, "b", 50), (3, "c", 20)])

    def test_empates_comparten_puesto(self):
        self.assertEqual(almacen.armar_ranking([("b", 50), ("a", 50), ("c", 30)]), [(1, "a", 50), (1, "b", 50), (3, "c", 30)])

    def test_cero_puntos_no_entra(self):
        self.assertEqual(almacen.armar_ranking([("a", 0), ("b", 5), ("c", -3)]), [(1, "b", 5)])

    def test_vacio(self):
        self.assertEqual(almacen.armar_ranking([]), [])

    def test_top_incluye_a_todos_los_empatados_en_el_puesto_10(self):
        filas = [(f"u{n:02d}", 1000 - n) for n in range(9)] + [("x", 50), ("y", 50), ("z", 50)]
        top = almacen.recortar_top(almacen.armar_ranking(filas))
        self.assertEqual(len(top), 12)
        self.assertEqual({p for p, u, _ in top if u in "xyz"}, {10})

    def test_top_deja_fuera_el_empate_que_empieza_en_el_11(self):
        filas = [(f"u{n:02d}", 1000 - n) for n in range(10)] + [("x", 50), ("y", 50)]
        top = almacen.recortar_top(almacen.armar_ranking(filas))
        self.assertEqual([u for _, u, _ in top], [f"u{n:02d}" for n in range(10)])

    def test_puntos_para_entrar(self):
        ranking = almacen.armar_ranking([(f"u{n:02d}", 100 - n) for n in range(15)])
        self.assertEqual(almacen.puntos_para_entrar(ranking), 91)   # el 10.º tiene 100 - 9
        self.assertEqual(almacen.puntos_para_entrar(almacen.armar_ranking([("a", 5), ("b", 4)])), 1)  # hay sitio libre
        self.assertEqual(almacen.puntos_para_entrar([]), 1)


# ==============================================================================
# BASE DE DATOS
# ==============================================================================
class TestRankingBD(BDTestCase):
    def test_solo_estudiantes_con_puntos(self):
        alumno("ana", 100)
        alumno("beto", 50)
        alumno("cata", None)            # nunca ha jugado: sin progreso
        alumno("dani", 0)
        alumno("profe", 999, rol="Profesor")
        self.assertEqual(almacen.ranking_estudiantes(), [(1, "ana", 100), (2, "beto", 50)])

    def test_filtra_por_grado(self):
        alumno("ana", 100, "11")
        alumno("beto", 300, "10")
        self.assertEqual(almacen.ranking_estudiantes("11"), [(1, "ana", 100)])
        self.assertEqual([u for _, u, _ in almacen.ranking_estudiantes()], ["beto", "ana"])

    def test_progreso_viejo_sin_puntos_usa_las_monedas(self):
        almacen.crear_usuario("viejo", "v@edu.co", "clave", "Estudiante", None, "11")
        almacen.guardar_progreso("viejo", {"coins": 40, "diamonds": 3})
        self.assertEqual(almacen.ranking_estudiantes(), [(1, "viejo", 40)])

    def test_ocultar_y_restaurar(self):
        alumno("ana", 100)
        alumno("beto", 50)
        almacen.ocultar_del_ranking("ana")
        self.assertEqual(almacen.ranking_estudiantes(), [(1, "beto", 50)])
        self.assertEqual(almacen.ocultos_del_ranking(), ["ana"])
        almacen.restaurar_al_ranking("ana")
        self.assertEqual(almacen.ranking_estudiantes()[0], (1, "ana", 100))
        self.assertEqual(almacen.ocultos_del_ranking(), [])

    def test_ocultar_dos_veces_no_falla(self):
        alumno("ana", 100)
        almacen.ocultar_del_ranking("ana")
        almacen.ocultar_del_ranking("ana")
        self.assertEqual(almacen.ocultos_del_ranking(), ["ana"])

    def test_una_base_antigua_se_actualiza_sin_perder_datos(self):
        import sqlite3
        ruta = os.path.join(_TMP, "antigua.db")
        con = sqlite3.connect(ruta)
        con.executescript("""
            CREATE TABLE usuarios (usuario TEXT PRIMARY KEY, clave TEXT NOT NULL, rol TEXT NOT NULL, materia TEXT, correo TEXT, grado TEXT);
            CREATE TABLE misiones (id INTEGER PRIMARY KEY AUTOINCREMENT, materia TEXT NOT NULL, datos TEXT NOT NULL);
            CREATE TABLE progreso (usuario TEXT PRIMARY KEY, datos TEXT NOT NULL);
            INSERT INTO usuarios VALUES ('luis', 'x$y', 'Estudiante', NULL, 'l@edu.co', '11');
            INSERT INTO progreso VALUES ('luis', '{"coins": 100}');
        """)
        con.commit()
        con.close()
        almacen.RUTA = ruta
        almacen.iniciar()
        self.assertEqual(almacen.ranking_estudiantes(), [(1, "luis", 100)])
        self.assertEqual(almacen.ocultos_del_ranking(), [])


# ==============================================================================
# PUNTAJE EN LA BÓVEDA
# ==============================================================================
class TestBovedaPuntos(BDTestCase):
    def test_ganar_suma_monedas_diamantes_y_puntos(self):
        b = APP_final.BovedaCore("ana", "11")
        b.ganar(10, 2)
        self.assertEqual((b.coins, b.diamonds, b.puntos), (10, 2, 10))

    def test_comprar_no_baja_los_puntos(self):
        b = APP_final.BovedaCore("ana", "11")
        b.ganar(100, 0)
        ok, _ = b.comprar_item(60, 0, "Avatar Robot")
        self.assertTrue(ok)
        self.assertEqual((b.coins, b.puntos), (40, 100))

    def test_exportar_importar(self):
        b = APP_final.BovedaCore("ana", "11")
        b.ganar(30, 1)
        otro = APP_final.BovedaCore("ana", "11")
        otro.importar(b.exportar())
        self.assertEqual(otro.puntos, 30)

    def test_importar_progreso_viejo_arranca_con_las_monedas_actuales(self):
        b = APP_final.BovedaCore("ana", "11")
        b.importar({"coins": 40, "diamonds": 3, "hearts": 4})
        self.assertEqual(b.puntos, 40)

    def test_victoria_del_quiz_suma_puntos(self):
        b = APP_final.BovedaCore("ana", "11")
        b.procesar_victoria_quiz()
        self.assertEqual((b.coins, b.puntos), (5, 5))

    def test_archivo_validado_suma_puntos(self):
        b = APP_final.BovedaCore("ana", "11")
        ruta = os.path.join(_TMP, "apuntes.txt")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write("Mis apuntes sobre la derivada de una función")
        ok, msg = b.procesar_archivo_estricto(ruta, "Matemáticas", "derivada", True, 25, 4)
        self.assertTrue(ok, msg)
        self.assertEqual((b.coins, b.puntos), (25, 25))

    def _vista_estudiante(self, boveda):
        log = types.SimpleNamespace(configure=lambda **k: None)
        return types.SimpleNamespace(boveda=boveda, lbl_log=log, update_hud=lambda: None, abrir_materia=lambda m: None,
                                     clave_juego=lambda m, t: f"{m}#{t['titulo']}")

    def test_responder_pregunta_suma_puntos(self):
        b = APP_final.BovedaCore("ana", "11")
        entrada = types.SimpleNamespace(get=lambda: "una opinión bien completa", delete=lambda *a: None)
        APP_final.ViewEstudianteTablero.responder_pregunta(self._vista_estudiante(b), "Física", {"monedas": 12, "diamantes": 1}, entrada)
        self.assertEqual((b.coins, b.puntos), (12, 12))

    def test_terminar_un_juego_suma_puntos_proporcionales(self):
        b = APP_final.BovedaCore("ana", "11")
        APP_final.ViewEstudianteTablero.finalizar_juego(self._vista_estudiante(b), "Física", {"titulo": "J", "monedas": 100, "diamantes": 10}, 0.5)
        self.assertEqual((b.coins, b.puntos), (50, 50))


# ==============================================================================
# LA VISTA
# ==============================================================================
class TestVistaRanking(BDTestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ctk.CTk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        for _ in range(10):
            cls.root.update()
            time.sleep(0.02)
        cls.root.destroy()

    def poblar(self, n=15):
        """s01 tiene 150 pts, s02 140 ... s15 10 pts (grado 11). El 10.º (s10) tiene 60."""
        for k in range(1, n + 1):
            alumno(f"s{k:02d}", (16 - k) * 10)

    def vista(self, usuario=None, rol="Estudiante", puntos=None, grado="11"):
        b = APP_final.BovedaCore(usuario or "profe", grado if rol == "Estudiante" else None)
        if puntos is not None:
            b.puntos = puntos
        v = APP_final.ViewLeaderboard(ctk.CTkFrame(self.root), b, rol=rol)
        self.root.update()
        return v

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

    def hijos(self, w):
        for h in w.winfo_children():
            yield h
            yield from self.hijos(h)

    def boton(self, v, texto):
        return [h for h in self.hijos(v) if isinstance(h, ctk.CTkButton) and texto in h.cget("text")]

    # -- estudiante --
    def test_estudiante_ve_solo_el_top_10(self):
        self.poblar()
        v = self.vista("s12", puntos=40)
        self.assertEqual([u for _, u, _ in v.mostrados], [f"s{k:02d}" for k in range(1, 11)])
        t = self.textos(v)
        self.assertIn("S01", t)
        self.assertNotIn("S15", t)      # el último puesto jamás se muestra
        self.assertNotIn("S11", t)

    def test_estudiante_fuera_del_top_ve_su_puntaje_y_cuanto_le_falta_sin_puesto(self):
        self.poblar()
        v = self.vista("s12", puntos=40)
        t = v.lbl_tarjeta.cget("text")
        self.assertIn("40 pts", t)
        self.assertIn("te faltan 20", t)   # el 10.º tiene 60
        self.assertNotIn("#", t)
        self.assertNotIn("puesto", t.lower())
        self.assertNotIn("(Tú)", self.textos(v))

    def test_estudiante_dentro_del_top_aparece_resaltado(self):
        self.poblar()
        v = self.vista("s03", puntos=130)
        self.assertIn("top 10", v.lbl_tarjeta.cget("text"))
        self.assertIn("S03 (Tú)", self.textos(v))

    def test_usa_el_puntaje_en_vivo_del_estudiante(self):
        self.poblar()
        v = self.vista("s12", puntos=500)     # en la base tiene 40, pero acaba de ganar mucho
        self.assertEqual(v.mostrados[0][1], "s12")
        self.assertIn("S12 (Tú)", self.textos(v))
        self.assertEqual(len([1 for _, u, _ in v.mostrados if u == "s12"]), 1)

    def test_estudiante_sin_puntos(self):
        self.poblar()
        alumno("nuevo", None)
        v = self.vista("nuevo", puntos=0)
        self.assertIn("primer punto", v.lbl_tarjeta.cget("text"))

    def test_solo_ve_a_los_de_su_grado(self):
        self.poblar()
        alumno("mayor", 9999, "10")
        v = self.vista("s12", puntos=40)
        self.assertNotIn("Mayor", self.textos(v))

    def test_el_primero_lleva_medalla(self):
        self.poblar()
        self.assertIn("🥇", self.textos(self.vista("s12", puntos=40)))

    def test_ranking_vacio(self):
        alumno("solo", None)
        v = self.vista("solo", puntos=0)
        self.assertIn("Aún nadie", self.textos(v))

    def test_estudiante_oculto_ve_su_puntaje_sin_promesas(self):
        self.poblar()
        almacen.ocultar_del_ranking("s12")
        v = self.vista("s12", puntos=40)
        t = v.lbl_tarjeta.cget("text")
        self.assertIn("40 pts", t)
        self.assertNotIn("faltan", t)
        self.assertNotIn("S12", self.textos(v))

    # -- profesor y administrador --
    def test_profesor_ve_el_top_de_todos_los_grados_sin_tarjeta_personal(self):
        self.poblar()
        alumno("mayor", 9999, "10")
        v = self.vista(rol="Profesor")
        self.assertIsNone(v.lbl_tarjeta)
        self.assertEqual(v.mostrados[0][1], "mayor")
        self.assertIn("Participan: 16", self.textos(v))
        self.assertEqual(self.boton(v, "Ocultar"), [])

    def test_administrador_oculta_y_restaura(self):
        self.poblar()
        v = self.vista(rol="Administrador")
        botones = self.boton(v, "Ocultar")
        self.assertEqual(len(botones), 10)
        botones[0].invoke()
        self.root.update()
        self.assertEqual(almacen.ocultos_del_ranking(), ["s01"])
        self.assertNotIn("S01", [f"S{u[1:]}" for _, u, _ in v.mostrados])
        self.assertEqual(v.mostrados[0][1], "s02")
        restaurar = self.boton(v, "Restaurar")
        self.assertEqual(len(restaurar), 1)
        restaurar[0].invoke()
        self.root.update()
        self.assertEqual(almacen.ocultos_del_ranking(), [])
        self.assertEqual(v.mostrados[0][1], "s01")

    def test_actualizar_relee_la_base_compartida(self):
        self.poblar()
        v = self.vista("s12", puntos=40)
        almacen.guardar_progreso("s15", {"coins": 0, "puntos": 1000})   # otro estudiante gana puntos
        self.boton(v, "Actualizar")[0].invoke()
        self.root.update()
        self.assertEqual(v.mostrados[0][1], "s15")


if __name__ == "__main__":
    unittest.main()
