"""Pruebas del logo de Neon OS: archivos generados, recorte del rótulo, icono de las ventanas y logo en la pantalla de acceso.

Ejecutar desde esta carpeta:   python pruebas_logo.py -v
Usa una base de datos temporal (nunca toca neon_os.db).
"""
import atexit
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

_TMP = tempfile.mkdtemp(prefix="neon_logo_")
atexit.register(shutil.rmtree, _TMP, ignore_errors=True)
os.environ["NEON_DB"] = os.path.join(_TMP, "import.db")   # antes de importar almacen / APP_final
CARPETA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CARPETA)

import customtkinter as ctk
from PIL import Image

import APP_final
import preparar_logo
import rutas

ROOT = None


def setUpModule():
    global ROOT
    ROOT = ctk.CTk()
    ROOT.withdraw()


def tearDownModule():
    for _ in range(10):
        ROOT.update()
        time.sleep(0.02)
    ROOT.destroy()


def hicono(ventana):
    """El icono grande que Windows tiene asignado a la ventana (0 = ninguno propio). Tk no permite leerlo de vuelta con wm iconbitmap."""
    import ctypes
    return ctypes.windll.user32.SendMessageW(int(ventana.wm_frame(), 16), 0x007F, 1, 0)     # WM_GETICON, ICON_BIG


def esperar(segundos):
    """Deja correr la ventana (customtkinter pone su icono por defecto 200 ms después de abrirla)."""
    fin = time.time() + segundos
    while time.time() < fin:
        ROOT.update()
        time.sleep(0.02)


def imagen_con_rotulo(ruta, con_rotulo=True):
    """Fondo transparente, un dibujo grande (rojo) y, si se pide, un rótulo pequeño y separado arriba (como «LOGOTIPO PRINCIPAL»)."""
    img = Image.new("RGBA", (200, 220), (0, 0, 0, 0))
    if con_rotulo:
        img.paste((40, 40, 40, 255), (30, 10, 170, 30))           # rótulo: filas 10-29
    img.paste((220, 20, 20, 255), (50, 80, 150, 200))             # dibujo: filas 80-199, columnas 50-149
    img.save(ruta)
    return ruta


class TestArchivosDelLogo(unittest.TestCase):
    def test_estan_el_original_el_logo_de_la_app_y_el_icono(self):
        for nombre in ("logo.png", "logo_app.png", "logo.ico"):
            with self.subTest(nombre=nombre):
                self.assertTrue(os.path.isfile(os.path.join(CARPETA, nombre)))

    def test_el_logo_de_la_app_es_rgba_con_fondo_transparente_y_sin_bordes_vacios(self):
        with Image.open(os.path.join(CARPETA, "logo_app.png")) as img:
            img.load()
        self.assertEqual(img.mode, "RGBA")
        for esquina in ((0, 0), (img.width - 1, 0), (0, img.height - 1), (img.width - 1, img.height - 1)):
            self.assertEqual(img.getpixel(esquina)[3], 0, esquina)
        caja = img.getchannel("A").point(lambda a: 255 if a > preparar_logo.UMBRAL_ALFA else 0).getbbox()
        self.assertTrue(caja[0] > 0 and caja[1] > 0 and caja[2] < img.width and caja[3] < img.height)    # hay un poco de margen
        self.assertGreater(img.width, 100)
        self.assertGreater(img.height, 100)

    def test_el_icono_trae_los_tamanos_de_windows(self):
        with Image.open(os.path.join(CARPETA, "logo.ico")) as ico:
            self.assertTrue({(16, 16), (32, 32), (48, 48), (256, 256)} <= set(ico.ico.sizes()))

    def test_el_logo_de_la_app_sale_del_original_con_el_script(self):
        with tempfile.TemporaryDirectory() as carpeta:
            tamano = preparar_logo.preparar(os.path.join(CARPETA, "logo.png"), carpeta)
            with Image.open(os.path.join(carpeta, "logo_app.png")) as png, Image.open(os.path.join(carpeta, "logo.ico")) as ico:
                self.assertEqual(png.size, tamano)
                self.assertEqual(sorted(ico.ico.sizes()), sorted(preparar_logo.TAMANOS_ICO))


class TestRecorte(unittest.TestCase):
    def test_se_quita_el_rotulo_suelto_y_se_conserva_el_dibujo(self):
        with tempfile.TemporaryDirectory() as carpeta:
            with Image.open(imagen_con_rotulo(os.path.join(carpeta, "a.png"))) as a, \
                    Image.open(imagen_con_rotulo(os.path.join(carpeta, "b.png"), con_rotulo=False)) as b:
                con, sin = preparar_logo.recortar_logo(a), preparar_logo.recortar_logo(b)
        self.assertEqual(con.size, sin.size)                             # el rótulo no cambia nada
        margen = round(120 * preparar_logo.MARGEN)
        self.assertEqual(con.size, (100 + 2 * margen, 120 + 2 * margen))  # justo el dibujo (100x120) más el margen
        self.assertEqual(con.getpixel((con.width // 2, con.height // 2))[:3], (220, 20, 20))
        self.assertTrue(all(con.getpixel((x, y))[3] == 0 for x in (0, con.width - 1) for y in (0, con.height - 1)))

    def test_una_imagen_sin_dibujo_no_rompe_el_script(self):
        vacia = Image.new("RGBA", (50, 50), (0, 0, 0, 0))
        self.assertEqual(preparar_logo.recortar_logo(vacia).size, (50, 50))

    def test_el_cuadrado_para_el_icono_centra_el_logo(self):
        lienzo = preparar_logo.cuadrado(Image.new("RGBA", (200, 100), (255, 0, 0, 255)), 64)
        self.assertEqual(lienzo.size, (64, 64))
        self.assertEqual(lienzo.getpixel((32, 32))[3], 255)
        self.assertEqual(lienzo.getpixel((32, 2))[3], 0)                  # arriba queda transparente


class TestRecursosEIcono(unittest.TestCase):
    def test_recurso_busca_junto_al_codigo_y_dentro_del_paquete_del_exe(self):
        self.assertEqual(rutas.recurso("logo.ico"), os.path.join(CARPETA, "logo.ico"))
        with mock.patch.object(sys, "_MEIPASS", r"C:\paquete\_internal", create=True):
            self.assertEqual(rutas.recurso("logo.ico"), os.path.join(r"C:\paquete\_internal", "logo.ico"))

    @unittest.skipUnless(sys.platform.startswith("win"), "el icono .ico es de Windows")
    def test_poner_icono_aplica_el_logo(self):
        con, sin = ctk.CTkToplevel(ROOT), ctk.CTkToplevel(ROOT)
        try:
            rutas.poner_icono(con)
            esperar(0.5)
            self.assertNotEqual(hicono(con), 0)
            self.assertNotEqual(hicono(con), hicono(sin))               # «sin» se queda con el icono azul de customtkinter
        finally:
            con.destroy(); sin.destroy()

    def test_poner_icono_pasa_la_ruta_del_logo(self):
        ventana = mock.Mock()
        rutas.poner_icono(ventana)
        ventana.iconbitmap.assert_called_once_with(os.path.join(CARPETA, "logo.ico"))

    def test_poner_icono_no_rompe_nada_si_falta_el_archivo_o_el_sistema_lo_rechaza(self):
        ventana = mock.Mock()
        with mock.patch.object(rutas, "recurso", return_value=os.path.join(_TMP, "no-existe.ico")):
            rutas.poner_icono(ventana)
        ventana.iconbitmap.assert_not_called()
        ventana.iconbitmap.side_effect = RuntimeError("no se pudo")
        rutas.poner_icono(ventana)                                           # no lanza (con el archivo real)

    @unittest.skipUnless(sys.platform.startswith("win"), "el icono .ico es de Windows")
    def test_la_ventana_principal_usa_el_logo_como_icono(self):
        guion = os.path.join(_TMP, "ventana_principal.py")
        with open(guion, "w", encoding="utf-8") as f:
            f.write("import os, sys, tempfile, tkinter as tk\n"
                    "sys.path.insert(0, sys.argv[1])\n"
                    "os.environ['NEON_DB'] = os.path.join(tempfile.mkdtemp(), 'x.db')\n"
                    "import APP_final\n"
                    "import ctypes, time, customtkinter as ctk\n"
                    "app = APP_final.MainApp()\n"
                    "sin = ctk.CTkToplevel(app)   # una ventana sin iconbitmap: se queda con el icono por defecto de customtkinter\n"
                    "fin = time.time() + 0.6\n"
                    "while time.time() < fin: app.update(); time.sleep(0.02)\n"
                    "h = lambda v: ctypes.windll.user32.SendMessageW(int(v.wm_frame(), 16), 0x7F, 1, 0)\n"
                    "print('ICONO_APP=%d ICONO_POR_DEFECTO=%d' % (h(app), h(sin)))\n"
                    "app.destroy()\n")
        r = subprocess.run([sys.executable, guion, CARPETA], capture_output=True, text=True, encoding="utf-8", timeout=90, cwd=_TMP)
        self.assertEqual(r.returncode, 0, r.stderr)
        encontrado = re.search(r"ICONO_APP=(\d+) ICONO_POR_DEFECTO=(\d+)", r.stdout)
        self.assertIsNotNone(encontrado, r.stdout)
        propio, defecto = int(encontrado.group(1)), int(encontrado.group(2))
        self.assertNotEqual(propio, 0)
        self.assertNotEqual(propio, defecto)


class TestLogoEnLaPantallaDeAcceso(unittest.TestCase):
    def test_cargar_logo_respeta_la_proporcion(self):
        logo = APP_final.cargar_logo(110)
        with Image.open(os.path.join(CARPETA, "logo_app.png")) as original:
            ancho, alto = original.size
        self.assertEqual(logo.cget("size")[1], 110)
        self.assertEqual(logo.cget("size")[0], round(ancho * 110 / alto))

    def test_sin_el_archivo_la_app_funciona_sin_logo(self):
        with mock.patch.object(rutas, "recurso", return_value=os.path.join(_TMP, "no-existe.png")):
            self.assertIsNone(APP_final.cargar_logo(110))
            vista = APP_final.ViewAuth(ROOT, APP_final.DatabaseManager(), lambda *a: None)
            try:
                self.assertIsNone(vista.lbl_logo)
                self.assertEqual(vista.lbl_title.cget("text"), "Acceso NeonOS")
            finally:
                vista.destroy()

    def test_la_pantalla_de_acceso_muestra_el_logo_encima_del_titulo(self):
        vista = APP_final.ViewAuth(ROOT, APP_final.DatabaseManager(), lambda *a: None)
        try:
            vista.pack(fill="both", expand=True)
            ROOT.update()
            self.assertIsNotNone(vista.lbl_logo)
            self.assertEqual(vista.lbl_logo.winfo_manager(), "pack")
            self.assertLess(vista.lbl_logo.winfo_y(), vista.lbl_title.winfo_y())       # arriba del título
            self.assertGreater(vista.lbl_logo.winfo_height(), 50)
        finally:
            vista.destroy()

    def test_el_logo_solo_va_en_el_login_y_vuelve_al_regresar(self):
        import almacen
        almacen.iniciar()
        vista = APP_final.ViewAuth(ROOT, APP_final.DatabaseManager(), lambda *a: None)
        try:
            vista.pack(fill="both", expand=True)
            ROOT.update()
            self.assertEqual(vista.lbl_logo.winfo_manager(), "pack")
            vista.toggle_mode()
            self.assertEqual(vista.lbl_logo.winfo_manager(), "")                       # registro: escondido (la tarjeta es más alta)
            vista.toggle_mode()
            self.assertEqual(vista.lbl_logo.winfo_manager(), "pack")                   # de vuelta al login: reaparece
            vista.mostrar_verificacion(almacen.ADMINISTRADORES[0])
            self.assertEqual(vista.lbl_logo.winfo_manager(), "")                       # verificación: escondido
            vista.volver()
            ROOT.update()
            self.assertEqual(vista.lbl_logo.winfo_manager(), "pack")                   # y vuelve
            self.assertLess(vista.lbl_logo.winfo_y(), vista.lbl_title.winfo_y())
        finally:
            vista.destroy()

    def test_la_tarjeta_cabe_en_la_ventana_de_1150x850_en_todas_las_pantallas(self):
        import almacen
        almacen.iniciar()
        almacen.crear_usuario("profe", "profe@correo.test", "clave123", "Profesor", "Física", None, verificado=False)
        almacen.crear_usuario("ana", "ana@correo.test", "clave123", "Estudiante", None, "11", verificado=False)
        vista = APP_final.ViewAuth(ROOT, APP_final.DatabaseManager(), lambda *a: None)
        try:
            vista.pack(fill="both", expand=True)
            alturas = {}
            vista._poner_modo(True); ROOT.update(); alturas["login"] = vista.card.winfo_height()
            for rol in ("Estudiante", "Profesor"):
                vista.rol_var.set(rol); vista._poner_modo(False); ROOT.update(); alturas["registro " + rol] = vista.card.winfo_height()
            for usuario in ("ana", "profe", almacen.ADMINISTRADORES[0]):
                vista.mostrar_verificacion(usuario); ROOT.update(); alturas["verificación " + usuario] = vista.card.winfo_height()
            self.assertEqual({k: v for k, v in alturas.items() if v > 850 - 30}, {}, alturas)    # 30 px de aire arriba y abajo
        finally:
            vista.destroy()


if __name__ == "__main__":
    unittest.main()
