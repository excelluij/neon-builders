"""Pruebas del acceso: administradores predeterminados, código de profesor por correo, bloqueo de cuentas sin verificar y DatabaseManager.

Ejecutar desde esta carpeta:   python pruebas_auth.py -v
Usa una base de datos temporal (nunca toca neon_os.db) y un emisor FALSO: no envía correos reales.
"""
import atexit
import hashlib
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

_TMP = tempfile.mkdtemp(prefix="neon_auth_")
atexit.register(shutil.rmtree, _TMP, ignore_errors=True)
os.environ["NEON_DB"] = os.path.join(_TMP, "import.db")   # antes de importar almacen / APP_final
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import almacen
import APP_final
from pruebas_verificacion import CONFIG, BDTestCase, Emisor, Reloj

# Huellas (saladas, pbkdf2) de las claves de administrador que estuvieron escritas en el código (APP_final.py y app_movil.py):
# solo sirven para detectar si reaparecen; no permiten recuperar la clave.
HUELLAS_ANTIGUAS = [
    {"sal": "19e6dc54ba7b52fb", "huella": "0d25544e35066ff8cf0036c5e6097306fea478ec8a8fdd225a4e9f5d4082f257", "largo": 11},
    {"sal": "16cf2e1e18335fb0", "huella": "9e7fdf16c8fc440388d45f827df04c5f32f33c11fef28ea5b8c085b19ceda2c5", "largo": 11},
]


def archivos_de_texto(raiz):
    """(ruta, texto) de cada archivo de texto del proyecto (código, documentación y configuración)."""
    for carpeta, subcarpetas, archivos in os.walk(raiz):
        subcarpetas[:] = [d for d in subcarpetas if d not in ("__pycache__", ".git", ".venv")]      # .venv: librerías ajenas (miles de archivos)
        for nombre in archivos:
            if nombre.lower().endswith((".py", ".md", ".txt", ".json", ".ini", ".cfg", ".env", ".bat", ".ps1", ".toml", ".yml", ".yaml")):
                ruta = os.path.join(carpeta, nombre)
                with open(ruta, encoding="utf-8", errors="ignore") as f:
                    yield ruta, f.read()


def buscar_huellas(raiz, huellas):
    """Recorre los archivos de texto de `raiz` y devuelve (cuántos revisó, [archivos donde alguna «palabra» coincide con una huella]).
    No necesita conocer las claves: compara hashes salados y lentos (pbkdf2, 200 000 iteraciones) de las «palabras» del largo justo."""
    revisados, coincidencias = 0, []
    for ruta, texto in archivos_de_texto(raiz):
        revisados += 1
        candidatas = set()
        for palabra in re.findall(r"[^\s\"'`]+", texto):                        # «palabras» tal cual y partidas por = : , ; ( ) [ ] { } < >
            candidatas.add(palabra)
            candidatas.update(re.split(r"[=:,;()\[\]{}<>]+", palabra))
        for trozo in candidatas:
            if not any(c.isdigit() for c in trozo):
                continue                                                  # filtro barato: así solo se calcula el hash lento de unas pocas
            for huella in huellas:
                if len(trozo) == huella["largo"] and hashlib.pbkdf2_hmac(
                        "sha256", trozo.encode(), huella["sal"].encode(), 200_000).hex() == huella["huella"]:
                    coincidencias.append(os.path.relpath(ruta, raiz))
    return revisados, coincidencias


ADMIN_1, ADMIN_2 = almacen.ADMINISTRADORES
CLAVE_ADMIN = "Cl4ve-De-Prueba-Admin"


class TestAdministrador(BDTestCase):
    """Los administradores son dos cuentas predefinidas en la base (el usuario es su correo): nacen sin contraseña y la crean en su
    primer acceso con un código enviado a ese correo. Ya no hay NEON_ADMIN_CLAVE: nada que configurar y ninguna clave en el código."""

    def setUp(self):
        super().setUp()
        almacen.iniciar()                              # el BDTestCase borra las cuentas: así se vuelven a crear como en un primer arranque
        self.emisor, self.reloj = Emisor(), Reloj(1000.0)
        self.db = APP_final.DatabaseManager(enviar=self.emisor, reloj=self.reloj, config=CONFIG)

    def activar(self, correo_=ADMIN_1, clave=CLAVE_ADMIN):
        self.assertTrue(self.db.reenviar_codigo(correo_).ok)
        r = self.db.verificar_codigo(correo_, self.emisor.enviados[-1][1], None, clave)
        self.assertTrue(r.ok, r.mensaje)

    def test_las_dos_cuentas_predeterminadas_piden_el_primer_acceso_en_vez_de_dar_error(self):
        for correo_ in (ADMIN_1, ADMIN_2):
            for clave in ("", "cualquiera", CLAVE_ADMIN):
                with self.subTest(correo=correo_, clave=clave):
                    self.assertEqual(self.db.autenticar(correo_, clave, "Administrador"), (False, APP_final.MSG_PRIMER_ACCESO))

    def test_ya_no_depende_de_ninguna_variable_de_entorno(self):
        for entorno in ({}, {"NEON_ADMIN_CLAVE": ""}, {"NEON_ADMIN_CLAVE": "   ", "NEON_ADMIN_USUARIO": "otro"}):
            with self.subTest(entorno=entorno), mock.patch.dict(os.environ, entorno, clear=True):
                ok, mensaje = self.db.autenticar(ADMIN_1, CLAVE_ADMIN, "Administrador")
                self.assertFalse(ok)
                self.assertNotIn("NEON_ADMIN_CLAVE", mensaje)
                self.assertNotIn("no está configurado", mensaje)

    def test_tras_el_primer_acceso_entra_con_su_correo_y_su_contrasena(self):
        self.activar()
        ok, datos = self.db.autenticar(ADMIN_1, CLAVE_ADMIN, "Administrador")
        self.assertTrue(ok)
        self.assertEqual((datos["role"], datos["correo"], datos["verificado"]), ("Administrador", ADMIN_1, True))
        self.assertTrue(self.db.autenticar("  LuisBaco2005@Gmail.COM ", CLAVE_ADMIN, "Administrador")[0])     # el correo no distingue mayúsculas
        self.assertEqual(self.db.autenticar(ADMIN_2, CLAVE_ADMIN, "Administrador"), (False, APP_final.MSG_PRIMER_ACCESO))   # la otra sigue pendiente

    def test_las_dos_cuentas_son_independientes(self):
        self.activar(ADMIN_1, CLAVE_ADMIN)
        self.activar(ADMIN_2, CLAVE_ADMIN + "2")
        self.assertTrue(self.db.autenticar(ADMIN_1, CLAVE_ADMIN, "Administrador")[0])
        self.assertTrue(self.db.autenticar(ADMIN_2, CLAVE_ADMIN + "2", "Administrador")[0])
        self.assertFalse(self.db.autenticar(ADMIN_1, CLAVE_ADMIN + "2", "Administrador")[0])
        self.assertFalse(self.db.autenticar(ADMIN_2, CLAVE_ADMIN, "Administrador")[0])

    def test_credenciales_incorrectas_no_entran(self):
        self.activar()
        for usuario, clave in ((ADMIN_1, "otra"), ("otro@correo.test", CLAVE_ADMIN), (ADMIN_1, ""), ("", ""), (ADMIN_1, CLAVE_ADMIN + " "),
                               ("luix", CLAVE_ADMIN)):
            with self.subTest(usuario=usuario, clave=clave):
                ok, mensaje = self.db.autenticar(usuario, clave, "Administrador")
                self.assertEqual((ok, mensaje), (False, APP_final.MSG_ADMIN_DENEGADO))
                self.assertNotIn(CLAVE_ADMIN, mensaje)
        self.assertFalse(self.db.autenticar(ADMIN_1, CLAVE_ADMIN, "Estudiante")[0])         # con el rol equivocado tampoco
        self.assertFalse(self.db.autenticar(ADMIN_1, CLAVE_ADMIN, "Profesor")[0])

    def test_un_estudiante_o_profesor_no_puede_entrar_como_administrador(self):
        almacen.crear_usuario("ana", "ana@correo.test", "clave123", "Estudiante", None, "11")
        almacen.crear_usuario("profe", "profe@correo.test", "clave123", "Profesor", "Física", None)
        for usuario in ("ana", "profe"):
            with self.subTest(usuario=usuario):
                self.assertEqual(self.db.autenticar(usuario, "clave123", "Administrador"), (False, APP_final.MSG_ADMIN_DENEGADO))

    def test_nadie_puede_registrarse_como_administrador_ni_con_su_nombre_o_correo(self):
        self.assertEqual(self.db.registrar_usuario("x", "x@correo.test", "clave123", "Administrador").codigo, "datos")
        r = self.db.registrar_usuario(ADMIN_1.upper(), "a@correo.test", "clave123", "Estudiante", None, "11")
        self.assertEqual((r.ok, r.codigo), (False, "usuario_existe"))
        r = self.db.registrar_usuario("intruso", ADMIN_2, "clave123", "Profesor", "Física")
        self.assertEqual((r.ok, r.codigo), (False, "correo_existe"))
        self.assertEqual(self.emisor.enviados, [])

    def test_rol_de(self):
        almacen.crear_usuario("ana", "ana@correo.test", "clave123", "Estudiante", None, "11")
        self.assertEqual((self.db.rol_de(ADMIN_1), self.db.rol_de("ana"), self.db.rol_de("nadie")), ("Administrador", "Estudiante", None))

    def test_el_codigo_fuente_no_contiene_credenciales_ni_direcciones_personales(self):
        ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "APP_final.py")
        with open(ruta, encoding="utf-8") as f:
            fuente = f.read()
        self.assertNotRegex(fuente, r'\bp\s*==\s*"')                       # ninguna contraseña comparada con un literal
        self.assertNotRegex(fuente, r"[\w.+-]+@gmail\.com")               # las direcciones de los administradores viven en almacen.py
        self.assertNotIn("NEON_ADMIN_CLAVE", fuente)                       # la contraseña ya no sale del entorno

    def test_las_cuentas_de_administrador_no_llevan_contrasena_en_el_codigo(self):
        ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "almacen.py")
        with open(ruta, encoding="utf-8") as f:
            fuente = f.read()
        self.assertEqual(set(re.findall(r"[\w.+-]+@gmail\.com", fuente)), {ADMIN_1, ADMIN_2})       # solo esas dos direcciones, ninguna más
        self.assertNotRegex(fuente, r'SIN_CLAVE\s*=\s*"[^!]')              # el marcador de «sin contraseña» no es una contraseña

    def test_la_clave_de_administrador_antigua_no_aparece_en_ningun_archivo_del_proyecto(self):
        """Revisión independiente, hallazgo 2: había una clave antigua en app_movil.py. No se guarda ninguna clave ni un trozo: solo
        hashes salados y lentos (pbkdf2) y sus largos; se prueba cada «palabra» de ese largo de todos los archivos de texto del proyecto
        (cubre que reaparezca como texto suelto o literal, no incrustada dentro de una frase más larga)."""
        raiz = os.path.dirname(os.path.abspath(__file__))
        revisados, coincidencias = buscar_huellas(raiz, HUELLAS_ANTIGUAS)
        self.assertGreater(revisados, 20)                                  # de verdad se recorrió el proyecto
        self.assertEqual(coincidencias, [])

    def test_el_escaner_de_claves_antiguas_detecta_una_clave_conocida(self):
        sustituta, sal = "abc123xyz90", "sal-de-prueba"
        huella = {"sal": sal, "huella": hashlib.pbkdf2_hmac("sha256", sustituta.encode(), sal.encode(), 200_000).hex(), "largo": len(sustituta)}
        with tempfile.TemporaryDirectory() as carpeta:
            os.makedirs(os.path.join(carpeta, "docs"))
            casos = {"a.py": f'if p == "{sustituta}":\n', "docs/b.md": f"la clave es `{sustituta}`.\n", "c.txt": f"clave={sustituta}\n"}
            ruidos = {"d.py": "x = 1  # nada que ver con 12345678901\n", "e.md": "texto normal sin claves\n"}
            for nombre, contenido in {**casos, **ruidos}.items():
                with open(os.path.join(carpeta, nombre), "w", encoding="utf-8") as f:
                    f.write(contenido)
            revisados, coincidencias = buscar_huellas(carpeta, [huella])
        self.assertEqual(revisados, 5)
        self.assertEqual(sorted(coincidencias), sorted(os.path.normpath(n) for n in casos))

    def test_app_movil_lee_la_clave_de_administrador_del_entorno(self):
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_movil.py"), encoding="utf-8") as f:
            fuente = f.read()
        self.assertIn("NEON_ADMIN_CLAVE", fuente)                          # el prototipo móvil sigue con su acceso de demostración por entorno
        self.assertNotRegex(fuente, r'Administrador"[^\n]*\bp\s*==\s*"')    # ninguna contraseña de administrador comparada con un literal


class TestCodigoProfesor(BDTestCase):
    """El código de profesor ya no es una variable de entorno compartida (NEON_CODIGO_PROFESOR): lo genera la app, único y aleatorio
    para cada profesor, y llega por correo junto con el código de verificación."""

    def setUp(self):
        super().setUp()
        self.emisor, self.reloj = Emisor(), Reloj(1000.0)
        self.db = APP_final.DatabaseManager(enviar=self.emisor, reloj=self.reloj, config=CONFIG)

    def registrar(self, usuario="profe"):
        return self.db.registrar_usuario(usuario, f"{usuario}@correo.test", "clave123", "Profesor", "Física")

    def test_el_registro_de_profesor_ya_no_pide_ni_depende_de_ningun_codigo_configurado(self):
        for entorno in ({}, {"NEON_CODIGO_PROFESOR": ""}, {"NEON_CODIGO_PROFESOR": "uno-viejo"}):
            with self.subTest(entorno=entorno), mock.patch.dict(os.environ, entorno, clear=True):
                self.db.cancelar_registro("profe", "clave123")
                r = self.registrar()
                self.assertTrue(r.ok, r.mensaje)
        usuario = almacen.obtener_usuario("profe")
        self.assertEqual((usuario["role"], usuario["verificado"]), ("Profesor", False))

    def test_el_correo_lleva_el_codigo_de_verificacion_y_un_codigo_de_profesor_distinto_para_cada_uno(self):
        self.registrar("profe1")
        self.registrar("profe2")
        self.assertEqual(len(self.emisor.enviados), 2)
        self.assertEqual(len({p for p in self.emisor.profesor}), 2)
        self.assertTrue(all(re.fullmatch(r"[A-Z2-9]{5}-[A-Z2-9]{5}", p) for p in self.emisor.profesor))

    def test_con_los_dos_codigos_el_profesor_se_verifica_y_entra(self):
        self.registrar()
        self.assertEqual(self.db.autenticar("profe", "clave123", "Profesor"), (False, APP_final.MSG_NO_VERIFICADO))
        r = self.db.verificar_codigo("profe", self.emisor.enviados[0][1], self.emisor.profesor[0])
        self.assertTrue(r.ok, r.mensaje)
        ok, datos = self.db.autenticar("profe", "clave123", "Profesor")
        self.assertTrue(ok)
        self.assertEqual((datos["role"], datos["materia"]), ("Profesor", "Física"))

    def test_sin_el_codigo_de_profesor_o_con_uno_ajeno_no_se_verifica(self):
        self.registrar("profe1")
        self.registrar("profe2")
        codigo1 = self.emisor.enviados[0][1]
        self.assertEqual(self.db.verificar_codigo("profe1", codigo1).codigo, "formato_profesor")
        self.assertEqual(self.db.verificar_codigo("profe1", codigo1, self.emisor.profesor[1]).codigo, "incorrecto")
        self.assertFalse(almacen.obtener_usuario("profe1")["verificado"])

    def test_los_estudiantes_no_necesitan_codigo(self):
        r = self.db.registrar_usuario("ana", "ana@correo.test", "clave123", "Estudiante", None, "11")
        self.assertTrue(r.ok, r.mensaje)
        self.assertTrue(self.db.verificar_codigo("ana", self.emisor.enviados[0][1]).ok)

    def test_el_codigo_fijo_ya_no_esta_en_el_codigo_ni_se_usa(self):
        for nombre in ("APP_final.py", "verificacion.py", "almacen.py"):
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), nombre), encoding="utf-8") as f:
                self.assertNotIn("NEON_CODIGO_PROFESOR", f.read(), nombre)

    def test_el_codigo_antiguo_no_esta_en_ningun_archivo_del_proyecto(self):
        antiguo = ("PROFE" + "2026").lower()                              # armado a trozos para que esta prueba tampoco lo contenga
        raiz = os.path.dirname(os.path.abspath(__file__))
        con_el_codigo = [os.path.relpath(r, raiz) for r, texto in archivos_de_texto(raiz) if antiguo in texto.lower()]
        self.assertEqual(con_el_codigo, [])

    def test_las_cuentas_demo_ya_no_se_siembran_con_una_clave_escrita_en_el_codigo(self):
        raiz = os.path.dirname(os.path.abspath(__file__))
        for nombre in ("almacen.py", "APP_final.py", "app_movil.py"):
            with open(os.path.join(raiz, nombre), encoding="utf-8") as f:
                fuente = f.read()
            with self.subTest(archivo=nombre):
                self.assertNotRegex(fuente, r'_hash\(\s*"123"\s*\)')            # la semilla antigua
                self.assertNotRegex(fuente, r'\bp\s*==\s*"123"')                   # ni el login de demostración del prototipo móvil
        for nombre in ("almacen.py", "app_movil.py"):
            with open(os.path.join(raiz, nombre), encoding="utf-8") as f:
                self.assertIn("NEON_DEMO_CLAVE", f.read())


class TestAutenticacion(BDTestCase):
    def setUp(self):
        super().setUp()
        self.emisor, self.reloj = Emisor(), Reloj(1000.0)
        self.db = APP_final.DatabaseManager(enviar=self.emisor, reloj=self.reloj, config=CONFIG)

    def registrar(self, usuario="ana", correo="ana@correo.test", rol="Estudiante", materia=None, grado="11"):
        return self.db.registrar_usuario(usuario, correo, "clave123", rol, materia, grado)

    def test_una_cuenta_sin_verificar_no_entra_y_con_la_clave_mala_el_mensaje_es_generico(self):
        self.assertTrue(self.registrar().ok)
        self.assertEqual(self.db.autenticar("ana", "clave123", "Estudiante"), (False, APP_final.MSG_NO_VERIFICADO))
        ok, mensaje = self.db.autenticar("ana", "mala", "Estudiante")
        self.assertEqual((ok, mensaje), (False, "❌ Credenciales incorrectas o Rol equivocado."))     # no revela que existe
        self.assertEqual(self.db.autenticar("ana", "clave123", "Profesor")[1], "❌ Credenciales incorrectas o Rol equivocado.")

    def test_tras_verificar_la_cuenta_entra(self):
        self.registrar()
        self.assertTrue(self.db.verificar_codigo("ana", self.emisor.enviados[0][1]).ok)
        ok, datos = self.db.autenticar("ana", "clave123", "Estudiante")
        self.assertTrue(ok)
        self.assertEqual((datos["role"], datos["grado"], datos["verificado"]), ("Estudiante", "11", True))

    def test_las_cuentas_que_ya_existian_siguen_entrando(self):
        almacen.crear_usuario("carla", "c@x.test", "clave123", "Estudiante", None, "11")
        self.assertTrue(self.db.autenticar("carla", "clave123", "Estudiante")[0])

    def test_los_profesores_tambien_deben_verificar(self):
        self.assertTrue(self.registrar("profe", "profe@correo.test", "Profesor", "Física", None).ok)
        self.assertEqual(self.db.autenticar("profe", "clave123", "Profesor"), (False, APP_final.MSG_NO_VERIFICADO))

    def test_reglas_de_registro_que_se_conservan(self):
        self.assertEqual(self.registrar(grado=None).codigo, "datos")                                    # el estudiante necesita grado
        self.assertEqual(self.db.registrar_usuario("x", "x@correo.test", "clave123", "Administrador").codigo, "datos")
        self.assertEqual(self.db.registrar_usuario("", "x@correo.test", "clave123", "Estudiante", None, "11").codigo, "datos")
        self.assertEqual(self.db.registrar_usuario("x", "", "clave123", "Estudiante", None, "11").codigo, "datos")
        self.assertEqual(self.emisor.enviados, [])

    def test_el_grado_debe_ser_uno_de_los_que_existen(self):                # revisión independiente, hallazgo 12
        for grado in ("99", "abc", "", "11 ", "0"):
            with self.subTest(grado=grado):
                self.assertEqual(self.registrar(grado=grado).codigo, "datos")
        self.assertIsNone(almacen.obtener_usuario("ana"))
        self.assertEqual(self.emisor.enviados, [])
        self.assertTrue(self.registrar(grado="11").ok)

    def test_sin_configuracion_el_registro_falla_de_forma_segura(self):
        db = APP_final.DatabaseManager(enviar=self.emisor, reloj=self.reloj)                             # config=None: lee el entorno
        with mock.patch.dict(os.environ, {}, clear=True):
            r = db.registrar_usuario("ana", "ana@correo.test", "clave123", "Estudiante", None, "11")
        self.assertEqual((r.ok, r.codigo), (False, "config"))
        self.assertIsNone(almacen.obtener_usuario("ana"))

    def test_correo_de_y_modo_desarrollo(self):
        self.registrar()
        self.assertEqual(self.db.correo_de("ana"), "a***@correo.test")
        self.assertEqual(self.db.correo_de("nadie"), "")
        with mock.patch.dict(os.environ, {"NEON_CORREO_MODO": "consola"}, clear=True):
            self.assertTrue(APP_final.DatabaseManager().modo_desarrollo())
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(APP_final.DatabaseManager().modo_desarrollo())

    def test_reenviar_cancelar_y_segundos_pasan_por_el_manager(self):
        self.registrar()
        self.assertEqual(self.db.segundos_para_reenviar("ana"), 60)
        self.reloj.t = 1060.0
        self.assertTrue(self.db.reenviar_codigo("ana").ok)
        self.assertEqual(len(self.emisor.enviados), 2)
        self.assertEqual(self.db.cancelar_registro("ana", "mala").codigo, "clave")
        self.assertTrue(self.db.cancelar_registro("ana", "clave123").ok)
        self.assertIsNone(almacen.obtener_usuario("ana"))


if __name__ == "__main__":
    unittest.main()
