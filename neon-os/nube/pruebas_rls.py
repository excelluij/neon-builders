"""Pruebas de seguridad del esquema en la nube (Supabase). Corren contra el PROYECTO DE PRUEBAS, nunca el real.

Necesitan tres valores, de variables de entorno o del archivo local nube/.env.pruebas (nunca se imprimen):
    NEON_TEST_URL, NEON_TEST_ANON_KEY, NEON_TEST_SERVICE_KEY
Sin ellos todas las pruebas se omiten. Ejecutar desde la carpeta del proyecto:   python nube/pruebas_rls.py -v
"""
import os
import pathlib
import unittest
import uuid

import requests

ARCHIVO_CLAVES = pathlib.Path(__file__).with_name(".env.pruebas")
NOMBRES = ("NEON_TEST_URL", "NEON_TEST_ANON_KEY", "NEON_TEST_SERVICE_KEY")


def _leer_claves():
    valores = {n: os.environ.get(n, "").strip() for n in NOMBRES}
    if ARCHIVO_CLAVES.exists():
        for linea in ARCHIVO_CLAVES.read_text(encoding="utf-8-sig").splitlines():
            if "=" in linea and not linea.lstrip().startswith("#"):
                nombre, valor = linea.split("=", 1)
                if nombre.strip() in valores and not valores[nombre.strip()]:
                    valores[nombre.strip()] = valor.strip().strip("\"'")
    return valores


class Nube:
    """Cliente mínimo de Supabase para las pruebas: usuarios por la API de administración, el resto con sesión real."""

    def __init__(self, url, anon, servicio):
        self.url, self.anon, self.servicio = url.rstrip("/"), anon, servicio
        self.creados = []

    def _cabeceras(self, token=None, clave=None):
        return {"apikey": clave or self.anon, "Authorization": f"Bearer {token or clave or self.anon}",
                "Content-Type": "application/json"}

    def crear_usuario(self, correo, clave, metadatos=None):
        """Crea un usuario ya confirmado (API de administración). Devuelve el JSON; en error trae 'error_code'/'msg'."""
        r = requests.post(f"{self.url}/auth/v1/admin/users", headers=self._cabeceras(clave=self.servicio), timeout=20,
                          json={"email": correo, "password": clave, "email_confirm": True, "user_metadata": metadatos or {}})
        datos = r.json()
        datos["status"] = r.status_code
        if r.status_code < 300 and datos.get("id"):
            self.creados.append(datos["id"])
        return datos

    def entrar(self, correo, clave):
        """Inicia sesión como lo haría una app: devuelve el token de acceso."""
        r = requests.post(f"{self.url}/auth/v1/token?grant_type=password", headers=self._cabeceras(), timeout=20,
                          json={"email": correo, "password": clave})
        r.raise_for_status()
        return r.json()["access_token"]

    def rest(self, metodo, tabla, token=None, servicio=False, json=None, **params):
        cab = self._cabeceras(token=token, clave=self.servicio if servicio else None)
        cab["Prefer"] = "return=representation"
        return requests.request(metodo, f"{self.url}/rest/v1/{tabla}", headers=cab, params=params, json=json, timeout=20)

    def rpc(self, nombre, datos, token=None):
        return requests.post(f"{self.url}/rest/v1/rpc/{nombre}", headers=self._cabeceras(token=token), json=datos, timeout=20)

    def borrar_creados(self):
        for uid in self.creados:
            requests.delete(f"{self.url}/auth/v1/admin/users/{uid}", headers=self._cabeceras(clave=self.servicio), timeout=20)
        self.creados.clear()


def _nueva():
    v = _leer_claves()
    return Nube(*(v[n] for n in NOMBRES)) if all(v.values()) else None


@unittest.skipUnless(_nueva(), "faltan NEON_TEST_URL / NEON_TEST_ANON_KEY / NEON_TEST_SERVICE_KEY (ver nube/.env.pruebas)")
class PruebaNube(unittest.TestCase):
    def setUp(self):
        self.nube = _nueva()
        self.addCleanup(self.nube.borrar_creados)

    def correo(self):
        return f"neon-{uuid.uuid4().hex[:10]}@example.com"

    def perfil(self, uid):
        filas = self.nube.rest("GET", "perfiles", servicio=True, id=f"eq.{uid}").json()
        return filas[0] if filas else None


class TestEsquema(PruebaNube):
    def test_registro_con_rol_administrador_en_metadatos_queda_estudiante(self):
        u = self.nube.crear_usuario(self.correo(), "Clave-de-prueba-1",
                                    {"usuario": "Ana_" + uuid.uuid4().hex[:6], "rol": "Administrador", "materia": "Física"})
        self.assertLess(u["status"], 300, u)
        p = self.perfil(u["id"])
        self.assertEqual(p["rol"], "Estudiante")
        self.assertIsNone(p["materia"])

    def test_usuario_repetido_con_otra_capitalizacion_se_rechaza(self):
        nombre = "Ana_" + uuid.uuid4().hex[:6]
        primero = self.nube.crear_usuario(self.correo(), "Clave-de-prueba-1", {"usuario": nombre})
        self.assertLess(primero["status"], 300, primero)
        segundo = self.nube.crear_usuario(self.correo(), "Clave-de-prueba-1", {"usuario": nombre.lower()})
        self.assertGreaterEqual(segundo["status"], 400)

    def test_perfil_creado_automaticamente_con_usuario_y_grado_de_los_metadatos(self):
        nombre = "Luis_" + uuid.uuid4().hex[:6]
        u = self.nube.crear_usuario(self.correo(), "Clave-de-prueba-1", {"usuario": nombre, "grado": "11"})
        p = self.perfil(u["id"])
        self.assertEqual((p["usuario"], p["grado"]), (nombre, "11"))


if __name__ == "__main__":
    unittest.main()
