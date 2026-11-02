import customtkinter as ctk
from tkinter import filedialog, messagebox
import multiprocessing
import pygame
import random
import sys

def run_game_engine():
    pygame.init()
    w, h = 800, 600
    pantalla = pygame.display.set_mode((w, h))
    pygame.display.set_caption("Neon Builders - Simulator")
    reloj = pygame.time.Clock()
    nodos = [{"x": random.randint(50, w-50), "y": random.randint(50, h-50), "color": random.choice([(0, 242, 254), (79, 172, 254)])} for _ in range(15)]
    corriendo = True
    while corriendo:
        for evento in pygame.event.get():
            if evento.type == pygame.QUIT: corriendo = False
        pantalla.fill((20, 21, 26))
        for n in nodos:
            pygame.draw.circle(pantalla, n["color"], (n["x"], n["y"]), 15)
            n["x"] += random.randint(-2, 2); n["y"] += random.randint(-2, 2)
        pygame.display.flip()
        reloj.tick(60)
    pygame.quit()
    sys.exit()

class ViewEstudianteTablero(ctk.CTkFrame):
    def __init__(self, master, boveda_core, update_hud_callback, misiones_globales, colors, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.boveda = boveda_core
        self.update_hud = update_hud_callback
        self.misiones = misiones_globales
        self.colors = colors
        
        self.grid_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.grid_frame.pack(fill="both", expand=True)
        
        self.detalle_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.construir_grid()

    def construir_grid(self):
        for w in self.grid_frame.winfo_children(): w.destroy()
        
        header = ctk.CTkFrame(self.grid_frame, fg_color=self.colors["bg_card"], corner_radius=15)
        header.pack(fill="x", padx=10, pady=(0, 20))
        
        ctk.CTkLabel(header, text="🌐 Central de Misiones (Los 6 Cuadros)", font=ctk.CTkFont(size=24, weight="bold"), text_color=self.colors["accent_1"]).pack(anchor="w", padx=20, pady=(15, 0))
        ctk.CTkLabel(header, text="Si un bloque está en ROJO, tienes una misión oficial. Si no, puedes entrar a farmear libremente.", text_color=self.colors["text_muted"]).pack(anchor="w", padx=20, pady=(0, 15))

        container = ctk.CTkFrame(self.grid_frame, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20)
        container.grid_columnconfigure((0, 1, 2), weight=1, uniform="col")
        container.grid_rowconfigure((0, 1), weight=1, uniform="row")
        
        materias = [("Matemáticas", 0, 0), ("Física", 0, 1), ("Química", 0, 2),
                    ("Sociales", 1, 0), ("Ciencias", 1, 1), ("Inglés", 1, 2)]
                    
        for mat, r, c in materias:
            tiene_mision = len(self.misiones[mat]) > 0
            
            if tiene_mision:
                color_fondo = self.colors["danger"]
                color_texto = "#ffffff"
                texto_extra = "\n⚠️ ¡TAREA PENDIENTE!"
            else:
                color_fondo = self.colors["bg_card"]
                color_texto = self.colors[f"mat_{mat.lower()}"]
                texto_extra = "\n(Zona Libre)"
            
            btn = ctk.CTkButton(container, text=f"{mat}{texto_extra}", font=ctk.CTkFont(size=20, weight="bold"),
                                fg_color=color_fondo, text_color=color_texto, corner_radius=15, height=120,
                                hover_color=self.colors["bg_sidebar"], command=lambda m=mat: self.abrir_materia(m))
            btn.grid(row=r, column=c, padx=10, pady=10, sticky="nsew")

    def abrir_materia(self, materia):
        self.grid_frame.pack_forget()
        self.detalle_frame.pack(fill="both", expand=True)
        for w in self.detalle_frame.winfo_children(): w.destroy()
        
        color_tema = self.colors[f"mat_{materia.lower()}"]
        
        header = ctk.CTkFrame(self.detalle_frame, fg_color=color_tema, corner_radius=15)
        header.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkLabel(header, text=f"Laboratorio de {materia}", font=ctk.CTkFont(size=24, weight="bold"), text_color="#ffffff").pack(side="left", padx=20, pady=15)
        ctk.CTkButton(header, text="⬅ Volver a los Cuadros", fg_color=self.colors["bg_app"], text_color="#ffffff", command=self.volver_grid).pack(side="right", padx=20)
        
        content_frame = ctk.CTkFrame(self.detalle_frame, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=10, pady=10)
        content_frame.grid_columnconfigure((0, 1, 2), weight=1, uniform="col")
        content_frame.grid_rowconfigure(0, weight=1)
        
        # Columna 1: Tareas
        col_tareas = ctk.CTkScrollableFrame(content_frame, fg_color=self.colors["bg_app"])
        col_tareas.grid(row=0, column=0, sticky="nsew", padx=5)
        ctk.CTkLabel(col_tareas, text="📝 Tareas (Archivos)", font=ctk.CTkFont(size=20, weight="bold"), text_color=self.colors["danger"]).pack(pady=10)
        
        # Columna 2: Opinión / Preguntas
        col_preg = ctk.CTkScrollableFrame(content_frame, fg_color=self.colors["bg_app"])
        col_preg.grid(row=0, column=1, sticky="nsew", padx=5)
        ctk.CTkLabel(col_preg, text="💬 Columna de Opinión", font=ctk.CTkFont(size=20, weight="bold"), text_color=self.colors["accent_1"]).pack(pady=10)
        
        # Columna 3: Presentación Libre
        col_libres = ctk.CTkFrame(content_frame, fg_color=self.colors["bg_card"], corner_radius=10)
        col_libres.grid(row=0, column=2, sticky="nsew", padx=5)
        ctk.CTkLabel(col_libres, text="📂 Presentación Libre", font=ctk.CTkFont(size=20, weight="bold"), text_color=color_tema).pack(pady=20)
        ctk.CTkLabel(col_libres, text="Sube apuntes para ganar\npuntos pasivos (15🪙 | 3💎)", font=ctk.CTkFont(size=14)).pack()
        e_con = ctk.CTkEntry(col_libres, placeholder_text="Concepto clave...", width=250, height=40)
        e_con.pack(pady=20)
        ctk.CTkButton(col_libres, text="Subir y Ganar Puntos", fg_color=color_tema, command=lambda: self.auditar_libre(materia, e_con)).pack(pady=10)
        
        misiones = self.misiones[materia]
        m_tareas = [m for m in misiones if "[Pregunta]" not in m['titulo']]
        m_preguntas = [m for m in misiones if "[Pregunta]" in m['titulo']]
        
        if m_tareas:
            for m in m_tareas:
                card = ctk.CTkFrame(col_tareas, fg_color="#451a1a", border_width=2, border_color=self.colors["danger"], corner_radius=10)
                card.pack(fill="x", pady=10, padx=10)
                ctk.CTkLabel(card, text=m['titulo'], font=ctk.CTkFont(size=14, weight="bold"), wraplength=200).pack(pady=5)
                ctk.CTkLabel(card, text=f"Drop: {m['monedas']}🪙 | {m['diamantes']}💎", font=ctk.CTkFont(weight="bold"), text_color=self.colors["warning"]).pack(pady=5)
                if "[Juego]" in m['titulo']:
                    cmd = lambda t=m: multiprocessing.Process(target=run_game_engine).start()
                    ctk.CTkButton(card, text="Jugar 🎮", fg_color=self.colors["accent_1"], text_color="#000000", command=cmd).pack(pady=10)
                else:
                    ctk.CTkButton(card, text="Subir Archivo 📂", fg_color=self.colors["danger"], command=lambda t=m: self.auditar_oficial(materia, t)).pack(pady=10)
        else:
            ctk.CTkLabel(col_tareas, text="Sin tareas por ahora.").pack(pady=50)

        if m_preguntas:
            for m in m_preguntas:
                card = ctk.CTkFrame(col_preg, fg_color=self.colors["bg_sidebar"], border_width=2, border_color=self.colors["accent_1"], corner_radius=10)
                card.pack(fill="x", pady=10, padx=10)
                ctk.CTkLabel(card, text=m['titulo'], font=ctk.CTkFont(size=14, weight="bold"), wraplength=200).pack(pady=5)
                ctk.CTkLabel(card, text=f"Premio: {m['monedas']}🪙 | {m['diamantes']}💎", text_color=self.colors["warning"]).pack(pady=5)
                e_ans = ctk.CTkEntry(card, placeholder_text="Tu respuesta...", width=200)
                e_ans.pack(pady=5)
                ctk.CTkButton(card, text="Responder 💬", fg_color=self.colors["accent_1"], text_color="#000000", command=lambda t=m, e=e_ans: self.responder_pregunta(materia, t, e)).pack(pady=10)
        else:
            ctk.CTkLabel(col_preg, text="Sin preguntas hoy.").pack(pady=50)
            
        self.lbl_log = ctk.CTkLabel(self.detalle_frame, text="", font=ctk.CTkFont(size=16, weight="bold"))
        self.lbl_log.pack(pady=10)

    def volver_grid(self):
        self.detalle_frame.pack_forget()
        self.construir_grid() 
        self.grid_frame.pack(fill="both", expand=True)

    def auditar_oficial(self, materia, tarea_dict):
        ruta = filedialog.askopenfilename(title=f"Sube la tarea de {materia}")
        if ruta:
            exito, msg = self.boveda.procesar_archivo_estricto(ruta, materia, self.boveda.diccionario_materias[materia][0], recompensa_monedas=tarea_dict["monedas"], recompensa_diamantes=tarea_dict["diamantes"])
            self.lbl_log.configure(text=msg, text_color=self.colors["success"] if exito else self.colors["danger"])
            self.update_hud()

    def auditar_libre(self, materia, entry_widget):
        concepto = entry_widget.get().strip()
        if not concepto: 
            self.lbl_log.configure(text="⚠️ Escribe de qué trata el archivo primero.", text_color=self.colors["warning"])
            return
        ruta = filedialog.askopenfilename(title="Sube tus apuntes libres")
        if ruta:
            exito, msg = self.boveda.procesar_archivo_estricto(ruta, materia, concepto, recompensa_monedas=15, recompensa_diamantes=3)
            self.lbl_log.configure(text=msg, text_color=self.colors["success"] if exito else self.colors["danger"])
            entry_widget.delete(0, 'end')
            self.update_hud()

    def responder_pregunta(self, materia, tarea_dict, entry_widget):
        ans = entry_widget.get().strip()
        if len(ans) > 5:
            m_ganadas = int(tarea_dict["monedas"])
            d_ganados = int(tarea_dict["diamantes"])
            self.boveda.coins += m_ganadas
            self.boveda.diamonds += d_ganados
            self.lbl_log.configure(text=f"✅ Opinión enviada. \n💎 Drop: +{m_ganadas} 🪙 | +{d_ganados} 💎", text_color=self.colors["success"])
            entry_widget.delete(0, 'end')
            self.update_hud()
        else:
            self.lbl_log.configure(text="⚠️ Escribe una opinión más completa.", text_color=self.colors["warning"])

class BaseStoreView(ctk.CTkFrame):
    def __init__(self, master, boveda_core, update_hud_callback, colors, titulo, subtitulo, color_titulo, items_data, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.boveda = boveda_core; self.update_hud = update_hud_callback; self.colors = colors
        header = ctk.CTkFrame(self, fg_color=self.colors["bg_card"], corner_radius=15); header.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkLabel(header, text=titulo, font=ctk.CTkFont(size=24, weight="bold"), text_color=color_titulo).pack(anchor="w", padx=20, pady=(15, 5))
        if subtitulo: ctk.CTkLabel(header, text=subtitulo, font=ctk.CTkFont(size=14), text_color=self.colors["text_muted"]).pack(anchor="w", padx=20, pady=(0, 15))
            
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent"); scroll.pack(fill="both", expand=True, padx=10, pady=10)
        items_frame = ctk.CTkFrame(scroll, fg_color="transparent"); items_frame.pack(fill="x", padx=10, pady=5)
        
        for i, data in enumerate(items_data):
            self.crear_item(items_frame, data[0], data[1], data[2], data[3], i // 2, i % 2)
            
        self.lbl_log = ctk.CTkLabel(scroll, text="", font=ctk.CTkFont(size=16, weight="bold")); self.lbl_log.pack(pady=20)

    def crear_item(self, parent, titulo, costo_c, costo_d, color, fila, col):
        card = ctk.CTkFrame(parent, fg_color=self.colors["bg_card"], corner_radius=15); card.grid(row=fila, column=col, padx=10, pady=10, sticky="nsew"); parent.grid_columnconfigure(col, weight=1)
        ctk.CTkLabel(card, text=titulo, font=ctk.CTkFont(size=18, weight="bold"), text_color=color).pack(pady=(15, 5))
        if costo_c > 0 and costo_d > 0: precio_txt = f"🪙 {costo_c}  o  💎 {costo_d}"
        elif costo_c > 0: precio_txt = f"🪙 {costo_c}"
        elif costo_d > 0: precio_txt = f"💎 {costo_d}"
        else: precio_txt = "Gratis"
        ctk.CTkLabel(card, text=precio_txt).pack(pady=10)
        ctk.CTkButton(card, text="Comprar", fg_color=self.colors["bg_sidebar"], command=lambda: self.comprar(costo_c, costo_d, titulo)).pack(pady=(10, 20))

    def comprar(self, costo_c, costo_d, item):
        exito, msg = self.boveda.comprar_item(costo_c, costo_d, item)
        self.lbl_log.configure(text=f"¡Transacción! {msg}" if exito else msg, text_color=self.colors["success"] if exito else self.colors["danger"]); self.update_hud()

class ViewAvatares(ctk.CTkFrame):
    def __init__(self, master, boveda, update_hud, colors, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.boveda = boveda; self.update_hud = update_hud; self.colors = colors
        header = ctk.CTkFrame(self, fg_color=self.colors["bg_card"], corner_radius=15); header.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkLabel(header, text="👤 Selección de Avatar", font=ctk.CTkFont(size=24, weight="bold"), text_color=self.colors["accent_1"]).pack(anchor="w", padx=20, pady=(15, 5))
        ctk.CTkLabel(header, text="Elige tu personaje. Los bloqueados requieren monedas.", font=ctk.CTkFont(size=14), text_color=self.colors["text_muted"]).pack(anchor="w", padx=20, pady=(0, 15))
        
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent"); scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        ctk.CTkLabel(scroll, text="🔓 Avatares Básicos (Desbloqueados)", font=ctk.CTkFont(size=20, weight="bold"), text_color=self.colors["success"]).pack(anchor="w", padx=10, pady=10)
        f_bas = ctk.CTkFrame(scroll, fg_color="transparent"); f_bas.pack(fill="x", padx=10)
        f_bas.grid_columnconfigure((0, 1, 2), weight=1)
        self.crear_avatar(f_bas, "Novato", "novice_student", 0, 0, 0)
        self.crear_avatar(f_bas, "Curioso", "curious_mind", 0, 0, 1)
        self.crear_avatar(f_bas, "Lector", "fast_reader", 0, 0, 2)
        
        ctk.CTkLabel(scroll, text="🔒 Avatares Avanzados (Bloqueados)", font=ctk.CTkFont(size=20, weight="bold"), text_color=self.colors["warning"]).pack(anchor="w", padx=10, pady=(30, 10))
        f_prem = ctk.CTkFrame(scroll, fg_color="transparent"); f_prem.pack(fill="x", padx=10)
        f_prem.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.crear_avatar(f_prem, "Cyber-Ninja", "cyber_ninja", 500, 0, 0)
        self.crear_avatar(f_prem, "Hacker", "hacker_pro", 1000, 0, 1)
        self.crear_avatar(f_prem, "Hechicero", "magic_wizard", 750, 0, 2)
        self.crear_avatar(f_prem, "Robot", "battle_mech", 1500, 0, 3)
        
        self.lbl_log = ctk.CTkLabel(scroll, text="", font=ctk.CTkFont(size=16, weight="bold")); self.lbl_log.pack(pady=20)

    def cargar_img(self, seed, lbl):
        # En estudiante.py podríamos no tener generar_avatar_2d importado. 
        # Pero podemos simularlo o si falla se queda en ⌛
        try:
            from PIL import Image
            import urllib.request, io
            url = f"https://api.dicebear.com/7.x/bottts/png?seed={seed}&backgroundColor=1e293b"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            raw_data = urllib.request.urlopen(req, timeout=3).read()
            image = Image.open(io.BytesIO(raw_data)).resize((120, 120))
            img = ctk.CTkImage(light_image=image, dark_image=image, size=(120, 120))
            lbl.after(0, lambda: lbl.configure(text="", image=img))
        except: pass

    def crear_avatar(self, parent, titulo, seed, costo_c, fila, col):
        card = ctk.CTkFrame(parent, fg_color=self.colors["bg_card"], corner_radius=15); card.grid(row=fila, column=col, padx=5, pady=10, sticky="nsew")
        
        lbl_img = ctk.CTkLabel(card, text="⌛", width=100, height=100)
        lbl_img.pack(pady=(15, 5))
        import threading
        threading.Thread(target=self.cargar_img, args=(seed, lbl_img), daemon=True).start()
        
        ctk.CTkLabel(card, text=titulo, font=ctk.CTkFont(size=16, weight="bold")).pack(pady=5)
        
        if costo_c == 0:
            ctk.CTkLabel(card, text="Gratis", text_color=self.colors["success"]).pack(pady=5)
            btn_txt = "Equipar"
        else:
            ctk.CTkLabel(card, text=f"🪙 {costo_c}", text_color=self.colors["warning"]).pack(pady=5)
            btn_txt = "Desbloquear"
            
        def accionar():
            if costo_c == 0:
                self.boveda.avatar_seed = seed
                self.lbl_log.configure(text=f"✅ Avatar equipado: {titulo}", text_color=self.colors["success"])
                self.update_hud()
            else:
                exito, msg = self.boveda.comprar_item(costo_c, 0, f"Avatar {titulo}")
                if exito:
                    self.boveda.avatar_seed = seed
                    self.lbl_log.configure(text=f"✅ Desbloqueado y equipado: {titulo}", text_color=self.colors["success"])
                    self.update_hud()
                else:
                    self.lbl_log.configure(text=msg, text_color=self.colors["danger"])
                    
        ctk.CTkButton(card, text=btn_txt, fg_color=self.colors["bg_sidebar"], command=accionar).pack(pady=(10, 15), padx=10)

class ViewTienda(BaseStoreView):
    def __init__(self, master, boveda, update_hud, colors, **kwargs):
        items = [("Tarjeta de Regalo $5", 0, 50, colors["success"]), ("Entrada de Cine", 0, 100, colors["accent_2"]),
                 ("Snack / Dulce", 0, 20, colors["warning"]), ("Stickers Exclusivos", 0, 10, "#a855f7")]
        super().__init__(master, boveda, update_hud, colors, "💎 Tienda de Premios", "Recompensas fuera del colegio (Solo Diamantes)", colors["accent_1"], items, **kwargs)

class ViewMercado(BaseStoreView):
    def __init__(self, master, boveda, update_hud, colors, **kwargs):
        items = [("Pase: 10 Min Música", 100, 0, "#a855f7"), ("Inmunidad a Quiz", 300, 0, colors["danger"]),
                 ("Elegir Equipo", 200, 0, colors["success"]), ("Entrega Tarde (1 día)", 500, 0, colors["accent_2"])]
        super().__init__(master, boveda, update_hud, colors, "🛒 Mercado Escolar", "Beneficios exclusivos de clase (Solo Monedas)", colors["warning"], items, **kwargs)