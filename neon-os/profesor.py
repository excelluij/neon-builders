import customtkinter as ctk

class ViewProfesor(ctk.CTkFrame):
    def __init__(self, master, materia, misiones_globales, colors, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.materia = materia
        self.misiones = misiones_globales
        self.colors = colors
        self.color_tema = self.colors.get(f"mat_{materia.lower()}", self.colors["success"])

        header = ctk.CTkFrame(self, fg_color=self.colors["bg_card"], corner_radius=15)
        header.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkLabel(header, text=f"🧙‍♂️ Panel de Arquitecto: {self.materia}", font=ctk.CTkFont(size=24, weight="bold"), text_color=self.color_tema).pack(anchor="w", padx=20, pady=(15, 0))
        ctk.CTkLabel(header, text="Elige qué tipo de nodo (misión) quieres inyectar en los cuadros de tus estudiantes.", text_color=self.colors["text_muted"]).pack(anchor="w", padx=20, pady=(0, 15))

        self.grid_acciones = ctk.CTkFrame(self, fg_color="transparent")
        self.grid_acciones.pack(fill="x", padx=10, pady=10)
        self.grid_acciones.grid_columnconfigure((0, 1), weight=1, uniform="col")
        
        acciones = [("[Tarea] Subir Archivo", 0, 0), ("[Presentación] Exposición", 0, 1), 
                    ("[Quiz] Prueba Rápida", 1, 0), ("[Juego] Simulación Engine", 1, 1)]
                    
        for texto, r, c in acciones:
            btn = ctk.CTkButton(self.grid_acciones, text=texto, font=ctk.CTkFont(size=18, weight="bold"),
                                fg_color=self.colors["bg_card"], text_color=self.color_tema, height=100, corner_radius=15,
                                hover_color=self.colors["bg_sidebar"], border_width=2, border_color=self.color_tema,
                                command=lambda t=texto: self.preparar_formulario(t))
            btn.grid(row=r, column=c, padx=10, pady=10, sticky="nsew")

        self.f_crear = ctk.CTkFrame(self, fg_color=self.colors["bg_app"], corner_radius=15)
        self.lbl_tipo_accion = ctk.CTkLabel(self.f_crear, text="", font=ctk.CTkFont(size=20, weight="bold"))
        self.lbl_tipo_accion.pack(pady=(20, 10))
        
        self.e_t = ctk.CTkEntry(self.f_crear, placeholder_text="Título o Tema de la Misión", width=400, height=45); self.e_t.pack(pady=10)
        self.e_m = ctk.CTkEntry(self.f_crear, placeholder_text="Recompensa: Monedas (Ej: 50000)", width=400, height=45); self.e_m.pack(pady=10)
        self.e_d = ctk.CTkEntry(self.f_crear, placeholder_text="Recompensa: Diamantes (Ej: 10)", width=400, height=45); self.e_d.pack(pady=10)
        
        self.lbl_log = ctk.CTkLabel(self.f_crear, text="", font=ctk.CTkFont(size=14, weight="bold"))
        ctk.CTkButton(self.f_crear, text="Publicar en la Red 🌐", fg_color=self.color_tema, font=ctk.CTkFont(weight="bold"), height=50, command=self.publicar_mision).pack(pady=20)
        self.lbl_log.pack(pady=5)
        
        self.tipo_actual = ""

    def preparar_formulario(self, tipo):
        self.tipo_actual = tipo
        self.lbl_tipo_accion.configure(text=f"Configurando: {tipo}", text_color=self.color_tema)
        self.f_crear.pack(fill="both", expand=True, padx=10, pady=10)
        self.lbl_log.configure(text="")

    def publicar_mision(self):
        tit = self.e_t.get().strip(); mon = self.e_m.get().strip(); dia = self.e_d.get().strip()
        if tit and mon.isdigit() and dia.isdigit():
            # Inyecta la misión en el diccionario global (que afectará al estudiante)
            self.misiones[self.materia].append({
                "titulo": f"{self.tipo_actual} - {tit}", 
                "monedas": int(mon), 
                "diamantes": int(dia)
            })
            self.lbl_log.configure(text=f"✅ Nodo inyectado. Los estudiantes verán el bloque en rojo.", text_color=self.colors["success"])
            self.e_t.delete(0, 'end'); self.e_m.delete(0, 'end'); self.e_d.delete(0, 'end')
        else:
            self.lbl_log.configure(text="❌ Error: Llena todos los campos. Monedas y Diamantes deben ser números.", text_color=self.colors["danger"])