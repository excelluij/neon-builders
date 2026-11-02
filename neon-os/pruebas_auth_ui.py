"""Pruebas de la pantalla de acceso con verificación de correo (ViewAuth), con widgets reales.

Ejecutar desde esta carpeta:   python pruebas_auth_ui.py -v
Usa una base de datos temporal (nunca toca neon_os.db) y un emisor FALSO: no envía correos reales.
"""
import atexit
import contextlib
import io
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

_TMP = tempfile.mkdtemp(prefix="neon_authui_")
atexit.register(shutil.rmtree, _TMP, ignore_errors=True)
os.environ["NEON_DB"] = os.path.join(_TMP, "import.db")   # antes de importar almacen / APP_final
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import customtkinter as ctk

import almacen
import APP_final
import correo
from correo import ErrorCorreo
from pruebas_verificacion import CONFIG, BDTestCase, Emisor, Reloj

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


class EmisorLento(Emisor):
    """Se queda esperando hasta que la prueba lo libere: permite probar el estado «ocupado» de la interfaz."""

    def __init__(self):
        super().__init__()
        self.libre = threading.Event()

    def __call__(self, destino, codigo, config=None, **kw):
        self.libre.wait(5)
        return super().__call__(destino, codigo, config, **kw)


class AuthUITestCase(BDTestCase):
    def setUp(self):
        super().setUp()
        self.emisor, self.reloj, self.entradas = Emisor(), Reloj(1000.0), []
        self.vista = None

    def tearDown(self):
        if self.vista is not None:
            self.vista.destroy()
        super().tearDown()

    def abrir(self, db=None):
        db = db or APP_final.DatabaseManager(enviar=self.emisor, reloj=self.reloj, config=CONFIG)
        self.vista = APP_final.ViewAuth(ROOT, db, lambda usuario, datos: self.entradas.append((usuario, datos)))
        self.vista.pack(fill="both", expand=True)
        ROOT.update()
        return self.vista

    def esperar(self, cond, seg=4.0):
        fin = time.time() + seg
        while time.time() < fin:
            ROOT.update()
            if cond():
                return True
            time.sleep(0.01)
        return cond()

    def escribir(self, entrada, texto):
        entrada.delete(0, "end")
        entrada.insert(0, texto)

    def llenar_registro(self, v, usuario="ana", correo_="ana@correo.test", clave="clave123"):
        if v.is_login:
            v.toggle_mode()
        self.escribir(v.e_u_r, usuario)
        self.escribir(v.e_c_r, correo_)
        self.escribir(v.e_p_r, clave)

    def registrar(self, v, **kw):
        self.llenar_registro(v, **kw)
        v.procesar_registro()
        self.assertTrue(self.esperar(lambda: not v._ocupado))        # terminó el envío (o nunca empezó)

    def en(self, v, frame):
        return frame.winfo_manager() == "pack"          # el frame está en pantalla


class TestRegistroYVerificacion(AuthUITestCase):
    def test_registro_feliz_muestra_la_verificacion_con_el_correo_enmascarado(self):
        v = self.abrir()
        self.registrar(v)
        self.assertEqual(v.pendiente, "ana")
        self.assertTrue(self.en(v, v.frame_verificar))
        self.assertFalse(self.en(v, v.frame_register) or self.en(v, v.frame_login))
        self.assertIn("a***@correo.test", v.lbl_correo.cget("text"))
        self.assertEqual(len(self.emisor.enviados), 1)
        self.assertFalse(almacen.obtener_usuario("ana")["verificado"])

    def test_el_envio_corre_en_un_hilo_y_los_botones_se_bloquean_contra_dobles_clics(self):   # enfoque de revisión 1
        lento = EmisorLento()
        self.emisor = lento
        v = self.abrir(APP_final.DatabaseManager(enviar=lento, reloj=self.reloj, config=CONFIG))
        self.llenar_registro(v)
        v.procesar_registro()
        self.assertEqual(str(v.btn_registrar.cget("state")), "disabled")
        v.procesar_registro()                                         # segundo clic mientras envía: se ignora
        lento.libre.set()
        self.assertTrue(self.esperar(lambda: v.pendiente == "ana"))
        self.assertEqual(len(lento.enviados), 1)

    def test_codigo_correcto_vuelve_al_login_con_el_usuario_y_sin_la_contrasena(self):
        v = self.abrir()
        self.registrar(v)
        self.escribir(v.e_codigo, self.emisor.enviados[0][1])
        v.procesar_verificacion()
        self.assertTrue(self.en(v, v.frame_login))
        self.assertEqual((v.e_u_l.get(), v.e_p_l.get(), v.pendiente), ("ana", "", None))
        self.assertIn("verificada", v.lbl_error.cget("text"))
        self.assertTrue(almacen.obtener_usuario("ana")["verificado"])
        self.escribir(v.e_p_l, "clave123")
        v.procesar_login()
        self.assertEqual([e[0] for e in self.entradas], ["ana"])

    def test_codigo_incorrecto_muestra_los_intentos_restantes_y_limpia_el_campo(self):
        v = self.abrir()
        self.registrar(v)
        malo = "000000" if self.emisor.enviados[0][1] != "000000" else "111111"
        self.escribir(v.e_codigo, malo)
        v.procesar_verificacion()
        self.assertIn("4 intentos", v.lbl_error.cget("text"))
        self.assertEqual(v.e_codigo.get(), "")
        self.assertTrue(self.en(v, v.frame_verificar))

    def test_el_campo_del_codigo_acepta_solo_digitos_y_maximo_6(self):
        v = self.abrir()
        self.registrar(v)
        self.escribir(v.e_codigo, "12a-3456789")
        v._limpiar_codigo(None)
        self.assertEqual(v.e_codigo.get(), "123456")

    def test_cuenta_atras_y_reenvio_con_un_solo_envio_aunque_se_haga_doble_clic(self):
        v = self.abrir()
        self.registrar(v)
        self.assertIn("60 s", v.lbl_espera.cget("text"))
        self.assertEqual(str(v.btn_reenviar.cget("state")), "disabled")
        self.reloj.t = 1060.0
        v._actualizar_espera()
        self.assertEqual(str(v.btn_reenviar.cget("state")), "normal")
        v.reenviar()
        v.reenviar()                                                  # doble clic
        self.assertTrue(v._ocupado)                                   # el envío está en curso: los botones están bloqueados
        self.assertTrue(self.esperar(lambda: not v._ocupado))
        self.assertEqual(len(self.emisor.enviados), 2)
        self.assertEqual(str(v.btn_reenviar.cget("state")), "disabled")   # vuelve a empezar la espera de 60 s
        self.assertIn("60 s", v.lbl_espera.cget("text"))
        self.assertIn("código nuevo", v.lbl_error.cget("text"))

    def test_cancelar_registro_pide_la_contrasena_y_luego_borra_la_cuenta(self):
        v = self.abrir()
        self.registrar(v)
        self.assertEqual(v.e_p_r.get(), "")                           # la clave no queda escrita en el formulario
        v.cancelar_registro()                                         # primer clic: pide la contraseña
        self.assertTrue(self.en(v, v.e_clave_cancelar))
        self.assertIsNotNone(almacen.obtener_usuario("ana"))
        self.escribir(v.e_clave_cancelar, "equivocada")
        v.cancelar_registro()
        self.assertIn("contraseña no es correcta", v.lbl_error.cget("text"))
        self.assertIsNotNone(almacen.obtener_usuario("ana"))          # con clave mala no se borra nada
        self.assertEqual(v.pendiente, "ana")
        self.escribir(v.e_clave_cancelar, "clave123")
        v.cancelar_registro()
        self.assertIsNone(almacen.obtener_usuario("ana"))
        self.assertIsNone(v.pendiente)
        self.assertTrue(self.en(v, v.frame_register))
        self.assertIn("cancelado", v.lbl_error.cget("text"))
        self.registrar(v)                                             # mismo usuario y correo otra vez
        self.assertEqual(v.pendiente, "ana")
        self.assertFalse(self.en(v, v.e_clave_cancelar))              # el campo de cancelación se reinicia

    def test_volver_sin_cancelar_deja_la_cuenta_pendiente_y_el_login_la_retoma(self):
        v = self.abrir()
        self.registrar(v)
        v.volver()
        self.assertTrue(self.en(v, v.frame_login))
        self.assertIsNotNone(almacen.obtener_usuario("ana"))
        self.escribir(v.e_u_l, "ana")
        self.escribir(v.e_p_l, "clave123")
        v.procesar_login()
        self.assertEqual(v.pendiente, "ana")
        self.assertTrue(self.en(v, v.frame_verificar))
        self.assertEqual(self.entradas, [])
        self.assertIn("aún no está verificado", v.lbl_error.cget("text"))

    def test_login_de_una_cuenta_ya_verificada_sigue_funcionando(self):
        almacen.crear_usuario("carla", "c@x.test", "clave123", "Estudiante", None, "11")
        v = self.abrir()
        self.escribir(v.e_u_l, "carla")
        self.escribir(v.e_p_l, "clave123")
        v.procesar_login()
        self.assertEqual([e[0] for e in self.entradas], ["carla"])

    def test_login_con_clave_incorrecta_no_revela_si_la_cuenta_existe_ni_esta_pendiente(self):
        v = self.abrir()
        self.registrar(v)
        v.volver()
        self.escribir(v.e_u_l, "ana")
        self.escribir(v.e_p_l, "mala")
        v.procesar_login()
        self.assertNotIn("verificado", v.lbl_error.cget("text"))
        self.assertTrue(self.en(v, v.frame_login))


class TestRevision(AuthUITestCase):
    """Hallazgos de la revisión independiente de la pieza 4 (ViewAuth)."""

    def test_el_registro_no_congela_la_ventana_mientras_el_correo_se_envia(self):
        lento = EmisorLento()
        v = self.abrir(APP_final.DatabaseManager(enviar=lento, reloj=self.reloj, config=CONFIG))
        self.llenar_registro(v)
        inicio = time.time()
        v.procesar_registro()
        self.assertLess(time.time() - inicio, 1.0)                    # vuelve enseguida: el envío (que espera) va en otro hilo
        self.assertTrue(v._ocupado)
        lento.libre.set()
        self.assertTrue(self.esperar(lambda: not v._ocupado))

    def test_mientras_se_envia_no_se_puede_cambiar_de_pantalla_ni_entrar_con_otra_cuenta(self):
        almacen.crear_usuario("carla", "carla@correo.test", "clave123", "Estudiante", None, "11")
        lento = EmisorLento()
        v = self.abrir(APP_final.DatabaseManager(enviar=lento, reloj=self.reloj, config=CONFIG))
        self.llenar_registro(v)
        v.procesar_registro()
        for boton in (v.btn_toggle, v.sel_rol, v.btn_login):
            self.assertEqual(str(boton.cget("state")), "disabled")
        v.toggle_mode()                                               # se ignora
        self.assertTrue(self.en(v, v.frame_register))
        self.escribir(v.e_u_l, "carla")
        self.escribir(v.e_p_l, "clave123")
        v.procesar_login()                                            # se ignora: no entra ni abre otra verificación
        self.assertEqual((self.entradas, v.pendiente), ([], None))
        lento.libre.set()
        self.assertTrue(self.esperar(lambda: v.pendiente == "ana"))
        for boton in (v.btn_toggle, v.sel_rol, v.btn_login):
            self.assertEqual(str(boton.cget("state")), "normal")

    def test_un_segundo_clic_en_verificar_con_el_campo_vacio_no_borra_los_intentos_restantes(self):
        v = self.abrir()
        self.registrar(v)
        malo = "000000" if self.emisor.enviados[0][1] != "000000" else "111111"
        self.escribir(v.e_codigo, malo)
        v.procesar_verificacion()
        self.assertIn("4 intentos", v.lbl_error.cget("text"))
        v.procesar_verificacion()                                     # doble clic: el campo ya está vacío
        self.assertIn("4 intentos", v.lbl_error.cget("text"))
        self.assertEqual(almacen.datos_verificacion("ana")["intentos"], 1)

    def test_con_el_campo_vacio_la_primera_vez_pide_los_6_digitos_y_no_gasta_intentos(self):
        v = self.abrir()
        self.registrar(v)
        v.procesar_verificacion()
        self.assertIn("6 dígitos", v.lbl_error.cget("text"))
        self.assertEqual(almacen.datos_verificacion("ana")["intentos"], 0)

    def test_la_contrasena_del_login_no_queda_escrita_al_pasar_a_la_verificacion(self):
        v = self.abrir()
        self.registrar(v)
        v.volver()
        self.escribir(v.e_u_l, "ana")
        self.escribir(v.e_p_l, "clave123")
        v.procesar_login()
        self.assertEqual(v.pendiente, "ana")
        self.assertEqual(v.e_p_l.get(), "")
        v.volver()
        self.assertEqual((v.e_u_l.get(), v.e_p_l.get()), ("ana", ""))

    def test_si_la_base_falla_en_un_tic_la_cuenta_atras_se_reprograma(self):
        v = self.abrir()
        self.registrar(v)
        with mock.patch.object(v.db, "segundos_para_reenviar", side_effect=sqlite3.OperationalError("database is locked")):
            v._actualizar_espera()                                    # no lanza
        self.assertIsNotNone(v._espera_id)                            # y volverá a intentarlo en un segundo
        self.reloj.t = 1060.0
        v._actualizar_espera()
        self.assertEqual(str(v.btn_reenviar.cget("state")), "normal")

    def test_el_limite_de_codigos_se_muestra_en_la_pantalla(self):
        v = self.abrir()
        self.registrar(v)
        for n in range(4):
            self.reloj.t = 1060.0 * (n + 1)
            v.reenviar()
            self.assertTrue(self.esperar(lambda: not v._ocupado))
        self.reloj.t = 100000.0
        v.reenviar()
        self.assertTrue(self.esperar(lambda: not v._ocupado))
        self.assertIn("máximo de códigos", v.lbl_error.cget("text"))
        self.assertEqual(len(self.emisor.enviados), 5)


class TestFallos(AuthUITestCase):
    def test_sin_configuracion_el_registro_falla_de_forma_segura(self):
        v = self.abrir(APP_final.DatabaseManager(enviar=self.emisor, reloj=self.reloj))     # config=None: lee el entorno
        with mock.patch.dict(os.environ, {}, clear=True):
            self.registrar(v)
        self.assertIn("no está configurado", v.lbl_error.cget("text"))
        self.assertIsNone(v.pendiente)
        self.assertTrue(self.en(v, v.frame_register))
        self.assertIsNone(almacen.obtener_usuario("ana"))

    def test_fallo_del_proveedor_muestra_el_motivo_y_no_deja_cuenta(self):
        self.emisor.falla = ErrorCorreo("El proveedor rechazó las credenciales de correo configuradas.", False)
        v = self.abrir()
        self.registrar(v)
        self.assertIn("credenciales", v.lbl_error.cget("text"))
        self.assertIsNone(v.pendiente)
        self.assertIsNone(almacen.obtener_usuario("ana"))
        self.assertEqual(str(v.btn_registrar.cget("state")), "normal")                      # se puede reintentar

    def test_un_error_inesperado_en_el_hilo_se_muestra_sin_romper_la_pantalla(self):
        v = self.abrir()
        with mock.patch.object(v.db, "registrar_usuario", side_effect=RuntimeError("explotó")):
            self.registrar(v)
        self.assertIn("error inesperado", v.lbl_error.cget("text"))
        self.assertEqual(str(v.btn_registrar.cget("state")), "normal")

    def test_correo_ya_registrado_se_informa_en_la_pantalla(self):
        almacen.crear_usuario("carla", "ana@correo.test", "clave123", "Estudiante", None, "11")
        v = self.abrir()
        self.registrar(v)
        self.assertIn("correo ya está registrado", v.lbl_error.cget("text"))
        self.assertEqual(self.emisor.enviados, [])

    def test_modo_desarrollo_avisa_en_pantalla_y_el_codigo_sale_por_la_consola(self):
        salida = io.StringIO()
        v = self.abrir(APP_final.DatabaseManager(reloj=self.reloj, config=correo.Config(modo="consola")))
        with contextlib.redirect_stdout(salida):
            self.registrar(v)
        self.assertIn("modo desarrollo", v.lbl_correo.cget("text"))
        codigo = salida.getvalue().split("ana@correo.test: ")[1].strip()
        self.escribir(v.e_codigo, codigo)
        v.procesar_verificacion()
        self.assertTrue(almacen.obtener_usuario("ana")["verificado"])

    def test_en_produccion_la_pantalla_nunca_muestra_el_codigo(self):
        v = self.abrir()
        self.registrar(v)
        codigo = self.emisor.enviados[0][1]
        textos = [v.lbl_correo.cget("text"), v.lbl_error.cget("text"), v.lbl_espera.cget("text")]
        self.assertTrue(all(codigo not in t for t in textos))


class TestProfesorUI(AuthUITestCase):
    """El profesor ya no escribe un código fijo al registrarse: recibe por correo su código de verificación Y su código de profesor
    (único), y los escribe los dos en la pantalla de verificación."""

    def llenar_profesor(self, v, usuario="profe"):
        if v.is_login:
            v.toggle_mode()
        v.rol_var.set("Profesor")
        v.actualizar_vistas_rol("Profesor")
        self.escribir(v.e_u_r, usuario)
        self.escribir(v.e_c_r, f"{usuario}@correo.test")
        self.escribir(v.e_p_r, "clave123")

    def registrar_profesor(self, v, usuario="profe"):
        self.llenar_profesor(v, usuario)
        v.procesar_registro()
        self.assertTrue(self.esperar(lambda: not v._ocupado))

    def test_el_formulario_de_registro_de_profesor_no_pide_ningun_codigo(self):
        v = self.abrir()
        self.llenar_profesor(v)
        self.assertTrue(self.en(v, v.combo_materia_reg))
        self.assertTrue(self.en(v, v.lbl_aviso_profesor))
        self.assertIn("código de profesor", v.lbl_aviso_profesor.cget("text"))
        self.assertFalse(self.en(v, v.e_codigo_profesor))                  # ese campo ahora vive en la pantalla de verificación
        v.rol_var.set("Estudiante")
        v.actualizar_vistas_rol("Estudiante")
        self.assertFalse(self.en(v, v.lbl_aviso_profesor))
        self.assertTrue(self.en(v, v.combo_grado_reg))

    def test_el_registro_de_profesor_funciona_sin_ninguna_variable_de_codigo(self):
        v = self.abrir()
        with mock.patch.dict(os.environ, {}, clear=True):
            self.registrar_profesor(v)
        self.assertEqual(v.pendiente, "profe")
        self.assertNotIn("NEON_CODIGO_PROFESOR", v.lbl_error.cget("text"))
        self.assertEqual(len(self.emisor.enviados), 1)
        self.assertRegex(self.emisor.profesor[0], r"^[A-Z2-9]{5}-[A-Z2-9]{5}$")

    def test_la_verificacion_del_profesor_muestra_el_campo_del_codigo_de_profesor(self):
        v = self.abrir()
        self.registrar_profesor(v)
        self.assertTrue(self.en(v, v.frame_verificar))
        self.assertTrue(self.en(v, v.e_codigo) and self.en(v, v.e_codigo_profesor))
        self.assertFalse(self.en(v, v.e_clave_nueva) or self.en(v, v.e_clave_nueva2))
        self.assertTrue(self.en(v, v.btn_cancelar))
        self.assertIn("código de profesor", v.lbl_correo.cget("text"))
        self.assertIn("p***@correo.test", v.lbl_correo.cget("text"))
        self.assertEqual(v.btn_verificar.cget("text"), "Verificar")
        textos = [v.lbl_correo.cget("text"), v.lbl_error.cget("text"), v.lbl_espera.cget("text")]
        self.assertTrue(all(self.emisor.profesor[0] not in t for t in textos))     # la pantalla nunca muestra el código

    def test_el_estudiante_no_ve_el_campo_del_codigo_de_profesor(self):
        v = self.abrir()
        self.registrar(v)
        self.assertFalse(self.en(v, v.e_codigo_profesor))
        self.assertNotIn("profesor", v.lbl_correo.cget("text"))

    def test_con_los_dos_codigos_el_profesor_queda_verificado_y_entra(self):
        v = self.abrir()
        self.registrar_profesor(v)
        self.escribir(v.e_codigo, self.emisor.enviados[0][1])
        self.escribir(v.e_codigo_profesor, self.emisor.profesor[0].lower())            # vale en minúsculas
        v.procesar_verificacion()
        self.assertTrue(self.en(v, v.frame_login))
        self.assertEqual((v.e_u_l.get(), v.pendiente), ("profe", None))
        self.assertIn("verificada", v.lbl_error.cget("text"))
        self.assertTrue(almacen.obtener_usuario("profe")["verificado"])
        self.assertEqual((v.e_codigo.get(), v.e_codigo_profesor.get()), ("", ""))
        v.rol_var.set("Profesor")
        self.escribir(v.e_p_l, "clave123")
        v.procesar_login()
        self.assertEqual([e[0] for e in self.entradas], ["profe"])

    def test_sin_el_codigo_de_profesor_pide_que_lo_escriba_y_no_gasta_intentos(self):
        v = self.abrir()
        self.registrar_profesor(v)
        codigo = self.emisor.enviados[0][1]
        self.escribir(v.e_codigo, codigo)
        v.procesar_verificacion()
        self.assertIn("código de profesor", v.lbl_error.cget("text"))
        self.assertEqual(almacen.datos_verificacion("profe")["intentos"], 0)
        self.assertEqual(v.e_codigo.get(), codigo)                                     # lo ya escrito se conserva
        self.assertFalse(almacen.obtener_usuario("profe")["verificado"])

    def test_codigo_de_profesor_equivocado_muestra_los_intentos_y_limpia_los_dos_campos(self):
        v = self.abrir()
        self.registrar_profesor(v)
        self.escribir(v.e_codigo, self.emisor.enviados[0][1])
        self.escribir(v.e_codigo_profesor, "AAAAA-AAAAA")
        v.procesar_verificacion()
        self.assertIn("4 intentos", v.lbl_error.cget("text"))
        self.assertEqual((v.e_codigo.get(), v.e_codigo_profesor.get()), ("", ""))
        self.assertTrue(self.en(v, v.frame_verificar))
        self.assertFalse(almacen.obtener_usuario("profe")["verificado"])

    def test_el_campo_del_codigo_de_profesor_se_da_formato_solo(self):
        v = self.abrir()
        self.registrar_profesor(v)
        for escrito, esperado in (("k7m2qx9tr4", "K7M2Q-X9TR4"), ("k7m2q", "K7M2Q"), ("k7m2q-x9tr4zzz", "K7M2Q-X9TR4"),
                                  ("k7 m2-q x9!tr4", "K7M2Q-X9TR4"), ("ilo01", ""), ("", "")):
            with self.subTest(escrito=escrito):
                self.escribir(v.e_codigo_profesor, escrito)
                v._limpiar_codigo_profesor(None)
                self.assertEqual(v.e_codigo_profesor.get(), esperado)

    def test_un_profesor_pendiente_que_vuelve_a_entrar_retoma_la_verificacion_con_los_dos_campos(self):
        v = self.abrir()
        self.registrar_profesor(v)
        v.volver()
        v.rol_var.set("Profesor")
        v.actualizar_vistas_rol("Profesor")
        self.escribir(v.e_u_l, "profe")
        self.escribir(v.e_p_l, "clave123")
        v.procesar_login()
        self.assertEqual(v.pendiente, "profe")
        self.assertTrue(self.en(v, v.e_codigo_profesor))
        self.assertEqual(self.entradas, [])

    def test_reenviar_manda_un_codigo_de_profesor_nuevo(self):
        v = self.abrir()
        self.registrar_profesor(v)
        self.reloj.t = 1060.0
        v._actualizar_espera()
        v.reenviar()
        self.assertTrue(self.esperar(lambda: not v._ocupado))
        self.assertEqual(len(self.emisor.enviados), 2)
        self.assertNotEqual(self.emisor.profesor[0], self.emisor.profesor[1])
        self.escribir(v.e_codigo, self.emisor.enviados[1][1])
        self.escribir(v.e_codigo_profesor, self.emisor.profesor[1])
        v.procesar_verificacion()
        self.assertTrue(almacen.obtener_usuario("profe")["verificado"])

    def test_al_salir_de_la_verificacion_de_un_profesor_los_campos_quedan_vacios_y_el_siguiente_estudiante_no_los_ve(self):
        v = self.abrir()
        self.registrar_profesor(v)
        self.escribir(v.e_codigo_profesor, "AAAAA-AAAAA")
        v.volver()
        self.assertEqual(v.e_codigo_profesor.get(), "")
        self.assertIsNone(v.rol_pendiente)
        v.rol_var.set("Estudiante")
        self.registrar(v, usuario="ana", correo_="ana@correo.test")
        self.assertEqual(v.rol_pendiente, "Estudiante")
        self.assertFalse(self.en(v, v.e_codigo_profesor))


class TestAdministradorUI(AuthUITestCase):
    """Primer acceso de un administrador predeterminado: código por correo + contraseña nueva, todo en la pantalla de verificación."""
    ADMIN = almacen.ADMINISTRADORES[0]
    CLAVE = "Mi-clave-segura-1"

    def setUp(self):
        super().setUp()
        almacen.iniciar()                                  # el BDTestCase borra las cuentas: se vuelven a crear como en un primer arranque

    def entrar_como_admin(self, v, correo_=None, clave="lo-que-sea"):
        v.rol_var.set("Administrador")
        v.actualizar_vistas_rol("Administrador")
        self.escribir(v.e_u_l, correo_ or self.ADMIN)
        self.escribir(v.e_p_l, clave)
        v.procesar_login()

    def pedir_codigo(self, v):
        v.reenviar()
        self.assertTrue(self.esperar(lambda: not v._ocupado))
        return self.emisor.enviados[-1][1]

    def test_el_campo_de_usuario_pide_el_correo_al_elegir_administrador(self):
        v = self.abrir()
        self.assertEqual(v.e_u_l.cget("placeholder_text"), "Usuario")
        v.rol_var.set("Administrador")
        v.actualizar_vistas_rol("Administrador")
        self.assertEqual(v.e_u_l.cget("placeholder_text"), "Correo de administrador")
        v.rol_var.set("Estudiante")
        v.actualizar_vistas_rol("Estudiante")
        self.assertEqual(v.e_u_l.cget("placeholder_text"), "Usuario")

    def test_entrar_por_primera_vez_ya_no_dice_que_falta_configurar_nada(self):
        v = self.abrir()
        with mock.patch.dict(os.environ, {}, clear=True):
            self.entrar_como_admin(v)
        self.assertNotIn("NEON_ADMIN_CLAVE", v.lbl_error.cget("text"))
        self.assertNotIn("no está configurado", v.lbl_error.cget("text"))
        self.assertEqual(v.pendiente, self.ADMIN)

    def test_el_primer_acceso_abre_la_pantalla_de_activacion_sin_enviar_nada_todavia(self):
        v = self.abrir()
        self.entrar_como_admin(v)
        self.assertTrue(self.en(v, v.frame_verificar))
        self.assertEqual((v.rol_pendiente, v.lbl_title.cget("text")), ("Administrador", "Activa tu cuenta"))
        self.assertTrue(all(self.en(v, w) for w in (v.e_codigo, v.e_clave_nueva, v.e_clave_nueva2)))
        self.assertFalse(self.en(v, v.e_codigo_profesor))
        self.assertFalse(self.en(v, v.btn_cancelar))                               # un administrador no cancela su cuenta
        self.assertEqual((v.btn_verificar.cget("text"), v.btn_reenviar.cget("text")), ("Activar cuenta", "Enviar código"))
        self.assertEqual(str(v.btn_reenviar.cget("state")), "normal")              # se puede pedir el código ya
        self.assertIn("Primer acceso", v.lbl_correo.cget("text"))
        self.assertIn("l***@gmail.com", v.lbl_correo.cget("text"))
        self.assertEqual(v.lbl_error.cget("text"), "")                             # la pantalla ya lo explica: no se repite el aviso
        self.assertEqual(self.emisor.enviados, [])
        self.assertEqual(v.e_p_l.get(), "")                                        # lo que escribió como contraseña no queda a la vista

    def test_los_campos_de_la_activacion_muestran_su_texto_de_ayuda(self):
        v = self.abrir()
        self.escribir(v.e_p_l, "x")
        self.entrar_como_admin(v)
        ROOT.update()
        self.assertEqual(v.e_clave_nueva._entry.get(), "Crea tu contraseña (mínimo 8 caracteres)")      # no quedan en blanco
        self.assertEqual(v.e_clave_nueva2._entry.get(), "Repite la contraseña")
        self.assertEqual(v.e_clave_nueva.get(), "")                                                    # y para el programa siguen vacíos

    def test_activar_la_cuenta_pidiendo_el_codigo_y_eligiendo_contrasena_y_luego_iniciar_sesion(self):
        v = self.abrir()
        self.entrar_como_admin(v)
        codigo = self.pedir_codigo(v)
        self.assertEqual(self.emisor.enviados[0][0], self.ADMIN)
        self.assertIn("código nuevo", v.lbl_error.cget("text"))
        self.escribir(v.e_codigo, codigo)
        self.escribir(v.e_clave_nueva, self.CLAVE)
        self.escribir(v.e_clave_nueva2, self.CLAVE)
        v.procesar_verificacion()
        self.assertTrue(self.en(v, v.frame_login))
        self.assertEqual((v.e_u_l.get(), v.pendiente), (self.ADMIN, None))
        self.assertIn("activada", v.lbl_error.cget("text"))
        self.assertEqual((v.e_clave_nueva.get(), v.e_clave_nueva2.get(), v.e_codigo.get()), ("", "", ""))
        self.assertTrue(almacen.obtener_usuario(self.ADMIN)["verificado"])
        self.escribir(v.e_p_l, self.CLAVE)
        v.procesar_login()
        self.assertEqual([e[0] for e in self.entradas], [self.ADMIN])
        self.assertEqual(self.entradas[0][1]["role"], "Administrador")

    def test_con_la_cuenta_activa_el_login_normal_funciona_y_no_vuelve_a_pedir_codigo(self):
        almacen.asignar_clave_admin(self.ADMIN, self.CLAVE)
        v = self.abrir()
        self.entrar_como_admin(v, clave=self.CLAVE)
        self.assertEqual([e[0] for e in self.entradas], [self.ADMIN])
        self.assertIsNone(v.pendiente)

    def test_con_la_cuenta_activa_una_clave_mala_se_niega(self):
        almacen.asignar_clave_admin(self.ADMIN, self.CLAVE)
        v = self.abrir()
        self.entrar_como_admin(v, clave="otra-clave-1")
        self.assertIn("ACCESO DENEGADO", v.lbl_error.cget("text"))
        self.assertEqual((self.entradas, v.pendiente), ([], None))
        self.assertTrue(self.en(v, v.frame_login))

    def test_contrasenas_distintas_no_activan_ni_gastan_intentos(self):
        v = self.abrir()
        self.entrar_como_admin(v)
        codigo = self.pedir_codigo(v)
        self.escribir(v.e_codigo, codigo)
        self.escribir(v.e_clave_nueva, self.CLAVE)
        self.escribir(v.e_clave_nueva2, self.CLAVE + "x")
        v.procesar_verificacion()
        self.assertIn("no coinciden", v.lbl_error.cget("text"))
        self.assertFalse(almacen.obtener_usuario(self.ADMIN)["verificado"])
        self.assertEqual(almacen.datos_verificacion(self.ADMIN)["intentos"], 0)
        self.assertEqual(v.e_codigo.get(), codigo)

    def test_contrasena_corta_pide_una_mas_larga_y_conserva_lo_escrito(self):
        v = self.abrir()
        self.entrar_como_admin(v)
        codigo = self.pedir_codigo(v)
        self.escribir(v.e_codigo, codigo)
        self.escribir(v.e_clave_nueva, "corta")
        self.escribir(v.e_clave_nueva2, "corta")
        v.procesar_verificacion()
        self.assertIn("al menos 8", v.lbl_error.cget("text"))
        self.assertEqual(almacen.datos_verificacion(self.ADMIN)["intentos"], 0)
        self.assertEqual(v.e_codigo.get(), codigo)
        self.assertFalse(almacen.obtener_usuario(self.ADMIN)["verificado"])

    def test_codigo_incorrecto_muestra_los_intentos_y_no_activa(self):
        v = self.abrir()
        self.entrar_como_admin(v)
        codigo = self.pedir_codigo(v)
        self.escribir(v.e_codigo, "000000" if codigo != "000000" else "111111")
        self.escribir(v.e_clave_nueva, self.CLAVE)
        self.escribir(v.e_clave_nueva2, self.CLAVE)
        v.procesar_verificacion()
        self.assertIn("4 intentos", v.lbl_error.cget("text"))
        self.assertEqual(v.e_codigo.get(), "")
        self.assertFalse(almacen.obtener_usuario(self.ADMIN)["verificado"])
        self.assertFalse(almacen.verificar_clave(self.ADMIN, self.CLAVE))

    def test_cancelar_no_hace_nada_para_un_administrador(self):
        v = self.abrir()
        self.entrar_como_admin(v)
        v.cancelar_registro()
        self.assertFalse(v._cancelando)
        self.assertIsNotNone(almacen.obtener_usuario(self.ADMIN))
        self.assertEqual(v.pendiente, self.ADMIN)

    def test_volver_deja_el_primer_acceso_pendiente_y_la_otra_cuenta_funciona_igual(self):
        v = self.abrir()
        self.entrar_como_admin(v)
        v.volver()
        self.assertTrue(self.en(v, v.frame_login))
        self.assertFalse(almacen.obtener_usuario(self.ADMIN)["verificado"])
        self.entrar_como_admin(v, correo_=almacen.ADMINISTRADORES[1])
        self.assertEqual(v.pendiente, almacen.ADMINISTRADORES[1])
        self.assertIn("d***@gmail.com", v.lbl_correo.cget("text"))

    def test_despues_de_la_pantalla_de_administrador_un_estudiante_vuelve_a_ver_la_normal(self):
        v = self.abrir()
        self.entrar_como_admin(v)
        v.volver()
        v.rol_var.set("Estudiante")
        self.registrar(v)                                                          # un estudiante se registra después
        self.assertEqual(v.rol_pendiente, "Estudiante")
        self.assertFalse(self.en(v, v.e_clave_nueva) or self.en(v, v.e_clave_nueva2) or self.en(v, v.e_codigo_profesor))
        self.assertTrue(self.en(v, v.btn_cancelar))
        self.assertEqual((v.btn_verificar.cget("text"), v.btn_reenviar.cget("text"), v.lbl_title.cget("text")),
                         ("Verificar", "Reenviar código", "Verifica tu correo"))

    def test_si_el_correo_falla_en_el_primer_acceso_el_motivo_se_ve_y_se_puede_reintentar(self):
        v = self.abrir()
        self.entrar_como_admin(v)
        self.emisor.falla = ErrorCorreo("El proveedor de correo no permite enviar desde esta conexión (dirección IP no autorizada).", False)
        v.reenviar()
        self.assertTrue(self.esperar(lambda: not v._ocupado))
        self.assertIn("IP no autorizada", v.lbl_error.cget("text"))
        self.assertEqual(str(v.btn_reenviar.cget("state")), "normal")              # el fallo no gasta la espera
        self.emisor.falla = None
        self.assertTrue(self.pedir_codigo(v))


if __name__ == "__main__":
    unittest.main()
