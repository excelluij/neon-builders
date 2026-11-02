import customtkinter as ctk
from tkinter import messagebox, simpledialog, filedialog
import sqlite3
import webbrowser
import os
import shutil

import rutas

# Configuración de colores Neón por Materia (Estilo Colombiano / ICFES)
SUBJECT_COLORS = {
    "Matemáticas": "#00f2fe",      
    "Ciencias Naturales": "#059669", 
    "Ciencias Sociales": "#f59e0b", 
    "Lengua Castellana": "#ec4899", 
    "Inglés": "#3b82f6",           
    "Tecnología": "#a855f7"        
}

# ==============================================================================
# 🧠 INTERFAZ SECUNDARIA: LA VENTANA DE CONTENIDO ENLAZADA A LA DB
# ==============================================================================
class VentanaContenidoMateria(ctk.CTkToplevel):
    def __init__(self, master, nombre_materia, color_materia, **kwargs):
        super().__init__(master, **kwargs)
        self.title(f"NeonOS - Bóveda de {nombre_materia}")
        rutas.poner_icono(self)
        self.geometry("550x650")
        self.configure(fg_color="#14151a") 
        
        self.nombre_materia = nombre_materia
        self.color_materia = color_materia
        
        self.after(200, lambda: self.lift())
        self.focus_set()
        
        ctk.CTkLabel(
            self, 
            text=f"Área de {nombre_materia} ⚡", 
            font=ctk.CTkFont(size=22, weight="bold"), 
            text_color=color_materia
        ).pack(pady=20)
        
        self.frame_links = ctk.CTkScrollableFrame(self, width=480, height=400, fg_color="#21232d", corner_radius=15)
        self.frame_links.pack(pady=10, padx=20, fill="both", expand=True)
        
        self.btn_add = ctk.CTkButton(
            self, 
            text="+ Adjuntar Material (Canva / PPT / Archivo)", 
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=color_materia, 
            text_color="#14151a", 
            hover_color="#ffffff", 
            height=40,
            command=self.agregar_material_a_db
        )
        self.btn_add.pack(pady=20, padx=20, fill="x")
        
        self.cargar_links_desde_db()

    def cargar_links_desde_db(self):
        for widget in self.frame_links.winfo_children():
            widget.destroy()
            
        try:
            conn = sqlite3.connect('nexus_cloud_data.db')
            cursor = conn.cursor()
            # Añadimos 'tipo' para saber si es URL o Archivo
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS links_materias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    materia TEXT, 
                    titulo TEXT, 
                    link TEXT,
                    tipo TEXT DEFAULT 'url'
                )
            ''')
            # Extraemos también el ID para poder borrar (Basurita)
            cursor.execute("SELECT id, titulo, link, tipo FROM links_materias WHERE materia=?", (self.nombre_materia,))
            registros = cursor.fetchall()
            conn.close()
            
            if not registros:
                ctk.CTkLabel(
                    self.frame_links, 
                    text="No hay material adjunto todavía.\n¡Rompe la Matrix y sube el primero!", 
                    text_color="#8b8d98", 
                    font=ctk.CTkFont(size=13)
                ).pack(pady=50)
            else:
                for id_mat, titulo, link, tipo in registros:
                    self.crear_tarjeta_link(id_mat, titulo, link, tipo)
        except Exception as e:
            messagebox.showerror("Error de Bóveda", f"Colapso en la Matrix: {e}")

    def crear_tarjeta_link(self, id_mat, titulo, link, tipo):
        card = ctk.CTkFrame(self.frame_links, fg_color="#1b1d24", corner_radius=10)
        card.pack(fill="x", pady=5, padx=5)
        
        icono_tipo = "📂" if tipo == "archivo" else "🌐"
        
        ctk.CTkLabel(
            card, 
            text=f"{icono_tipo} {titulo}", 
            font=ctk.CTkFont(size=14, weight="bold"), 
            text_color="#ffffff", 
            anchor="w"
        ).pack(side="left", padx=15, pady=15)
        
        # Botón Basurita (Destruir datos)
        btn_borrar = ctk.CTkButton(
            card, 
            text="🗑️", 
            fg_color="#ff4b4b", 
            hover_color="#cc0000",
            width=40, 
            height=28, 
            command=lambda i=id_mat: self.borrar_material(i)
        )
        btn_borrar.pack(side="right", padx=(5, 15), pady=15)

        # Botón Abrir (Lanzar contenido)
        btn_abrir = ctk.CTkButton(
            card, 
            text="Abrir 🚀", 
            fg_color=self.color_materia, 
            text_color="#14151a", 
            hover_color="#ffffff", 
            width=70, 
            height=28, 
            font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda l=link: webbrowser.open(l) if tipo == "url" else os.startfile(l)
        )
        btn_abrir.pack(side="right", padx=5, pady=15)

    def borrar_material(self, id_mat):
        # Confirmación para no borrar por accidente
        confirmar = messagebox.askyesno("Alerta", "¿Seguro que quieres eliminar este material para siempre?")
        if confirmar:
            try:
                conn = sqlite3.connect('nexus_cloud_data.db')
                cursor = conn.cursor()
                cursor.execute("DELETE FROM links_materias WHERE id=?", (id_mat,))
                conn.commit()
                conn.close()
                self.cargar_links_desde_db() # Recargar la vista
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo borrar: {e}")

    def agregar_material_a_db(self):
        titulo = simpledialog.askstring("Nuevo Material", f"Escribe el título para el material de {self.nombre_materia}:")
        if not titulo: return
        
        # Le damos el poder al usuario de elegir la estrategia
        es_archivo = messagebox.askyesno("Estrategia", "¿Vas a subir un Archivo local?\n(Sí = PPT/PDF/Word | No = Link de Canva/Drive)")
        
        if es_archivo:
            ruta_origen = filedialog.askopenfilename(title="Selecciona tu archivo")
            if not ruta_origen: return
            
            # Creamos la carpeta secreta en el proyecto si no existe
            carpeta_destino = os.path.join(rutas.carpeta_app(), "materiales_neon")
            os.makedirs(carpeta_destino, exist_ok=True)
            
            # Copiamos el archivo al sistema
            nombre_archivo = os.path.basename(ruta_origen)
            ruta_final = os.path.join(carpeta_destino, nombre_archivo)
            try:
                shutil.copy(ruta_origen, ruta_final)
                link = ruta_final
                tipo = "archivo"
            except Exception as e:
                messagebox.showerror("Error", f"Fallo al copiar el archivo: {e}")
                return
        else:
            link = simpledialog.askstring("Adjuntar Enlace", "Pega el link de Canva, YouTube o Google Drive:")
            if not link: return
            tipo = "url"
        
        # 🧠 Guardamos solo el texto (Ruta o URL) en la Bóveda
        try:
            conn = sqlite3.connect('nexus_cloud_data.db')
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO links_materias (materia, titulo, link, tipo) VALUES (?, ?, ?, ?)", 
                (self.nombre_materia, titulo, link, tipo)
            )
            conn.commit()
            conn.close()
            
            self.cargar_links_desde_db()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar la información: {e}")

# ==============================================================================
# 💅 INTERFAZ PRINCIPAL: EL GRID AESTHETIC DE MATERIAS
# ==============================================================================
class ViewMaterias(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        
        self.lbl_welcome = ctk.CTkLabel(
            self, 
            text="Selecciona tu Área de Entrenamiento ⚡", 
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color="#ffffff"
        )
        self.lbl_welcome.pack(pady=(20, 30))

        self.grid_container = ctk.CTkFrame(self, fg_color="transparent")
        self.grid_container.pack(fill="both", expand=True, padx=20)

        self.renderizar_materias()

    def renderizar_materias(self):
        materias = [
            ("Matemáticas", "📐", "Cálculo, Álgebra y Lógica"),
            ("Ciencias Naturales", "🧪", "Física, Química y Biología"),
            ("Ciencias Sociales", "🌍", "Historia, Geografía y Ciudadanía"),
            ("Lengua Castellana", "📖", "Lectura Crítica y Literatura"),
            ("Inglés", "🇬🇧", "Grammar & Listening"),
            ("Tecnología", "💻", "Programación y Robótica")
        ]

        row, col = 0, 0
        for nombre, icono, desc in materias:
            color = SUBJECT_COLORS.get(nombre, "#ffffff")
            
            card = ctk.CTkFrame(self.grid_container, fg_color="#21232d", corner_radius=15, border_width=2, border_color=color)
            card.grid(row=row, column=col, padx=15, pady=15, sticky="nsew")
            
            ctk.CTkLabel(card, text=icono, font=ctk.CTkFont(size=40)).pack(pady=(20, 5))
            ctk.CTkLabel(card, text=nombre, font=ctk.CTkFont(size=18, weight="bold"), text_color=color).pack()
            ctk.CTkLabel(card, text=desc, font=ctk.CTkFont(size=12), text_color="#8b8d98").pack(pady=(5, 20))
            
            btn_entrar = ctk.CTkButton(
                card, 
                text="Iniciar Misión ⚡", 
                fg_color=color, 
                text_color="#14151a",
                hover_color="#ffffff",
                font=ctk.CTkFont(weight="bold"),
                command=lambda n=nombre: self.seleccionar_materia(n)
            )
            btn_entrar.pack(pady=(0, 20), padx=20)

            col += 1
            if col > 2: 
                col = 0
                row += 1

        for i in range(3): 
            self.grid_container.grid_columnconfigure(i, weight=1)

    def seleccionar_materia(self, nombre):
        color = SUBJECT_COLORS.get(nombre, "#ffffff")
        VentanaContenidoMateria(self, nombre, color)