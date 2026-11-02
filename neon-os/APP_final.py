import sys
import re
import requests
import random
import threading
import datetime
import hashlib
import json
import copy
import webbrowser
import urllib.request
import io
import os
import hmac
import time
import tkinter as tk
import customtkinter as ctk
from tkinter import filedialog, messagebox

if __name__ == "__main__":      # solo al arrancar la app (no al importar: las pruebas no leen el .env real). Va ANTES de
    import rutas
    os.chdir(rutas.carpeta_app())   # nexus_cloud_data.db se abre por ruta relativa: siempre junto a la app, abras desde donde abras
    import entorno            # importar juegos / ia_local / almacen, que leen variables NEON_* al cargarse.
    entorno.cargar_env()

import rutas
import juegos
import arena
import almacen
import ia_local
import correo
import verificacion

try:
    from PIL import Image
except ImportError:
    print("⚠️ Faltan librerías. Ejecuta: pip install pillow")
    sys.exit()

# ==============================================================================
# 🧠 BASE DE DATOS LOCAL (SQLite en almacen.py) Y MEMORIA GLOBAL
# ==============================================================================
almacen.iniciar()
MISIONES_GLOBALES = almacen.cargar_misiones()  # las misiones publicadas sobreviven al cerrar la app

MSG_NO_VERIFICADO = "📧 Tu correo aún no está verificado. Ingresa el código que te enviamos."
MSG_PRIMER_ACCESO = "🔑 Primer acceso de administrador: pide tu código por correo y crea tu contraseña."
MSG_CREDENCIALES = "❌ Credenciales incorrectas o Rol equivocado."
MSG_ADMIN_DENEGADO = "🚫 ACCESO DENEGADO: Credenciales de Dios (Admin) incorrectas."


class DatabaseManager:
    """Usuarios guardados en el archivo neon_os.db (claves protegidas con hash) y verificación de correo.
    `enviar`, `reloj` y `config` se inyectan en las pruebas; en producción valen None (SMTP real, hora real, variables de entorno)."""

    def __init__(self, enviar=None, reloj=None, config=None):
        self.enviar, self.reloj, self.config = enviar, reloj or time.time, config

    def autenticar(self, u, p, rol_esperado):
        usuario = u.strip().lower()
        datos = almacen.obtener_usuario(usuario)
        if rol_esperado == "Administrador":
            # Las cuentas de administrador (almacen.ADMINISTRADORES) viven en la base, con el correo como usuario. Nacen sin contraseña:
            # mientras no la tengan, el acceso es el primer acceso (código por correo + contraseña nueva), sea cual sea la que escriban.
            if datos and datos["role"] == "Administrador":
                if not datos["verificado"]:
                    return False, MSG_PRIMER_ACCESO
                if almacen.verificar_clave(usuario, p):
                    return True, datos
            return False, MSG_ADMIN_DENEGADO
        if datos and almacen.verificar_clave(usuario, p) and datos["role"] == rol_esperado:
            if not datos["verificado"]:        # solo se revela tras acertar usuario, clave y rol
                return False, MSG_NO_VERIFICADO
            return True, datos
        return False, MSG_CREDENCIALES

    def registrar_usuario(self, u, correo_electronico, p, role, materia=None, grado=None):
        """Crea la cuenta SIN verificar y envía el código por correo (a los profesores, también su código de profesor).
        Devuelve un verificacion.Resultado."""
        if role == "Administrador":
            return verificacion.Resultado(False, "🚫 ALERTA MATRIX: Los administradores son cuentas predefinidas: no se registran.", "datos")
        u_clean = u.lower().strip()
        if not u_clean or not p or not correo_electronico:
            return verificacion.Resultado(False, "⚠️ Llena todos los campos para continuar.", "datos")
        if role == "Estudiante" and grado not in juegos.GRADOS:
            return verificacion.Resultado(False, "⚠️ Elige tu grado para continuar.", "datos")
        return verificacion.iniciar_registro(u_clean, correo_electronico, p, role, materia, grado,
                                             enviar=self.enviar, reloj=self.reloj, config=self.config)

    def verificar_codigo(self, usuario, codigo, codigo_profesor=None, clave_nueva=None):
        return verificacion.verificar(usuario, codigo, codigo_profesor=codigo_profesor, clave_nueva=clave_nueva, reloj=self.reloj)

    def rol_de(self, usuario):
        """Rol de la cuenta ("Estudiante", "Profesor", "Administrador"); None si no existe."""
        datos = almacen.obtener_usuario(usuario)
        return datos["role"] if datos else None

    def reenviar_codigo(self, usuario):
        return verificacion.reenviar(usuario, enviar=self.enviar, reloj=self.reloj, config=self.config)

    def cancelar_registro(self, usuario, clave):
        return verificacion.cancelar_registro(usuario, clave)

    def segundos_para_reenviar(self, usuario):
        return verificacion.segundos_para_reenviar(usuario, reloj=self.reloj)

    def correo_de(self, usuario):
        """Correo de la cuenta, enmascarado (j***@correo.com); vacío si no existe."""
        datos = almacen.obtener_usuario(usuario)
        return verificacion.mascara_correo(datos["correo"]) if datos and datos["correo"] else ""

    def modo_desarrollo(self):
        """True si el correo está en modo desarrollo explícito (el código se imprime en la consola, no se envía)."""
        try:
            config = self.config or correo.cargar_config()
        except correo.ErrorCorreo:
            return False
        return bool(config and config.modo == "consola")

# ==============================================================================
# 💅 INTERFAZ: PALETA NEON OS PREMIUM (Con colores únicos por materia)
# ==============================================================================
COLORS = {
    "bg_app": "#0f172a", "bg_sidebar": "#1e293b", "bg_card": "#334155",
    "accent_1": "#38bdf8", "accent_2": "#818cf8", "text_main": "#f8fafc",
    "text_muted": "#94a3b8", "danger": "#ef4444", "success": "#10b981",
    "warning": "#f59e0b", 
    "mat_química": "#10b981", "mat_quimica": "#10b981",   # Verde
    "mat_física": "#3b82f6", "mat_fisica": "#3b82f6",     # Azul
    "mat_matemáticas": "#ef4444", "mat_matematicas": "#ef4444", # Rojo
    "mat_ciencias": "#8b5cf6", "mat_ciencia": "#8b5cf6",   # Morado
    "mat_sociales": "#f59e0b",                            # Naranja
    "mat_inglés": "#ec4899", "mat_ingles": "#ec4899"      # Rosa
}
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# ==============================================================================
# 🛡️ LA BÓVEDA (Núcleo de Economía, Rachas, Avatares y Anti-Hack)
# ==============================================================================
class BovedaCore:
    CORAZONES_ARENA = 5  # partidas de la Arena por día (independientes de las Vidas, que protegen contra el fraude)

    def __init__(self, username, grado=None):
        self.username = username
        self.grado = grado
        self.coins = 0
        self.diamonds = 0
        self.puntos = 0  # monedas ganadas en total: no baja al comprar y es lo que mide el ranking
        self.corazones_arena = self.CORAZONES_ARENA
        self.arena_fecha = None  # fecha ISO de la última recarga de corazones de la Arena
        self.records = {}  # mejor puntaje por juego clásico de la Arena ("serpiente", "tetris")
        self.hearts = 5
        self.streak = 1
        self.avatar_seed = username # Semilla base para el Avatar 2D
        self.last_regen_date = datetime.date.today()
        self.hashes_procesados = set()
        self.juegos_reclamados = set()  # claves "materia#id" de misiones de juego ya cobradas

        self.diccionario_materias = {
            "Química": ["molécula", "átomo", "reacción", "enlace", "carbono"],
            "Física": ["velocidad", "fuerza", "gravedad", "aceleración", "energía"],
            "Matemáticas": ["ecuación", "derivada", "integral", "álgebra", "geometría"],
            "Ciencias": ["biología", "ecosistema", "célula", "planeta", "naturaleza"],
            "Sociales": ["historia", "geografía", "sociedad", "cultura", "política"],
            "Inglés": ["verb", "grammar", "vocabulary", "english", "listening"]
        }

    def exportar(self):
        return {"coins": self.coins, "diamonds": self.diamonds, "puntos": self.puntos, "corazones_arena": self.corazones_arena, "arena_fecha": self.arena_fecha, "records": self.records, "hearts": self.hearts, "streak": self.streak,
                "avatar_seed": self.avatar_seed, "last_regen_date": self.last_regen_date.isoformat(),
                "hashes": sorted(self.hashes_procesados), "juegos_reclamados": sorted(self.juegos_reclamados)}

    def importar(self, d):
        self.coins, self.diamonds = d.get("coins", 0), d.get("diamonds", 0)
        self.puntos = d.get("puntos", self.coins)  # progresos viejos sin contador: arrancan con sus monedas actuales
        self.corazones_arena = d.get("corazones_arena", self.CORAZONES_ARENA)
        self.arena_fecha = d.get("arena_fecha")
        self.records = dict(d.get("records") or {})
        self.hearts, self.streak = d.get("hearts", 5), d.get("streak", 1)
        self.avatar_seed = d.get("avatar_seed", self.avatar_seed)
        try:
            self.last_regen_date = datetime.date.fromisoformat(d["last_regen_date"])
        except (KeyError, ValueError):
            pass
        self.hashes_procesados = set(d.get("hashes", []))
        self.juegos_reclamados = set(d.get("juegos_reclamados", []))

    def ganar(self, monedas, diamantes=0):
        """Única puerta para recibir recompensas: suma monedas y diamantes, y los puntos del ranking."""
        self.coins += monedas
        self.diamonds += diamantes
        self.puntos += monedas

    def arena_recargar(self, hoy=None):
        """Una vez por día los corazones de la Arena vuelven a 5. Se recargan al consultarlos (no solo al iniciar
        sesión) y solo hacia adelante: atrasar el reloj del equipo no da corazones."""
        hoy = (hoy or datetime.date.today()).isoformat()
        if self.arena_fecha is None or self.arena_fecha < hoy:
            self.corazones_arena, self.arena_fecha = self.CORAZONES_ARENA, hoy

    def corazones_arena_disponibles(self, hoy=None):
        self.arena_recargar(hoy)
        return self.corazones_arena

    def gastar_corazon_arena(self, hoy=None):
        """Cada partida cuesta 1 corazón, que se gasta al empezar. Devuelve (ok, mensaje)."""
        if self.corazones_arena_disponibles(hoy) <= 0:
            return False, "Sin corazones: vuelven mañana"
        self.corazones_arena -= 1
        return True, "❤️ −1 corazón"

    def devolver_corazon_arena(self):
        """Devuelve el corazón de una partida que no pudo abrirse (nunca pasa del máximo)."""
        self.corazones_arena = min(self.CORAZONES_ARENA, self.corazones_arena + 1)

    def registrar_record(self, juego, puntaje):
        """Guarda el puntaje si supera el récord del juego (y es mayor que 0). Devuelve True si es récord nuevo."""
        if puntaje > 0 and puntaje > self.records.get(juego, 0):
            self.records[juego] = puntaje
            return True
        return False

    def regenerar_diario(self):
        hoy = datetime.date.today()
        if hoy > self.last_regen_date:
            diferencia = (hoy - self.last_regen_date).days
            self.hearts = 5
            self.last_regen_date = hoy
            if diferencia == 1:
                self.streak += 1 
                return True, f"🔥 ¡Racha de {self.streak} días! Vidas restauradas."
            else:
                self.streak = 1  
                return True, "❄️ Perdiste tu racha por inactividad. Vidas restauradas a 5."
        return False, "⏳ Aún no termina el día actual."

    def generar_huella_archivo(self, ruta_archivo):
        sha256_hash = hashlib.sha256()
        try:
            with open(ruta_archivo, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""): sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception: return None

    def escanear_contenido_interno(self, ruta_archivo, palabras_esperadas, concepto_clave):
        try:
            with open(ruta_archivo, "r", encoding="utf-8", errors="ignore") as f:
                contenido = f.read().lower()
            if any(p in contenido for p in palabras_esperadas): return True
        except Exception: pass
        
        nombre_archivo = os.path.basename(ruta_archivo).lower()
        if concepto_clave.lower() in nombre_archivo or any(p in nombre_archivo for p in palabras_esperadas): return True
        return False

    def procesar_archivo_estricto(self, ruta_archivo, materia, concepto_clave, es_tarea_oficial=False, recompensa_monedas=10, recompensa_diamantes=2):
        if self.hearts <= 0: return False, "💀 Sin vidas. Vuelve mañana."
        huella = self.generar_huella_archivo(ruta_archivo)
        if not huella: return False, "⚠️ Archivo corrupto."
        if huella in self.hashes_procesados: self.hearts -= 1; return False, "🚫 FRAUDE: Archivo reciclado. \n💔 -1 Vida"
        
        concepto_limpio = concepto_clave.lower().strip()
        palabras = self.diccionario_materias.get(materia, [])
        if not any(p in concepto_limpio for p in palabras): self.hearts -= 1; return False, f"🚫 ERROR: Concepto no cuadra con {materia}. \n💔 -1 Vida"
        if not self.escanear_contenido_interno(ruta_archivo, palabras, concepto_clave): self.hearts -= 1; return False, f"🚫 FRAUDE: El interior no cuadra. \n💔 -1 Vida"

        self.hashes_procesados.add(huella)
        m_ganadas = int(recompensa_monedas)
        d_ganados = int(recompensa_diamantes)
        self.ganar(m_ganadas, d_ganados)
        return True, f"✅ Validado. \n💎 Drop: +{m_ganadas} 🪙 | +{d_ganados} 💎"

    def comprar_item(self, c, d, nombre_item):
        """LÓGICA OR: Cobra en monedas O en diamantes."""
        pago_exitoso = False
        metodo = ""
        
        if self.coins >= c and c > 0:
            self.coins -= c
            pago_exitoso = True
            metodo = "Monedas"
        elif self.diamonds >= d and d > 0:
            self.diamonds -= d
            pago_exitoso = True
            metodo = "Diamantes"
            
        if pago_exitoso:
            if "Avatar" in nombre_item:
                self.avatar_seed = nombre_item.replace(" ", "") + self.username
                return True, f"✅ Pagado con {metodo}. ¡Avatar Actualizado!"
            return True, f"✅ Pagado con {metodo}."
            
        return False, "❌ Fondos insuficientes de ambas divisas."
        
    def procesar_victoria_quiz(self):
        self.ganar(5, 2); return "✅ ¡Hackeo exitoso! \n💎 Drop: +5 🪙 | +2 💎"
        
    def procesar_derrota_quiz(self):
        if self.hearts > 0: self.hearts -= 1; return f"❌ ¡Error! \n💔 -1 vida."
        return "💀 Sin vidas."

# ==============================================================================
# 🧠 UTILIDADES DE RED, API DE AVATARES Y NAVEGADOR
# ==============================================================================
def extraer_datos_matrix(tema):
    try:
        url = f"https://es.wikipedia.org/api/rest_v1/page/summary/{tema}"
        res = requests.get(url, headers={'User-Agent': 'NeonOS_Edu_Project/1.0'}, timeout=5)
        if res.status_code == 200: return True, re.compile(re.escape(tema), re.IGNORECASE).sub("██████", res.json().get('extract', '')), tema.lower()
        return False, "Dato no encontrado.", ""
    except:
        dic_offline = {"gravedad": "Atracción planetaria...", "carbono": "Elemento vital..."}
        if tema.lower() in dic_offline: return True, dic_offline[tema.lower()], tema.lower()
        return False, "Fallo de conexión.", ""

def generar_avatar_2d(seed_name):
    """Conecta con la API de DiceBear para generar el Avatar 2D."""
    try:
        # Genera un avatar estilo bot basado en la semilla del usuario
        url = f"https://api.dicebear.com/7.x/bottts/png?seed={seed_name}&backgroundColor=1e293b"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        raw_data = urllib.request.urlopen(req, timeout=3).read()
        image = Image.open(io.BytesIO(raw_data)).resize((120, 120))
        return ctk.CTkImage(light_image=image, dark_image=image, size=(120, 120))
    except Exception as e:
        # Fallback si falla el internet: Muestra un cuadro gris
        img_vacia = Image.new('RGB', (120, 120), color=COLORS["bg_card"])
        return ctk.CTkImage(light_image=img_vacia, dark_image=img_vacia, size=(120, 120))

def cargar_logo(alto):
    """El logo de Neon OS (logo_app.png, ver preparar_logo.py) como imagen de `alto` píxeles de alto, con su proporción. None si falta
    el archivo: la app funciona igual, solo sin logo."""
    try:
        imagen = Image.open(rutas.recurso("logo_app.png")).convert("RGBA")
        return ctk.CTkImage(light_image=imagen, dark_image=imagen, size=(max(1, round(imagen.width * alto / imagen.height)), alto))
    except Exception:
        return None

# ==============================================================================
# 💅 VISTAS DE LA INTERFAZ
# ==============================================================================
class ViewAuth(ctk.CTkFrame):
    def __init__(self, master, db_manager, on_success_callback, **kwargs):
        super().__init__(master, fg_color=COLORS["bg_app"], **kwargs)
        self.db = db_manager; self.on_success = on_success_callback; self.is_login = True
        self.pendiente = None        # usuario cuya cuenta espera el código de verificación
        self.rol_pendiente = None    # su rol: decide qué pide la pantalla (profesor: código de profesor; administrador: contraseña nueva)
        self._ocupado = False        # hay un envío en curso: bloquea los dobles clics
        self._cancelando = False     # el campo de contraseña de «Cancelar registro» está a la vista
        self._espera_id = None       # temporizador de la cuenta atrás del reenvío

        self.card = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=20, width=400)
        self.card.place(relx=0.5, rely=0.5, anchor="center")
        logo = cargar_logo(110)
        self.lbl_logo = ctk.CTkLabel(self.card, text="", image=logo) if logo is not None else None
        if self.lbl_logo is not None: self.lbl_logo.pack(pady=(24, 0))
        self.lbl_title = ctk.CTkLabel(self.card, text="Acceso NeonOS", font=ctk.CTkFont(size=28, weight="bold"))
        self.lbl_title.pack(pady=(10 if logo is not None else 30, 10))
        self.lbl_error = ctk.CTkLabel(self.card, text="", text_color=COLORS["danger"], wraplength=320); self.lbl_error.pack(pady=(0, 10))

        self.rol_var = ctk.StringVar(value="Estudiante")
        self.sel_rol = ctk.CTkSegmentedButton(self.card, values=["Estudiante", "Profesor", "Administrador"], variable=self.rol_var, command=self.actualizar_vistas_rol, selected_color=COLORS["accent_2"])
        self.sel_rol.pack(pady=(0, 15), padx=20, fill="x")

        # FRAME LOGIN (Corregido distorsiones y anchos)
        self.frame_login = ctk.CTkFrame(self.card, fg_color="transparent")
        self.e_u_l = ctk.CTkEntry(self.frame_login, placeholder_text="Usuario", width=300, height=45, corner_radius=10); self.e_u_l.pack(pady=10)
        self.e_p_l = ctk.CTkEntry(self.frame_login, placeholder_text="Contraseña", show="*", width=300, height=45, corner_radius=10); self.e_p_l.pack(pady=10)
        self.btn_login = ctk.CTkButton(self.frame_login, text="Iniciar Sesión", height=45, width=300, corner_radius=10, fg_color=COLORS["accent_2"], command=self.procesar_login)
        self.btn_login.pack(pady=(20, 10))

        self.e_u_l.bind("<Return>", lambda e: self.procesar_login())
        self.e_p_l.bind("<Return>", lambda e: self.procesar_login())

        # FRAME REGISTRO (Corregido distorsiones y anchos)
        self.frame_register = ctk.CTkFrame(self.card, fg_color="transparent")
        self.e_u_r = ctk.CTkEntry(self.frame_register, placeholder_text="Nuevo Usuario", width=300, height=45, corner_radius=10); self.e_u_r.pack(pady=10)
        self.e_c_r = ctk.CTkEntry(self.frame_register, placeholder_text="Correo Electrónico", width=300, height=45, corner_radius=10); self.e_c_r.pack(pady=10)
        self.e_p_r = ctk.CTkEntry(self.frame_register, placeholder_text="Nueva Contraseña", show="*", width=300, height=45, corner_radius=10); self.e_p_r.pack(pady=10)
        self.combo_materia_reg = ctk.CTkComboBox(self.frame_register, values=["Matemáticas", "Física", "Química", "Sociales", "Ciencias", "Inglés"], width=300, height=45)
        self.lbl_aviso_profesor = ctk.CTkLabel(self.frame_register, text="Te enviaremos por correo tu código de verificación\ny tu código de profesor (único para ti).",
                                               wraplength=300, justify="center", text_color=COLORS["text_muted"])
        # Solo aparecen los grados que ya tienen contenido; al agregar otro grado en banco_grado11.py sale aquí solo.
        self.combo_grado_reg = ctk.CTkComboBox(self.frame_register, values=[juegos.etiqueta_grado(g) for g in juegos.GRADOS], width=300, height=45, state="readonly")
        self.combo_grado_reg.set(juegos.etiqueta_grado(juegos.GRADOS[-1]))
        self.btn_registrar = ctk.CTkButton(self.frame_register, text="Registrar Rol", height=45, width=300, corner_radius=10, fg_color=COLORS["success"], command=self.procesar_registro)
        self.btn_registrar.pack(pady=(20, 10))

        # FRAME VERIFICACIÓN DE CORREO (aparece tras registrarse o al entrar con una cuenta sin verificar)
        self.frame_verificar = ctk.CTkFrame(self.card, fg_color="transparent")
        self.lbl_correo = ctk.CTkLabel(self.frame_verificar, text="", wraplength=300, justify="center", text_color=COLORS["text_muted"]); self.lbl_correo.pack(pady=(0, 10))
        self.e_codigo = ctk.CTkEntry(self.frame_verificar, placeholder_text="Código de %d dígitos" % verificacion.LARGO, width=300, height=55, corner_radius=10,
                                     justify="center", font=ctk.CTkFont(size=24, weight="bold")); self.e_codigo.pack(pady=10)
        self.e_codigo.bind("<KeyRelease>", self._limpiar_codigo)
        self.e_codigo.bind("<Return>", lambda e: self.procesar_verificacion())
        # Solo profesores: el código de profesor (único, llega en el mismo correo). Solo administradores en su primer acceso: la contraseña nueva.
        self.e_codigo_profesor = ctk.CTkEntry(self.frame_verificar, placeholder_text="Código de profesor (XXXXX-XXXXX)", width=300, height=45, corner_radius=10,
                                              justify="center", font=ctk.CTkFont(size=18, weight="bold"))
        self.e_codigo_profesor.bind("<KeyRelease>", self._limpiar_codigo_profesor)
        self.e_codigo_profesor.bind("<Return>", lambda e: self.procesar_verificacion())
        self.e_clave_nueva = ctk.CTkEntry(self.frame_verificar, placeholder_text="Crea tu contraseña (mínimo %d caracteres)" % almacen.MIN_CLAVE_ADMIN,
                                          show="*", width=300, height=45, corner_radius=10)
        self.e_clave_nueva2 = ctk.CTkEntry(self.frame_verificar, placeholder_text="Repite la contraseña", show="*", width=300, height=45, corner_radius=10)
        self.e_clave_nueva2.bind("<Return>", lambda e: self.procesar_verificacion())
        self.btn_verificar = ctk.CTkButton(self.frame_verificar, text="Verificar", height=45, width=300, corner_radius=10, fg_color=COLORS["success"], command=self.procesar_verificacion)
        self.btn_verificar.pack(pady=(10, 5))
        self.lbl_espera = ctk.CTkLabel(self.frame_verificar, text="", text_color=COLORS["text_muted"]); self.lbl_espera.pack()
        self.btn_reenviar = ctk.CTkButton(self.frame_verificar, text="Reenviar código", height=36, width=300, corner_radius=10, fg_color=COLORS["accent_2"], command=self.reenviar)
        self.btn_reenviar.pack(pady=(0, 10))
        self.e_clave_cancelar = ctk.CTkEntry(self.frame_verificar, placeholder_text="Tu contraseña (para cancelar)", show="*", width=300, height=40, corner_radius=10)
        self.btn_cancelar = ctk.CTkButton(self.frame_verificar, text="Cancelar registro", height=36, width=300, corner_radius=10, fg_color="transparent", border_width=1, text_color=COLORS["danger"], hover_color=COLORS["bg_sidebar"], command=self.cancelar_registro)
        self.btn_cancelar.pack(pady=(0, 5))
        self.btn_volver = ctk.CTkButton(self.frame_verificar, text="Volver al inicio", height=30, width=300, fg_color="transparent", text_color=COLORS["text_muted"], hover_color=COLORS["bg_sidebar"], command=self.volver)
        self.btn_volver.pack(pady=(0, 10))

        self.btn_toggle = ctk.CTkButton(self.card, text="¿No tienes cuenta? Regístrate", fg_color="transparent", text_color=COLORS["text_muted"], hover_color=COLORS["bg_sidebar"], command=self.toggle_mode)
        self._poner_modo(True)

    def destroy(self):
        self._parar_espera()
        super().destroy()

    # ---------- navegación entre las pantallas de la tarjeta ----------
    def _mostrar(self, frame):
        for f in (self.frame_login, self.frame_register, self.frame_verificar): f.pack_forget()
        self.sel_rol.pack_forget(); self.btn_toggle.pack_forget()
        verificando = frame is self.frame_verificar
        # el logo solo va en el inicio de sesión: el registro y la verificación son pantallas más altas y con el logo no cabrían en la ventana
        if self.lbl_logo is not None:
            if frame is not self.frame_login: self.lbl_logo.pack_forget()
            elif self.lbl_logo.winfo_manager() != "pack": self.lbl_logo.pack(pady=(24, 0), before=self.lbl_title)
            self.lbl_title.pack_configure(pady=(10, 10) if frame is self.frame_login else (30, 10))
        if not verificando: self.sel_rol.pack(pady=(0, 15), padx=20, fill="x")
        frame.pack(fill="both", expand=True, padx=20, pady=(0, 25) if verificando else 0)
        if not verificando: self.btn_toggle.pack(pady=(10, 30))

    def _poner_modo(self, es_login):
        self.is_login = es_login
        self._mostrar(self.frame_login if es_login else self.frame_register)
        self.lbl_title.configure(text="Acceso NeonOS" if es_login else "Nuevo Registro")
        self.btn_toggle.configure(text="¿No tienes cuenta? Regístrate" if es_login else "¿Ya tienes cuenta? Inicia sesión")
        self.actualizar_vistas_rol(self.rol_var.get())

    def actualizar_vistas_rol(self, choice):
        self.e_u_l.configure(placeholder_text="Correo de administrador" if choice == "Administrador" else "Usuario")
        boton = self.frame_register.winfo_children()[-1]
        for w in (self.combo_materia_reg, self.lbl_aviso_profesor, self.combo_grado_reg): w.pack_forget()
        if self.is_login: return
        if choice == "Profesor":
            self.combo_materia_reg.pack(pady=10, before=boton)
            self.lbl_aviso_profesor.pack(pady=(0, 10), before=boton)
        elif choice == "Estudiante":
            self.combo_grado_reg.pack(pady=10, before=boton)

    def toggle_mode(self):
        if self._ocupado: return
        self.lbl_error.configure(text="")
        self._poner_modo(not self.is_login)

    def _vaciar(self, campo):
        """Vacía un campo SIN perder su texto de ayuda: CTkEntry.delete() sobre un campo vacío borra el texto de ayuda y lo deja en blanco."""
        if campo.get(): campo.delete(0, "end")

    def _mensaje(self, texto, tono="error"):
        color = {"error": COLORS["danger"], "ok": COLORS["success"], "info": COLORS["text_muted"]}[tono]
        self.lbl_error.configure(text=texto, text_color=color)

    # ---------- acceso ----------
    def procesar_login(self):
        if self._ocupado: return
        rol = self.rol_var.get()
        usuario = self.e_u_l.get().strip().lower()
        exito, msg_o_data = self.db.autenticar(usuario, self.e_p_l.get(), rol)
        if exito: self.on_success(usuario, msg_o_data)
        elif msg_o_data == MSG_NO_VERIFICADO: self.mostrar_verificacion(usuario, msg_o_data, "info")    # clave y rol correctos, falta el código
        elif msg_o_data == MSG_PRIMER_ACCESO: self.mostrar_verificacion(usuario)                       # la propia pantalla explica el primer acceso
        else: self._mensaje(msg_o_data)

    def procesar_registro(self):
        if self._ocupado: return
        rol = self.rol_var.get()
        materia = self.combo_materia_reg.get() if rol == "Profesor" else None
        grado = self.combo_grado_reg.get().replace("°", "").strip() if rol == "Estudiante" else None
        usuario, correo_electronico, clave = self.e_u_r.get().strip().lower(), self.e_c_r.get().strip(), self.e_p_r.get()

        def terminado(res, error):
            self._ocupar(False)
            if error is not None:
                self._mensaje("⚠️ Ocurrió un error inesperado. Inténtalo de nuevo.")
            elif res.ok:
                self._vaciar(self.e_p_r)                      # la contraseña no se queda escrita en el formulario
                self.mostrar_verificacion(usuario)
            else:
                self._mensaje(res.mensaje)

        self._ocupar(True)
        self._mensaje("⏳ Enviando el código a tu correo...", "info")
        ia_local.en_hilo(self, lambda: self.db.registrar_usuario(usuario, correo_electronico, clave, rol, materia, grado), terminado)

    # ---------- verificación de correo ----------
    def _ocupar(self, ocupado):
        """Bloquea los botones mientras se envía un correo (así un doble clic no manda dos códigos)."""
        self._ocupado = ocupado
        estado = "disabled" if ocupado else "normal"
        for boton in (self.btn_registrar, self.btn_verificar, self.btn_cancelar, self.btn_volver, self.btn_toggle, self.sel_rol, self.btn_login):
            boton.configure(state=estado)
        if ocupado: self.btn_reenviar.configure(state="disabled")
        elif self.pendiente: self._actualizar_espera()

    def _limpiar_codigo(self, _evento):
        """El código son solo dígitos, máximo 6: lo demás se descarta al escribir o pegar."""
        actual = self.e_codigo.get()
        limpio = "".join(c for c in actual if c in "0123456789")[:verificacion.LARGO]
        if limpio != actual:
            self.e_codigo.delete(0, "end"); self.e_codigo.insert(0, limpio)

    def _limpiar_codigo_profesor(self, _evento):
        """Formato XXXXX-XXXXX: mayúsculas, solo las letras y números que usa el código, y el guion se pone solo."""
        actual = self.e_codigo_profesor.get()
        letras = "".join(c for c in actual.upper() if c in verificacion.ALFABETO_PROFESOR)[:verificacion.LARGO_PROFESOR]
        limpio = letras if len(letras) <= 5 else f"{letras[:5]}-{letras[5:]}"
        if limpio != actual:
            self.e_codigo_profesor.delete(0, "end"); self.e_codigo_profesor.insert(0, limpio)

    def _campos_de_verificacion(self, rol):
        """Qué pide la pantalla según la cuenta: el profesor, además, su código de profesor; el administrador (primer acceso), su contraseña nueva."""
        for w in (self.e_codigo_profesor, self.e_clave_nueva, self.e_clave_nueva2, self.btn_cancelar): w.pack_forget()
        if rol == "Profesor":
            self.e_codigo_profesor.pack(pady=10, after=self.e_codigo)
        if rol == "Administrador":
            self.e_clave_nueva.pack(pady=10, after=self.e_codigo)
            self.e_clave_nueva2.pack(pady=10, after=self.e_clave_nueva)
        else:
            self.btn_cancelar.pack(pady=(0, 5), before=self.btn_volver)          # un administrador no puede cancelar su cuenta
        self.btn_verificar.configure(text="Activar cuenta" if rol == "Administrador" else "Verificar")
        self.btn_reenviar.configure(text="Enviar código" if rol == "Administrador" else "Reenviar código")

    def mostrar_verificacion(self, usuario, mensaje=None, tono="error"):
        self.pendiente = usuario
        self.rol_pendiente = rol = self.db.rol_de(usuario)
        self._vaciar(self.e_p_l)
        self._reiniciar_cancelacion()
        for campo in (self.e_codigo, self.e_codigo_profesor, self.e_clave_nueva, self.e_clave_nueva2): self._vaciar(campo)
        correo_ = self.db.correo_de(usuario) or "tu correo"
        if rol == "Administrador":
            texto = (f"Primer acceso de administrador.\nPulsa «Enviar código»: te mandaremos un código de {verificacion.LARGO} dígitos a {correo_}."
                     "\nEscríbelo aquí y crea tu contraseña.")
        elif rol == "Profesor":
            texto = f"Enviamos un código de {verificacion.LARGO} dígitos y tu código de profesor a {correo_}.\nEscribe los dos para activar tu cuenta."
        else:
            texto = f"Enviamos un código de {verificacion.LARGO} dígitos a {correo_}.\nEscríbelo para activar tu cuenta."
        if self.db.modo_desarrollo(): texto += "\n(modo desarrollo: el código está en la consola)"
        self.lbl_correo.configure(text=texto)
        self.lbl_title.configure(text="Activa tu cuenta" if rol == "Administrador" else "Verifica tu correo")
        self._mostrar(self.frame_verificar)
        self._campos_de_verificacion(rol)
        if mensaje: self._mensaje(mensaje, tono)
        else: self.lbl_error.configure(text="")
        self._actualizar_espera()
        if rol != "Administrador": self.e_codigo.focus_set()     # el administrador primero pide el código: su campo se queda con la ayuda a la vista

    def _parar_espera(self):
        if self._espera_id is not None:
            try: self.after_cancel(self._espera_id)
            except Exception: pass
            self._espera_id = None

    def _actualizar_espera(self):
        """Cuenta atrás de 60 s para poder reenviar el código."""
        self._parar_espera()
        if not self.pendiente: return
        try:
            segundos = self.db.segundos_para_reenviar(self.pendiente)
        except Exception:
            self._espera_id = self.after(1000, self._actualizar_espera)       # base ocupada: se reintenta en un segundo
            return
        if segundos > 0:
            self.lbl_espera.configure(text=f"Puedes reenviar el código en {segundos} s")
            self.btn_reenviar.configure(state="disabled")
            self._espera_id = self.after(1000, self._actualizar_espera)
        else:
            self.lbl_espera.configure(text="")
            self.btn_reenviar.configure(state="disabled" if self._ocupado else "normal")

    def procesar_verificacion(self):
        if self._ocupado or not self.pendiente: return
        usuario = self.pendiente
        codigo = self.e_codigo.get().strip()
        if not codigo:
            self.e_codigo.focus_set()
            if not self.lbl_error.cget("text"): self._mensaje(verificacion.MENSAJES["formato"], "info")
            return
        rol = self.rol_pendiente
        clave_nueva = None
        if rol == "Administrador":
            clave_nueva = self.e_clave_nueva.get()
            if clave_nueva != self.e_clave_nueva2.get():
                self._mensaje("Las contraseñas no coinciden.")
                return
        res = self.db.verificar_codigo(usuario, codigo, self.e_codigo_profesor.get() if rol == "Profesor" else None, clave_nueva)
        if res.ok:
            self._terminar_verificacion()
            self.e_u_l.delete(0, "end"); self.e_u_l.insert(0, usuario)
            self._vaciar(self.e_p_l)
            self._poner_modo(True)
            self._mensaje(res.mensaje, "ok")
            return
        if res.codigo in ("formato_profesor", "clave_corta"):    # no se gastó ningún intento: se conserva lo escrito
            self._mensaje(res.mensaje)
            return
        self._vaciar(self.e_codigo); self._vaciar(self.e_codigo_profesor)
        if res.codigo == "no_existe":                          # la cuenta pendiente se limpió (pasó más de un día)
            self._terminar_verificacion(); self._poner_modo(False)
        elif res.codigo == "ya_verificada":
            self._terminar_verificacion(); self.e_u_l.delete(0, "end"); self.e_u_l.insert(0, usuario); self._poner_modo(True)
        self._mensaje(res.mensaje)

    def reenviar(self):
        if self._ocupado or not self.pendiente: return
        usuario = self.pendiente

        def terminado(res, error):
            self._ocupar(False)
            if self.pendiente != usuario: return                # el usuario ya salió de esta pantalla
            if error is not None: self._mensaje("⚠️ Ocurrió un error inesperado. Inténtalo de nuevo.")
            else: self._mensaje(res.mensaje, "ok" if res.ok else "error")
            self._actualizar_espera()

        self._ocupar(True)
        self._mensaje("⏳ Enviando un código nuevo...", "info")
        ia_local.en_hilo(self, lambda: self.db.reenviar_codigo(usuario), terminado)

    def _reiniciar_cancelacion(self):
        self._cancelando = False
        self._vaciar(self.e_clave_cancelar); self.e_clave_cancelar.pack_forget()
        self.btn_cancelar.configure(text="Cancelar registro")

    def cancelar_registro(self):
        """Dos pasos: primero pide la contraseña de la cuenta y luego la borra, para que nadie cancele el registro de otra persona."""
        if self._ocupado or not self.pendiente or self.rol_pendiente == "Administrador": return
        if not self._cancelando:
            self._cancelando = True
            self.e_clave_cancelar.pack(pady=(0, 5), before=self.btn_cancelar)
            self.btn_cancelar.configure(text="Confirmar cancelación")
            self._mensaje("Escribe tu contraseña y confirma para cancelar el registro.", "info")
            self.e_clave_cancelar.focus_set()
            return
        res = self.db.cancelar_registro(self.pendiente, self.e_clave_cancelar.get())
        if not res.ok:
            self._mensaje(res.mensaje)
            return
        self._terminar_verificacion()
        self._poner_modo(False)
        self._mensaje(res.mensaje, "ok")

    def volver(self):
        """Sale de la verificación SIN borrar la cuenta: queda pendiente y se retoma al iniciar sesión."""
        if self._ocupado: return
        usuario = self.pendiente
        self._terminar_verificacion()
        if usuario: self.e_u_l.delete(0, "end"); self.e_u_l.insert(0, usuario)
        self._poner_modo(True)
        self.lbl_error.configure(text="")

    def _terminar_verificacion(self):
        self.pendiente = None
        self._parar_espera()
        self._reiniciar_cancelacion()
        self.rol_pendiente = None
        for campo in (self.e_codigo, self.e_codigo_profesor, self.e_clave_nueva, self.e_clave_nueva2): self._vaciar(campo)
        self.lbl_espera.configure(text="")

# ----------------- VISTAS DE ESTUDIANTE -----------------
class ViewEstudianteTablero(ctk.CTkFrame):
    def __init__(self, master, boveda_core, update_hud_callback, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.boveda = boveda_core; self.update_hud = update_hud_callback
        self.grid_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.grid_frame.pack(fill="both", expand=True)
        self.detalle_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.construir_grid()

    def misiones_visibles(self, materia):
        """Solo las misiones del grado del estudiante (las sin grado se muestran a todos)."""
        return [m for m in MISIONES_GLOBALES[materia] if m.get("grado") in (None, self.boveda.grado)]

    def construir_grid(self):
        for w in self.grid_frame.winfo_children(): w.destroy()
        header = ctk.CTkFrame(self.grid_frame, fg_color=COLORS["bg_card"], corner_radius=15)
        header.pack(fill="x", padx=10, pady=(0, 20))
        ctk.CTkLabel(header, text="🎓 Mis Materias", font=ctk.CTkFont(size=24, weight="bold"), text_color=COLORS["accent_1"]).pack(anchor="w", padx=20, pady=(15, 0))
        
        container = ctk.CTkFrame(self.grid_frame, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20)
        
        container.grid_columnconfigure(0, weight=1); container.grid_columnconfigure(1, weight=1); container.grid_columnconfigure(2, weight=1)
        container.grid_rowconfigure(0, weight=1); container.grid_rowconfigure(1, weight=1)
        
        materias = [("Matemáticas", 0, 0), ("Física", 0, 1), ("Química", 0, 2), ("Sociales", 1, 0), ("Ciencias", 1, 1), ("Inglés", 1, 2)]
        for mat, r, c in materias:
            tiene_mision = len(self.misiones_visibles(mat)) > 0
            color_mat = COLORS.get(f"mat_{mat.lower()}", COLORS["text_main"])
            
            if tiene_mision:
                color_fondo, color_texto, texto_extra = COLORS["danger"], "#ffffff", "\n⚠️ ¡Misión Pendiente!"
            else:
                color_fondo = color_mat
                color_texto = "#ffffff"
                texto_extra = "\nZona Limpia"
            
            btn = ctk.CTkButton(container, text=f"{mat}{texto_extra}", font=ctk.CTkFont(size=22, weight="bold"), fg_color=color_fondo, text_color=color_texto, corner_radius=15, height=120, command=lambda m=mat: self.abrir_materia(m))
            btn.grid(row=r, column=c, padx=10, pady=10, sticky="nsew")

    def abrir_materia(self, materia):
        self.grid_frame.pack_forget(); self.detalle_frame.pack(fill="both", expand=True)
        for w in self.detalle_frame.winfo_children(): w.destroy()

        color_tema = COLORS.get(f"mat_{materia.lower()}", COLORS["success"])
        header = ctk.CTkFrame(self.detalle_frame, fg_color=color_tema, corner_radius=15); header.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkLabel(header, text=f"Laboratorio: {materia}", font=ctk.CTkFont(size=24, weight="bold"), text_color="#ffffff").pack(side="left", padx=20, pady=15)
        ctk.CTkButton(header, text="⬅ Volver", fg_color=COLORS["bg_app"], text_color="#ffffff", command=self.volver_grid).pack(side="right", padx=20)

        content_frame = ctk.CTkFrame(self.detalle_frame, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=10, pady=(0, 5))
        content_frame.grid_columnconfigure((0, 1, 2), weight=1, uniform="col")
        content_frame.grid_rowconfigure((0, 1), weight=1, uniform="fila")

        # Fila 1: Tareas | Opinión | Presentación libre
        col_tareas = ctk.CTkScrollableFrame(content_frame, fg_color=COLORS["bg_app"])
        col_tareas.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        ctk.CTkLabel(col_tareas, text="📝 Tareas (Archivos)", font=ctk.CTkFont(size=20, weight="bold"), text_color=COLORS["danger"]).pack(pady=10)

        col_preg = ctk.CTkScrollableFrame(content_frame, fg_color=COLORS["bg_app"])
        col_preg.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        ctk.CTkLabel(col_preg, text="💬 Columna de Opinión", font=ctk.CTkFont(size=20, weight="bold"), text_color=COLORS["accent_1"]).pack(pady=10)

        col_libres = ctk.CTkFrame(content_frame, fg_color=COLORS["bg_card"], corner_radius=10)
        col_libres.grid(row=0, column=2, sticky="nsew", padx=5, pady=5)
        ctk.CTkLabel(col_libres, text="📂 Presentación Libre", font=ctk.CTkFont(size=20, weight="bold"), text_color=color_tema).pack(pady=(14, 6))
        ctk.CTkLabel(col_libres, text="Sube apuntes para ganar\npuntos pasivos (15🪙 | 3💎)", font=ctk.CTkFont(size=14)).pack()
        e_con = ctk.CTkEntry(col_libres, placeholder_text="Concepto clave...", width=220, height=36)
        e_con.pack(pady=10)
        ctk.CTkButton(col_libres, text="Subir y Ganar Puntos", fg_color=color_tema, command=lambda: self.auditar_libre(materia, e_con)).pack(pady=4)

        # Fila 2: Juegos | Tutor IA
        col_juegos = ctk.CTkScrollableFrame(content_frame, fg_color=COLORS["bg_app"])
        col_juegos.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        ctk.CTkLabel(col_juegos, text="🎮 Juegos", font=ctk.CTkFont(size=20, weight="bold"), text_color=COLORS["success"]).pack(pady=10)

        col_ia = ctk.CTkFrame(content_frame, fg_color=COLORS["bg_card"], corner_radius=10)
        col_ia.grid(row=1, column=1, columnspan=2, sticky="nsew", padx=5, pady=5)
        self.construir_ia(col_ia, materia, color_tema)

        misiones = self.misiones_visibles(materia)
        m_juegos = [m for m in misiones if "[Juego]" in m['titulo']]
        m_tareas = [m for m in misiones if "[Pregunta]" not in m['titulo'] and "[Juego]" not in m['titulo']]
        m_preguntas = [m for m in misiones if "[Pregunta]" in m['titulo']]

        if m_tareas:
            for m in m_tareas:
                card = ctk.CTkFrame(col_tareas, fg_color="#451a1a", border_width=2, border_color=COLORS["danger"], corner_radius=10)
                card.pack(fill="x", pady=10, padx=10)
                ctk.CTkLabel(card, text=m['titulo'], font=ctk.CTkFont(size=14, weight="bold"), wraplength=200).pack(pady=5)
                ctk.CTkLabel(card, text=f"Drop: {m['monedas']}🪙 | {m['diamantes']}💎", font=ctk.CTkFont(weight="bold"), text_color=COLORS["warning"]).pack(pady=5)
                ctk.CTkButton(card, text="Subir Archivo 📂", fg_color=COLORS["danger"], command=lambda t=m: self.auditar_oficial(materia, t)).pack(pady=10)
        else:
            ctk.CTkLabel(col_tareas, text="Sin tareas por ahora.").pack(pady=30)

        if m_juegos:
            for m in m_juegos:
                card = ctk.CTkFrame(col_juegos, fg_color=COLORS["bg_sidebar"], border_width=2, border_color=COLORS["success"], corner_radius=10)
                card.pack(fill="x", pady=8, padx=10)
                ctk.CTkLabel(card, text=m['titulo'].replace("[Juego] - ", ""), font=ctk.CTkFont(size=14, weight="bold"), wraplength=200).pack(pady=(8, 2))
                if m.get("juego_id") in juegos.TIPOS:
                    info = juegos.info_tipo(m["juego_id"])
                    extra = " · ✏️ adaptado por tu profe" if m.get("banco") else ""
                    ctk.CTkLabel(card, text=f"{info['icono']} {info['nombre']}\nTema: {m.get('tema', '')}{extra}", text_color=COLORS["text_muted"], wraplength=200, font=ctk.CTkFont(size=12)).pack()
                ctk.CTkLabel(card, text=f"Drop: {m['monedas']}🪙 | {m['diamantes']}💎", font=ctk.CTkFont(weight="bold"), text_color=COLORS["warning"]).pack(pady=4)
                if self.clave_juego(materia, m) in self.boveda.juegos_reclamados:
                    ctk.CTkButton(card, text="Completado ✅", state="disabled", fg_color=COLORS["success"]).pack(pady=(2, 10))
                else:
                    ctk.CTkButton(card, text="Jugar 🎮", fg_color=COLORS["accent_1"], text_color="#000000", command=lambda t=m, mat=materia: self.jugar_y_reclamar(mat, t)).pack(pady=(2, 10))
        else:
            ctk.CTkLabel(col_juegos, text="Sin juegos por ahora.").pack(pady=30)

        if m_preguntas:
            for m in m_preguntas:
                card = ctk.CTkFrame(col_preg, fg_color=COLORS["bg_sidebar"], border_width=2, border_color=COLORS["accent_1"], corner_radius=10)
                card.pack(fill="x", pady=10, padx=10)
                ctk.CTkLabel(card, text=m['titulo'], font=ctk.CTkFont(size=14, weight="bold"), wraplength=200).pack(pady=5)
                ctk.CTkLabel(card, text=f"Premio: {m['monedas']}🪙 | {m['diamantes']}💎", text_color=COLORS["warning"]).pack(pady=5)
                e_ans = ctk.CTkEntry(card, placeholder_text="Tu respuesta...", width=200)
                e_ans.pack(pady=5)
                ctk.CTkButton(card, text="Responder 💬", fg_color=COLORS["accent_1"], text_color="#000000", command=lambda t=m, e=e_ans: self.responder_pregunta(materia, t, e)).pack(pady=10)
        else:
            ctk.CTkLabel(col_preg, text="Sin preguntas hoy.").pack(pady=30)

        self.lbl_log = ctk.CTkLabel(self.detalle_frame, text="", font=ctk.CTkFont(size=15, weight="bold"))
        self.lbl_log.pack(pady=4)

    # ---- Tutor IA (local) ----
    def clave_juego(self, materia, m):
        return f"{materia}#{m.get('id', m['titulo'])}"

    def construir_ia(self, parent, materia, color):
        ctk.CTkLabel(parent, text="🤖 Tutor IA", font=ctk.CTkFont(size=20, weight="bold"), text_color=color).pack(anchor="w", padx=15, pady=(10, 0))
        self.lbl_modo_ia = ctk.CTkLabel(parent, text=ia_local.estado_texto(), font=ctk.CTkFont(size=12), text_color=COLORS["text_muted"])
        self.lbl_modo_ia.pack(anchor="w", padx=15)
        self.chat_ia = ctk.CTkTextbox(parent, wrap="word", fg_color=COLORS["bg_app"], height=110, state="disabled")
        self.chat_ia.pack(fill="both", expand=True, padx=15, pady=8)
        self.historial_ia = []
        self.chat_agregar("🤖", f"¡Hola! Soy tu tutor de {materia}. Pregúntame lo que no hayas entendido de clase.")
        fila = ctk.CTkFrame(parent, fg_color="transparent"); fila.pack(fill="x", padx=15, pady=(0, 12))
        entrada = ctk.CTkEntry(fila, placeholder_text="Escribe tu duda de la clase...", height=38)
        entrada.pack(side="left", fill="x", expand=True)
        boton = ctk.CTkButton(fila, text="Preguntar", width=110, height=38, fg_color=color, command=lambda: self.preguntar_ia(materia, entrada, boton, parent))
        boton.pack(side="right", padx=(8, 0))
        entrada.bind("<Return>", lambda e: self.preguntar_ia(materia, entrada, boton, parent))

    def chat_agregar(self, quien, texto):
        self.chat_ia.configure(state="normal")
        self.chat_ia.insert("end", f"{quien}  {texto}\n\n")
        self.chat_ia.see("end")
        self.chat_ia.configure(state="disabled")

    def preguntar_ia(self, materia, entrada, boton, parent):
        pregunta = entrada.get().strip()
        if not pregunta or str(boton.cget("state")) == "disabled": return
        entrada.delete(0, 'end'); self.chat_agregar("🧑", pregunta)
        boton.configure(state="disabled", text="Pensando…")
        historial = list(self.historial_ia)
        grado = self.boveda.grado or juegos.GRADOS[-1]
        bancos = juegos.BANCOS.get(grado, {}).get(materia, {})

        def listo(respuesta, error):
            try:
                if error: respuesta = "⚠️ No pude responder ahora mismo. Intenta de nuevo."
                self.historial_ia += [("user", pregunta), ("assistant", respuesta)]
                self.chat_agregar("🤖", respuesta)
                boton.configure(state="normal", text="Preguntar")
                self.lbl_modo_ia.configure(text=ia_local.estado_texto())
            except tk.TclError:
                pass
        ia_local.en_hilo(parent, lambda: ia_local.responder_tutor(pregunta, materia, grado, historial, bancos), listo)

    def volver_grid(self):
        self.detalle_frame.pack_forget(); self.construir_grid(); self.grid_frame.pack(fill="both", expand=True)

    def auditar_oficial(self, materia, tarea_dict):
        ruta = filedialog.askopenfilename()
        if ruta:
            exito, msg = self.boveda.procesar_archivo_estricto(ruta, materia, self.boveda.diccionario_materias[materia][0], True, tarea_dict["monedas"], tarea_dict["diamantes"])
            self.lbl_log.configure(text=msg, text_color=COLORS["success"] if exito else COLORS["danger"]); self.update_hud()

    def auditar_libre(self, materia, entry_widget):
        concepto = entry_widget.get().strip()
        if not concepto: return
        ruta = filedialog.askopenfilename()
        if ruta:
            exito, msg = self.boveda.procesar_archivo_estricto(ruta, materia, concepto, False, 15, 3)
            self.lbl_log.configure(text=msg, text_color=COLORS["success"] if exito else COLORS["danger"])
            entry_widget.delete(0, 'end'); self.update_hud()

    def responder_pregunta(self, materia, tarea_dict, entry_widget):
        ans = entry_widget.get().strip()
        if len(ans) > 5:
            m_ganadas = int(tarea_dict["monedas"])
            d_ganados = int(tarea_dict["diamantes"])
            self.boveda.ganar(m_ganadas, d_ganados)
            self.lbl_log.configure(text=f"✅ Opinión enviada. \n💎 Drop: +{m_ganadas} 🪙 | +{d_ganados} 💎", text_color=COLORS["success"])
            entry_widget.delete(0, 'end')
            self.update_hud()
        else:
            self.lbl_log.configure(text="⚠️ Escribe una opinión más completa.", text_color=COLORS["warning"])

    def jugar_y_reclamar(self, materia, tarea_dict):
        color = COLORS.get(f"mat_{materia.lower()}", COLORS["accent_2"])
        ventana = juegos.lanzar_juego(self.winfo_toplevel(), tarea_dict.get("grado") or self.boveda.grado, materia, tarea_dict.get("tema"),
                                      tarea_dict.get("juego_id"), color, lambda fraccion: self.finalizar_juego(materia, tarea_dict, fraccion),
                                      banco=tarea_dict.get("banco"))
        if ventana is None:
            self.lbl_log.configure(text="⚠️ Este juego ya no está disponible.", text_color=COLORS["warning"])

    def finalizar_juego(self, materia, tarea_dict, fraccion):
        """La recompensa es proporcional al puntaje; se cobra una sola vez por misión."""
        try:
            if fraccion <= 0:
                self.lbl_log.configure(text="🎮 Sin puntos esta vez. Puedes intentarlo de nuevo.", text_color=COLORS["warning"])
                return
            m_ganadas = round(int(tarea_dict["monedas"]) * fraccion)
            d_ganados = round(int(tarea_dict["diamantes"]) * fraccion)
            self.boveda.ganar(m_ganadas, d_ganados)
            self.boveda.juegos_reclamados.add(self.clave_juego(materia, tarea_dict))
            self.update_hud()
            self.abrir_materia(materia)  # refresca la tarjeta como "Completado"
            self.lbl_log.configure(text=f"🎮 ¡Juego completado ({round(fraccion * 100)}%)! \n💎 Drop: +{m_ganadas} 🪙 | +{d_ganados} 💎", text_color=COLORS["success"])
        except tk.TclError:
            pass  # la vista ya se cerró (cierre de sesión)

# ----------------- VISTA: ADMIN -----------------
class ViewAdminMonitor(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        header = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=15); header.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkLabel(header, text="👁️ Monitoreo Global (6 Cuadros)", font=ctk.CTkFont(size=24, weight="bold"), text_color="#a855f7").pack(anchor="w", padx=20, pady=15)
        self.grid_frame = ctk.CTkFrame(self, fg_color="transparent"); self.grid_frame.pack(fill="both", expand=True)
        self.construir_grid()

    def construir_grid(self):
        for w in self.grid_frame.winfo_children(): w.destroy()
        container = ctk.CTkFrame(self.grid_frame, fg_color="transparent"); container.pack(fill="both", expand=True, padx=20)
        
        container.grid_columnconfigure(0, weight=1); container.grid_columnconfigure(1, weight=1); container.grid_columnconfigure(2, weight=1)
        container.grid_rowconfigure(0, weight=1); container.grid_rowconfigure(1, weight=1)
        
        materias = [("Matemáticas", 0, 0), ("Física", 0, 1), ("Química", 0, 2), ("Sociales", 1, 0), ("Ciencias", 1, 1), ("Inglés", 1, 2)]
        for mat, r, c in materias:
            num = len(MISIONES_GLOBALES[mat])
            color_mat = COLORS.get(f"mat_{mat.lower()}", COLORS["text_main"])
            ctk.CTkButton(container, text=f"{mat}\n{num} Misiones", font=ctk.CTkFont(size=20, weight="bold"), fg_color=COLORS["bg_card"], text_color=color_mat, corner_radius=15, height=120, state="disabled").grid(row=r, column=c, padx=10, pady=10, sticky="nsew")
        ctk.CTkButton(self.grid_frame, text="Actualizar Red", fg_color="#a855f7", command=self.construir_grid).pack(pady=10)

# ----------------- VISTA: PROFESOR -----------------
class ViewProfesor(ctk.CTkScrollableFrame):
    def __init__(self, master, materia, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.materia = materia; color_tema = COLORS.get(f"mat_{materia.lower()}", COLORS["success"])
        header = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=15); header.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkLabel(header, text=f"🧙‍♂️ Panel de Profesor: {self.materia}", font=ctk.CTkFont(size=24, weight="bold"), text_color=color_tema).pack(anchor="w", padx=20, pady=(15, 0))
        
        self.grid_acciones = ctk.CTkFrame(self, fg_color="transparent"); self.grid_acciones.pack(fill="x", padx=10, pady=10)
        self.grid_acciones.grid_columnconfigure(0, weight=1); self.grid_acciones.grid_columnconfigure(1, weight=1)
        
        acciones = [("[Tarea] Subir Archivo", 0, 0), ("[Pregunta] Opinión/Foro", 0, 1), ("[Quiz] Prueba", 1, 0), ("[Juego] Menú de Juegos 🎮", 1, 1)]
        for texto, r, c in acciones:
            ctk.CTkButton(self.grid_acciones, text=texto, font=ctk.CTkFont(size=18, weight="bold"), fg_color=COLORS["bg_card"], text_color=color_tema, height=80, corner_radius=15, command=lambda t=texto: self.preparar_form(t)).grid(row=r, column=c, padx=10, pady=10, sticky="nsew")

        self.zona_menu = ctk.CTkFrame(self, fg_color="transparent"); self.zona_menu.pack(fill="x", padx=10)
        self.juego_sel = None; self.tarjetas_juego = {}; self.tema_sel = None; self.banco_base = self.banco_edit = None
        self.f_crear = ctk.CTkFrame(self, fg_color=COLORS["bg_app"], corner_radius=15)
        self.lbl_tipo = ctk.CTkLabel(self.f_crear, text="", font=ctk.CTkFont(size=20, weight="bold")); self.lbl_tipo.pack(pady=10)
        self.e_t = ctk.CTkEntry(self.f_crear, placeholder_text="Título", width=400, height=40); self.e_t.pack(pady=5)
        self.e_m = ctk.CTkEntry(self.f_crear, placeholder_text="Monedas (Ej: 50000)", width=400, height=40); self.e_m.pack(pady=5)
        self.e_d = ctk.CTkEntry(self.f_crear, placeholder_text="Diamantes (Ej: 5)", width=400, height=40); self.e_d.pack(pady=5)
        self.lbl_log = ctk.CTkLabel(self.f_crear, text=""); ctk.CTkButton(self.f_crear, text="Publicar Misión", fg_color=color_tema, command=self.publicar_mision).pack(pady=10); self.lbl_log.pack()
        self.tipo_actual = ""

    def preparar_form(self, tipo):
        for w in self.zona_menu.winfo_children(): w.destroy()
        self.juego_sel = None; self.tarjetas_juego = {}; self.tema_sel = None
        self.lbl_log.configure(text="")
        if tipo.startswith("[Juego]"):
            self.tipo_actual = "[Juego]"; self.lbl_tipo.configure(text="Nueva: [Juego] — elige grado y tema")
            self.construir_selector_tema()
        else:
            self.tipo_actual = tipo; self.lbl_tipo.configure(text=f"Nueva: {tipo}")
        self.f_crear.pack(fill="both", expand=True, padx=10, pady=10)

    def construir_selector_tema(self):
        """Paso 1 del juego: el profesor elige el grado y el TEMA; recién ahí aparecen los 8 juegos de ese tema."""
        color_tema = COLORS.get(f"mat_{self.materia.lower()}", COLORS["success"])
        ctk.CTkLabel(self.zona_menu, text=f"🎮 Juego de {self.materia}: ¿de qué tema?", font=ctk.CTkFont(size=20, weight="bold"), text_color=color_tema).pack(anchor="w", padx=10, pady=(10, 5))
        fila = ctk.CTkFrame(self.zona_menu, fg_color="transparent"); fila.pack(fill="x", padx=10)
        self.combo_grado = ctk.CTkComboBox(fila, values=[juegos.etiqueta_grado(g) for g in juegos.GRADOS], width=110, height=40, state="readonly", command=lambda _: self.cambiar_grado())
        self.combo_grado.set(juegos.etiqueta_grado(juegos.GRADOS[-1])); self.combo_grado.pack(side="left", padx=(0, 10))
        self.combo_tema = ctk.CTkComboBox(fila, values=[], width=420, height=40, state="readonly", command=self.elegir_tema)
        self.combo_tema.pack(side="left")
        self.zona_cards = ctk.CTkFrame(self.zona_menu, fg_color="transparent"); self.zona_cards.pack(fill="x")
        self.cambiar_grado()

    def grado_actual(self):
        return self.combo_grado.get().replace("°", "").strip()

    def cambiar_grado(self):
        temas = juegos.temas_de(self.grado_actual(), self.materia)
        self.combo_tema.configure(values=temas); self.combo_tema.set("Selecciona un tema…")
        self.tema_sel = None; self.juego_sel = None
        for w in self.zona_cards.winfo_children(): w.destroy()

    def elegir_tema(self, tema):
        self.tema_sel = tema; self.juego_sel = None; self.tarjetas_juego = {}
        self.banco_base = json.loads(json.dumps(juegos.BANCOS[self.grado_actual()][self.materia][tema]))
        self.banco_edit = copy.deepcopy(self.banco_base)
        for w in self.zona_cards.winfo_children(): w.destroy()
        color_tema = COLORS.get(f"mat_{self.materia.lower()}", COLORS["success"])
        ctk.CTkLabel(self.zona_cards, text=f"Juegos sobre «{tema}»", font=ctk.CTkFont(size=16, weight="bold"), text_color=COLORS["text_muted"]).pack(anchor="w", padx=10, pady=(12, 2))
        grid = ctk.CTkFrame(self.zona_cards, fg_color="transparent"); grid.pack(fill="x")
        for c in range(4): grid.grid_columnconfigure(c, weight=1, uniform="juego")
        for n, j in enumerate(juegos.juegos_de(tema)):
            card = ctk.CTkFrame(grid, fg_color=COLORS["bg_card"], corner_radius=12, border_width=2, border_color=COLORS["bg_card"])
            card.grid(row=n // 4, column=n % 4, padx=5, pady=5, sticky="nsew")
            ctk.CTkLabel(card, text=j["icono"], font=ctk.CTkFont(size=30)).pack(pady=(8, 0))
            ctk.CTkLabel(card, text=juegos.info_tipo(j["id"])["nombre"], font=ctk.CTkFont(size=13, weight="bold"), wraplength=140).pack(padx=6)
            ctk.CTkLabel(card, text=j["desc"], font=ctk.CTkFont(size=11), text_color=COLORS["text_muted"], wraplength=140).pack(padx=6, pady=3)
            f = ctk.CTkFrame(card, fg_color="transparent"); f.pack(pady=(2, 8))
            ctk.CTkButton(f, text="Elegir", width=58, height=28, fg_color=color_tema, command=lambda i=j["id"]: self.elegir_juego(i)).pack(side="left", padx=2)
            ctk.CTkButton(f, text="Probar", width=58, height=28, fg_color=COLORS["bg_sidebar"],
                          command=lambda i=j["id"]: juegos.lanzar_juego(self.winfo_toplevel(), self.grado_actual(), self.materia, self.tema_sel, i, color_tema, lambda fr: None, banco=self.banco_edit)).pack(side="left", padx=2)
            self.tarjetas_juego[j["id"]] = card
        self.construir_panel_ia(color_tema)
        self.lbl_tipo.configure(text=f"Nueva: [Juego] — tema «{tema}»: elige uno")

    # ---- Personalizar el juego con IA local ----
    def construir_panel_ia(self, color_tema):
        panel = ctk.CTkFrame(self.zona_cards, fg_color=COLORS["bg_card"], corner_radius=12)
        panel.pack(fill="x", padx=5, pady=(12, 4))
        fila_t = ctk.CTkFrame(panel, fg_color="transparent"); fila_t.pack(fill="x", padx=12, pady=(10, 0))
        ctk.CTkLabel(fila_t, text="🤖 Personalizar este juego con IA", font=ctk.CTkFont(size=16, weight="bold"), text_color=color_tema).pack(side="left")
        ctk.CTkButton(fila_t, text="Ver contenido", width=110, height=28, fg_color=COLORS["bg_sidebar"], command=self.ver_contenido).pack(side="right")
        ctk.CTkButton(fila_t, text="Restablecer", width=100, height=28, fg_color=COLORS["bg_sidebar"], command=self.restablecer_banco).pack(side="right", padx=6)
        self.lbl_modo_prof = ctk.CTkLabel(panel, text=ia_local.estado_texto(), font=ctk.CTkFont(size=12), text_color=COLORS["text_muted"])
        self.lbl_modo_prof.pack(anchor="w", padx=12)
        self.chat_prof = ctk.CTkTextbox(panel, wrap="word", height=100, fg_color=COLORS["bg_app"], state="disabled")
        self.chat_prof.pack(fill="x", padx=12, pady=6)
        fila = ctk.CTkFrame(panel, fg_color="transparent"); fila.pack(fill="x", padx=12, pady=(0, 10))
        self.e_ia = ctk.CTkEntry(fila, placeholder_text="Ej: quita la palabra enzima  ·  agrega una pregunta sobre ...", height=36)
        self.e_ia.pack(side="left", fill="x", expand=True)
        self.btn_ia = ctk.CTkButton(fila, text="Aplicar", width=90, height=36, fg_color=color_tema, command=self.aplicar_ia)
        self.btn_ia.pack(side="right", padx=(8, 0))
        self.e_ia.bind("<Return>", lambda e: self.aplicar_ia())
        self.log_prof("🤖", "Este juego es la base: dime qué quitar, cambiar o agregar y lo adapto a lo que vieron tus estudiantes. "
                            "Los cambios solo afectan al juego que publiques ahora. Usa «Ver contenido» para ver qué trae.")

    def log_prof(self, quien, texto):
        self.chat_prof.configure(state="normal")
        self.chat_prof.insert("end", f"{quien}  {texto}\n\n")
        self.chat_prof.see("end")
        self.chat_prof.configure(state="disabled")

    def aplicar_ia(self):
        instruccion = self.e_ia.get().strip()
        if not instruccion or str(self.btn_ia.cget("state")) == "disabled": return
        self.e_ia.delete(0, 'end'); self.log_prof("🧑", instruccion)
        self.btn_ia.configure(state="disabled", text="Pensando…")
        tema, grado, banco = self.tema_sel, self.grado_actual(), copy.deepcopy(self.banco_edit)

        def listo(res, error):
            try:
                self.btn_ia.configure(state="normal", text="Aplicar")
                if error:
                    self.log_prof("⚠️", "No pude aplicar el cambio. Intenta de nuevo."); return
                nuevo, informes, _modo = res
                if tema == self.tema_sel:
                    self.banco_edit = nuevo
                self.log_prof("🤖", "\n".join(informes) if informes else "No hice cambios.")
                self.lbl_modo_prof.configure(text=ia_local.estado_texto())
            except tk.TclError:
                pass
        ia_local.en_hilo(self.zona_cards, lambda: ia_local.editar_banco(banco, instruccion, self.materia, tema, grado), listo)

    def restablecer_banco(self):
        self.banco_edit = copy.deepcopy(self.banco_base)
        self.log_prof("🤖", "Listo: volvió al contenido original del tema.")

    def ver_contenido(self):
        ventana = ctk.CTkToplevel(self); ventana.title(f"Contenido del juego · {self.tema_sel}"); ventana.geometry("760x620"); rutas.poner_icono(ventana)
        ventana.configure(fg_color=COLORS["bg_app"])
        caja = ctk.CTkTextbox(ventana, wrap="word", font=ctk.CTkFont(size=13))
        caja.pack(fill="both", expand=True, padx=14, pady=14)
        caja.insert("1.0", ia_local.resumen_texto(self.banco_edit)); caja.configure(state="disabled")
        ventana.after(250, lambda: (ventana.lift(), ventana.focus_force()))

    def elegir_juego(self, juego_id):
        self.juego_sel = juego_id
        for i, card in self.tarjetas_juego.items():
            card.configure(border_color=COLORS["success"] if i == juego_id else COLORS["bg_card"])
        j = [x for x in juegos.juegos_de(self.tema_sel) if x["id"] == juego_id][0]
        self.lbl_tipo.configure(text=f"Nueva: [Juego] — {j['nombre']}")
        self.e_t.delete(0, 'end'); self.e_t.insert(0, j["nombre"])

    def publicar_mision(self):
        t, m, d = self.e_t.get(), self.e_m.get(), self.e_d.get()
        if self.tipo_actual == "[Juego]" and not self.tema_sel:
            self.lbl_log.configure(text="⚠️ Primero elige el tema del juego.", text_color=COLORS["warning"]); return
        if self.tipo_actual == "[Juego]" and not self.juego_sel:
            self.lbl_log.configure(text="⚠️ Elige uno de los juegos del tema.", text_color=COLORS["warning"]); return
        if t and m.isdigit() and d.isdigit():
            mision = {"titulo": f"{self.tipo_actual} - {t}", "monedas": int(m), "diamantes": int(d)}
            if self.tipo_actual == "[Juego]":
                mision.update({"juego_id": self.juego_sel, "tema": self.tema_sel, "grado": self.grado_actual()})
                if self.banco_edit != self.banco_base: mision["banco"] = self.banco_edit  # versión adaptada por el profesor
            almacen.guardar_mision(self.materia, mision)
            MISIONES_GLOBALES[self.materia].append(mision)
            self.lbl_log.configure(text="✅ Misión Publicada en la red de estudiantes.", text_color=COLORS["success"])
            self.e_t.delete(0, 'end'); self.e_m.delete(0, 'end'); self.e_d.delete(0, 'end')
        else:
            self.lbl_log.configure(text="⚠️ Llena título, monedas y diamantes (números).", text_color=COLORS["warning"])

# ----------------- VISTAS COMPARTIDAS -----------------
class BaseStoreView(ctk.CTkFrame):
    def __init__(self, master, boveda_core, update_hud_callback, titulo, subtitulo, color_titulo, items_data, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.boveda = boveda_core; self.update_hud = update_hud_callback
        header = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=15); header.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkLabel(header, text=titulo, font=ctk.CTkFont(size=24, weight="bold"), text_color=color_titulo).pack(anchor="w", padx=20, pady=(15, 5))
        if subtitulo: ctk.CTkLabel(header, text=subtitulo, font=ctk.CTkFont(size=14), text_color=COLORS["text_muted"]).pack(anchor="w", padx=20, pady=(0, 15))
            
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent"); scroll.pack(fill="both", expand=True, padx=10, pady=10)
        items_frame = ctk.CTkFrame(scroll, fg_color="transparent"); items_frame.pack(fill="x", padx=10, pady=5)
        
        for i, data in enumerate(items_data):
            self.crear_item(items_frame, data[0], data[1], data[2], data[3], i // 2, i % 2)
            
        self.lbl_log = ctk.CTkLabel(scroll, text="", font=ctk.CTkFont(size=16, weight="bold")); self.lbl_log.pack(pady=20)

    def crear_item(self, parent, titulo, costo_c, costo_d, color, fila, col):
        card = ctk.CTkFrame(parent, fg_color=COLORS["bg_card"], corner_radius=15); card.grid(row=fila, column=col, padx=10, pady=10, sticky="nsew"); parent.grid_columnconfigure(col, weight=1)
        ctk.CTkLabel(card, text=titulo, font=ctk.CTkFont(size=18, weight="bold"), text_color=color).pack(pady=(15, 5))
        if costo_c > 0 and costo_d > 0: precio_txt = f"🪙 {costo_c}  o  💎 {costo_d}"
        elif costo_c > 0: precio_txt = f"🪙 {costo_c}"
        elif costo_d > 0: precio_txt = f"💎 {costo_d}"
        else: precio_txt = "Gratis"
        ctk.CTkLabel(card, text=precio_txt).pack(pady=10)
        ctk.CTkButton(card, text="Comprar", fg_color=COLORS["bg_sidebar"], command=lambda: self.comprar(costo_c, costo_d, titulo)).pack(pady=(10, 20))

    def comprar(self, costo_c, costo_d, item):
        exito, msg = self.boveda.comprar_item(costo_c, costo_d, item)
        self.lbl_log.configure(text=f"¡Transacción! {msg}" if exito else msg, text_color=COLORS["success"] if exito else COLORS["danger"]); self.update_hud()

class ViewAvatares(ctk.CTkFrame):
    def __init__(self, master, boveda, update_hud, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.boveda = boveda; self.update_hud = update_hud
        header = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=15); header.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkLabel(header, text="👤 Selección de Avatar", font=ctk.CTkFont(size=24, weight="bold"), text_color=COLORS["accent_1"]).pack(anchor="w", padx=20, pady=(15, 5))
        ctk.CTkLabel(header, text="Elige tu personaje. Los bloqueados requieren monedas.", font=ctk.CTkFont(size=14), text_color=COLORS["text_muted"]).pack(anchor="w", padx=20, pady=(0, 15))
        
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent"); scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        ctk.CTkLabel(scroll, text="🔓 Avatares Básicos (Desbloqueados)", font=ctk.CTkFont(size=20, weight="bold"), text_color=COLORS["success"]).pack(anchor="w", padx=10, pady=10)
        f_bas = ctk.CTkFrame(scroll, fg_color="transparent"); f_bas.pack(fill="x", padx=10)
        f_bas.grid_columnconfigure((0, 1, 2), weight=1)
        self.crear_avatar(f_bas, "Novato", "novice_student", 0, 0, 0)
        self.crear_avatar(f_bas, "Curioso", "curious_mind", 0, 0, 1)
        self.crear_avatar(f_bas, "Lector", "fast_reader", 0, 0, 2)
        
        ctk.CTkLabel(scroll, text="🔒 Avatares Avanzados (Bloqueados)", font=ctk.CTkFont(size=20, weight="bold"), text_color=COLORS["warning"]).pack(anchor="w", padx=10, pady=(30, 10))
        f_prem = ctk.CTkFrame(scroll, fg_color="transparent"); f_prem.pack(fill="x", padx=10)
        f_prem.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.crear_avatar(f_prem, "Cyber-Ninja", "cyber_ninja", 500, 0, 0)
        self.crear_avatar(f_prem, "Hacker", "hacker_pro", 1000, 0, 1)
        self.crear_avatar(f_prem, "Hechicero", "magic_wizard", 750, 0, 2)
        self.crear_avatar(f_prem, "Robot", "battle_mech", 1500, 0, 3)
        
        self.lbl_log = ctk.CTkLabel(scroll, text="", font=ctk.CTkFont(size=16, weight="bold")); self.lbl_log.pack(pady=20)

    def cargar_img(self, seed, lbl):
        try:
            img = generar_avatar_2d(seed)
            lbl.after(0, lambda: lbl.configure(text="", image=img))
        except: pass

    def crear_avatar(self, parent, titulo, seed, costo_c, fila, col):
        card = ctk.CTkFrame(parent, fg_color=COLORS["bg_card"], corner_radius=15); card.grid(row=fila, column=col, padx=5, pady=10, sticky="nsew")
        
        lbl_img = ctk.CTkLabel(card, text="⌛", width=100, height=100)
        lbl_img.pack(pady=(15, 5))
        threading.Thread(target=self.cargar_img, args=(seed, lbl_img), daemon=True).start()
        
        ctk.CTkLabel(card, text=titulo, font=ctk.CTkFont(size=16, weight="bold")).pack(pady=5)
        
        if costo_c == 0:
            ctk.CTkLabel(card, text="Gratis", text_color=COLORS["success"]).pack(pady=5)
            btn_txt = "Equipar"
        else:
            ctk.CTkLabel(card, text=f"🪙 {costo_c}", text_color=COLORS["warning"]).pack(pady=5)
            btn_txt = "Desbloquear"
            
        def accionar():
            if costo_c == 0:
                self.boveda.avatar_seed = seed
                self.lbl_log.configure(text=f"✅ Avatar equipado: {titulo}", text_color=COLORS["success"])
                self.update_hud()
            else:
                exito, msg = self.boveda.comprar_item(costo_c, 0, f"Avatar {titulo}")
                if exito:
                    self.boveda.avatar_seed = seed
                    self.lbl_log.configure(text=f"✅ Desbloqueado y equipado: {titulo}", text_color=COLORS["success"])
                    self.update_hud()
                else:
                    self.lbl_log.configure(text=msg, text_color=COLORS["danger"])
                    
        ctk.CTkButton(card, text=btn_txt, fg_color=COLORS["bg_sidebar"], command=accionar).pack(pady=(10, 15), padx=10)

class ViewTienda(BaseStoreView):
    def __init__(self, master, boveda, update_hud, **kwargs):
        items = [("Tarjeta de Regalo $5", 0, 50, COLORS["success"]), ("Entrada de Cine", 0, 100, COLORS["accent_2"]),
                 ("Snack / Dulce", 0, 20, COLORS["warning"]), ("Stickers Exclusivos", 0, 10, "#a855f7")]
        super().__init__(master, boveda, update_hud, "💎 Tienda de Premios", "Recompensas fuera del colegio (Solo Diamantes)", COLORS["accent_1"], items, **kwargs)

class ViewMercado(BaseStoreView):
    def __init__(self, master, boveda, update_hud, **kwargs):
        items = [("Pase: 10 Min Música", 100, 0, "#a855f7"), ("Inmunidad a Quiz", 300, 0, COLORS["danger"]),
                 ("Elegir Equipo", 200, 0, COLORS["success"]), ("Entrega Tarde (1 día)", 500, 0, COLORS["accent_2"])]
        super().__init__(master, boveda, update_hud, "🛒 Mercado Escolar", "Beneficios exclusivos de clase (Solo Monedas)", COLORS["warning"], items, **kwargs)

class ViewLeaderboard(ctk.CTkFrame):
    """Top 10 de estudiantes por puntaje acumulado (monedas ganadas en total; no bajan al comprar).
    Un estudiante ve solo el top de su grado y su propia tarjeta: nunca la lista completa ni su puesto si queda fuera,
    para que nadie quede expuesto en el último lugar. Profesores y administrador ven el top de todos los grados."""
    TOP = 10
    MEDALLAS = {1: "🥇", 2: "🥈", 3: "🥉"}

    def __init__(self, master, boveda_core, rol="Estudiante", **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.boveda, self.rol = boveda_core, rol
        self.es_estudiante, self.es_admin = rol == "Estudiante", rol == "Administrador"
        self.mostrados, self.lbl_tarjeta, self.lbl_total = [], None, None
        header = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=15); header.pack(fill="x", padx=10, pady=(0, 10))
        derecha = ctk.CTkFrame(header, fg_color="transparent"); derecha.pack(side="right", padx=20)
        ctk.CTkButton(derecha, text="Actualizar", fg_color=COLORS["accent_2"], command=self.render_board).pack()
        if not self.es_estudiante:
            self.lbl_total = ctk.CTkLabel(derecha, text="", font=ctk.CTkFont(size=14, weight="bold"), text_color=COLORS["text_muted"])
            self.lbl_total.pack(pady=(6, 0))
        izquierda = ctk.CTkFrame(header, fg_color="transparent"); izquierda.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(izquierda, text="🏆 Muro de los Inmortales", font=ctk.CTkFont(size=24, weight="bold"), text_color=COLORS["warning"]).pack(anchor="w", padx=20, pady=(15, 0))
        sub = ("Los 10 mejores de tu grado. Tus puntos son las monedas que has ganado en total: gastarlas no te baja."
               if self.es_estudiante else "Los 10 mejores estudiantes de todos los grados.")
        ctk.CTkLabel(izquierda, text=sub, font=ctk.CTkFont(size=13), text_color=COLORS["text_muted"], wraplength=600, justify="left").pack(anchor="w", padx=20, pady=(0, 12))

        self.board_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_app"], corner_radius=15); self.board_frame.pack(fill="both", expand=True, padx=10, pady=10)
        if self.es_estudiante:
            tarjeta = ctk.CTkFrame(self.board_frame, fg_color=COLORS["bg_card"], corner_radius=12, border_width=2, border_color=COLORS["accent_1"])
            tarjeta.pack(side="bottom", fill="x", padx=30, pady=(0, 14))
            self.lbl_tarjeta = ctk.CTkLabel(tarjeta, text="", font=ctk.CTkFont(size=16, weight="bold"), wraplength=720, justify="left")
            self.lbl_tarjeta.pack(anchor="w", padx=18, pady=12)
        self.list_frame = ctk.CTkScrollableFrame(self.board_frame, fg_color="transparent"); self.list_frame.pack(fill="both", expand=True, padx=30, pady=10)
        self.render_board()

    def render_board(self):
        for w in self.list_frame.winfo_children(): w.destroy()
        ocultos = almacen.ocultos_del_ranking()
        ranking = almacen.ranking_estudiantes(self.boveda.grado if self.es_estudiante else None)
        if self.es_estudiante and self.boveda.username not in ocultos:
            # el puntaje propio se toma en vivo: puede ser mayor que el guardado si acaba de ganar monedas
            filas = [(u, p) for _, u, p in ranking if u != self.boveda.username] + [(self.boveda.username, self.boveda.puntos)]
            ranking = almacen.armar_ranking(filas)
        self.mostrados = almacen.recortar_top(ranking, self.TOP)
        if self.lbl_total: self.lbl_total.configure(text=f"👥 Participan: {len(ranking)}")
        if not self.mostrados:
            ctk.CTkLabel(self.list_frame, text="Aún nadie suma puntos. ¡Sé el primero en la lista! 🚀", font=ctk.CTkFont(size=16), text_color=COLORS["text_muted"]).pack(pady=30)
        for puesto, usuario, puntos in self.mostrados:
            self._fila(puesto, usuario, puntos)
        if self.es_admin and ocultos: self._seccion_ocultos(ocultos)
        if self.lbl_tarjeta: self.lbl_tarjeta.configure(text=self._texto_tarjeta(ranking, ocultos))

    def _fila(self, puesto, usuario, puntos):
        yo = self.es_estudiante and usuario == self.boveda.username
        row = ctk.CTkFrame(self.list_frame, fg_color=COLORS["bg_card"], corner_radius=10, border_width=2 if yo else 0, border_color=COLORS["accent_1"])
        row.pack(fill="x", pady=3)
        nombre = usuario.capitalize() + (" (Tú)" if yo else "")
        color_marca = {1: "#fbbf24", 2: "#cbd5e1", 3: "#d97706"}.get(puesto, COLORS["text_muted"])  # oro, plata y bronce (Tk dibuja las medallas en un solo color)
        ctk.CTkLabel(row, text=self.MEDALLAS.get(puesto, f"#{puesto}"), font=ctk.CTkFont(size=18, weight="bold"), text_color=color_marca, width=50, anchor="w").pack(side="left", padx=(15, 0), pady=5)
        ctk.CTkLabel(row, text=nombre, font=ctk.CTkFont(size=18, weight="bold")).pack(side="left", padx=(8, 15), pady=5)
        if self.es_admin:
            ctk.CTkButton(row, text="Ocultar 🙈", fg_color=COLORS["danger"], width=90, command=lambda u=usuario: self._cambiar_visibilidad(almacen.ocultar_del_ranking, u)).pack(side="right", padx=10)
        ctk.CTkLabel(row, text=f"{puntos} pts", font=ctk.CTkFont(size=16, weight="bold"), text_color=COLORS["accent_1"]).pack(side="right", padx=20)

    def _seccion_ocultos(self, ocultos):
        ctk.CTkLabel(self.list_frame, text="🙈 Ocultos del ranking", font=ctk.CTkFont(size=16, weight="bold"), text_color=COLORS["text_muted"]).pack(anchor="w", pady=(18, 4))
        for usuario in ocultos:
            row = ctk.CTkFrame(self.list_frame, fg_color=COLORS["bg_sidebar"], corner_radius=10); row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=usuario.capitalize(), font=ctk.CTkFont(size=15), text_color=COLORS["text_muted"]).pack(side="left", padx=15, pady=6)
            ctk.CTkButton(row, text="Restaurar", fg_color=COLORS["success"], width=90, command=lambda u=usuario: self._cambiar_visibilidad(almacen.restaurar_al_ranking, u)).pack(side="right", padx=10)

    def _cambiar_visibilidad(self, accion, usuario):
        accion(usuario)
        self.after_idle(self.render_board)  # el botón que se pulsó se destruye al redibujar: mejor después del clic

    def _texto_tarjeta(self, ranking, ocultos):
        yo, pts = self.boveda.username, self.boveda.puntos
        base = f"⭐ Tu puntaje: {pts} pts"
        if yo in ocultos: return base
        if pts <= 0: return base + " · Gana tu primer punto jugando una misión 🎮"
        if any(u == yo for _, u, _ in self.mostrados): return base + " · ¡Estás en el top 10! 🎉"
        return base + f" · te faltan {almacen.puntos_para_entrar(ranking, self.TOP) - pts} para entrar al top 10"

class ViewArena(ctk.CTkFrame):
    """Pestaña de práctica rápida del estudiante: partidas de 2 minutos que cuestan 1 corazón (5 por día).
    Tiene el duelo de preguntas y dos juegos clásicos puros: serpiente y Tetris (premio menor, sin preguntas)."""

    def __init__(self, master, boveda_core, update_hud_callback, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.boveda, self.update_hud = boveda_core, update_hud_callback
        self.grado = self.boveda.grado or juegos.GRADOS[-1]
        self.ventana, self._en_curso, self._ultimo = None, False, None   # _ultimo: lo necesario para repetir la partida
        header = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=15); header.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkLabel(header, text="⚔️ Arena", font=ctk.CTkFont(size=24, weight="bold"), text_color=COLORS["accent_1"]).pack(anchor="w", padx=20, pady=(15, 0))
        ctk.CTkLabel(header, text="Partidas de 2 minutos. Cada una cuesta 1 ❤️ y los corazones se recargan cada día.",
                     font=ctk.CTkFont(size=13), text_color=COLORS["text_muted"]).pack(anchor="w", padx=20, pady=(0, 12))
        self.lbl_corazones = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=22, weight="bold"), text_color=COLORS["danger"])
        self.lbl_corazones.pack(pady=(6, 10))

        cartas = ctk.CTkFrame(self, fg_color="transparent"); cartas.pack(fill="x", padx=10)
        cartas.grid_columnconfigure((0, 1, 2), weight=1, uniform="juego")
        duelo = ctk.CTkFrame(cartas, fg_color=COLORS["bg_card"], corner_radius=15, border_width=2, border_color=COLORS["accent_1"])
        duelo.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")
        ctk.CTkLabel(duelo, text="⚔️ Duelo de preguntas", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(16, 4))
        ctk.CTkLabel(duelo, text="Vence al robot en 2 minutos. Acierta rápido para golpear más fuerte.", font=ctk.CTkFont(size=12),
                     text_color=COLORS["text_muted"], wraplength=210).pack(padx=10)
        self.combo_materia = ctk.CTkComboBox(duelo, values=["Mezcla"] + self._materias(), state="readonly", width=190)
        self.combo_materia.set("Mezcla"); self.combo_materia.pack(pady=12)
        self.btn_jugar = ctk.CTkButton(duelo, text="Jugar (−1 ❤️)", fg_color=COLORS["accent_1"], text_color="#000000", command=self.jugar)
        self.btn_jugar.pack(pady=(0, 16))
        botones_arcade = []
        for col, (titulo, texto, accion) in enumerate((("🐍 Serpiente", "Come frutas sin chocar. ¡Cada fruta suma!", self.jugar_serpiente),
                                                       ("🧱 Tetris", "Completa líneas antes de que se acabe el tiempo.", self.jugar_tetris)), start=1):
            carta = ctk.CTkFrame(cartas, fg_color=COLORS["bg_card"], corner_radius=15)
            carta.grid(row=0, column=col, padx=8, pady=8, sticky="nsew")
            ctk.CTkLabel(carta, text=titulo, font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(16, 4))
            ctk.CTkLabel(carta, text=texto, font=ctk.CTkFont(size=12), text_color=COLORS["text_muted"], wraplength=210).pack(padx=10)
            boton = ctk.CTkButton(carta, text="Jugar (−1 ❤️)", fg_color=COLORS["accent_2"], width=190, command=accion)
            boton.pack(pady=(46, 16))
            botones_arcade.append(boton)
        self.btn_serpiente, self.btn_tetris = botones_arcade

        self.lbl_resultado = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=16, weight="bold"), wraplength=720)
        self.lbl_resultado.pack(pady=16)
        self.refrescar()
        self.after(30_000, self._refresco_periodico)

    def _materias(self):
        """Materias del grado con preguntas suficientes para un duelo."""
        return [m for m in juegos.BANCOS.get(self.grado, {}) if len(arena.armar_pool(juegos.BANCOS, self.grado, m)) >= arena.MIN_PREGUNTAS]

    def _mensaje(self, texto, color):
        self.lbl_resultado.configure(text=texto, text_color=color)

    def _refresco_periodico(self):
        """Cada 30 s vuelve a leer los corazones: con la app abierta de un día para otro y 0 corazones el botón
        está desactivado y jugar() nunca correría, así que la recarga tiene que venir de aquí."""
        if not self.winfo_exists():
            return
        self.refrescar()
        self.after(30_000, self._refresco_periodico)

    def refrescar(self):
        n = self.boveda.corazones_arena_disponibles()
        self.lbl_corazones.configure(text=arena.corazones_texto(n) + ("   ·   Sin corazones: vuelven mañana" if n <= 0 else ""))
        for boton in (self.btn_jugar, self.btn_serpiente, self.btn_tetris):
            boton.configure(state="normal" if n > 0 else "disabled")

    def _corazones_restantes(self):
        return self.boveda.corazones_arena_disponibles()

    def _lanzar(self, juego, abrir, valido=lambda: None):
        """Camino único de las tres partidas. `abrir()` crea la ventana; `valido()` devuelve un texto de error (o None)
        y se comprueba antes de gastar el corazón."""
        if self._en_curso:                      # ya hay una partida: se trae al frente en vez de ignorar el clic
            if self.ventana is not None and self.ventana.winfo_exists():
                if self.ventana.state() == "iconic":    # minimizada: lift() no la devuelve a la pantalla
                    self.ventana.deiconify()
                self.ventana.lift()
                self.ventana.focus_force()
            return
        if self.boveda.corazones_arena_disponibles() <= 0:
            self._mensaje("Sin corazones: vuelven mañana", COLORS["warning"]); self.refrescar(); return
        error = valido()
        if error:
            self._mensaje(error, COLORS["warning"]); return
        ok, msg = self.boveda.gastar_corazon_arena()
        if not ok:
            self._mensaje(msg, COLORS["warning"]); self.refrescar(); return
        self.update_hud()                       # guarda el progreso: el corazón ya está gastado
        self.refrescar()
        if self.ventana is not None and self.ventana.winfo_exists():
            self.ventana.destroy()              # la pantalla final de una partida anterior
        self._ultimo = (juego, abrir, valido)
        self._en_curso = True                   # antes de abrir: un segundo clic durante la apertura no debe gastar otro corazón
        self._mensaje("", COLORS["text_main"])
        try:
            self.ventana = abrir()
        except Exception:                       # si la ventana no abre, el corazón vuelve y la pestaña sigue viva
            self.boveda.devolver_corazon_arena()
            self._en_curso, self.ventana = False, None
            self.update_hud()
            self.refrescar()
            self._mensaje("⚠️ No se pudo abrir la partida. Te devolvimos el corazón.", COLORS["warning"])

    def jugar(self):
        """Duelo de preguntas con la materia elegida en el selector."""
        eleccion = self.combo_materia.get()
        pool = arena.armar_pool(juegos.BANCOS, self.grado, None if eleccion == "Mezcla" else eleccion)
        color = COLORS.get(f"mat_{eleccion.lower()}", COLORS["accent_2"])
        self._lanzar("duelo", lambda: juegos.lanzar_duelo(self.winfo_toplevel(), eleccion, pool, color, self._al_terminar, self._revancha,
                                                           self._corazones_restantes),
                     lambda: "⚠️ No hay suficientes preguntas para armar este duelo." if len(pool) < arena.MIN_PREGUNTAS else None)

    def _jugar_arcade(self, juego, lanzador):
        self._lanzar(juego, lambda: lanzador(self.winfo_toplevel(), COLORS["accent_2"], lambda puntaje: self._al_terminar_arcade(juego, puntaje),
                                              self._revancha, self._corazones_restantes, record=self.boveda.records.get(juego, 0)))

    def jugar_serpiente(self):
        self._jugar_arcade("serpiente", juegos.lanzar_serpiente)

    def jugar_tetris(self):
        self._jugar_arcade("tetris", juegos.lanzar_tetris)

    def _al_terminar_arcade(self, juego, puntaje):
        """Premio por puntaje y récord personal. puntaje=None significa que se abandonó la partida: sin premio ni récord."""
        self._en_curso = False
        if puntaje is None:
            self.update_hud()
            self.refrescar()
            self._mensaje("Abandonaste la partida: sin premio, el corazón ya estaba gastado.", COLORS["warning"])
            return
        monedas = arena.premio_arcade(juego, puntaje)
        self.boveda.ganar(monedas)
        nuevo = self.boveda.registrar_record(juego, puntaje)
        self.update_hud()
        self.refrescar()
        icono, unidad = ("🐍", "frutas") if juego == "serpiente" else ("🧱", "líneas")
        self._mensaje(f"{icono} {puntaje} {unidad}: +{monedas} 🪙" + (" · 🏅 ¡Nuevo récord!" if nuevo else ""),
                      COLORS["success"] if nuevo else COLORS["accent_1"])

    def _al_terminar(self, resultado):
        self._en_curso = False
        monedas = arena.premio(resultado)
        self.boveda.ganar(monedas)
        self.update_hud()
        self.refrescar()
        texto, color = {"victoria": (f"🏆 ¡Ganaste! +{monedas} 🪙", COLORS["success"]), "empate": (f"🤝 Empate: +{monedas} 🪙", COLORS["accent_1"]),
                        "derrota": (f"💪 Casi: +{monedas} 🪙. ¡Revancha!", COLORS["warning"]),
                        "abandono": ("Abandonaste el duelo: sin premio, el corazón ya estaba gastado.", COLORS["warning"])}[resultado]
        self._mensaje(texto, color)

    def _revancha(self):
        if self.ventana is not None and self.ventana.winfo_exists():
            self.ventana.destroy()
        self._en_curso = False
        if self._ultimo is not None:            # repite el mismo juego (y, en el duelo, las mismas preguntas posibles)
            self._lanzar(*self._ultimo)

class ViewAIQuiz(ctk.CTkFrame):
    def __init__(self, master, boveda_core, update_hud_callback, **kwargs):
        super().__init__(master, fg_color=COLORS["bg_card"], corner_radius=15, **kwargs)
        self.boveda = boveda_core; self.update_hud = update_hud_callback
        ctk.CTkLabel(self, text="🌐 Arena Neural (AI Quiz)", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=30, pady=15)
        
        f_c = ctk.CTkFrame(self, fg_color="transparent"); f_c.pack(fill="x", padx=30, pady=10)
        self.e_t = ctk.CTkEntry(f_c, placeholder_text="Ej: gravedad...", width=350, height=40); self.e_t.pack(side="left", padx=(0, 15))
        ctk.CTkButton(f_c, text="Generar Reto ⚡", fg_color="#a855f7", command=self.generar_quiz).pack(side="left")
        
        self.f_q = ctk.CTkFrame(self, fg_color=COLORS["bg_sidebar"], corner_radius=15); self.f_q.pack(fill="both", expand=True, padx=30, pady=20)
        self.lbl_q = ctk.CTkLabel(self.f_q, text="Esperando conexión...", font=ctk.CTkFont(size=16), wraplength=600); self.lbl_q.pack(pady=(40, 20))
        self.e_ans = ctk.CTkEntry(self.f_q, placeholder_text="Adivina el tema...", width=300, height=40)
        self.btn_sub = ctk.CTkButton(self.f_q, text="Validar", fg_color=COLORS["accent_2"], command=self.validar_respuesta)
        self.lbl_resultado = ctk.CTkLabel(self.f_q, text="", font=ctk.CTkFont(size=16, weight="bold"))
        self.tema_actual = ""

    def generar_quiz(self):
        t = self.e_t.get().strip()
        if t: threading.Thread(target=lambda: self._mostrar_quiz(*extraer_datos_matrix(t)), daemon=True).start()

    def _mostrar_quiz(self, exito, res, t_l):
        if exito: self.tema_actual = t_l; self.lbl_q.configure(text=res); self.e_ans.pack(pady=10); self.btn_sub.pack(pady=10)

    def validar_respuesta(self):
        res = self.e_ans.get().strip().lower()
        if res and (res == self.tema_actual or res in self.tema_actual):
            self.lbl_resultado.configure(text=self.boveda.procesar_victoria_quiz(), text_color=COLORS["success"])
        else: self.lbl_resultado.configure(text=self.boveda.procesar_derrota_quiz(), text_color=COLORS["danger"])
        self.lbl_resultado.pack(pady=10); self.update_hud()

# ==============================================================================
# 💅 MAIN APP
# ==============================================================================
class MainApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Neon OS"); self.geometry("1150x850"); self.configure(fg_color=COLORS["bg_app"])
        rutas.poner_icono(self)
        self.protocol("WM_DELETE_WINDOW", self.cerrar_app)
        self.db_manager = DatabaseManager(); self.boveda = None 
        self.mostrar_auth()

    def guardar_progreso(self):
        if self.boveda:
            almacen.guardar_progreso(self.boveda.username, self.boveda.exportar())

    def cerrar_app(self):
        self.guardar_progreso(); self.destroy()

    def mostrar_auth(self):
        self.guardar_progreso(); self.boveda = None
        for w in self.winfo_children(): w.destroy()
        ViewAuth(self, self.db_manager, self.iniciar_sesion).pack(fill="both", expand=True)

    def cargar_avatar_en_hilo(self):
        """Descarga la imagen del avatar 2D sin congelar la pantalla."""
        try:
            nuevo_avatar = generar_avatar_2d(self.boveda.avatar_seed)
            self.after(0, lambda: self.lbl_avatar.configure(text="", image=nuevo_avatar))
        except: 
            self.after(0, lambda: self.lbl_avatar.configure(text="Sin conexión a Matrix"))

    def actualizar_hud(self):
        if self.boveda:
            self.guardar_progreso()
            self.lbl_hearts.configure(text=f"❤️ {self.boveda.hearts}/5 Vidas")
            self.lbl_coins.configure(text=f"🪙 {self.boveda.coins} Monedas")
            self.lbl_diamonds.configure(text=f"💎 {self.boveda.diamonds} Diamantes")
            self.lbl_streak.configure(text=f"🔥 Racha: {self.boveda.streak} Días")
            if self.lbl_arena: self.lbl_arena.configure(text=f"⚔️ Arena: {self.boveda.corazones_arena_disponibles()}/{BovedaCore.CORAZONES_ARENA}")
            # Refresca el avatar en caso de que haya comprado uno en el mercado
            threading.Thread(target=self.cargar_avatar_en_hilo, daemon=True).start()

    def iniciar_sesion(self, usuario, user_data):
        for w in self.winfo_children(): w.destroy()
        rol = user_data["role"]; materia_docente = user_data["materia"]
        self.boveda = BovedaCore(usuario, user_data.get("grado"))
        guardado = almacen.cargar_progreso(usuario)
        if guardado: self.boveda.importar(guardado)
        self.boveda.regenerar_diario(); self.guardar_progreso()
        
        s = ctk.CTkFrame(self, width=300, fg_color=COLORS["bg_sidebar"], corner_radius=0); s.pack(side="left", fill="y")
        
        # Espacio para el Avatar 2D
        self.lbl_avatar = ctk.CTkLabel(s, text="Cargando Avatar...", width=120, height=120)
        self.lbl_avatar.pack(pady=(30, 10))
        
        ctk.CTkLabel(s, text=usuario.split("@")[0].capitalize(), font=ctk.CTkFont(size=24, weight="bold"), text_color=COLORS["text_main"]).pack(pady=0)
        
        color_rol = "#a855f7" if rol == "Administrador" else (COLORS["success"] if rol == "Profesor" else COLORS["accent_1"])
        perfil_txt = f"Perfil: {rol}" + (f" · Grado {juegos.etiqueta_grado(self.boveda.grado)}" if rol == "Estudiante" and self.boveda.grado else "")
        ctk.CTkLabel(s, text=perfil_txt, font=ctk.CTkFont(size=14, weight="bold"), text_color=color_rol).pack(pady=(0, 20))
        
        f_stats = ctk.CTkFrame(s, fg_color=COLORS["bg_card"], corner_radius=15); f_stats.pack(fill="x", padx=20, pady=10)
        self.lbl_hearts = ctk.CTkLabel(f_stats, text=f"❤️ {self.boveda.hearts}/5 Vidas", font=ctk.CTkFont(size=18, weight="bold"), text_color=COLORS["danger"]); self.lbl_hearts.pack(anchor="w", padx=20, pady=(20, 10))
        self.lbl_coins = ctk.CTkLabel(f_stats, text=f"🪙 {self.boveda.coins} Monedas", font=ctk.CTkFont(size=18, weight="bold"), text_color=COLORS["warning"]); self.lbl_coins.pack(anchor="w", padx=20, pady=10)
        self.lbl_diamonds = ctk.CTkLabel(f_stats, text=f"💎 {self.boveda.diamonds} Diamantes", font=ctk.CTkFont(size=18, weight="bold"), text_color=COLORS["accent_1"]); self.lbl_diamonds.pack(anchor="w", padx=20, pady=10)
        self.lbl_arena = None  # la línea de corazones de la Arena solo la tienen los estudiantes
        if rol == "Estudiante":
            self.lbl_arena = ctk.CTkLabel(f_stats, text=f"⚔️ Arena: {self.boveda.corazones_arena_disponibles()}/{BovedaCore.CORAZONES_ARENA}", font=ctk.CTkFont(size=18, weight="bold"), text_color="#a855f7"); self.lbl_arena.pack(anchor="w", padx=20, pady=10)
        self.lbl_streak = ctk.CTkLabel(f_stats, text=f"🔥 Racha: {self.boveda.streak} Días", font=ctk.CTkFont(size=18, weight="bold"), text_color="#f97316"); self.lbl_streak.pack(anchor="w", padx=20, pady=(10, 20))
        
        ctk.CTkButton(s, text="Cerrar Sesión", fg_color="transparent", hover_color=COLORS["danger"], text_color=COLORS["danger"], command=self.mostrar_auth).pack(side="bottom", pady=30, padx=20, fill="x")

        # Cargar el Avatar inicial en un hilo separado
        threading.Thread(target=self.cargar_avatar_en_hilo, daemon=True).start()

        content = ctk.CTkFrame(self, fg_color=COLORS["bg_app"]); content.pack(side="right", fill="both", expand=True, padx=20, pady=20)
        tabs = ctk.CTkTabview(content, fg_color=COLORS["bg_app"], segmented_button_selected_color=COLORS["accent_2"], corner_radius=15); tabs.pack(fill="both", expand=True)
        
        if rol == "Administrador":
            tabs.add("Monitoreo 👁️"); ViewAdminMonitor(tabs.tab("Monitoreo 👁️")).pack(fill="both", expand=True)
            tabs.add("Arena AI 🤖"); ViewAIQuiz(tabs.tab("Arena AI 🤖"), self.boveda, self.actualizar_hud).pack(fill="both", expand=True)
            tabs.add("Ranking 🏆"); ViewLeaderboard(tabs.tab("Ranking 🏆"), self.boveda, rol=rol).pack(fill="both", expand=True)
        elif rol == "Profesor":
            tabs.add("Misiones 🧙‍♂️"); ViewProfesor(tabs.tab("Misiones 🧙‍♂️"), materia_docente).pack(fill="both", expand=True)
            tabs.add("Ranking 🏆"); ViewLeaderboard(tabs.tab("Ranking 🏆"), self.boveda, rol=rol).pack(fill="both", expand=True)
        else:
            tabs.add("Completo ✅"); ViewEstudianteTablero(tabs.tab("Completo ✅"), self.boveda, self.actualizar_hud).pack(fill="both", expand=True)
            tabs.add("Arena ⚔️"); ViewArena(tabs.tab("Arena ⚔️"), self.boveda, self.actualizar_hud).pack(fill="both", expand=True)
            tabs.add("Avatares 👤"); ViewAvatares(tabs.tab("Avatares 👤"), self.boveda, self.actualizar_hud).pack(fill="both", expand=True)
            tabs.add("Tienda 💎"); ViewTienda(tabs.tab("Tienda 💎"), self.boveda, self.actualizar_hud).pack(fill="both", expand=True)
            tabs.add("Mercado 🛒"); ViewMercado(tabs.tab("Mercado 🛒"), self.boveda, self.actualizar_hud).pack(fill="both", expand=True)
            tabs.add("Ranking 🏆"); ViewLeaderboard(tabs.tab("Ranking 🏆"), self.boveda, rol=rol).pack(fill="both", expand=True)

if __name__ == "__main__":
    MainApp().mainloop()