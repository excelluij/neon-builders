import sqlite3
import hashlib
import re
import os
import pandas as pd
import logging

logger = logging.getLogger("NeonBuilders_DB")

class DatabaseManager:
    def __init__(self, db_path="nexus_cloud_data.db"):
        directorio_actual = os.path.dirname(os.path.abspath(__file__))
        self.db_path = os.path.join(directorio_actual, db_path)
        self.crear_tablas()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def crear_tablas(self):
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # Tabla segura de usuarios
                cursor.execute("PRAGMA table_info(usuarios)")
                columnas = [col[1] for col in cursor.fetchall()]
                if columnas and 'salt' not in columnas:
                    logger.warning("Purgando tabla de usuarios vieja e insegura...")
                    cursor.execute("DROP TABLE usuarios")

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS usuarios (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        usuario TEXT UNIQUE NOT NULL,
                        correo TEXT UNIQUE NOT NULL,
                        password TEXT NOT NULL,
                        salt TEXT NOT NULL,
                        puntos INTEGER DEFAULT 0
                    )
                ''')
        except sqlite3.Error as e:
            logger.error(f"Error fatal creando tablas: {e}")

    def _hash_password(self, password: str, salt: bytes = None):
        if salt is None:
            salt = os.urandom(32)
        key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        return key.hex(), salt.hex()

    def registrar_usuario(self, usuario, correo, password):
        if not usuario or not correo or not password:
            return False, "Todos los campos son obligatorios."
        if not re.match(r"[^@]+@[^@]+\.[^@]+", correo):
            return False, "Formato de correo electrónico inválido."
            
        pwd_hash, salt = self._hash_password(password)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO usuarios (usuario, correo, password, salt, puntos) VALUES (?, ?, ?, ?, ?)",
                               (usuario, correo, pwd_hash, salt, 0))
            return True, "Registro exitoso. Inicia sesión."
        except sqlite3.IntegrityError:
            return False, "Error: El usuario o correo ya está registrado."

    def autenticar(self, identificador, password):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT usuario, password, salt FROM usuarios WHERE usuario=? OR correo=?",
                           (identificador, identificador))
            user = cursor.fetchone()
            if user:
                username, stored_hash, stored_salt = user
                attempt_hash, _ = self._hash_password(password, bytes.fromhex(stored_salt))
                if attempt_hash == stored_hash:
                    return True, username
        return False, "Credenciales incorrectas."

    def guardar_encuesta_db(self, df):
        """Recibe el DataFrame limpio y lo guarda en SQLite."""
        try:
            with self._get_connection() as conn:
                df.to_sql("encuestas_alumnos", conn, if_exists="append", index=False)
            return True, f"Se insertaron {len(df)} respuestas en la Matrix."
        except Exception as e:
            return False, f"Error en BD: {e}"

    def obtener_datos_encuesta(self):
        """Retorna la tabla de encuestas como un DataFrame de Pandas."""
        try:
            with self._get_connection() as conn:
                return pd.read_sql_query("SELECT * FROM encuestas_alumnos", conn)
        except Exception:
            return pd.DataFrame() # Retorna vacío si no existe