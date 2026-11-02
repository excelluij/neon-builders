"""Pruebas de correo.py: configuración por entorno, mensaje, envío SMTP y errores del proveedor.

Ejecutar desde esta carpeta:   python pruebas_correo.py -v
Todas las pruebas usan un SMTP FALSO: ninguna envía correos reales ni usa credenciales reales.
La única que enviaría un correo real (TestEnvioReal) se salta sola si no hay variables de entorno configuradas
(ver docs/CORREO.md) y solo la ejecuta quien tenga sus propias credenciales.
"""
import contextlib
import io
import os
import smtplib
import socket
import ssl
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import correo

CLAVE_SECRETA = "clave-secreta-solo-de-prueba"
ENTORNO = {
    "NEON_SMTP_HOST": "smtp.proveedor.test",
    "NEON_SMTP_USUARIO": "usuario@proveedor.test",
    "NEON_SMTP_CLAVE": CLAVE_SECRETA,
    "NEON_SMTP_REMITENTE": "Neon OS <no-responder@proveedor.test>",
}


def fabrica(registro, **fallas):
    """SMTP falso: guarda cada llamada en `registro`; `fallas` = {"conexion"|"starttls"|"login"|"envio"|"quit": excepción}."""
    class SMTPFalso:
        def __init__(self, host, puerto, timeout=None, context=None):
            registro.append(("init", host, puerto, timeout, context is not None))
            if "conexion" in fallas:
                raise fallas["conexion"]

        def quit(self):
            registro.append(("quit",))
            if "quit" in fallas:
                raise fallas["quit"]

        def close(self):
            registro.append(("cierre",))

        def starttls(self, context=None):
            registro.append(("starttls", context is not None))
            if "starttls" in fallas:
                raise fallas["starttls"]

        def login(self, usuario, clave):
            registro.append(("login", usuario, clave))
            if "login" in fallas:
                raise fallas["login"]

        def send_message(self, mensaje):
            registro.append(("envio", mensaje))
            if "envio" in fallas:
                raise fallas["envio"]
    return SMTPFalso


class TestConfig(unittest.TestCase):
    def test_configuracion_completa_con_valores_por_defecto(self):
        c = correo.cargar_config(ENTORNO)
        self.assertEqual((c.host, c.puerto, c.usuario, c.seguridad, c.timeout, c.modo),
                         ("smtp.proveedor.test", 587, "usuario@proveedor.test", "starttls", 15.0, "smtp"))
        self.assertEqual(c.remitente, "Neon OS <no-responder@proveedor.test>")

    def test_cada_variable_obligatoria_es_necesaria(self):
        for nombre in ("NEON_SMTP_HOST", "NEON_SMTP_USUARIO", "NEON_SMTP_CLAVE", "NEON_SMTP_REMITENTE"):
            with self.subTest(falta=nombre):
                entorno = {k: v for k, v in ENTORNO.items() if k != nombre}
                self.assertIsNone(correo.cargar_config(entorno))
                self.assertIsNone(correo.cargar_config({**entorno, nombre: "   "}))     # vacía o solo espacios

    def test_valores_con_espacios_se_recortan_y_la_seguridad_ssl_cambia_el_puerto_por_defecto(self):
        c = correo.cargar_config({**ENTORNO, "NEON_SMTP_HOST": "  smtp.proveedor.test  ", "NEON_SMTP_SEGURIDAD": " SSL "})
        self.assertEqual((c.host, c.seguridad, c.puerto), ("smtp.proveedor.test", "ssl", 465))
        self.assertEqual(correo.cargar_config({**ENTORNO, "NEON_SMTP_PUERTO": "2525", "NEON_SMTP_TIMEOUT": "7"}).puerto, 2525)

    def test_puerto_seguridad_timeout_y_modo_invalidos(self):
        for extra in ({"NEON_SMTP_PUERTO": "abc"}, {"NEON_SMTP_PUERTO": "0"}, {"NEON_SMTP_PUERTO": "70000"},
                      {"NEON_SMTP_SEGURIDAD": "ninguna"}, {"NEON_SMTP_TIMEOUT": "-3"}, {"NEON_SMTP_TIMEOUT": "x"},
                      {"NEON_CORREO_MODO": "produccion"}, {"NEON_SMTP_REMITENTE": "sin-arroba"}):
            with self.subTest(extra=extra), self.assertRaises(correo.ErrorCorreo) as cm:
                correo.cargar_config({**ENTORNO, **extra})
            self.assertFalse(cm.exception.reintentable)

    def test_modo_consola_no_exige_credenciales(self):
        c = correo.cargar_config({"NEON_CORREO_MODO": "consola"})
        self.assertEqual(c.modo, "consola")
        self.assertEqual(correo.cargar_config({"NEON_CORREO_MODO": " CONSOLA "}).modo, "consola")

    def test_repr_de_la_configuracion_no_contiene_la_clave(self):
        c = correo.cargar_config(ENTORNO)
        self.assertNotIn(CLAVE_SECRETA, repr(c))
        self.assertNotIn(CLAVE_SECRETA, str(c))


class TestMensaje(unittest.TestCase):
    def test_contenido_del_mensaje(self):
        m = correo.construir_mensaje("ana@correo.test", "048213", correo.cargar_config(ENTORNO))
        self.assertEqual((m["To"], m["From"], m["Subject"]), ("ana@correo.test", "Neon OS <no-responder@proveedor.test>",
                                                              "Tu código de verificación de Neon OS"))
        cuerpo = m.get_content()
        self.assertIn("048213", cuerpo)
        self.assertIn("10 minutos", cuerpo)

    def test_el_correo_de_un_profesor_lleva_los_dos_codigos(self):
        m = correo.construir_mensaje("profe@correo.test", "048213", correo.cargar_config(ENTORNO), codigo_profesor="K7M2Q-X9TR4")
        self.assertEqual(m["Subject"], "Tu código de verificación y tu código de profesor de Neon OS")
        cuerpo = m.get_content()
        for texto in ("048213", "K7M2Q-X9TR4", "10 minutos", "código de profesor"):
            self.assertIn(texto, cuerpo)
        self.assertEqual(m["To"], "profe@correo.test")

    def test_sin_codigo_de_profesor_el_correo_es_el_de_siempre(self):
        for kw in ({}, {"codigo_profesor": None}, {"codigo_profesor": ""}):
            with self.subTest(kw=kw):
                m = correo.construir_mensaje("ana@correo.test", "048213", correo.cargar_config(ENTORNO), **kw)
                self.assertEqual(m["Subject"], "Tu código de verificación de Neon OS")
                self.assertNotIn("profesor", m.get_content())

    def test_destinos_invalidos_o_con_inyeccion_de_cabeceras_se_rechazan(self):
        c = correo.cargar_config(ENTORNO)
        for destino in ("ana@correo.test\nBcc: victima@x.test", "ana@correo.test\r\n", "sin-arroba", "a b@x.test",
                        "ana@correo.test, otro@x.test", "<ana@correo.test>", "", "ana@"):
            with self.subTest(destino=destino), self.assertRaises(correo.ErrorCorreo) as cm:
                correo.construir_mensaje(destino, "123456", c)
            self.assertFalse(cm.exception.reintentable)


class TestEnvio(unittest.TestCase):
    def enviar(self, config=None, destino="ana@correo.test", **fallas):
        registro = []
        correo.enviar_codigo(destino, "123456", config or correo.cargar_config(ENTORNO), smtp_factory=fabrica(registro, **fallas))
        return registro

    def test_starttls_login_envio_y_cierre_en_ese_orden(self):
        r = self.enviar()
        self.assertEqual([x[0] for x in r], ["init", "starttls", "login", "envio", "quit", "cierre"])
        self.assertEqual(r[0][1:], ("smtp.proveedor.test", 587, 15.0, False))
        self.assertEqual(r[1], ("starttls", True))                       # con contexto TLS verificado
        self.assertEqual(r[2], ("login", "usuario@proveedor.test", CLAVE_SECRETA))
        self.assertEqual(r[3][1]["To"], "ana@correo.test")

    def test_ssl_usa_contexto_y_no_llama_starttls(self):
        r = self.enviar(correo.cargar_config({**ENTORNO, "NEON_SMTP_SEGURIDAD": "ssl"}))
        self.assertEqual([x[0] for x in r], ["init", "login", "envio", "quit", "cierre"])
        self.assertEqual((r[0][2], r[0][4]), (465, True))

    def test_errores_del_proveedor_se_traducen(self):
        casos = [
            ("login", smtplib.SMTPAuthenticationError(535, b"bad"), False, "credenciales"),
            ("envio", smtplib.SMTPRecipientsRefused({"ana@correo.test": (550, b"no")}), False, "dirección"),
            ("envio", smtplib.SMTPSenderRefused(553, b"no", "a@b.test"), False, "remitente"),
            ("envio", smtplib.SMTPDataError(452, b"limite"), True, "limitó"),
            ("conexion", smtplib.SMTPConnectError(421, b"x"), True, "conectar"),
            ("envio", smtplib.SMTPServerDisconnected("x"), True, "conectar"),
            ("conexion", socket.timeout("t"), True, "conectar"),
            ("starttls", ssl.SSLError("s"), True, "conectar"),
            ("conexion", ConnectionRefusedError("c"), True, "conectar"),
            ("envio", smtplib.SMTPException("otro"), True, "error"),
        ]
        for donde, excepcion, reintentable, fragmento in casos:
            with self.subTest(excepcion=type(excepcion).__name__, donde=donde):
                with self.assertRaises(correo.ErrorCorreo) as cm:
                    self.enviar(**{donde: excepcion})
                self.assertEqual(cm.exception.reintentable, reintentable)
                self.assertIn(fragmento, cm.exception.mensaje)

    def test_el_bloqueo_por_ip_de_brevo_tiene_su_propio_mensaje_y_no_dice_que_la_clave_esta_mal(self):
        for texto in (b"5.7.1 Unauthorized IP address: 190.1.2.3", b"unauthorized ip address"):
            with self.subTest(texto=texto), self.assertRaises(correo.ErrorCorreo) as cm:
                self.enviar(login=smtplib.SMTPAuthenticationError(525, texto))
            self.assertFalse(cm.exception.reintentable)
            self.assertIn("IP no autorizada", cm.exception.mensaje)
            self.assertNotIn("credenciales", cm.exception.mensaje)
            self.assertNotIn("190.1.2.3", cm.exception.mensaje)                 # no repite el texto del proveedor
        with self.assertRaises(correo.ErrorCorreo) as cm:                       # una clave mala (535) sigue diciendo credenciales
            self.enviar(login=smtplib.SMTPAuthenticationError(535, b"5.7.8 Authentication failed"))
        self.assertIn("credenciales", cm.exception.mensaje)

    def test_el_correo_de_un_profesor_se_envia_con_los_dos_codigos_por_smtp(self):
        registro = []
        correo.enviar_codigo("profe@correo.test", "123456", correo.cargar_config(ENTORNO), smtp_factory=fabrica(registro),
                             codigo_profesor="K7M2Q-X9TR4")
        cuerpo = [x for x in registro if x[0] == "envio"][0][1].get_content()
        self.assertIn("123456", cuerpo)
        self.assertIn("K7M2Q-X9TR4", cuerpo)

    def test_modo_consola_imprime_tambien_el_codigo_de_profesor_y_en_smtp_no_se_imprime(self):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            correo.enviar_codigo("profe@correo.test", "123456", correo.Config(modo="consola"), codigo_profesor="K7M2Q-X9TR4")
        self.assertIn("123456", salida.getvalue())
        self.assertIn("K7M2Q-X9TR4", salida.getvalue())
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            correo.enviar_codigo("profe@correo.test", "123456", correo.cargar_config(ENTORNO), smtp_factory=fabrica([]),
                                 codigo_profesor="K7M2Q-X9TR4")
        self.assertEqual(salida.getvalue(), "")

    def test_los_mensajes_de_error_no_contienen_la_clave_ni_el_texto_del_proveedor(self):
        excepcion = smtplib.SMTPAuthenticationError(535, ("clave incorrecta: " + CLAVE_SECRETA).encode())
        with self.assertRaises(correo.ErrorCorreo) as cm:
            self.enviar(login=excepcion)
        self.assertNotIn(CLAVE_SECRETA, cm.exception.mensaje)
        self.assertNotIn(CLAVE_SECRETA, repr(cm.exception))
        self.assertNotIn(CLAVE_SECRETA, str(cm.exception))

    def test_la_conexion_se_cierra_aunque_falle_el_envio(self):
        registro = []
        with self.assertRaises(correo.ErrorCorreo):
            correo.enviar_codigo("ana@correo.test", "123456", correo.cargar_config(ENTORNO),
                                 smtp_factory=fabrica(registro, envio=smtplib.SMTPDataError(452, b"x")))
        self.assertEqual(registro[-1], ("cierre",))

    def test_sin_configuracion_falla_con_un_mensaje_claro_y_sin_tocar_smtp(self):
        registro = []
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaises(correo.ErrorCorreo) as cm:
            correo.enviar_codigo("ana@correo.test", "123456", smtp_factory=fabrica(registro))
        self.assertFalse(cm.exception.reintentable)
        self.assertIn("NEON_SMTP_HOST", cm.exception.mensaje)
        self.assertEqual(registro, [])

    def test_la_configuracion_se_lee_del_entorno_cuando_no_se_pasa(self):
        registro = []
        with mock.patch.dict(os.environ, ENTORNO, clear=True):
            correo.enviar_codigo("ana@correo.test", "123456", smtp_factory=fabrica(registro))
        self.assertEqual([x[0] for x in registro], ["init", "starttls", "login", "envio", "quit", "cierre"])

    def test_modo_consola_imprime_el_codigo_y_no_usa_smtp(self):
        registro, salida = [], io.StringIO()
        with contextlib.redirect_stdout(salida):
            correo.enviar_codigo("ana@correo.test", "654321", correo.cargar_config({"NEON_CORREO_MODO": "consola"}),
                                 smtp_factory=fabrica(registro))
        self.assertIn("654321", salida.getvalue())
        self.assertIn("ana@correo.test", salida.getvalue())
        self.assertEqual(registro, [])

    def test_en_modo_smtp_el_codigo_nunca_se_imprime(self):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(salida):
            self.enviar()
        self.assertNotIn("123456", salida.getvalue())


class TestRevision(unittest.TestCase):
    """Hallazgos de la revisión independiente de la pieza 4 (correo.py)."""

    def enviar(self, **fallas):
        registro = []
        correo.enviar_codigo("ana@correo.test", "123456", correo.cargar_config(ENTORNO), smtp_factory=fabrica(registro, **fallas))
        return registro

    def test_los_rechazos_temporales_4xx_se_muestran_como_temporales_aunque_sean_de_remitente_destinatario_o_login(self):
        casos = [
            ("envio", smtplib.SMTPSenderRefused(451, b"temporal", "a@b.test")),
            ("envio", smtplib.SMTPRecipientsRefused({"ana@correo.test": (450, b"greylisting")})),
            ("login", smtplib.SMTPAuthenticationError(454, b"temporal")),
        ]
        for donde, excepcion in casos:
            with self.subTest(excepcion=type(excepcion).__name__):
                with self.assertRaises(correo.ErrorCorreo) as cm:
                    self.enviar(**{donde: excepcion})
                self.assertTrue(cm.exception.reintentable)
                self.assertIn("limitó", cm.exception.mensaje)

    def test_los_rechazos_permanentes_5xx_siguen_siendo_permanentes(self):
        casos = [
            ("envio", smtplib.SMTPSenderRefused(550, b"no", "a@b.test"), "remitente"),
            ("envio", smtplib.SMTPRecipientsRefused({"ana@correo.test": (550, b"no")}), "dirección"),
            ("login", smtplib.SMTPAuthenticationError(535, b"no"), "credenciales"),
        ]
        for donde, excepcion, fragmento in casos:
            with self.subTest(fragmento=fragmento):
                with self.assertRaises(correo.ErrorCorreo) as cm:
                    self.enviar(**{donde: excepcion})
                self.assertFalse(cm.exception.reintentable)
                self.assertIn(fragmento, cm.exception.mensaje)

    def test_direcciones_con_comentarios_o_caracteres_raros_no_son_validas(self):
        c = correo.cargar_config(ENTORNO)
        for destino in ("victima(1)@x.co", "victima(2)@x.co", "víctima@x.co", "ana@exámple.co", "ana@x..co", ".ana@x.co",
                        "ana.@x.co", "a..b@x.co", "ana@x", "ana@.co", "an a@x.co", "ana@x_y.co", 'ana"@x.co', "ana\\@x.co"):
            with self.subTest(destino=destino), self.assertRaises(correo.ErrorCorreo):
                correo.construir_mensaje(destino, "123456", c)

    def test_direcciones_normales_siguen_siendo_validas(self):
        c = correo.cargar_config(ENTORNO)
        for destino in ("ana@correo.test", "ana.perez+neon@edu.co", "o'brien@x.co", "a_b-c@sub.dominio.edu.co", "A1@X-Y.CO"):
            with self.subTest(destino=destino):
                self.assertEqual(correo.construir_mensaje(destino, "123456", c)["To"], destino)

    def test_timeout_nan_o_infinito_se_rechaza_como_valor_invalido(self):
        for valor in ("nan", "inf", "-inf", "NaN"):
            with self.subTest(valor=valor), self.assertRaises(correo.ErrorCorreo) as cm:
                correo.cargar_config({**ENTORNO, "NEON_SMTP_TIMEOUT": valor})
            self.assertFalse(cm.exception.reintentable)

    def test_un_error_inesperado_del_cliente_se_traduce_sin_filtrar_la_clave(self):
        casos = [("login", UnicodeEncodeError("ascii", CLAVE_SECRETA, 0, 1, "ordinal not in range")),
                 ("envio", ValueError("valor raro " + CLAVE_SECRETA)),
                 ("starttls", RuntimeError(CLAVE_SECRETA))]
        for donde, excepcion in casos:
            with self.subTest(excepcion=type(excepcion).__name__):
                with self.assertRaises(correo.ErrorCorreo) as cm:
                    self.enviar(**{donde: excepcion})
                self.assertNotIn(CLAVE_SECRETA, cm.exception.mensaje)
                self.assertNotIn(CLAVE_SECRETA, repr(cm.exception))
                self.assertIsNone(cm.exception.__cause__)

    def test_probar_con_un_error_inesperado_imprime_un_mensaje_y_no_un_traceback(self):
        registro, salida = [], io.StringIO()
        with mock.patch.dict(os.environ, ENTORNO, clear=True), contextlib.redirect_stdout(salida):
            codigo = correo.main(["--probar", "ana@correo.test"],
                                 smtp_factory=fabrica(registro, login=UnicodeEncodeError("ascii", CLAVE_SECRETA, 0, 1, "x")))
        self.assertEqual(codigo, 1)
        self.assertNotIn(CLAVE_SECRETA, salida.getvalue())
        self.assertNotIn("Traceback", salida.getvalue())

    def test_si_el_servidor_falla_al_despedirse_el_correo_ya_enviado_cuenta_como_entregado(self):
        for excepcion in (smtplib.SMTPResponseException(250, b"ok"), smtplib.SMTPServerDisconnected("cerrado"), OSError("red")):
            with self.subTest(excepcion=type(excepcion).__name__):
                registro = self.enviar(quit=excepcion)                    # no lanza
                self.assertEqual([x[0] for x in registro][-3:], ["envio", "quit", "cierre"])

    def test_la_conexion_se_cierra_siempre_aunque_fallen_el_envio_y_la_despedida(self):
        registro = []
        with self.assertRaises(correo.ErrorCorreo) as cm:
            correo.enviar_codigo("ana@correo.test", "123456", correo.cargar_config(ENTORNO),
                                 smtp_factory=fabrica(registro, envio=smtplib.SMTPDataError(452, b"x"), quit=OSError("red")))
        self.assertIn("limitó", cm.exception.mensaje)                     # se informa el error del envío, no el de la despedida
        self.assertEqual(registro[-1], ("cierre",))

    def test_el_contexto_tls_verifica_certificado_y_nombre_del_servidor(self):
        contextos = []

        class Espia:
            def __init__(self, host, puerto, timeout=None, context=None):
                contextos.append(("init", context))

            def starttls(self, context=None):
                contextos.append(("starttls", context))

            def login(self, *a): pass
            def send_message(self, *a): pass
            def quit(self): pass
            def close(self): pass

        correo.enviar_codigo("ana@correo.test", "123456", correo.cargar_config(ENTORNO), smtp_factory=Espia)
        correo.enviar_codigo("ana@correo.test", "123456", correo.cargar_config({**ENTORNO, "NEON_SMTP_SEGURIDAD": "ssl"}), smtp_factory=Espia)
        con_contexto = [c for _, c in contextos if c is not None]
        self.assertEqual([d for d, c in contextos if c is not None], ["starttls", "init"])     # starttls (587) e init con SSL (465)
        for c in con_contexto:
            self.assertTrue(c.check_hostname)
            self.assertEqual(c.verify_mode, ssl.CERT_REQUIRED)

    def _intentos_con_certificado_malo_en(self, host_configurado, hosts_con_certificado_malo, error=None):
        """Devuelve (hosts intentados, correos enviados) cuando el certificado falla en `hosts_con_certificado_malo`."""
        intentados, enviados = [], []
        malo = error or ssl.SSLCertVerificationError("Hostname mismatch")

        class Falso:
            def __init__(self, host, puerto, timeout=None, context=None):
                intentados.append(host)
                self.host = host

            def starttls(self, context=None):
                if self.host in hosts_con_certificado_malo:
                    raise malo

            def login(self, *a): pass
            def send_message(self, *a): enviados.append(self.host)
            def quit(self): pass
            def close(self): pass

        config = correo.cargar_config({**ENTORNO, "NEON_SMTP_HOST": host_configurado})
        try:
            correo.enviar_codigo("ana@correo.test", "123456", config, smtp_factory=Falso)
        except correo.ErrorCorreo:
            pass
        return intentados, enviados

    def test_si_el_certificado_no_coincide_con_el_nombre_de_brevo_se_prueba_el_otro_nombre_oficial(self):
        self.assertEqual(self._intentos_con_certificado_malo_en("smtp-relay.brevo.com", {"smtp-relay.brevo.com"}),
                         (["smtp-relay.brevo.com", "smtp-relay.sendinblue.com"], ["smtp-relay.sendinblue.com"]))
        self.assertEqual(self._intentos_con_certificado_malo_en("smtp-relay.sendinblue.com", {"smtp-relay.sendinblue.com"}),
                         (["smtp-relay.sendinblue.com", "smtp-relay.brevo.com"], ["smtp-relay.brevo.com"]))

    def test_si_el_primer_nombre_de_brevo_funciona_no_se_prueba_el_segundo(self):
        self.assertEqual(self._intentos_con_certificado_malo_en("smtp-relay.brevo.com", set()),
                         (["smtp-relay.brevo.com"], ["smtp-relay.brevo.com"]))

    def test_si_los_dos_nombres_fallan_no_se_envia_nada_y_no_se_desactiva_la_verificacion(self):
        intentados, enviados = self._intentos_con_certificado_malo_en("smtp-relay.brevo.com", set(correo.NOMBRES_BREVO))
        self.assertEqual((intentados, enviados), (list(correo.NOMBRES_BREVO), []))

    def test_otros_proveedores_y_otros_errores_tls_no_se_reintentan_con_otro_host(self):
        self.assertEqual(self._intentos_con_certificado_malo_en("smtp.proveedor.test", {"smtp.proveedor.test"})[0],
                         ["smtp.proveedor.test"])
        self.assertEqual(self._intentos_con_certificado_malo_en("smtp-relay.brevo.com", {"smtp-relay.brevo.com"},
                                                                error=ssl.SSLError("otro"))[0],
                         ["smtp-relay.brevo.com"])


class TestComandos(unittest.TestCase):
    def test_config_lista_las_variables_sin_mostrar_valores(self):
        salida = io.StringIO()
        with mock.patch.dict(os.environ, {**ENTORNO}, clear=True), contextlib.redirect_stdout(salida):
            codigo = correo.main(["--config"])
        texto = salida.getvalue()
        self.assertEqual(codigo, 0)
        for nombre in ("NEON_SMTP_HOST", "NEON_SMTP_USUARIO", "NEON_SMTP_CLAVE", "NEON_SMTP_REMITENTE"):
            self.assertIn(nombre, texto)
        self.assertNotIn(CLAVE_SECRETA, texto)
        self.assertNotIn("smtp.proveedor.test", texto)

    def test_config_con_faltantes_devuelve_error(self):
        salida = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(salida):
            self.assertEqual(correo.main(["--config"]), 1)
        self.assertIn("falta", salida.getvalue())

    def test_probar_envia_un_mensaje_de_prueba_con_el_emisor_inyectado(self):
        registro, salida = [], io.StringIO()
        with mock.patch.dict(os.environ, ENTORNO, clear=True), contextlib.redirect_stdout(salida):
            codigo = correo.main(["--probar", "ana@correo.test"], smtp_factory=fabrica(registro))
        self.assertEqual(codigo, 0)
        self.assertEqual(registro[3][1]["To"], "ana@correo.test")
        self.assertNotIn(CLAVE_SECRETA, salida.getvalue())

    def test_probar_informa_el_error_del_proveedor_sin_la_clave(self):
        registro, salida = [], io.StringIO()
        with mock.patch.dict(os.environ, ENTORNO, clear=True), contextlib.redirect_stdout(salida):
            codigo = correo.main(["--probar", "ana@correo.test"],
                                 smtp_factory=fabrica(registro, login=smtplib.SMTPAuthenticationError(535, b"x")))
        self.assertEqual(codigo, 1)
        self.assertIn("credenciales", salida.getvalue())
        self.assertNotIn(CLAVE_SECRETA, salida.getvalue())

    def test_sin_argumentos_muestra_la_ayuda(self):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            self.assertEqual(correo.main([]), 2)
        self.assertIn("--probar", salida.getvalue())


class TestProbarEnModoConsola(unittest.TestCase):
    """`--probar` con NEON_CORREO_MODO=consola decía «no se envía nada» y justo después «✅ Correo de prueba enviado»."""

    def test_enviar_prueba_devuelve_si_envio_de_verdad(self):
        registro = []
        self.assertIs(correo.enviar_prueba("ana@correo.test", correo.cargar_config(ENTORNO), smtp_factory=fabrica(registro)), True)
        self.assertEqual(registro[3][0], "envio")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertIs(correo.enviar_prueba("ana@correo.test", correo.Config(modo="consola"), smtp_factory=fabrica(registro)), False)

    def test_en_modo_consola_probar_no_dice_que_envio_nada_y_sale_con_error(self):
        registro, salida = [], io.StringIO()
        with mock.patch.dict(os.environ, {"NEON_CORREO_MODO": "consola"}, clear=True), contextlib.redirect_stdout(salida):
            codigo = correo.main(["--probar", "ana@correo.test"], smtp_factory=fabrica(registro))
        self.assertEqual(codigo, 1)                                          # no se verificó el envío real
        texto = salida.getvalue()
        self.assertIn("no se envió nada", texto)
        self.assertIn("NEON_CORREO_MODO", texto)                             # dice qué quitar para probar el envío real
        self.assertNotIn("Correo de prueba enviado", texto)
        self.assertEqual(registro, [])

    def test_en_modo_smtp_probar_sigue_diciendo_que_se_envio(self):
        registro, salida = [], io.StringIO()
        with mock.patch.dict(os.environ, ENTORNO, clear=True), contextlib.redirect_stdout(salida):
            self.assertEqual(correo.main(["--probar", "ana@correo.test"], smtp_factory=fabrica(registro)), 0)
        self.assertIn("Correo de prueba enviado a ana@correo.test", salida.getvalue())


class TestDocumentacion(unittest.TestCase):
    RUTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "CORREO.md")
    VARIABLES = (correo.VARIABLES_OBLIGATORIAS + correo.VARIABLES_OPCIONALES +
                 ("NEON_ADMIN_CLAVE", "NEON_ADMIN_USUARIO", "NEON_PRUEBA_CORREO_DESTINO", "NEON_DB", "NEON_DEMO_CLAVE"))

    def leer(self):
        with open(self.RUTA, encoding="utf-8") as f:
            return f.read()

    def test_la_documentacion_menciona_todas_las_variables(self):
        texto = self.leer()
        faltan = [v for v in self.VARIABLES if v not in texto]
        self.assertEqual(faltan, [], "docs/CORREO.md no menciona estas variables")

    def test_la_documentacion_explica_los_pasos_y_comandos_clave(self):
        texto = self.leer()
        for fragmento in ("smtp-relay.brevo.com", "python correo.py --config", "python correo.py --probar",
                          "NEON_CORREO_MODO", "consola", "SPF", "DKIM", "copia de neon_os.db",
                          # revisión independiente: límites que el administrador debe conocer
                          "app_movil.py", "máximo de 5 códigos", "Get-ChildItem Env:", "todos los equipos", "controla el equipo",
                          "no garantiza los bloqueos", "desde que se crearon",
                          # código de profesor y cuentas de demostración fuera del código
                          "python almacen.py --cuentas-demo", "python almacen.py --retirar-cuentas-demo --si", "primer arranque",
                          # administradores predeterminados, código de profesor por correo, reinicio de personas y bloqueo por IP
                          "python almacen.py --clave-admin", "python almacen.py --reiniciar-personas", "Activar cuenta", "Enviar código",
                          "código de profesor", "luisbaco2005@gmail.com", "dsandovaltorres05@gmail.com", "Unauthorized IP",
                          # archivo .env, .gitignore y dependencias
                          ".env.example", "requirements.txt", ".gitignore", "python -m venv", "junto a `APP_final.py`",
                          "prioridad", ".env.txt", "pip install -r requirements.txt"):
            with self.subTest(fragmento=fragmento):
                self.assertIn(fragmento, texto)

    def test_la_documentacion_no_contiene_claves_reales(self):
        texto = self.leer()
        self.assertNotRegex(texto, r"xsmtpsib-[A-Za-z0-9-]{16,}")          # formato de las claves SMTP de Brevo
        self.assertNotRegex(texto, r"xkeysib-[A-Za-z0-9-]{16,}")


def _hay_credenciales_reales():
    try:
        config = correo.cargar_config()
    except correo.ErrorCorreo:
        return False
    return bool(config and config.modo == "smtp" and os.environ.get("NEON_PRUEBA_CORREO_DESTINO"))


@unittest.skipUnless(_hay_credenciales_reales(),
                     "Prueba de integración REAL: define las variables NEON_SMTP_* y NEON_PRUEBA_CORREO_DESTINO (docs/CORREO.md)")
class TestEnvioReal(unittest.TestCase):
    def test_envia_un_correo_real_al_destino_de_prueba(self):
        correo.enviar_codigo(os.environ["NEON_PRUEBA_CORREO_DESTINO"], "000000")      # lanza ErrorCorreo si el proveedor falla


if __name__ == "__main__":
    unittest.main()
