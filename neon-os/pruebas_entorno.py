"""Pruebas del cargador de .env (entorno.py), del .gitignore, de .env.example y de requirements.txt.

Ejecutar desde esta carpeta:   python pruebas_entorno.py -v
Nunca lee el .env real del proyecto ni toca neon_os.db: todo se prueba con carpetas y bases temporales y con credenciales FALSAS.
"""
import ast
import atexit
import contextlib
import io
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

_TMP = tempfile.mkdtemp(prefix="neon_entorno_")
atexit.register(shutil.rmtree, _TMP, ignore_errors=True)
os.environ["NEON_DB"] = os.path.join(_TMP, "import.db")           # antes de importar almacen
RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RAIZ)

import almacen
import correo
import entorno

SECRETO = "clave-secreta-solo-de-prueba-7"
ENV_BREVO = f"""# configuración de prueba (FALSA)
NEON_SMTP_HOST=smtp.proveedor.test
NEON_SMTP_USUARIO=usuario@proveedor.test
NEON_SMTP_CLAVE={SECRETO}
NEON_SMTP_REMITENTE="Neon OS <no-responder@proveedor.test>"
"""


def entorno_limpio(**extra):
    """Entorno para los procesos hijos: el actual sin ninguna variable NEON_*."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("NEON_")}
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(extra)
    return env


class ConCarpeta(unittest.TestCase):
    def setUp(self):
        self.carpeta = tempfile.mkdtemp(prefix="caso_", dir=_TMP)

    def escribir(self, nombre, contenido, binario=False):
        ruta = os.path.join(self.carpeta, nombre)
        with open(ruta, "wb" if binario else "w", **({} if binario else {"encoding": "utf-8", "newline": ""})) as f:
            f.write(contenido)
        return ruta


# ==============================================================================
# El formato del .env
# ==============================================================================
class TestParser(unittest.TestCase):
    def pares(self, texto):
        return [(n, v) for n, v, _ in entorno.parsear(texto)[0]]

    def test_comentarios_y_lineas_vacias_se_ignoran(self):
        self.assertEqual(entorno.parsear("# nota\n\n   # otra\nNEON_A=1\n")[0], [("NEON_A", "1", 4)])

    def test_export_espacios_y_tabuladores(self):
        self.assertEqual(self.pares("export NEON_A=1\n\tNEON_B = valor con espacios  \nNEON_C=\t x"),
                         [("NEON_A", "1"), ("NEON_B", "valor con espacios"), ("NEON_C", "x")])

    def test_comillas_simples_o_dobles_rodean_el_valor_y_se_quitan(self):
        self.assertEqual(self.pares('NEON_A="hola mundo"\nNEON_B=\'x y\'\nNEON_C="a\'b"\nNEON_D=\'a"b\''),
                         [("NEON_A", "hola mundo"), ("NEON_B", "x y"), ("NEON_C", "a'b"), ("NEON_D", 'a"b')])
        self.assertEqual(self.pares('NEON_A=" con espacios al borde "'), [("NEON_A", " con espacios al borde ")])

    def test_el_valor_puede_llevar_igual_y_almohadilla_sin_comillas(self):
        # no hay comentarios al final de línea: una clave con # no se corta
        self.assertEqual(self.pares("NEON_A=abc=def#ghi\nNEON_B=a b # c"), [("NEON_A", "abc=def#ghi"), ("NEON_B", "a b # c")])

    def test_valor_vacio_y_unicode(self):
        self.assertEqual(self.pares("NEON_A=\nNEON_B=contraseña-ñ-ü"), [("NEON_A", ""), ("NEON_B", "contraseña-ñ-ü")])

    def test_bom_y_finales_de_linea_de_windows(self):
        self.assertEqual(self.pares("\ufeffNEON_A=1\r\nNEON_B=2\r\n\r\n"), [("NEON_A", "1"), ("NEON_B", "2")])

    def test_lineas_invalidas_se_reportan_por_numero_y_no_aportan_variables(self):
        texto = 'NEON_OK=1\nesto no es una linea\n=sinnombre\nNEON_SIN_IGUAL\nNEON_ABIERTA="sin cerrar\n1MAL=3\nNEON_FIN=2\n'
        pares, invalidas = entorno.parsear(texto)
        self.assertEqual([(n, v) for n, v, _ in pares], [("NEON_OK", "1"), ("NEON_FIN", "2")])
        self.assertEqual(invalidas, [2, 3, 4, 5, 6])

    def test_parsear_devuelve_los_nombres_tal_cual_y_el_filtro_lo_hace_cargar_env(self):
        self.assertEqual(self.pares("PATH=x\nneon_x=1\nNEON_A=1"), [("PATH", "x"), ("neon_x", "1"), ("NEON_A", "1")])


# ==============================================================================
# Cargar el archivo en el entorno
# ==============================================================================
class TestCargar(ConCarpeta):
    def cargar(self, contenido, env=None, **kw):
        ruta = self.escribir(".env", contenido)
        env = {} if env is None else env
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            resumen = entorno.cargar_env(ruta, env, **kw)
        return resumen, env, err.getvalue()

    def test_carga_las_variables_en_el_entorno_dado(self):
        resumen, env, _ = self.cargar(ENV_BREVO)
        self.assertEqual(env["NEON_SMTP_HOST"], "smtp.proveedor.test")
        self.assertEqual(env["NEON_SMTP_CLAVE"], SECRETO)
        self.assertEqual(env["NEON_SMTP_REMITENTE"], "Neon OS <no-responder@proveedor.test>")
        self.assertTrue(resumen["existe"])
        self.assertEqual(sorted(resumen["cargadas"]), ["NEON_SMTP_CLAVE", "NEON_SMTP_HOST", "NEON_SMTP_REMITENTE", "NEON_SMTP_USUARIO"])
        self.assertIsNone(resumen["error"])

    def test_lo_que_ya_esta_definido_en_el_sistema_tiene_prioridad(self):
        resumen, env, _ = self.cargar("NEON_SMTP_HOST=del-env\nNEON_SMTP_USUARIO=u", {"NEON_SMTP_HOST": "del-sistema"})
        self.assertEqual(env["NEON_SMTP_HOST"], "del-sistema")
        self.assertEqual(env["NEON_SMTP_USUARIO"], "u")
        self.assertEqual((resumen["ya_definidas"], resumen["cargadas"]), (["NEON_SMTP_HOST"], ["NEON_SMTP_USUARIO"]))

    def test_una_variable_vacia_del_sistema_cuenta_como_no_definida(self):
        _, env, _ = self.cargar("NEON_SMTP_HOST=del-env", {"NEON_SMTP_HOST": "   "})
        self.assertEqual(env["NEON_SMTP_HOST"], "del-env")

    def test_solo_se_cargan_variables_NEON_y_las_demas_se_ignoran_por_nombre(self):
        resumen, env, aviso = self.cargar("PATH=C:\\peligro\nPYTHONPATH=x\nneon_minuscula=1\nNEON-RARA=2\nNEON_A=1\nNEON_B_2=2")
        self.assertEqual(env, {"NEON_A": "1", "NEON_B_2": "2"})
        self.assertEqual(sorted(resumen["ignoradas"]), ["NEON-RARA", "PATH", "PYTHONPATH", "neon_minuscula"])
        self.assertIn("PATH", aviso)
        self.assertNotIn("peligro", aviso)                                  # avisa del nombre, nunca del valor

    def test_valores_vacios_no_se_cargan(self):
        resumen, env, _ = self.cargar("NEON_SMTP_PUERTO=\nNEON_A=1")
        self.assertEqual(env, {"NEON_A": "1"})
        self.assertEqual(resumen["vacias"], ["NEON_SMTP_PUERTO"])

    def test_si_una_variable_se_repite_gana_la_ultima(self):
        _, env, _ = self.cargar("NEON_A=1\nNEON_A=2")
        self.assertEqual(env["NEON_A"], "2")

    def test_sin_archivo_no_hace_nada_ni_avisa(self):
        env, err = {}, io.StringIO()
        with contextlib.redirect_stderr(err):
            resumen = entorno.cargar_env(os.path.join(self.carpeta, ".env"), env)
        self.assertEqual((resumen["existe"], resumen["cargadas"], env, err.getvalue()), (False, [], {}, ""))
        self.assertEqual(entorno.describir(resumen), [])

    def test_si_existe_env_txt_pero_no_env_lo_avisa(self):
        self.escribir(".env.txt", "NEON_A=1")
        env = {}
        with contextlib.redirect_stderr(io.StringIO()):
            resumen = entorno.cargar_env(os.path.join(self.carpeta, ".env"), env)
        self.assertTrue(resumen["aviso_txt"])
        self.assertEqual(env, {})                                           # no se carga: el archivo debe llamarse .env
        self.assertTrue(any(".env.txt" in linea for linea in entorno.describir(resumen)))

    def test_archivo_ilegible_o_no_utf8_no_lanza_y_no_carga_nada(self):
        env, err = {}, io.StringIO()
        with contextlib.redirect_stderr(err):
            r1 = entorno.cargar_env(self.carpeta, env)                       # una carpeta en vez de un archivo
        self.assertEqual(env, {})
        malo = self.escribir("raro.env", b"NEON_A=\xff\xfe\x00", binario=True)
        with contextlib.redirect_stderr(err):
            r2 = entorno.cargar_env(malo, env)
        self.assertEqual(env, {})
        self.assertIsNotNone(r2["error"])
        self.assertIn("UTF-8", r2["error"])
        self.assertIn("no se pudo leer", err.getvalue().lower())
        self.assertTrue(r1["existe"])
        self.assertIsNotNone(r1["error"])

    def test_lineas_invalidas_se_avisan_por_numero_sin_mostrar_su_contenido(self):
        resumen, env, aviso = self.cargar(f'NEON_OK=1\nNEON_SMTP_CLAVE "{SECRETO}"\n')
        self.assertEqual(resumen["invalidas"], [2])
        self.assertIn("línea 2", aviso)
        self.assertNotIn(SECRETO, aviso)
        self.assertEqual(env, {"NEON_OK": "1"})

    def test_ningun_mensaje_ni_resumen_muestra_los_valores(self):
        resumen, _, aviso = self.cargar(ENV_BREVO + "PATH=valor-raro\nNEON_BAD\n")
        salida = aviso + "\n".join(entorno.describir(resumen)) + repr(resumen)
        for valor in (SECRETO, "smtp.proveedor.test", "usuario@proveedor.test", "valor-raro"):
            self.assertNotIn(valor, salida)

    def test_avisar_false_no_escribe_nada(self):
        _, _, aviso = self.cargar("PATH=x\nNEON_BAD\n", avisar=False)
        self.assertEqual(aviso, "")

    def test_describir_resume_cuantas_variables_se_leyeron_sin_valores(self):
        resumen, _, _ = self.cargar(ENV_BREVO, {"NEON_SMTP_HOST": "del-sistema"})
        lineas = entorno.describir(resumen)
        texto = "\n".join(lineas)
        self.assertIn(".env", texto)
        self.assertIn("NEON_SMTP_CLAVE", texto)
        self.assertIn("prioridad", texto)                                   # menciona que el sistema gana (NEON_SMTP_HOST)
        self.assertNotIn(SECRETO, texto)

    def test_por_defecto_usa_el_entorno_real_y_el_env_junto_a_la_app(self):
        self.assertEqual(entorno.RUTA_POR_DEFECTO, os.path.join(RAIZ, ".env"))
        ruta = self.escribir(".env", "NEON_PRUEBA_X=hola")
        with mock.patch.dict(os.environ, {}, clear=True):
            entorno.cargar_env(ruta)
            self.assertEqual(os.environ["NEON_PRUEBA_X"], "hola")

    def test_con_un_env_brevo_la_configuracion_de_correo_queda_completa(self):
        _, env, _ = self.cargar(ENV_BREVO)
        config = correo.cargar_config(env)
        self.assertEqual((config.host, config.usuario, config.puerto, config.seguridad, config.modo),
                         ("smtp.proveedor.test", "usuario@proveedor.test", 587, "starttls", "smtp"))
        self.assertEqual(config.clave, SECRETO)
        self.assertNotIn(SECRETO, repr(config))


# ==============================================================================
# Que cada arranque lea el .env (en un proceso aparte, con copias en una carpeta temporal)
# ==============================================================================
def _es_main(nodo):
    return (isinstance(nodo, ast.If) and isinstance(nodo.test, ast.Compare) and isinstance(nodo.test.left, ast.Name)
            and nodo.test.left.id == "__name__" and any(isinstance(c, ast.Constant) and c.value == "__main__" for c in nodo.test.comparators))


def _llama(nodo, nombre):
    return any(isinstance(n, ast.Call) and getattr(n.func, "attr", getattr(n.func, "id", None)) == nombre for n in ast.walk(nodo))


def _arbol(archivo):
    with open(os.path.join(RAIZ, archivo), encoding="utf-8") as f:
        return ast.parse(f.read())


class TestArranques(ConCarpeta):
    def copiar(self, *archivos):
        for a in archivos:
            shutil.copy(os.path.join(RAIZ, a), self.carpeta)

    def correr(self, *args, env=None, cwd=None):
        r = subprocess.run([sys.executable, *args], cwd=cwd or self.carpeta, env=env or entorno_limpio(), capture_output=True,
                           text=True, encoding="utf-8", timeout=60)
        return r.returncode, r.stdout + r.stderr

    def test_correo_config_lee_el_env_junto_al_script_aunque_se_ejecute_desde_otra_carpeta(self):
        self.copiar("correo.py", "entorno.py", "rutas.py")
        self.escribir(".env", ENV_BREVO)
        otra = tempfile.mkdtemp(dir=_TMP)
        codigo, salida = self.correr(os.path.join(self.carpeta, "correo.py"), "--config", cwd=otra)
        self.assertEqual(codigo, 0, salida)
        self.assertIn("Configuración completa", salida)
        self.assertIn(".env", salida)
        for valor in (SECRETO, "smtp.proveedor.test", "usuario@proveedor.test"):
            self.assertNotIn(valor, salida)

    def test_correo_config_sin_env_sigue_diciendo_que_faltan_variables(self):
        self.copiar("correo.py", "entorno.py", "rutas.py")
        codigo, salida = self.correr("correo.py", "--config")
        self.assertEqual(codigo, 1)
        self.assertIn("faltan variables obligatorias", salida)

    def test_las_variables_del_sistema_ganan_al_env_en_el_arranque(self):
        self.copiar("correo.py", "entorno.py", "rutas.py")
        self.escribir(".env", ENV_BREVO + "NEON_CORREO_MODO=consola\n")
        codigo, salida = self.correr("correo.py", "--config", env=entorno_limpio(NEON_CORREO_MODO="smtp"))
        self.assertEqual(codigo, 0, salida)
        self.assertIn("Configuración completa", salida)                      # gana «smtp» del sistema, no «consola» del .env
        self.assertNotIn("Modo desarrollo", salida)

    def test_almacen_usa_el_NEON_DB_del_env(self):
        self.copiar("almacen.py", "entorno.py", "rutas.py")
        base = os.path.join(self.carpeta, "desde_env.db")
        con = sqlite3.connect(base)
        con.execute("CREATE TABLE usuarios (usuario TEXT PRIMARY KEY, clave TEXT NOT NULL, rol TEXT NOT NULL, materia TEXT, correo TEXT, grado TEXT)")
        con.execute("INSERT INTO usuarios VALUES ('camilo', ?, 'Profesor', 'Física', 'c@x.test', NULL)", (almacen._hash(almacen.CLAVE_DEMO_ANTIGUA),))
        con.commit()
        con.close()
        self.escribir(".env", f"NEON_DB={base}\n")
        codigo, salida = self.correr("almacen.py", "--cuentas-demo")
        self.assertEqual(codigo, 0, salida)
        self.assertIn("camilo", salida)
        self.assertIn("desde_env.db", salida)

    def test_cada_punto_de_arranque_carga_el_env_solo_al_ejecutarse_como_programa(self):
        # APP_final.py: antes de importar juegos / ia_local / almacen (leen NEON_* al importarse), y solo bajo __main__
        arbol = _arbol("APP_final.py")
        cuerpo = arbol.body
        bloques = [i for i, n in enumerate(cuerpo) if _es_main(n) and _llama(n, "cargar_env")]
        self.assertEqual(len(bloques), 1, "APP_final.py debe cargar el .env en un bloque if __name__ == '__main__'")
        for modulo in ("juegos", "arena", "almacen", "ia_local", "correo", "verificacion"):
            donde = [i for i, n in enumerate(cuerpo) if isinstance(n, ast.Import) and any(a.name == modulo for a in n.names)]
            self.assertTrue(donde, modulo)
            self.assertLess(bloques[0], donde[0], f"el .env se debe cargar antes de importar {modulo}")
        # almacen.py: antes de calcular RUTA
        cuerpo = _arbol("almacen.py").body
        bloques = [i for i, n in enumerate(cuerpo) if _es_main(n) and _llama(n, "cargar_env")]
        ruta = [i for i, n in enumerate(cuerpo) if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "RUTA" for t in n.targets)]
        self.assertTrue(bloques and ruta and bloques[0] < ruta[0], "almacen.py debe cargar el .env antes de calcular RUTA")
        # correo.py y app_movil.py: dentro del bloque principal, antes de ejecutar
        for archivo, ejecutar in (("correo.py", "main"), ("app_movil.py", "run")):
            principal = [n for n in _arbol(archivo).body if _es_main(n)]
            self.assertTrue(principal, archivo)
            orden = [("cargar_env" if _llama(s, "cargar_env") else ejecutar if _llama(s, ejecutar) else None) for s in principal[-1].body]
            orden = [o for o in orden if o]
            self.assertEqual(orden[:2], ["cargar_env", ejecutar], archivo)


# ==============================================================================
# Archivos del proyecto: .gitignore, .env.example, requirements.txt
# ==============================================================================
def _lineas(nombre):
    with open(os.path.join(RAIZ, nombre), encoding="utf-8") as f:
        return [linea.rstrip("\n") for linea in f]


def _nombres_neon_que_lee_el_codigo():
    nombres = set()
    for archivo in os.listdir(RAIZ):
        if archivo.endswith(".py") and not archivo.startswith("pruebas_"):
            with open(os.path.join(RAIZ, archivo), encoding="utf-8", errors="ignore") as f:
                nombres.update(re.findall(r"\bNEON_[A-Z0-9_]+\b", f.read()))
    return nombres


def _git_ignora(ruta):
    """True/False según `git check-ignore`; None si no hay git o la carpeta no está en un repositorio."""
    try:
        r = subprocess.run(["git", "check-ignore", "-q", "--", ruta], cwd=RAIZ, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return {0: True, 1: False}.get(r.returncode)


class TestGitignore(unittest.TestCase):
    def test_el_gitignore_excluye_env_bases_de_datos_y_cache(self):
        reglas = {linea.strip() for linea in _lineas(".gitignore") if linea.strip() and not linea.startswith("#")}
        for regla in (".env", ".env.*", "!.env.example", "*.db", "__pycache__/", "*.pyc"):
            self.assertIn(regla, reglas)

    def test_git_confirma_que_se_ignora_y_que_no(self):
        if _git_ignora(".env") is None:
            self.skipTest("git no está disponible o la carpeta no está en un repositorio")
        for ruta in (".env", ".env.local", "neon_os.db", "copia_antes.db", "__pycache__/almacen.cpython-310.pyc", ".venv/Scripts/python.exe"):
            with self.subTest(ignorado=ruta):
                self.assertTrue(_git_ignora(ruta), ruta)
        for ruta in (".env.example", "almacen.py", "requirements.txt", ".gitignore", "docs/CORREO.md", "pruebas_entorno.py"):
            with self.subTest(no_ignorado=ruta):
                self.assertFalse(_git_ignora(ruta), ruta)


class TestEnvExample(unittest.TestCase):
    SEGUROS = {"", "smtp-relay.brevo.com", "587", "465", "starttls", "ssl", "15", "smtp", "consola", "luix"}

    def test_lista_todas_las_variables_NEON_que_lee_el_codigo(self):
        en_el_ejemplo = set(re.findall(r"\bNEON_[A-Z0-9_]+\b", "\n".join(_lineas(".env.example"))))
        self.assertEqual(sorted(_nombres_neon_que_lee_el_codigo() - en_el_ejemplo), [])

    def test_copiarlo_tal_cual_a_env_no_carga_nada(self):
        texto = "\n".join(_lineas(".env.example"))
        pares, invalidas = entorno.parsear(texto)
        self.assertEqual((pares, invalidas), ([], []))                      # todo comentado: hay que descomentar y rellenar

    def test_descomentado_solo_contiene_marcadores_y_valores_no_secretos(self):
        activas = []
        for linea in _lineas(".env.example"):
            m = re.match(r"^#\s*(NEON_[A-Z0-9_]+\s*=.*)$", linea)
            if m:
                activas.append(m.group(1))
        pares, invalidas = entorno.parsear("\n".join(activas))
        self.assertEqual(invalidas, [])
        self.assertGreaterEqual(len(pares), 10)
        for nombre, valor, _ in pares:
            with self.subTest(nombre=nombre):
                self.assertTrue(valor in self.SEGUROS or re.fullmatch(r"<[^<>]+>", valor) or re.fullmatch(r".*<[^<>]+>.*", valor),
                                f"{nombre} parece traer un valor real")

    def test_menciona_la_advertencia_de_no_subirlo_a_git(self):
        self.assertIn("nunca", "\n".join(_lineas(".env.example")).lower())


class TestRequirements(unittest.TestCase):
    ASIGNADOS = {"PIL": "pillow"}

    def requisitos(self):
        out = {}
        for linea in _lineas("requirements.txt"):
            linea = linea.strip()
            if not linea or linea.startswith("#"):
                continue
            self.assertRegex(linea, r"^[A-Za-z0-9_.-]+==\d+(\.\d+)*$", f"se esperaba nombre==versión: {linea!r}")
            nombre, version = linea.split("==")
            out[nombre.lower()] = version
        return out

    def modulos_locales_de_la_app(self):
        """APP_final.py y todo lo que importa de la propia carpeta (cierre transitivo)."""
        locales = {a[:-3] for a in os.listdir(RAIZ) if a.endswith(".py")}
        vistos, pendientes = set(), ["APP_final"]
        while pendientes:
            m = pendientes.pop()
            if m in vistos:
                continue
            vistos.add(m)
            for n in ast.walk(_arbol(m + ".py")):
                for nombre in ([a.name for a in n.names] if isinstance(n, ast.Import) else [n.module] if isinstance(n, ast.ImportFrom) and n.module else []):
                    if nombre.split(".")[0] in locales:
                        pendientes.append(nombre.split(".")[0])
        return vistos

    def test_las_dependencias_estan_fijadas_a_versiones_probadas(self):
        pedidos = self.requisitos()
        self.assertTrue({"customtkinter", "pillow", "requests"} <= set(pedidos))

    def test_cubre_todo_lo_de_terceros_que_importa_la_app(self):
        pedidos = self.requisitos()
        locales = {a[:-3] for a in os.listdir(RAIZ) if a.endswith(".py")}
        faltan = set()
        for modulo in self.modulos_locales_de_la_app():
            for n in ast.walk(_arbol(modulo + ".py")):
                nombres = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module] if isinstance(n, ast.ImportFrom) and n.module else []
                for nombre in nombres:
                    raiz = nombre.split(".")[0]
                    if raiz in sys.stdlib_module_names or raiz in locales:
                        continue
                    if self.ASIGNADOS.get(raiz, raiz).lower() not in pedidos:
                        faltan.add(raiz)
        self.assertEqual(sorted(faltan), [])

    def test_no_incluye_enlaces_ni_instalaciones_editables(self):
        texto = "\n".join(_lineas("requirements.txt"))
        for prohibido in ("http://", "https://", "git+", "-e ", "--index-url", "--extra-index-url"):
            self.assertNotIn(prohibido, texto)


if __name__ == "__main__":
    unittest.main()
