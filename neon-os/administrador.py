import customtkinter as ctk
import requests
import re
import threading
import random
from tkinter import messagebox

class ViewAdminMonitor(ctk.CTkFrame):
    def __init__(self, master, misiones_globales, colors, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.misiones = misiones_globales
        self.colors = colors

        header = ctk.CTkFrame(self, fg_color=self.colors["bg_card"], corner_radius=15)
        header.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkLabel(header, text="👁️ Ojo que Todo lo Ve (Monitoreo de Misiones)", font=ctk.CTkFont(size=24, weight="bold"), text_color="#a855f7").pack(anchor="w", padx=20, pady=(15, 0))
        
        self.grid_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.grid_frame.pack(fill="both", expand=True)
        self.construir_grid()

    def construir_grid(self):
        for w in self.grid_frame.winfo_children(): w.destroy()
        
        container = ctk.CTkFrame(self.grid_frame, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)
        container.grid_columnconfigure((0, 1, 2), weight=1, uniform="col")
        container.grid_rowconfigure((0, 1), weight=1, uniform="row")
        
        materias = [("Química", 0, 0), ("Física", 0, 1), ("Matemáticas", 0, 2),
                    ("Tecnología", 1, 0), ("Sociales", 1, 1), ("Inglés", 1, 2)]
                    
        for mat, r, c in materias:
            num_misiones = len(self.misiones[mat])
            texto = f"{mat}\n{num_misiones} Misiones Activas"
            
            btn = ctk.CTkButton(container, text=texto, font=ctk.CTkFont(size=20, weight="bold"),
                                fg_color=self.colors["bg_card"], text_color=self.colors[f"mat_{mat.lower()}"], 
                                corner_radius=15, height=120, hover_color=self.colors["bg_sidebar"], state="disabled")
            btn.grid(row=r, column=c, padx=10, pady=10, sticky="nsew")
            
        ctk.CTkButton(self.grid_frame, text="Actualizar Red 🔄", fg_color="#a855f7", font=ctk.CTkFont(weight="bold"), command=self.construir_grid).pack(pady=10)

class ViewLeaderboard(ctk.CTkFrame):
    def __init__(self, master, boveda_core, is_admin, colors, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.boveda = boveda_core
        self.is_admin = is_admin
        self.colors = colors
        
        header = ctk.CTkFrame(self, fg_color=self.colors["bg_card"], corner_radius=15); header.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkLabel(header, text="🏆 El Muro de los Inmortales", font=ctk.CTkFont(size=24, weight="bold"), text_color=self.colors["warning"]).pack(anchor="w", padx=20, pady=(15, 0))
        
        self.board_frame = ctk.CTkFrame(self, fg_color=self.colors["bg_app"], corner_radius=15)
        self.board_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # NPCs Poblados
        self.competidores = [
            {"nombre": "Daniel Sandoval", "monedas": 15000, "diamantes": 50},
            {"nombre": "Luis Barreto", "monedas": 14500, "diamantes": 48},
            {"nombre": "Sofía C.", "monedas": 8000, "diamantes": 20},
            {"nombre": "Mateo R.", "monedas": 300, "diamantes": 2},
            {"nombre": "Hacker_NPC", "monedas": 999999, "diamantes": 999}
        ]
        
        controles = ctk.CTkFrame(self.board_frame, fg_color="transparent"); controles.pack(fill="x", padx=30, pady=10)
        ctk.CTkButton(controles, text="Actualizar Ranking 🔄", fg_color=self.colors["accent_2"], command=self.render_board).pack(side="left", padx=10)
        
        self.list_frame = ctk.CTkFrame(self.board_frame, fg_color="transparent")
        self.list_frame.pack(fill="both", expand=True, padx=30, pady=10)
        self.render_board()

    def banear_jugador(self, nombre_jugador):
        self.competidores = [npc for npc in self.competidores if npc["nombre"] != nombre_jugador]
        messagebox.showwarning("Ban Hammer 🔨", f"El usuario '{nombre_jugador}' fue eliminado de la Matrix por tramposo.")
        self.render_board()

    def render_board(self):
        for w in self.list_frame.winfo_children(): w.destroy()
        
        lista = self.competidores.copy()
        lista.append({"nombre": self.boveda.username + " (Tú)", "monedas": self.boveda.coins, "diamantes": self.boveda.diamonds})
        lista = sorted(lista, key=lambda x: x["monedas"], reverse=True)
        
        for i, user in enumerate(lista):
            row = ctk.CTkFrame(self.list_frame, fg_color=self.colors["bg_card"], corner_radius=10); row.pack(fill="x", pady=5)
            ctk.CTkLabel(row, text=f"#{i+1}  {user['nombre']}", font=ctk.CTkFont(size=18, weight="bold")).pack(side="left", padx=15, pady=15)
            
            if self.is_admin and "(Tú)" not in user["nombre"]: 
                ctk.CTkButton(row, text="Banear 🔨", fg_color=self.colors["danger"], width=60, font=ctk.CTkFont(weight="bold"), command=lambda n=user["nombre"]: self.banear_jugador(n)).pack(side="right", padx=15)
                
            ctk.CTkLabel(row, text=f"🪙 {user['monedas']}  |  💎 {user['diamantes']}", font=ctk.CTkFont(size=16, weight="bold"), text_color=self.colors["accent_1"]).pack(side="right", padx=30)

def extraer_datos_matrix(tema):
    try:
        headers = {'User-Agent': 'NeonOS_Edu_Project/1.0'}
        url = f"https://es.wikipedia.org/api/rest_v1/page/summary/{tema}"
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            return True, re.compile(re.escape(tema), re.IGNORECASE).sub("██████", res.json().get('extract', '')), tema.lower()
        return False, "Dato no encontrado en la red.", ""
    except:
        return False, "Fallo de conexión. Revisa el internet.", ""

class ViewAIQuiz(ctk.CTkFrame):
    def __init__(self, master, boveda_core, update_hud_callback, colors, **kwargs):
        super().__init__(master, fg_color=colors["bg_card"], corner_radius=15, **kwargs)
        self.boveda = boveda_core; self.update_hud = update_hud_callback; self.colors = colors
        ctk.CTkLabel(self, text="🌐 Arena Neural (AI Quiz)", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=30, pady=(30, 5))
        
        f_c = ctk.CTkFrame(self, fg_color="transparent"); f_c.pack(fill="x", padx=30, pady=10)
        self.e_t = ctk.CTkEntry(f_c, placeholder_text="Ej: gravedad, software...", width=350, height=45); self.e_t.pack(side="left", padx=(0, 15))
        self.btn_g = ctk.CTkButton(f_c, text="Extraer Data ⚡", fg_color="#a855f7", height=45, font=ctk.CTkFont(weight="bold"), command=self.generar_quiz); self.btn_g.pack(side="left")
        
        self.f_q = ctk.CTkFrame(self, fg_color=self.colors["bg_sidebar"], corner_radius=15); self.f_q.pack(fill="both", expand=True, padx=30, pady=20)
        self.lbl_q = ctk.CTkLabel(self.f_q, text="Esperando conexión...", font=ctk.CTkFont(size=16), wraplength=600); self.lbl_q.pack(pady=(40, 20))
        
        self.e_ans = ctk.CTkEntry(self.f_q, placeholder_text="Adivina el tema oculto...", width=300, height=45)
        self.btn_sub = ctk.CTkButton(self.f_q, text="Validar", fg_color=self.colors["accent_2"], height=45, command=self.validar_respuesta)
        self.lbl_resultado = ctk.CTkLabel(self.f_q, text="", font=ctk.CTkFont(size=16, weight="bold"))
        self.tema_actual = ""

    def generar_quiz(self):
        t = self.e_t.get().strip()
        if t: threading.Thread(target=self._manejar_red, args=(t,), daemon=True).start()

    def _manejar_red(self, tema):
        exito, res, t_l = extraer_datos_matrix(tema)
        if exito: self.tema_actual = t_l; self.after(0, lambda: self._mostrar_quiz(res))

    def _mostrar_quiz(self, texto):
        self.lbl_q.configure(text=f"¿De qué habla este texto?\n\n{texto}"); self.e_ans.pack(pady=10); self.btn_sub.pack(pady=10)

    def validar_respuesta(self):
        res = self.e_ans.get().strip().lower()
        if res == self.tema_actual or res in self.tema_actual:
            msg = self.boveda.procesar_victoria_quiz(); self.lbl_resultado.configure(text=msg, text_color=self.colors["success"])
        else:
            msg = self.boveda.procesar_derrota_quiz(); self.lbl_resultado.configure(text=f"{msg}\nEra: {self.tema_actual}", text_color=self.colors["danger"])
        self.lbl_resultado.pack(pady=10); self.update_hud()