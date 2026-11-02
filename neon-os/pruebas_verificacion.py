"""Pruebas de la verificación de correo: base de datos (almacen.py) y reglas (verificacion.py).

Ejecutar desde esta carpeta:   python pruebas_verificacion.py -v
Usa una base de datos temporal (nunca toca neon_os.db) y un emisor FALSO: no envía correos reales.
"""
import atexit
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest

_TMP = tempfile.mkdtemp(prefix="neon_verif_")
atexit.register(shutil.rmtree, _TMP, ignore_errors=True)
os.environ["NEON_DB"] = os.path.join(_TMP, "import.db")   # antes de importar almacen
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import almacen


class BDTestCase(unittest.TestCase):
    def setUp(self):
        almacen.RUTA = os.path.join(_TMP, f"{self.id().split('.')[-1]}_{time.time_ns()}.db")
        almacen.iniciar()
        with almacen._con() as con:
            con.execute("DELETE FROM usuarios")            # quita las cuentas de demostración y las de administrador
            con.execute("DELETE FROM verificaciones")      # (las pruebas de administradores las vuelven a crear con almacen.iniciar())


def pendiente(usuario="ana", correo="ana@correo.test", ahora=1000.0, hash_="H1", sal="S1", **kw):
    return almacen.registrar_pendiente(usuario, correo, kw.get("clave", "clave123"), kw.get("rol", "Estudiante"),
                                       kw.get("materia"), kw.get("grado", "11"), hash_, sal, ahora, 600)


# ==============================================================================
# TAREA 2: esquema y funciones atómicas
# ==============================================================================
class TestAlmacenVerificacion(BDTestCase):
    def test_una_base_antigua_se_migra_y_las_cuentas_existentes_quedan_verificadas(self):
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
        almacen.iniciar()                                          # idempotente
        self.assertTrue(almacen.obtener_usuario("luis")["verificado"])
        self.assertEqual(almacen.ranking_estudiantes(), [(1, "luis", 100)])
        self.assertIsNone(almacen.datos_verificacion("luis"))
        with almacen._con() as c:
            self.assertIn("verificado", [f[1] for f in c.execute("PRAGMA table_info(usuarios)")])

    def test_crear_usuario_es_verificada_por_defecto_y_se_puede_crear_sin_verificar(self):
        almacen.crear_usuario("ana", "a@x.test", "clave", "Estudiante", None, "11")
        almacen.crear_usuario("beto", "b@x.test", "clave", "Estudiante", None, "11", verificado=False)
        self.assertTrue(almacen.obtener_usuario("ana")["verificado"])
        self.assertFalse(almacen.obtener_usuario("beto")["verificado"])

    def test_registrar_pendiente_crea_la_cuenta_sin_verificar_y_su_verificacion(self):
        self.assertEqual(pendiente(correo="  Ana@Correo.TEST "), "ok")
        usuario = almacen.obtener_usuario("ana")
        self.assertEqual((usuario["verificado"], usuario["correo"], usuario["role"], usuario["grado"]),
                         (False, "ana@correo.test", "Estudiante", "11"))
        d = almacen.datos_verificacion("ana")
        self.assertEqual((d["correo"], d["codigo_hash"], d["sal"], d["intentos"], d["ultimo_envio"], d["expira"]),
                         ("ana@correo.test", "H1", "S1", 0, 1000.0, 1600.0))
        self.assertTrue(almacen.verificar_clave("ana", "clave123"))

    def test_usuario_y_correo_duplicados_no_dejan_nada_a_medias(self):
        self.assertEqual(pendiente(), "ok")
        self.assertEqual(pendiente(usuario="ana", correo="otro@correo.test"), "usuario_existe")
        self.assertEqual(pendiente(usuario="beto", correo=" ANA@correo.test "), "correo_existe")   # mayúsculas y espacios
        almacen.crear_usuario("carla", "Carla@Correo.Test", "clave", "Estudiante", None, "11")        # cuenta verificada ya existente
        self.assertEqual(pendiente(usuario="dani", correo="carla@correo.test"), "correo_existe")
        with almacen._con() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0], 2)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM verificaciones").fetchone()[0], 1)

    def test_un_fallo_a_mitad_deshace_todo(self):
        with self.assertRaises(sqlite3.IntegrityError):
            pendiente(hash_=None)                                    # codigo_hash es NOT NULL: falla tras insertar la cuenta
        self.assertIsNone(almacen.obtener_usuario("ana"))
        self.assertEqual(pendiente(), "ok")                          # y se puede volver a intentar

    def test_correo_en_uso(self):
        pendiente()
        almacen.crear_usuario("carla", "Carla@Correo.Test", "clave", "Estudiante", None, "11")
        self.assertTrue(almacen.correo_en_uso(" ANA@correo.test"))
        self.assertTrue(almacen.correo_en_uso("carla@correo.test"))
        self.assertFalse(almacen.correo_en_uso("nadie@correo.test"))

    def test_consumir_intento_llega_al_maximo_y_luego_none(self):
        pendiente()
        self.assertEqual([almacen.consumir_intento("ana", 5) for _ in range(5)], [1, 2, 3, 4, 5])
        self.assertIsNone(almacen.consumir_intento("ana", 5))
        self.assertEqual(almacen.datos_verificacion("ana")["intentos"], 5)
        self.assertIsNone(almacen.consumir_intento("nadie", 5))

    def test_renovar_codigo_reinicia_intentos_y_el_envio(self):
        pendiente()
        for _ in range(3):
            almacen.consumir_intento("ana", 5)
        self.assertTrue(almacen.renovar_codigo("ana", "H2", "S2", 2000.0, 1500.0))
        d = almacen.datos_verificacion("ana")
        self.assertEqual((d["codigo_hash"], d["sal"], d["intentos"], d["ultimo_envio"], d["expira"]), ("H2", "S2", 0, 1500.0, 2000.0))
        self.assertFalse(almacen.renovar_codigo("nadie", "H", "S", 1.0, 1.0))

    def test_reservar_envio_es_atomico_y_se_puede_restaurar(self):         # enfoque de revisión 1
        pendiente(ahora=1000.0)
        self.assertIsNone(almacen.reservar_envio("ana", 1059.0, 60))                  # aún no pasó la espera
        self.assertEqual(almacen.reservar_envio("ana", 1060.0, 60), 1000.0)           # reservó y devuelve el envío previo
        self.assertIsNone(almacen.reservar_envio("ana", 1060.0, 60))                  # la segunda solicitud simultánea pierde
        self.assertEqual(almacen.datos_verificacion("ana")["ultimo_envio"], 1060.0)
        almacen.restaurar_envio("ana", 1000.0)                                        # el proveedor falló: no se gasta la espera
        self.assertEqual(almacen.datos_verificacion("ana")["ultimo_envio"], 1000.0)
        self.assertEqual(almacen.reservar_envio("ana", 1060.0, 60), 1000.0)
        self.assertIsNone(almacen.reservar_envio("nadie", 1060.0, 60))
        self.assertIsNone(almacen.reservar_envio("ana", 900.0, 60))                   # el reloj retrocedió: no se permite

    def test_marcar_verificado_habilita_la_cuenta_y_borra_la_verificacion(self):
        pendiente()
        self.assertTrue(almacen.marcar_verificado("ana"))
        self.assertTrue(almacen.obtener_usuario("ana")["verificado"])
        self.assertIsNone(almacen.datos_verificacion("ana"))
        self.assertFalse(almacen.marcar_verificado("nadie"))

    def test_cancelar_pendiente_solo_borra_cuentas_sin_verificar(self):
        almacen.crear_usuario("carla", "c@x.test", "clave", "Estudiante", None, "11")
        self.assertFalse(almacen.cancelar_pendiente("carla"))
        self.assertIsNotNone(almacen.obtener_usuario("carla"))
        pendiente()
        self.assertTrue(almacen.cancelar_pendiente("ana"))
        self.assertIsNone(almacen.obtener_usuario("ana"))
        self.assertIsNone(almacen.datos_verificacion("ana"))
        self.assertEqual(pendiente(), "ok")                          # el usuario y el correo quedaron libres

    def test_limpiar_no_verificados_borra_los_de_mas_de_24_horas(self):
        pendiente(usuario="viejo", correo="viejo@x.test", ahora=0.0)
        pendiente(usuario="nuevo", correo="nuevo@x.test", ahora=50000.0)
        almacen.crear_usuario("carla", "c@x.test", "clave", "Estudiante", None, "11")
        self.assertEqual(almacen.limpiar_no_verificados(86400.0, 86400), 0)            # exactamente 24 h: todavía no
        self.assertEqual(almacen.limpiar_no_verificados(86401.0, 86400), 1)
        self.assertIsNone(almacen.obtener_usuario("viejo"))
        self.assertIsNotNone(almacen.obtener_usuario("nuevo"))
        self.assertIsNotNone(almacen.obtener_usuario("carla"))

    def test_el_ranking_no_incluye_a_los_estudiantes_pendientes(self):
        pendiente()
        almacen.guardar_progreso("ana", {"coins": 5, "puntos": 5})
        self.assertEqual(almacen.ranking_estudiantes(), [])                        # sin verificar el correo no aparece
        almacen.marcar_verificado("ana")
        self.assertEqual(almacen.ranking_estudiantes(), [(1, "ana", 5)])           # verificada: entra

    # -- revisión independiente de la pieza 4 ------------------------------------------------------------------
    def test_una_base_con_la_tabla_de_verificaciones_anterior_se_migra(self):
        ruta = os.path.join(_TMP, f"antigua2_{time.time_ns()}.db")
        con = sqlite3.connect(ruta)
        con.executescript("""
            CREATE TABLE usuarios (usuario TEXT PRIMARY KEY, clave TEXT NOT NULL, rol TEXT NOT NULL, materia TEXT, correo TEXT, grado TEXT,
                                   verificado INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE verificaciones (usuario TEXT PRIMARY KEY, codigo_hash TEXT NOT NULL, sal TEXT NOT NULL, expira REAL NOT NULL,
                                         intentos INTEGER NOT NULL DEFAULT 0, ultimo_envio REAL NOT NULL);
            INSERT INTO usuarios VALUES ('ana', 'x$y', 'Estudiante', NULL, 'ana@x.test', '11', 0);
            INSERT INTO verificaciones VALUES ('ana', 'H', 'S', 1600.0, 0, 1000.0);
        """)
        con.commit()
        con.close()
        almacen.RUTA = ruta
        almacen.iniciar()
        almacen.iniciar()                                                       # idempotente
        d = almacen.datos_verificacion("ana")
        self.assertEqual((d["envios"], d["creado"], d["ultimo_envio"]), (1, None, 1000.0))
        self.assertEqual(almacen.limpiar_no_verificados(1000.0 + 86401, 86400), 1)   # sin `creado` se usa el último envío

    def test_registrar_pendiente_guarda_cuando_se_creo_y_un_envio(self):
        pendiente(ahora=1234.0)
        d = almacen.datos_verificacion("ana")
        self.assertEqual((d["creado"], d["envios"]), (1234.0, 1))

    def test_la_caducidad_de_24_horas_cuenta_desde_que_se_creo_no_desde_el_ultimo_reenvio(self):
        pendiente(usuario="viejo", correo="viejo@x.test", ahora=0.0)
        self.assertEqual(almacen.reservar_envio("viejo", 80000.0, 60), 0.0)         # reenvía casi a las 24 h
        almacen.renovar_codigo("viejo", "H2", "S2", 80600.0, 80000.0)
        self.assertEqual(almacen.limpiar_no_verificados(86400.0, 86400), 0)         # exactamente 24 h: todavía no
        self.assertEqual(almacen.limpiar_no_verificados(86401.0, 86400), 1)         # reenviar no la mantiene viva
        self.assertIsNone(almacen.obtener_usuario("viejo"))
        self.assertIsNone(almacen.datos_verificacion("viejo"))

    def test_la_limpieza_no_toca_cuentas_verificadas_ni_deja_verificaciones_huerfanas(self):
        pendiente(usuario="viejo", correo="viejo@x.test", ahora=0.0)
        pendiente(usuario="otro", correo="otro@x.test", ahora=0.0)
        almacen.marcar_verificado("otro")                                           # se verificó justo antes de la limpieza
        self.assertEqual(almacen.limpiar_no_verificados(90000.0, 86400), 1)
        self.assertIsNotNone(almacen.obtener_usuario("otro"))
        with almacen._con() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM verificaciones").fetchone()[0], 0)

    def test_reservar_envio_respeta_el_tope_de_envios_y_restaurar_lo_devuelve(self):
        pendiente(ahora=1000.0)                                                     # envío 1
        self.assertEqual(almacen.reservar_envio("ana", 1060.0, 60, 3), 1000.0)      # envío 2
        self.assertEqual(almacen.reservar_envio("ana", 1120.0, 60, 3), 1060.0)      # envío 3
        self.assertEqual(almacen.reservar_envio("ana", 1180.0, 60, 3), "limite")    # el 4.º ya no
        self.assertEqual(almacen.datos_verificacion("ana")["envios"], 3)
        self.assertEqual(almacen.datos_verificacion("ana")["ultimo_envio"], 1120.0)  # y no toca la espera
        almacen.restaurar_envio("ana", 1060.0)                                      # el proveedor falló: devuelve el envío
        self.assertEqual(almacen.datos_verificacion("ana")["envios"], 2)
        self.assertEqual(almacen.reservar_envio("ana", 1180.0, 60, 3), 1060.0)
        self.assertEqual(almacen.reservar_envio("ana", 1240.0, 60), 1180.0)         # sin tope (por defecto) no se limita

    def test_marcar_verificado_con_hash_solo_vale_si_el_codigo_sigue_vigente(self):
        pendiente(hash_="H1")
        almacen.renovar_codigo("ana", "H2", "S2", 2000.0, 1500.0)                   # llegó un reenvío en medio
        self.assertFalse(almacen.marcar_verificado("ana", "H1"))                    # el código viejo ya no vale
        self.assertFalse(almacen.obtener_usuario("ana")["verificado"])
        self.assertIsNotNone(almacen.datos_verificacion("ana"))
        self.assertTrue(almacen.marcar_verificado("ana", "H2"))
        self.assertTrue(almacen.obtener_usuario("ana")["verificado"])
        self.assertFalse(almacen.marcar_verificado("ana", "H2"))                    # una segunda verificación no hace nada


# ==============================================================================
# TAREA 3: reglas (verificacion.py) con emisor y reloj falsos
# ==============================================================================
import contextlib
import io
from unittest import mock

import correo
import verificacion
from correo import ErrorCorreo

CONFIG = correo.Config(host="smtp.proveedor.test", puerto=587, usuario="u@proveedor.test", clave="clave-de-prueba",
                       remitente="Neon OS <no-responder@proveedor.test>")


class Emisor:
    """Emisor falso: guarda (destino, código) y puede fallar a pedido. Los códigos de profesor (solo los llevan los profesores)
    se guardan aparte, en el mismo orden que `enviados`: `profesor[n]` es el de `enviados[n]` o None."""

    def __init__(self):
        self.enviados, self.profesor, self.falla = [], [], None

    def __call__(self, destino, codigo, config=None, **kw):
        if self.falla:
            raise self.falla
        self.enviados.append((destino, codigo))
        self.profesor.append(kw.get("codigo_profesor"))


class Reloj:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class TestReglas(BDTestCase):
    def setUp(self):
        super().setUp()
        self.emisor, self.reloj = Emisor(), Reloj(1000.0)

    def registrar(self, usuario="ana", correo_="Ana@Correo.test", clave="clave123", rol="Estudiante", materia=None, grado="11", **kw):
        return verificacion.iniciar_registro(usuario, correo_, clave, rol, materia, grado, enviar=kw.get("emisor", self.emisor),
                                             reloj=kw.get("reloj", self.reloj), config=kw.get("config", CONFIG))

    def codigo(self, n=-1):
        return self.emisor.enviados[n][1]

    def incorrecto(self):
        return "000000" if self.codigo() != "000000" else "111111"

    # -- piezas puras --------------------------------------------------------------------
    def test_codigo_de_6_digitos_y_hash_con_sal(self):
        for _ in range(300):
            codigo = verificacion.generar_codigo()
            self.assertTrue(len(codigo) == 6 and codigo.isdigit(), codigo)
        self.assertEqual(verificacion.hash_codigo("123456", "s1"), verificacion.hash_codigo("123456", "s1"))
        self.assertNotEqual(verificacion.hash_codigo("123456", "s1"), verificacion.hash_codigo("123456", "s2"))
        self.assertNotEqual(verificacion.hash_codigo("123456", "s1"), verificacion.hash_codigo("123457", "s1"))
        self.assertEqual(len(verificacion.hash_codigo("123456", "s1")), 64)

    def test_correo_valido(self):
        for bueno in ("a@b.co", "ana.perez+neon@correo.com.co", "o'brien@x.org"):
            self.assertTrue(verificacion.correo_valido(bueno), bueno)
        for malo in ("", "sin", "a@b", "a b@c.co", "a@b.co\n", "a@b.co\r\nBcc: x@y.co", "@a.co", "a@@b.co", "a@b.co,c@d.co",
                     "x" * 70 + "@a.co", "a@" + "x" * 250 + ".co"):
            self.assertFalse(verificacion.correo_valido(malo), repr(malo))

    def test_mascara_del_correo(self):
        self.assertEqual(verificacion.mascara_correo("juan@gmail.com"), "j***@gmail.com")
        self.assertEqual(verificacion.mascara_correo("a@x.co"), "a***@x.co")
        self.assertEqual(verificacion.mascara_correo("sin-arroba"), "***")

    # -- registro ----------------------------------------------------------------------------
    def test_registro_feliz(self):
        r = self.registrar()
        self.assertEqual((r.ok, r.codigo), (True, "ok"))
        self.assertIn("a***@correo.test", r.mensaje)
        self.assertEqual(self.emisor.enviados[0][0], "ana@correo.test")
        self.assertTrue(len(self.codigo()) == 6 and self.codigo().isdigit())
        usuario = almacen.obtener_usuario("ana")
        self.assertEqual((usuario["verificado"], usuario["correo"]), (False, "ana@correo.test"))

    def test_sin_configuracion_no_toca_la_base_ni_envia(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            r = self.registrar(config=None)
        self.assertEqual((r.ok, r.codigo), (False, "config"))
        self.assertIn("no está configurado", r.mensaje)
        self.assertIsNone(almacen.obtener_usuario("ana"))
        self.assertEqual(self.emisor.enviados, [])

    def test_configuracion_invalida_tambien_se_informa_como_config(self):
        with mock.patch.dict(os.environ, {"NEON_CORREO_MODO": "produccion"}, clear=True):
            r = self.registrar(config=None)
        self.assertEqual((r.ok, r.codigo), (False, "config"))
        self.assertIsNone(almacen.obtener_usuario("ana"))

    def test_usuario_y_correo_duplicados(self):                         # enfoque de revisión 1 y 2
        self.assertTrue(self.registrar().ok)
        self.assertEqual(self.registrar().codigo, "usuario_existe")                                  # doble solicitud del mismo usuario
        self.assertEqual(self.registrar(usuario="beto", correo_="  ANA@correo.TEST ").codigo, "correo_existe")
        almacen.crear_usuario("carla", "Carla@Correo.test", "clave", "Estudiante", None, "11")
        self.assertEqual(self.registrar(usuario="dani", correo_="carla@correo.test").codigo, "correo_existe")
        self.assertEqual(len(self.emisor.enviados), 1)                                                # ninguno de los rechazados envió

    def test_correos_invalidos_no_crean_nada(self):                      # enfoque de revisión 2
        for malo in ("", "sin-arroba", "a b@c.co", "a@b.co\nBcc: x@y.co"):
            with self.subTest(correo=malo):
                self.assertEqual(self.registrar(correo_=malo).codigo, "correo_invalido")
        self.assertIsNone(almacen.obtener_usuario("ana"))
        self.assertEqual(self.emisor.enviados, [])

    def test_campos_vacios(self):
        self.assertEqual(self.registrar(usuario="  ").codigo, "datos")
        self.assertEqual(self.registrar(clave="").codigo, "datos")

    def test_fallo_del_proveedor_no_deja_cuenta_pendiente(self):         # enfoque de revisión 4
        self.emisor.falla = ErrorCorreo("El proveedor limitó el envío por ahora; inténtalo más tarde.", True)
        r = self.registrar()
        self.assertEqual((r.ok, r.codigo), (False, "envio"))
        self.assertIn("limitó", r.mensaje)
        self.assertIsNone(almacen.obtener_usuario("ana"))
        self.emisor.falla = None
        self.assertTrue(self.registrar().ok)                                                          # y se puede reintentar

    def test_un_error_inesperado_del_emisor_tambien_deshace_el_registro(self):
        self.emisor.falla = RuntimeError("explotó " + CONFIG.clave)
        r = self.registrar()
        self.assertEqual((r.ok, r.codigo), (False, "envio"))
        self.assertNotIn(CONFIG.clave, r.mensaje)
        self.assertNotIn("explotó", r.mensaje)
        self.assertIsNone(almacen.obtener_usuario("ana"))

    def test_pendientes_de_mas_de_24_horas_se_limpian_al_registrar_a_otro(self):
        self.registrar()
        self.reloj.t = 1000.0 + 86401
        r = self.registrar(usuario="beto", correo_="ana@correo.test")                                  # el correo de la pendiente vieja
        self.assertTrue(r.ok, r.mensaje)
        self.assertIsNone(almacen.obtener_usuario("ana"))

    # -- verificar ----------------------------------------------------------------------------
    def test_verificar_correcto(self):
        self.registrar()
        r = verificacion.verificar("ana", self.codigo(), reloj=self.reloj)
        self.assertEqual((r.ok, r.codigo), (True, "ok"))
        self.assertTrue(almacen.obtener_usuario("ana")["verificado"])
        self.assertIsNone(almacen.datos_verificacion("ana"))

    def test_verificar_incorrecto_cuenta_los_intentos_y_el_ultimo_avisa(self):
        self.registrar()
        mensajes = [verificacion.verificar("ana", self.incorrecto(), reloj=self.reloj) for _ in range(5)]
        self.assertTrue(all(m.codigo == "incorrecto" and not m.ok for m in mensajes))
        self.assertIn("4 intentos", mensajes[0].mensaje)
        self.assertIn("1 intento", mensajes[3].mensaje)
        self.assertIn("pide un código nuevo", mensajes[4].mensaje)

    def test_el_sexto_intento_con_el_codigo_correcto_esta_bloqueado(self):
        self.registrar()
        for _ in range(5):
            verificacion.verificar("ana", self.incorrecto(), reloj=self.reloj)
        r = verificacion.verificar("ana", self.codigo(), reloj=self.reloj)
        self.assertEqual((r.ok, r.codigo), (False, "intentos"))
        self.assertFalse(almacen.obtener_usuario("ana")["verificado"])

    def test_formato_invalido_no_gasta_intentos(self):
        self.registrar()
        for texto in ("", "12ab", "12345", "1234567", "12 34 5"):
            self.assertEqual(verificacion.verificar("ana", texto, reloj=self.reloj).codigo, "formato", repr(texto))
        self.assertEqual(almacen.datos_verificacion("ana")["intentos"], 0)
        self.assertTrue(verificacion.verificar("ana", " " + self.codigo() + " ", reloj=self.reloj).ok)   # espacios alrededor se ignoran

    def test_vigencia_de_10_minutos_en_el_borde(self):                   # enfoque de revisión 3
        self.registrar()
        self.reloj.t = 1000.0 + 599.9
        self.assertTrue(verificacion.verificar("ana", self.codigo(), reloj=self.reloj).ok)
        self.reloj.t = 5000.0
        self.registrar(usuario="beto", correo_="beto@correo.test")
        self.reloj.t = 5000.0 + 600.0
        r = verificacion.verificar("beto", self.codigo(), reloj=self.reloj)
        self.assertEqual((r.ok, r.codigo), (False, "vencido"))
        self.assertEqual(almacen.datos_verificacion("beto")["intentos"], 0)                            # vencido no gasta intentos

    def test_ya_verificada_y_cuenta_inexistente_y_verificacion_repetida(self):   # enfoque de revisión 1
        self.registrar()
        codigo = self.codigo()
        self.assertTrue(verificacion.verificar("ana", codigo, reloj=self.reloj).ok)
        self.assertEqual(verificacion.verificar("ana", codigo, reloj=self.reloj).codigo, "ya_verificada")
        self.assertEqual(verificacion.verificar("nadie", "123456", reloj=self.reloj).codigo, "no_existe")

    # -- reenviar ------------------------------------------------------------------------------
    def test_reenvio_cada_60_segundos_reinicia_intentos_e_invalida_el_codigo_anterior(self):   # enfoque de revisión 3
        with mock.patch.object(verificacion, "generar_codigo", side_effect=["111111", "222222"]):
            self.registrar()
            for _ in range(3):
                verificacion.verificar("ana", "999999", reloj=self.reloj)
            self.reloj.t = 1059.0
            r = verificacion.reenviar("ana", enviar=self.emisor, reloj=self.reloj, config=CONFIG)
            self.assertEqual((r.ok, r.codigo, r.segundos), (False, "espera", 1))
            self.assertEqual(len(self.emisor.enviados), 1)
            self.reloj.t = 1060.0
            r = verificacion.reenviar("ana", enviar=self.emisor, reloj=self.reloj, config=CONFIG)
        self.assertEqual((r.ok, r.codigo), (True, "ok"))
        self.assertEqual(self.emisor.enviados[1], ("ana@correo.test", "222222"))
        d = almacen.datos_verificacion("ana")
        self.assertEqual((d["intentos"], d["expira"], d["ultimo_envio"]), (0, 1660.0, 1060.0))
        self.assertEqual(verificacion.verificar("ana", "111111", reloj=self.reloj).codigo, "incorrecto")   # el viejo ya no sirve
        self.assertTrue(verificacion.verificar("ana", "222222", reloj=self.reloj).ok)

    def test_doble_clic_en_reenviar_solo_envia_uno(self):                # enfoque de revisión 1
        self.registrar()
        self.reloj.t = 1100.0
        primero = verificacion.reenviar("ana", enviar=self.emisor, reloj=self.reloj, config=CONFIG)
        segundo = verificacion.reenviar("ana", enviar=self.emisor, reloj=self.reloj, config=CONFIG)
        self.assertEqual((primero.ok, segundo.ok, segundo.codigo, segundo.segundos), (True, False, "espera", 60))
        self.assertEqual(len(self.emisor.enviados), 2)

    def test_fallo_del_proveedor_en_el_reenvio_no_cambia_nada_ni_gasta_la_espera(self):   # enfoque de revisión 4
        self.registrar()
        antes = almacen.datos_verificacion("ana")
        self.reloj.t = 1100.0
        self.emisor.falla = ErrorCorreo("No se pudo conectar con el servidor de correo.", True)
        r = verificacion.reenviar("ana", enviar=self.emisor, reloj=self.reloj, config=CONFIG)
        self.assertEqual((r.ok, r.codigo), (False, "envio"))
        self.assertEqual(almacen.datos_verificacion("ana"), antes)
        self.emisor.falla = None
        self.assertTrue(verificacion.reenviar("ana", enviar=self.emisor, reloj=self.reloj, config=CONFIG).ok)   # sin esperar otros 60 s

    def test_reenviar_sin_configuracion_cuenta_inexistente_y_verificada(self):
        self.registrar()
        self.reloj.t = 1100.0
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(verificacion.reenviar("ana", enviar=self.emisor, reloj=self.reloj).codigo, "config")
        self.assertEqual(verificacion.reenviar("nadie", enviar=self.emisor, reloj=self.reloj, config=CONFIG).codigo, "no_existe")
        verificacion.verificar("ana", self.codigo(), reloj=self.reloj)
        self.assertEqual(verificacion.reenviar("ana", enviar=self.emisor, reloj=self.reloj, config=CONFIG).codigo, "ya_verificada")

    def test_si_el_reloj_retrocede_la_espera_no_pasa_de_60_segundos(self):   # enfoque de revisión 3
        self.registrar()
        self.reloj.t = 900.0
        r = verificacion.reenviar("ana", enviar=self.emisor, reloj=self.reloj, config=CONFIG)
        self.assertEqual((r.codigo, r.segundos), ("espera", 60))
        self.assertEqual(verificacion.segundos_para_reenviar("ana", reloj=self.reloj), 60)

    def test_segundos_para_reenviar(self):
        self.registrar()
        for ahora, esperado in ((1000.0, 60), (1030.0, 30), (1059.5, 1), (1060.0, 0), (2000.0, 0)):
            self.reloj.t = ahora
            self.assertEqual(verificacion.segundos_para_reenviar("ana", reloj=self.reloj), esperado, ahora)
        self.assertEqual(verificacion.segundos_para_reenviar("nadie", reloj=self.reloj), 0)

    # -- cancelar --------------------------------------------------------------------------------
    def test_cancelar_registro_pide_la_contrasena(self):
        self.registrar()
        self.assertEqual(verificacion.cancelar_registro("ana", "mala").codigo, "clave")
        self.assertIsNotNone(almacen.obtener_usuario("ana"))
        r = verificacion.cancelar_registro("ana", "clave123")
        self.assertEqual((r.ok, r.codigo), (True, "ok"))
        self.assertIsNone(almacen.obtener_usuario("ana"))
        self.assertTrue(self.registrar().ok)                                                           # usuario y correo quedan libres

    def test_cancelar_no_borra_cuentas_verificadas_ni_inexistentes(self):
        almacen.crear_usuario("carla", "c@x.test", "clave123", "Estudiante", None, "11")
        self.assertEqual(verificacion.cancelar_registro("carla", "clave123").codigo, "ya_verificada")
        self.assertIsNotNone(almacen.obtener_usuario("carla"))
        self.assertEqual(verificacion.cancelar_registro("nadie", "x").codigo, "no_existe")

    # -- revisión independiente de la pieza 4 ------------------------------------------------------------------
    def test_roles_invalidos_se_rechazan(self):
        for rol in ("Hacker", "Administrador", "", "estudiante", None):
            with self.subTest(rol=rol):
                self.assertEqual(self.registrar(rol=rol).codigo, "datos")
        self.assertIsNone(almacen.obtener_usuario("ana"))
        self.assertEqual(self.emisor.enviados, [])
        self.assertTrue(self.registrar(usuario="profe", correo_="profe@correo.test", rol="Profesor", materia="Física", grado=None).ok)

    def test_tope_de_cinco_codigos_por_cuenta(self):
        self.registrar()                                                           # código 1
        for n in range(4):                                                         # códigos 2 a 5
            self.reloj.t = 1060.0 * (n + 1)
            self.assertTrue(verificacion.reenviar("ana", enviar=self.emisor, reloj=self.reloj, config=CONFIG).ok, n)
        self.reloj.t = 100000.0                                                    # mucho tiempo después: la espera ya no es el límite
        r = verificacion.reenviar("ana", enviar=self.emisor, reloj=self.reloj, config=CONFIG)
        self.assertEqual((r.ok, r.codigo), (False, "limite"))
        self.assertIn("máximo", r.mensaje)
        self.assertEqual(len(self.emisor.enviados), 5)
        self.assertEqual(almacen.datos_verificacion("ana")["envios"], 5)
        self.assertTrue(verificacion.verificar("ana", self.codigo(), reloj=Reloj(4300.0)).ok)       # el último código sigue valiendo

    def test_con_el_tope_alcanzado_se_puede_cancelar_y_empezar_de_nuevo(self):
        self.registrar()
        for n in range(4):
            self.reloj.t = 1060.0 * (n + 1)
            verificacion.reenviar("ana", enviar=self.emisor, reloj=self.reloj, config=CONFIG)
        self.assertEqual(verificacion.reenviar("ana", enviar=self.emisor, reloj=Reloj(99999.0), config=CONFIG).codigo, "limite")
        self.assertTrue(verificacion.cancelar_registro("ana", "clave123").ok)
        self.assertTrue(self.registrar(reloj=Reloj(100000.0)).ok)

    def test_un_envio_fallido_no_gasta_uno_de_los_cinco(self):
        self.registrar()
        self.emisor.falla = ErrorCorreo("No se pudo conectar con el servidor de correo.", True)
        for n in range(8):
            self.reloj.t = 1060.0 * (n + 1)
            self.assertEqual(verificacion.reenviar("ana", enviar=self.emisor, reloj=self.reloj, config=CONFIG).codigo, "envio")
        self.assertEqual(almacen.datos_verificacion("ana")["envios"], 1)
        self.emisor.falla = None
        self.assertTrue(verificacion.reenviar("ana", enviar=self.emisor, reloj=self.reloj, config=CONFIG).ok)
        self.assertEqual(almacen.datos_verificacion("ana")["envios"], 2)

    def test_un_codigo_reemplazado_mientras_se_verifica_ya_no_vale(self):
        self.registrar()
        viejo = self.codigo()
        original = almacen.consumir_intento

        def con_reenvio_en_medio(usuario, maximo):
            almacen.renovar_codigo(usuario, "otro-hash", "otra-sal", 9999.0, 1000.0)    # entra un reenvío justo ahora
            return original(usuario, maximo)

        with mock.patch.object(almacen, "consumir_intento", con_reenvio_en_medio):
            r = verificacion.verificar("ana", viejo, reloj=self.reloj)
        self.assertFalse(r.ok)
        self.assertEqual(r.codigo, "vencido")
        self.assertFalse(almacen.obtener_usuario("ana")["verificado"])

    def test_dos_verificaciones_simultaneas_con_el_mismo_codigo_solo_verifican_una_vez(self):
        self.registrar()
        codigo = self.codigo()
        original = almacen.consumir_intento

        def con_otra_verificacion_en_medio(usuario, maximo):
            almacen.marcar_verificado(usuario)                                          # la otra ventana ganó la carrera
            return original(usuario, maximo)

        with mock.patch.object(almacen, "consumir_intento", con_otra_verificacion_en_medio):
            r = verificacion.verificar("ana", codigo, reloj=self.reloj)
        self.assertEqual((r.ok, r.codigo), (False, "ya_verificada"))
        self.assertTrue(almacen.obtener_usuario("ana")["verificado"])

    def test_reenviar_a_una_cuenta_que_desaparece_a_mitad_responde_no_existe(self):
        self.registrar()
        self.reloj.t = 1100.0

        class EmisorQueBorra(Emisor):
            def __call__(inner, destino, codigo, config=None, **kw):
                almacen.cancelar_pendiente("ana")                                       # la limpieza la borró durante el envío
                super().__call__(destino, codigo, config)

        r = verificacion.reenviar("ana", enviar=EmisorQueBorra(), reloj=self.reloj, config=CONFIG)
        self.assertEqual((r.ok, r.codigo), (False, "no_existe"))

    def test_una_cuenta_borrada_antes_de_reservar_el_envio_no_dice_espera_60_s(self):
        self.registrar()
        self.reloj.t = 1100.0
        original = almacen.reservar_envio

        def borrada_antes(usuario, ahora, espera, maximo=None):
            almacen.cancelar_pendiente(usuario)
            return original(usuario, ahora, espera, maximo)

        with mock.patch.object(almacen, "reservar_envio", borrada_antes):
            r = verificacion.reenviar("ana", enviar=self.emisor, reloj=self.reloj, config=CONFIG)
        self.assertEqual((r.ok, r.codigo), (False, "no_existe"))
        self.assertEqual(len(self.emisor.enviados), 1)

    # -- simultaneidad REAL con hilos (la revisión independiente la comprobó a mano; aquí queda como prueba) ----------------
    @staticmethod
    def en_paralelo(n, trabajo):
        import threading
        resultados, hilos = [None] * n, []

        def correr(i):
            resultados[i] = trabajo(i)

        for i in range(n):
            hilos.append(threading.Thread(target=correr, args=(i,)))
        for h in hilos:
            h.start()
        for h in hilos:
            h.join(60)
        return resultados

    def test_doce_verificaciones_simultaneas_con_codigos_malos_gastan_exactamente_cinco_intentos(self):
        self.registrar()
        mal = self.incorrecto()
        rs = self.en_paralelo(12, lambda i: verificacion.verificar("ana", mal, reloj=self.reloj).codigo)
        self.assertEqual((rs.count("incorrecto"), rs.count("intentos")), (5, 7))
        self.assertEqual(almacen.datos_verificacion("ana")["intentos"], 5)

    def test_ocho_reenvios_simultaneos_solo_envian_uno(self):
        self.registrar()
        self.reloj.t = 1100.0
        rs = self.en_paralelo(8, lambda i: verificacion.reenviar("ana", enviar=self.emisor, reloj=self.reloj, config=CONFIG))
        self.assertEqual(sorted(r.codigo for r in rs), ["espera"] * 7 + ["ok"])
        self.assertEqual(len(self.emisor.enviados), 2)

    def test_ocho_registros_simultaneos_con_el_mismo_correo_solo_crean_una_cuenta(self):
        rs = self.en_paralelo(8, lambda i: self.registrar(usuario=f"u{i}", correo_="mismo@correo.test").codigo)
        self.assertEqual(sorted(rs), ["correo_existe"] * 7 + ["ok"])
        self.assertEqual(len(self.emisor.enviados), 1)
        with almacen._con() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0], 1)

    def test_dos_verificaciones_correctas_simultaneas_verifican_una_sola_vez(self):
        self.registrar()
        codigo = self.codigo()
        rs = self.en_paralelo(2, lambda i: verificacion.verificar("ana", codigo, reloj=self.reloj).codigo)
        self.assertEqual(sorted(rs), ["ok", "ya_verificada"])

    # -- secretos y modo desarrollo ---------------------------------------------------------------
    def test_el_codigo_en_claro_no_esta_en_la_base_ni_en_ningun_mensaje(self):   # enfoque de revisión 5
        with mock.patch.object(verificacion, "generar_codigo", side_effect=["654321", "654322"]):
            mensajes = [self.registrar().mensaje]
            self.reloj.t = 1100.0
            mensajes.append(verificacion.reenviar("ana", enviar=self.emisor, reloj=self.reloj, config=CONFIG).mensaje)
        mensajes.append(verificacion.verificar("ana", "000000", reloj=self.reloj).mensaje)
        with open(almacen.RUTA, "rb") as f:
            crudo = f.read()
        for codigo in ("654321", "654322"):
            self.assertNotIn(codigo.encode(), crudo)
            for mensaje in mensajes:
                self.assertNotIn(codigo, mensaje)

    def test_modo_consola_imprime_el_codigo_y_avisa_en_el_mensaje(self):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            r = verificacion.iniciar_registro("ana", "ana@correo.test", "clave123", "Estudiante", None, "11",
                                              reloj=self.reloj, config=correo.Config(modo="consola"))
        self.assertTrue(r.ok, r.mensaje)
        self.assertIn("modo desarrollo", r.mensaje)
        codigo = salida.getvalue().split("ana@correo.test: ")[1].strip()
        self.assertTrue(verificacion.verificar("ana", codigo, reloj=self.reloj).ok)

    def test_en_modo_smtp_nada_se_imprime(self):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(salida):
            self.registrar()
            verificacion.verificar("ana", self.incorrecto(), reloj=self.reloj)
        self.assertEqual(salida.getvalue(), "")


# ==============================================================================
# Cuentas de demostración: ya no se siembran con una clave escrita en el código
# ==============================================================================
CLAVE_ANTIGUA = "123"            # la clave con la que se sembraban antes camilo y daniel
CLAVE_DEMO = "Demo-clave-larga-1"


class TestCuentasDemo(BDTestCase):
    def base_nueva(self):
        almacen.RUTA = os.path.join(_TMP, f"demo_{time.time_ns()}.db")
        return almacen.RUTA

    def nombres(self):
        with almacen._con() as c:
            return sorted(f[0] for f in c.execute("SELECT usuario FROM usuarios WHERE rol <> 'Administrador'"))

    def con_cuentas_antiguas(self, **cambios):
        """Una base como la de una instalación vieja: camilo y daniel con la clave antigua (salvo los que se cambien)."""
        for nombre, rol, materia, grado in (("camilo", "Profesor", "Física", None), ("daniel", "Estudiante", None, "11")):
            almacen.crear_usuario(nombre, f"{nombre}@edu.co", cambios.get(nombre, CLAVE_ANTIGUA), rol, materia, grado)

    # -- semilla opcional por entorno --------------------------------------------------------------
    def test_una_base_nueva_no_trae_cuentas_de_demostracion(self):
        self.base_nueva()
        with mock.patch.dict(os.environ, {}, clear=True):
            almacen.iniciar()
        self.assertEqual(self.nombres(), [])

    def test_con_la_clave_demo_en_el_entorno_se_siembran_las_dos_cuentas_verificadas(self):
        self.base_nueva()
        with mock.patch.dict(os.environ, {"NEON_DEMO_CLAVE": f"  {CLAVE_DEMO}  "}, clear=True):
            almacen.iniciar()
            almacen.iniciar()                                                # idempotente: no duplica ni falla
        self.assertEqual(self.nombres(), ["camilo", "daniel"])
        for nombre in ("camilo", "daniel"):
            self.assertTrue(almacen.obtener_usuario(nombre)["verificado"])
            self.assertTrue(almacen.verificar_clave(nombre, CLAVE_DEMO))
            self.assertFalse(almacen.verificar_clave(nombre, CLAVE_ANTIGUA))
        self.assertEqual((almacen.obtener_usuario("camilo")["role"], almacen.obtener_usuario("daniel")["grado"]), ("Profesor", "11"))

    def test_una_clave_demo_corta_no_siembra_nada_y_avisa_sin_mostrar_la_clave(self):
        for corta in (CLAVE_ANTIGUA, "corta", "1234567"):
            with self.subTest(corta=corta):
                self.base_nueva()
                aviso = io.StringIO()
                with mock.patch.dict(os.environ, {"NEON_DEMO_CLAVE": corta}, clear=True), contextlib.redirect_stderr(aviso):
                    almacen.iniciar()
                self.assertEqual(self.nombres(), [])
                self.assertIn("NEON_DEMO_CLAVE", aviso.getvalue())
                self.assertNotIn(corta + "\n", aviso.getvalue().replace("NEON_DEMO_CLAVE", ""))

    def test_no_se_siembra_si_ya_hay_usuarios(self):
        self.base_nueva()
        almacen.iniciar()
        almacen.crear_usuario("carla", "c@x.test", "otra-clave-larga", "Estudiante", None, "11")
        with mock.patch.dict(os.environ, {"NEON_DEMO_CLAVE": CLAVE_DEMO}, clear=True):
            almacen.iniciar()
        self.assertEqual(self.nombres(), ["carla"])

    # -- detectar y retirar las cuentas demo que quedaron con la clave antigua ------------------------
    def test_se_detectan_solo_las_cuentas_demo_que_conservan_la_clave_antigua(self):
        self.con_cuentas_antiguas(daniel="una-clave-nueva-larga")            # daniel ya cambió su clave
        almacen.crear_usuario("carla", "c@x.test", CLAVE_ANTIGUA, "Estudiante", None, "11")   # no es una cuenta demo: no se toca
        self.assertEqual(almacen.cuentas_demo_con_clave_antigua(), ["camilo"])

    def test_listar_no_modifica_la_base(self):
        self.con_cuentas_antiguas()
        with open(almacen.RUTA, "rb") as f:
            antes = f.read()
        almacen.cuentas_demo_con_clave_antigua()
        with open(almacen.RUTA, "rb") as f:
            self.assertEqual(f.read(), antes)

    def test_retirar_borra_solo_esas_cuentas_y_su_progreso(self):
        self.con_cuentas_antiguas(daniel="una-clave-nueva-larga")
        almacen.crear_usuario("carla", "c@x.test", CLAVE_ANTIGUA, "Estudiante", None, "11")
        for nombre in ("camilo", "daniel", "carla"):
            almacen.guardar_progreso(nombre, {"coins": 5, "puntos": 5})
        almacen.ocultar_del_ranking("camilo")
        self.assertEqual(almacen.retirar_cuentas_demo(), ["camilo"])
        self.assertEqual(self.nombres(), ["carla", "daniel"])
        self.assertIsNone(almacen.cargar_progreso("camilo"))
        self.assertIsNotNone(almacen.cargar_progreso("daniel"))
        self.assertIsNotNone(almacen.cargar_progreso("carla"))
        self.assertNotIn("camilo", almacen.ocultos_del_ranking())
        self.assertEqual(almacen.retirar_cuentas_demo(), [])                  # repetirlo no hace nada

    def test_el_comando_sin_si_no_borra_y_con_si_borra(self):
        self.con_cuentas_antiguas()
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            self.assertEqual(almacen.main(["--cuentas-demo"]), 0)
            self.assertEqual(almacen.main(["--retirar-cuentas-demo"]), 2)       # sin --si: solo avisa
        self.assertEqual(self.nombres(), ["camilo", "daniel"])
        self.assertIn("camilo", salida.getvalue())
        self.assertIn("--si", salida.getvalue())
        self.assertNotIn("$", salida.getvalue())                                 # nunca imprime hashes
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            self.assertEqual(almacen.main(["--retirar-cuentas-demo", "--si"]), 0)
        self.assertEqual(self.nombres(), [])
        self.assertIn("camilo", salida.getvalue())
        with contextlib.redirect_stdout(io.StringIO()) as sin_nada:
            self.assertEqual(almacen.main(["--retirar-cuentas-demo", "--si"]), 0)
        self.assertIn("No hay", sin_nada.getvalue())

    def test_el_comando_se_puede_ejecutar_como_script(self):
        """Como lo lanzaría quien administra la instalación: `python almacen.py ...` (un proceso aparte, con NEON_DB)."""
        import subprocess
        self.con_cuentas_antiguas()
        entorno = {**os.environ, "NEON_DB": almacen.RUTA, "PYTHONIOENCODING": "utf-8"}
        carpeta = os.path.dirname(os.path.abspath(almacen.__file__))

        def correr(*args):
            r = subprocess.run([sys.executable, "almacen.py", *args], cwd=carpeta, env=entorno, capture_output=True, text=True,
                               encoding="utf-8", timeout=60)
            return r.returncode, r.stdout

        codigo, salida = correr("--cuentas-demo")
        self.assertEqual(codigo, 0)
        self.assertIn("camilo", salida)
        self.assertIn("daniel", salida)
        codigo, salida = correr("--retirar-cuentas-demo")
        self.assertEqual(codigo, 2)                                             # sin --si no borra
        self.assertEqual(self.nombres(), ["camilo", "daniel"])
        codigo, salida = correr("--retirar-cuentas-demo", "--si")
        self.assertEqual(codigo, 0)
        self.assertEqual(self.nombres(), [])
        self.assertEqual(correr()[0], 2)                                        # sin argumentos: el uso

    def test_el_comando_sin_argumentos_muestra_el_uso(self):
        with contextlib.redirect_stdout(io.StringIO()) as salida:
            self.assertEqual(almacen.main([]), 2)
        self.assertIn("--retirar-cuentas-demo", salida.getvalue())

    def test_una_base_que_no_existe_no_se_crea_al_listar_ni_al_retirar(self):
        almacen.RUTA = os.path.join(_TMP, f"nunca_{time.time_ns()}.db")
        self.assertEqual(almacen.cuentas_demo_con_clave_antigua(), [])
        self.assertEqual(almacen.retirar_cuentas_demo(), [])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(almacen.main(["--retirar-cuentas-demo", "--si"]), 0)
        self.assertFalse(os.path.exists(almacen.RUTA))

    def test_un_archivo_que_no_es_una_base_de_neon_no_rompe_el_listado(self):
        almacen.RUTA = os.path.join(_TMP, f"ajena_{time.time_ns()}.db")
        con = sqlite3.connect(almacen.RUTA)
        con.execute("CREATE TABLE otra_cosa (x)")
        con.commit()
        con.close()
        self.assertEqual(almacen.cuentas_demo_con_clave_antigua(), [])
        self.assertEqual(almacen.retirar_cuentas_demo(), [])


# ==============================================================================
# Código de profesor: único, aleatorio y entregado por correo junto con el código de verificación
# ==============================================================================
import re

PATRON_PROFESOR = re.compile(r"^[A-HJ-KM-NP-Z2-9]{5}-[A-HJ-KM-NP-Z2-9]{5}$")


class TestCodigoProfesor(BDTestCase):
    def setUp(self):
        super().setUp()
        self.emisor, self.reloj = Emisor(), Reloj(1000.0)

    def registrar(self, usuario="profe", rol="Profesor", **kw):
        return verificacion.iniciar_registro(usuario, f"{usuario}@correo.test", "clave123", rol, "Física" if rol == "Profesor" else None,
                                             "11" if rol == "Estudiante" else None, enviar=kw.get("emisor", self.emisor),
                                             reloj=self.reloj, config=CONFIG)

    def verificar(self, usuario, codigo, codigo_profesor, **kw):
        return verificacion.verificar(usuario, codigo, codigo_profesor=codigo_profesor, reloj=self.reloj, **kw)

    def ajeno(self, codigo_profesor):
        """Un código de profesor con forma válida pero distinto del dado."""
        return "AAAAA-AAAAA" if codigo_profesor != "AAAAA-AAAAA" else "BBBBB-BBBBB"

    # -- el código en sí -----------------------------------------------------------------------
    def test_el_formato_es_xxxxx_xxxxx_sin_caracteres_que_se_confundan(self):
        for _ in range(300):
            codigo = verificacion.generar_codigo_profesor()
            self.assertRegex(codigo, PATRON_PROFESOR)
            self.assertFalse(set(codigo) & set("ILO01"), codigo)

    def test_es_aleatorio(self):
        codigos = {verificacion.generar_codigo_profesor() for _ in range(500)}
        self.assertEqual(len(codigos), 500)                          # 50 bits: no se repite

    def test_se_acepta_en_minusculas_con_o_sin_guion_y_con_espacios(self):
        for escrito in ("k7m2q-x9tr4", "K7M2QX9TR4", " k7m2q x9tr4 ", "K7M2Q - X9TR4", "k7m2q-x9tr4\n"):
            with self.subTest(escrito=escrito):
                self.assertTrue(verificacion.codigo_profesor_valido(escrito))
                self.assertEqual(verificacion.normalizar_codigo_profesor(escrito), "K7M2QX9TR4")
                self.assertEqual(verificacion.huella_codigo_profesor(escrito), verificacion.huella_codigo_profesor("K7M2Q-X9TR4"))
        for malo in ("", None, "K7M2Q", "K7M2Q-X9TR45", "K7M2Q-X9TR0", "K7M2Q-X9TRI", "K7M2Q-X9T!4"):
            with self.subTest(malo=malo):
                self.assertFalse(verificacion.codigo_profesor_valido(malo))

    def test_la_huella_cambia_con_el_codigo(self):
        a, b = verificacion.huella_codigo_profesor("K7M2Q-X9TR4"), verificacion.huella_codigo_profesor("K7M2Q-X9TR5")
        self.assertNotEqual(a, b)
        self.assertEqual(len(a), 64)

    # -- el correo lo trae --------------------------------------------------------------------------
    def test_el_profesor_recibe_los_dos_codigos_en_el_mismo_correo(self):
        r = self.registrar()
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(len(self.emisor.enviados), 1)                    # un solo correo
        self.assertEqual(self.emisor.enviados[0][0], "profe@correo.test")
        self.assertRegex(self.emisor.profesor[0], PATRON_PROFESOR)
        self.assertIn("código de profesor", r.mensaje)
        self.assertNotIn(self.emisor.profesor[0], r.mensaje)              # el mensaje de la pantalla nunca lo muestra

    def test_el_estudiante_no_recibe_codigo_de_profesor(self):
        self.assertTrue(self.registrar("ana", "Estudiante").ok)
        self.assertEqual(self.emisor.profesor, [None])
        self.assertIsNone(almacen.datos_verificacion("ana")["prof_huella"])

    def test_dos_profesores_reciben_codigos_distintos_y_cada_uno_solo_sirve_a_su_dueno(self):
        self.assertTrue(self.registrar("profe1").ok)
        self.assertTrue(self.registrar("profe2").ok)
        (c1, c2), (p1, p2) = [e[1] for e in self.emisor.enviados], self.emisor.profesor
        self.assertNotEqual(p1, p2)
        self.assertEqual(verificacion.verificar("profe1", c1, codigo_profesor=p2, reloj=self.reloj).codigo, "incorrecto")   # el de otro no vale
        self.assertFalse(almacen.obtener_usuario("profe1")["verificado"])
        self.assertTrue(verificacion.verificar("profe1", c1, codigo_profesor=p1, reloj=self.reloj).ok)
        self.assertTrue(verificacion.verificar("profe2", c2, codigo_profesor=p2, reloj=self.reloj).ok)

    def test_un_codigo_ya_entregado_nunca_se_vuelve_a_entregar(self):
        with mock.patch.object(verificacion, "generar_codigo_profesor", side_effect=["AAAAA-AAAAA", "AAAAA-AAAAA", "AAAAA-AAAAA", "BBBBB-BBBBB"]):
            self.assertTrue(self.registrar("profe1").ok)
            self.assertTrue(self.registrar("profe2").ok)               # el generador repitió dos veces el primero: se descartan
        self.assertEqual(self.emisor.profesor, ["AAAAA-AAAAA", "BBBBB-BBBBB"])
        self.assertTrue(almacen.reservar_codigo_profesor("CCCCC") and not almacen.reservar_codigo_profesor("CCCCC"))

    def test_un_codigo_usado_por_un_profesor_ya_verificado_tampoco_se_reparte_de_nuevo(self):
        with mock.patch.object(verificacion, "generar_codigo_profesor", side_effect=["AAAAA-AAAAA", "AAAAA-AAAAA", "BBBBB-BBBBB"]):
            self.assertTrue(self.registrar("profe1").ok)
            self.assertTrue(self.verificar("profe1", self.emisor.enviados[0][1], "AAAAA-AAAAA").ok)
            self.assertTrue(self.registrar("profe2").ok)
        self.assertEqual(self.emisor.profesor[1], "BBBBB-BBBBB")

    # -- verificar ---------------------------------------------------------------------------------
    def test_con_los_dos_codigos_correctos_el_profesor_queda_verificado(self):
        self.registrar()
        r = self.verificar("profe", self.emisor.enviados[0][1], self.emisor.profesor[0])
        self.assertEqual((r.ok, r.codigo), (True, "ok"))
        self.assertTrue(almacen.obtener_usuario("profe")["verificado"])
        self.assertIsNone(almacen.datos_verificacion("profe"))

    def test_vale_escribirlo_en_minusculas_y_sin_guion(self):
        self.registrar()
        self.assertTrue(self.verificar("profe", self.emisor.enviados[0][1], self.emisor.profesor[0].lower().replace("-", " ")).ok)

    def test_sin_el_codigo_de_profesor_o_con_forma_invalida_no_gasta_intentos(self):
        self.registrar()
        codigo = self.emisor.enviados[0][1]
        for escrito in (None, "", "   ", "ABC", "AAAAA-AAAA0", self.emisor.profesor[0] + "X"):
            with self.subTest(escrito=escrito):
                r = self.verificar("profe", codigo, escrito)
                self.assertEqual((r.ok, r.codigo), (False, "formato_profesor"))
        self.assertEqual(almacen.datos_verificacion("profe")["intentos"], 0)
        self.assertFalse(almacen.obtener_usuario("profe")["verificado"])

    def test_codigo_de_verificacion_correcto_con_codigo_de_profesor_equivocado_no_verifica_y_gasta_un_intento(self):
        self.registrar()
        r = self.verificar("profe", self.emisor.enviados[0][1], self.ajeno(self.emisor.profesor[0]))
        self.assertEqual((r.ok, r.codigo), (False, "incorrecto"))
        self.assertIn("4 intentos", r.mensaje)
        self.assertIn("profesor", r.mensaje)
        self.assertEqual(almacen.datos_verificacion("profe")["intentos"], 1)

    def test_codigo_de_profesor_correcto_con_codigo_de_verificacion_equivocado_tampoco_verifica(self):
        self.registrar()
        malo = "000000" if self.emisor.enviados[0][1] != "000000" else "111111"
        r = self.verificar("profe", malo, self.emisor.profesor[0])
        self.assertEqual((r.ok, r.codigo), (False, "incorrecto"))
        self.assertFalse(almacen.obtener_usuario("profe")["verificado"])

    def test_los_intentos_son_compartidos_el_sexto_con_los_dos_correctos_esta_bloqueado(self):
        self.registrar()
        for _ in range(5):
            self.verificar("profe", "000000" if self.emisor.enviados[0][1] != "000000" else "111111", self.ajeno(self.emisor.profesor[0]))
        r = self.verificar("profe", self.emisor.enviados[0][1], self.emisor.profesor[0])
        self.assertEqual((r.ok, r.codigo), (False, "intentos"))

    def test_el_codigo_de_profesor_no_sirve_para_verificar_a_un_estudiante_ni_hace_falta(self):
        self.registrar("ana", "Estudiante")
        self.assertTrue(self.verificar("ana", self.emisor.enviados[0][1], None).ok)        # el estudiante no lo necesita
        self.registrar("beto", "Estudiante")
        self.assertTrue(self.verificar("beto", self.emisor.enviados[1][1], "cualquier cosa").ok)   # y si lo escribe, se ignora

    # -- reenvío ----------------------------------------------------------------------------------
    def test_el_reenvio_trae_un_codigo_de_profesor_nuevo_y_el_anterior_deja_de_valer(self):
        self.registrar()
        self.reloj.t = 1060.0
        r = verificacion.reenviar("profe", enviar=self.emisor, reloj=self.reloj, config=CONFIG)
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(len(self.emisor.enviados), 2)
        viejo, nuevo = self.emisor.profesor
        self.assertRegex(nuevo, PATRON_PROFESOR)
        self.assertNotEqual(viejo, nuevo)
        self.assertEqual(self.verificar("profe", self.emisor.enviados[1][1], viejo).codigo, "incorrecto")
        self.assertTrue(self.verificar("profe", self.emisor.enviados[1][1], nuevo).ok)

    def test_un_fallo_del_proveedor_en_el_reenvio_deja_vigente_el_codigo_de_profesor_anterior(self):
        self.registrar()
        self.reloj.t = 1100.0
        self.emisor.falla = ErrorCorreo("No se pudo conectar con el servidor de correo.", True)
        self.assertEqual(verificacion.reenviar("profe", enviar=self.emisor, reloj=self.reloj, config=CONFIG).codigo, "envio")
        self.emisor.falla = None
        self.assertTrue(self.verificar("profe", self.emisor.enviados[0][1], self.emisor.profesor[0]).ok)

    def test_una_cuenta_pendiente_de_antes_sin_codigo_de_profesor_se_arregla_reenviando(self):
        self.registrar()
        with almacen._con() as c:
            c.execute("UPDATE verificaciones SET prof_huella = NULL")               # como una cuenta creada con la versión anterior
        self.assertEqual(self.verificar("profe", self.emisor.enviados[0][1], "AAAAA-AAAAA").codigo, "incorrecto")
        self.reloj.t = 1100.0
        self.assertTrue(verificacion.reenviar("profe", enviar=self.emisor, reloj=self.reloj, config=CONFIG).ok)
        self.assertTrue(self.verificar("profe", self.emisor.enviados[1][1], self.emisor.profesor[1]).ok)

    # -- registro fallido y privacidad ----------------------------------------------------------------
    def test_si_el_correo_no_sale_no_queda_cuenta_de_profesor(self):
        self.emisor.falla = ErrorCorreo("El proveedor limitó el envío por ahora; inténtalo más tarde.", True)
        self.assertEqual(self.registrar().codigo, "envio")
        self.assertIsNone(almacen.obtener_usuario("profe"))
        self.emisor.falla = None
        self.assertTrue(self.registrar().ok)

    def test_los_codigos_en_claro_no_estan_en_la_base_ni_en_los_mensajes(self):
        r = self.registrar()
        self.reloj.t = 1100.0
        mensajes = [r.mensaje, verificacion.reenviar("profe", enviar=self.emisor, reloj=self.reloj, config=CONFIG).mensaje,
                    self.verificar("profe", "000000", self.ajeno(self.emisor.profesor[1])).mensaje]
        with open(almacen.RUTA, "rb") as f:
            crudo = f.read()
        for codigo in self.emisor.profesor:
            for forma in (codigo, codigo.replace("-", "")):
                self.assertNotIn(forma.encode(), crudo)
                for mensaje in mensajes:
                    self.assertNotIn(forma, mensaje)

    def test_modo_consola_imprime_tambien_el_codigo_de_profesor(self):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            r = verificacion.iniciar_registro("profe", "profe@correo.test", "clave123", "Profesor", "Física", None,
                                              reloj=self.reloj, config=correo.Config(modo="consola"))
        self.assertTrue(r.ok, r.mensaje)
        texto = salida.getvalue()
        codigo = texto.split("Código para profe@correo.test: ")[1].splitlines()[0].strip()
        profesor = texto.split("Código de profesor para profe@correo.test: ")[1].splitlines()[0].strip()
        self.assertRegex(profesor, PATRON_PROFESOR)
        self.assertTrue(verificacion.verificar("profe", codigo, codigo_profesor=profesor, reloj=self.reloj).ok)


# ==============================================================================
# Administradores predeterminados: cuentas en la base, sin contraseña hasta el primer acceso por correo
# ==============================================================================
ADMIN_1, ADMIN_2 = "luisbaco2005@gmail.com", "dsandovaltorres05@gmail.com"
CLAVE_NUEVA_ADMIN = "Mi-clave-segura-1"


class TestAdministradores(BDTestCase):
    def setUp(self):
        super().setUp()
        almacen.iniciar()                           # el BDTestCase las borra; así vuelven a crearse como en un primer arranque
        self.emisor, self.reloj = Emisor(), Reloj(1000.0)

    def pedir_codigo(self, correo_=ADMIN_1):
        r = verificacion.reenviar(correo_, enviar=self.emisor, reloj=self.reloj, config=CONFIG)
        self.assertTrue(r.ok, r.mensaje)
        return self.emisor.enviados[-1][1]

    def activar(self, correo_=ADMIN_1, clave=CLAVE_NUEVA_ADMIN):
        return verificacion.verificar(correo_, self.pedir_codigo(correo_), clave_nueva=clave, reloj=self.reloj)

    def test_existen_las_dos_cuentas_predeterminadas_sin_contrasena(self):
        self.assertEqual(almacen.ADMINISTRADORES, (ADMIN_1, ADMIN_2))
        for correo_ in (ADMIN_1, ADMIN_2):
            with self.subTest(correo=correo_):
                cuenta = almacen.obtener_usuario(correo_)
                self.assertEqual((cuenta["role"], cuenta["correo"], cuenta["verificado"]), ("Administrador", correo_, False))
                for intento in ("", "!", "clave", "1234567890", "Mi-clave-segura-1"):
                    self.assertFalse(almacen.verificar_clave(correo_, intento))      # sin contraseña: ninguna sirve

    def test_iniciar_es_idempotente_y_no_pisa_una_cuenta_ya_activada(self):
        self.assertTrue(self.activar().ok)
        almacen.iniciar()
        almacen.iniciar()
        self.assertTrue(almacen.obtener_usuario(ADMIN_1)["verificado"])
        self.assertTrue(almacen.verificar_clave(ADMIN_1, CLAVE_NUEVA_ADMIN))
        self.assertIsNone(almacen.datos_verificacion(ADMIN_1))                    # no se le vuelve a dejar un primer acceso pendiente
        self.assertFalse(almacen.obtener_usuario(ADMIN_2)["verificado"])

    def test_el_primer_acceso_envia_el_codigo_al_propio_correo_y_guarda_la_contrasena_elegida(self):
        r = self.activar()
        self.assertEqual((r.ok, r.codigo), (True, "ok"))
        self.assertEqual(self.emisor.enviados[0][0], ADMIN_1)
        self.assertIsNone(self.emisor.profesor[0])
        self.assertTrue(almacen.obtener_usuario(ADMIN_1)["verificado"])
        self.assertTrue(almacen.verificar_clave(ADMIN_1, CLAVE_NUEVA_ADMIN))
        self.assertFalse(almacen.verificar_clave(ADMIN_1, CLAVE_NUEVA_ADMIN + "x"))
        self.assertIsNone(almacen.datos_verificacion(ADMIN_1))
        self.assertFalse(almacen.obtener_usuario(ADMIN_2)["verificado"])           # la otra cuenta no se toca

    def test_antes_de_pedir_el_codigo_no_hay_ninguno_valido(self):
        r = verificacion.verificar(ADMIN_1, "000000", clave_nueva=CLAVE_NUEVA_ADMIN, reloj=self.reloj)
        self.assertEqual((r.ok, r.codigo), (False, "vencido"))
        self.assertFalse(almacen.obtener_usuario(ADMIN_1)["verificado"])

    def test_la_contrasena_corta_o_vacia_no_gasta_intentos_ni_activa(self):
        codigo = self.pedir_codigo()
        for clave in (None, "", "corta", "1234567"):
            with self.subTest(clave=clave):
                r = verificacion.verificar(ADMIN_1, codigo, clave_nueva=clave, reloj=self.reloj)
                self.assertEqual((r.ok, r.codigo), (False, "clave_corta"))
        self.assertEqual(almacen.datos_verificacion(ADMIN_1)["intentos"], 0)
        self.assertFalse(almacen.obtener_usuario(ADMIN_1)["verificado"])
        self.assertTrue(verificacion.verificar(ADMIN_1, codigo, clave_nueva="12345678", reloj=self.reloj).ok)      # justo 8: vale

    def test_con_el_codigo_equivocado_no_se_activa_ni_se_guarda_la_contrasena(self):
        codigo = self.pedir_codigo()
        malo = "000000" if codigo != "000000" else "111111"
        r = verificacion.verificar(ADMIN_1, malo, clave_nueva=CLAVE_NUEVA_ADMIN, reloj=self.reloj)
        self.assertEqual((r.ok, r.codigo), (False, "incorrecto"))
        self.assertIn("4 intentos", r.mensaje)
        self.assertFalse(almacen.obtener_usuario(ADMIN_1)["verificado"])
        self.assertFalse(almacen.verificar_clave(ADMIN_1, CLAVE_NUEVA_ADMIN))

    def test_un_atacante_no_puede_elegir_la_contrasena_sin_el_codigo_del_correo(self):
        self.pedir_codigo()                                                       # llega al correo del administrador, no al atacante
        for n in range(5):
            verificacion.verificar(ADMIN_1, f"{n:06d}", clave_nueva="clave-del-atacante", reloj=self.reloj)
        self.assertFalse(almacen.verificar_clave(ADMIN_1, "clave-del-atacante"))
        self.assertFalse(almacen.obtener_usuario(ADMIN_1)["verificado"])

    def test_los_administradores_no_tienen_tope_de_envios_solo_la_espera_de_60_segundos(self):
        for n in range(8):                                                        # un tope dejaría a cualquiera bloquear su acceso
            self.reloj.t = 1000.0 + 61 * n
            self.pedir_codigo()
        self.assertEqual(len(self.emisor.enviados), 8)
        self.reloj.t += 10
        self.assertEqual(verificacion.reenviar(ADMIN_1, enviar=self.emisor, reloj=self.reloj, config=CONFIG).codigo, "espera")

    def test_si_falta_la_fila_de_verificacion_el_envio_la_vuelve_a_crear(self):
        with almacen._con() as c:
            c.execute("DELETE FROM verificaciones")
        self.assertTrue(self.activar().ok)

    def test_un_administrador_no_se_puede_cancelar_ni_caduca(self):
        r = verificacion.cancelar_registro(ADMIN_1, "lo-que-sea")
        self.assertEqual((r.ok, r.codigo), (False, "no_cancelable"))
        self.assertFalse(almacen.cancelar_pendiente(ADMIN_1))
        self.assertEqual(almacen.limpiar_no_verificados(10 ** 12, 86400), 0)
        self.assertEqual(almacen.limpiar_no_verificados(10 ** 12, 0), 0)
        self.assertIsNotNone(almacen.obtener_usuario(ADMIN_1))
        self.assertIsNotNone(almacen.datos_verificacion(ADMIN_1))

    def test_nadie_puede_registrarse_con_el_nombre_o_el_correo_de_un_administrador(self):
        r = verificacion.iniciar_registro(ADMIN_1, "otro@correo.test", "clave123", "Estudiante", None, "11",
                                          enviar=self.emisor, reloj=self.reloj, config=CONFIG)
        self.assertEqual(r.codigo, "usuario_existe")
        r = verificacion.iniciar_registro("intruso", ADMIN_2.upper(), "clave123", "Profesor", "Física", None,
                                          enviar=self.emisor, reloj=self.reloj, config=CONFIG)
        self.assertEqual(r.codigo, "correo_existe")
        self.assertEqual(self.emisor.enviados, [])

    def test_los_administradores_no_aparecen_en_el_ranking(self):
        self.assertTrue(self.activar().ok)
        almacen.guardar_progreso(ADMIN_1, {"coins": 99, "puntos": 99})
        self.assertEqual(almacen.ranking_estudiantes(), [])

    # -- contraseña por la consola, sin correo ------------------------------------------------------------
    def test_asignar_clave_admin_funciona_sin_correo_y_valida(self):
        self.assertTrue(almacen.asignar_clave_admin("  LuisBaco2005@Gmail.com ", CLAVE_NUEVA_ADMIN))
        self.assertTrue(almacen.obtener_usuario(ADMIN_1)["verificado"])
        self.assertTrue(almacen.verificar_clave(ADMIN_1, CLAVE_NUEVA_ADMIN))
        self.assertIsNone(almacen.datos_verificacion(ADMIN_1))
        self.assertFalse(almacen.asignar_clave_admin(ADMIN_2, "corta"))
        self.assertFalse(almacen.asignar_clave_admin("otro@correo.test", CLAVE_NUEVA_ADMIN))
        self.assertIsNone(almacen.obtener_usuario("otro@correo.test"))
        self.assertFalse(almacen.obtener_usuario(ADMIN_2)["verificado"])

    def test_el_comando_clave_admin_pide_la_contrasena_dos_veces(self):
        with mock.patch("getpass.getpass", side_effect=[CLAVE_NUEVA_ADMIN, CLAVE_NUEVA_ADMIN]), contextlib.redirect_stdout(io.StringIO()) as salida:
            self.assertEqual(almacen.main(["--clave-admin", ADMIN_2]), 0)
        self.assertTrue(almacen.verificar_clave(ADMIN_2, CLAVE_NUEVA_ADMIN))
        self.assertNotIn(CLAVE_NUEVA_ADMIN, salida.getvalue())
        with mock.patch("getpass.getpass", side_effect=[CLAVE_NUEVA_ADMIN, "otra-distinta-1"]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(almacen.main(["--clave-admin", ADMIN_1]), 1)
        self.assertFalse(almacen.obtener_usuario(ADMIN_1)["verificado"])
        with mock.patch("getpass.getpass", side_effect=["corta", "corta"]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(almacen.main(["--clave-admin", ADMIN_1]), 1)
        with mock.patch("getpass.getpass") as pedir, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(almacen.main(["--clave-admin", "otro@correo.test"]), 1)       # ni siquiera pregunta
        pedir.assert_not_called()


# ==============================================================================
# Reiniciar a las personas inscritas
# ==============================================================================
class TestReiniciarPersonas(BDTestCase):
    def poblar(self):
        almacen.iniciar()
        almacen.crear_usuario("ana", "ana@correo.test", "clave123", "Estudiante", None, "11")
        almacen.crear_usuario("profe", "profe@correo.test", "clave123", "Profesor", "Física", None)
        pendiente(usuario="beto", correo="beto@correo.test")
        almacen.reservar_codigo_profesor("HUELLA")
        for nombre in ("ana", "profe"):
            almacen.guardar_progreso(nombre, {"coins": 50, "puntos": 50})
        almacen.ocultar_del_ranking("ana")
        almacen.guardar_mision("Física", {"titulo": "Una misión"})

    def tabla(self, nombre, ruta=None):
        with (sqlite3.connect(ruta) if ruta else almacen._con()) as c:
            return c.execute(f"SELECT COUNT(*) FROM {nombre}").fetchone()[0]

    def test_borra_a_todas_las_personas_y_deja_a_los_administradores_sin_contrasena(self):
        self.poblar()
        self.assertEqual(almacen.contar_personas(), 3)
        almacen.reiniciar_personas()
        self.assertEqual(almacen.contar_personas(), 0)
        for tabla in ("progreso", "ranking_ocultos", "codigos_profesor"):
            self.assertEqual(self.tabla(tabla), 0, tabla)
        for correo_ in almacen.ADMINISTRADORES:
            self.assertEqual(almacen.obtener_usuario(correo_)["role"], "Administrador")
            self.assertFalse(almacen.obtener_usuario(correo_)["verificado"])
            self.assertIsNotNone(almacen.datos_verificacion(correo_))                 # y con su primer acceso listo
        self.assertEqual(self.tabla("usuarios"), 2)
        self.assertEqual(almacen.ranking_estudiantes(), [])

    def test_conserva_las_misiones(self):
        self.poblar()
        almacen.reiniciar_personas()
        self.assertEqual(len(almacen.cargar_misiones()["Física"]), 1)

    def test_antes_hace_una_copia_con_todo_lo_que_habia(self):
        self.poblar()
        copia = almacen.reiniciar_personas()
        self.assertTrue(os.path.exists(copia))
        self.assertEqual(os.path.dirname(copia), os.path.dirname(almacen.RUTA))
        self.assertIn("copia_antes_de_reiniciar", os.path.basename(copia))
        self.assertNotEqual(copia, almacen.RUTA)
        con = sqlite3.connect(copia)
        try:
            nombres = {f[0] for f in con.execute("SELECT usuario FROM usuarios")}
        finally:
            con.close()
        self.assertTrue({"ana", "profe", "beto"} <= nombres)
        self.assertEqual(self.tabla("progreso", copia), 2)

    def test_el_comando_sin_si_no_borra_y_con_si_borra(self):
        self.poblar()
        with contextlib.redirect_stdout(io.StringIO()) as salida:
            self.assertEqual(almacen.main(["--reiniciar-personas"]), 2)
        self.assertEqual(almacen.contar_personas(), 3)
        self.assertIn("--si", salida.getvalue())
        self.assertIn("3 persona", salida.getvalue())
        with contextlib.redirect_stdout(io.StringIO()) as salida:
            self.assertEqual(almacen.main(["--reiniciar-personas", "--si"]), 0)
        self.assertEqual(almacen.contar_personas(), 0)
        self.assertIn("Copia previa", salida.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(almacen.main(["--reiniciar-personas", "--si"]), 0)         # repetirlo no falla

    def test_un_registro_nuevo_empieza_de_cero_aunque_quedaran_restos_de_ese_nombre(self):
        almacen.iniciar()
        almacen.guardar_progreso("luis", {"coins": 999, "puntos": 999})              # resto de una prueba anterior
        almacen.ocultar_del_ranking("luis")
        self.assertEqual(pendiente(usuario="luis", correo="luis@correo.test"), "ok")
        self.assertIsNone(almacen.cargar_progreso("luis"))
        self.assertNotIn("luis", almacen.ocultos_del_ranking())

    def test_se_puede_ejecutar_como_script(self):
        import subprocess
        self.poblar()
        entorno = {**os.environ, "NEON_DB": almacen.RUTA, "PYTHONIOENCODING": "utf-8"}
        carpeta = os.path.dirname(os.path.abspath(almacen.__file__))
        r = subprocess.run([sys.executable, "almacen.py", "--reiniciar-personas", "--si"], cwd=carpeta, env=entorno, capture_output=True,
                           text=True, encoding="utf-8", timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(almacen.contar_personas(), 0)


if __name__ == "__main__":
    unittest.main()
