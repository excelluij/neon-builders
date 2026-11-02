"""Juegos educativos de Neon OS: por grado, materia y tema (8 juegos por tema).

Cada juego se abre en su propia ventana y, al terminar, llama a
on_finish(fraccion) con un valor entre 0.0 y 1.0 (0 = abandono/sin aciertos).
La app usa esa fracción para repartir la recompensa de la misión.
"""
import random
import time
import unicodedata
import tkinter as tk
import customtkinter as ctk

BG, SIDE, CARD = "#0f172a", "#1e293b", "#334155"
OK, BAD, WARN, TXT, MUTED = "#10b981", "#ef4444", "#f59e0b", "#f8fafc", "#94a3b8"
PALETA_BURBUJAS = ["#38bdf8", "#818cf8", "#f472b6", "#fbbf24", "#34d399", "#fb7185"]

import rutas  # icono de las ventanas
import arena  # reglas del duelo y premios de la Arena
import serpiente  # motor de la Serpiente
import tetris  # motor del Tetris

# Contenido de grado 11 en banco_grado11.py
from banco_grado11 import BANCOS


# ==============================================================================
# UTILIDADES
# ==============================================================================
def _base(c):
    """Letra en mayúscula sin tilde (la Ñ se conserva)."""
    if c in "ñÑ":
        return "Ñ"
    return "".join(x for x in unicodedata.normalize("NFD", c) if unicodedata.category(x) != "Mn").upper()


FELICITACIONES = ["¡Eso es! 🎉", "¡Exacto! 🎯", "¡Muy bien! 👏", "¡Así se hace! 💪", "¡Correcto, vas volando! 🚀",
                  "¡Perfecto! ✨", "¡Qué nivel! 😎", "¡Bien pensado! 🧠"]
ANIMOS = ["No era esa, pero así se aprende 💡", "Casi. Mira cómo funciona 👀", "Buen intento, esto te sirve 💪",
          "Ojo con esta, ya la tienes 🔎"]
_ultima = {}


def _elegir(pool):
    """Una frase al azar, sin repetir la que acabamos de usar."""
    opciones = [x for x in pool if x != _ultima.get(id(pool))] or pool
    _ultima[id(pool)] = random.choice(opciones)
    return _ultima[id(pool)]


def felicitacion(racha=1):
    """Frase de aplauso; desde 3 aciertos seguidos suma el contador de racha."""
    frase = _elegir(FELICITACIONES)
    return f"🔥 ¡{racha} seguidas! {frase}" if racha >= 3 else frase


def animo():
    return _elegir(ANIMOS)


def desempacar_pregunta(item):
    """(pregunta, correcta, [malas], explicación). La explicación es opcional: '' si el banco no la trae."""
    return item[0], item[1], item[2], (item[3] if len(item) > 3 and isinstance(item[3], str) else "")


def desempacar_vf(item):
    """(afirmación, es_verdadera, explicación). La explicación es opcional."""
    return item[0], item[1], (item[2] if len(item) > 2 and isinstance(item[2], str) else "")


class JuegoBase(ctk.CTkToplevel):
    """Ventana base: cabecera, cuerpo, tarjeta de retroalimentación, temporizadores seguros y pantalla final."""

    def __init__(self, master, materia, nombre, color, on_finish, banco):
        super().__init__(master)
        self.materia, self.color, self._on_finish, self.banco = materia, color, on_finish, banco
        self.finalizado = False
        self._ids = []
        self.racha = 0
        self._id_ocultar = None
        self.title(f"{nombre} · {materia}")
        rutas.poner_icono(self)
        try:
            escala = self._get_window_scaling()  # escala de pantalla de customtkinter (p. ej. 1.25)
        except AttributeError:
            escala = 1.0
        # 760 de alto en pantallas grandes; en portátiles bajitos se recorta para que la ventana (y su botón Continuar) quepa
        self.escala = escala                    # los tk.Canvas trabajan en píxeles reales: quien los dibuje debe escalar igual
        self.alto_ventana = max(520, min(760, int(self.winfo_screenheight() / escala) - 110))
        self.geometry(f"780x{self.alto_ventana}")
        self.configure(fg_color=BG)
        self.protocol("WM_DELETE_WINDOW", self.cerrar)

        head = ctk.CTkFrame(self, fg_color=color, corner_radius=12)
        head.pack(fill="x", padx=14, pady=(14, 8))
        ctk.CTkLabel(head, text=nombre, font=ctk.CTkFont(size=17, weight="bold"), text_color="#ffffff", wraplength=520, justify="left").pack(side="left", padx=16, pady=12)
        self.lbl_estado = ctk.CTkLabel(head, text="", font=ctk.CTkFont(size=16, weight="bold"), text_color="#ffffff")
        self.lbl_estado.pack(side="right", padx=16)
        self.cuerpo = ctk.CTkFrame(self, fg_color="transparent")
        self.cuerpo.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.tarjeta = ctk.CTkFrame(self, corner_radius=14, border_width=2)  # aparece abajo solo cuando hay algo que decir

        self.after(250, self._enfocar)
        self.construir()

    # -- infraestructura -----------------------------------------------------
    def _enfocar(self):
        try:
            self.lift(); self.focus_force()
        except tk.TclError:
            pass

    def despues(self, ms, fn):
        def run():
            if not self.finalizado and self.winfo_exists():
                fn()
        i = self.after(ms, run)
        self._ids.append(i)
        return i

    def cancelar(self, i):
        try:
            self.after_cancel(i)
        except Exception:
            pass

    def limpiar(self):
        for w in self.cuerpo.winfo_children():
            w.destroy()

    # -- retroalimentación ---------------------------------------------------
    def _mostrar_tarjeta(self, fondo, borde, titulo, lineas=(), boton=None):
        """Pinta la tarjeta de abajo. boton = (texto, comando) o None."""
        if self.finalizado or not self.winfo_exists():
            return
        if self._id_ocultar:
            self.cancelar(self._id_ocultar)
            self._id_ocultar = None
        for w in self.tarjeta.winfo_children():
            w.destroy()
        self.tarjeta.configure(fg_color=fondo, border_color=borde)
        ctk.CTkLabel(self.tarjeta, text=titulo, font=ctk.CTkFont(size=18, weight="bold"), text_color="#ffffff",
                     wraplength=700, justify="left").pack(anchor="w", padx=18, pady=(12, 4 if lineas or boton else 12))
        for n, texto in enumerate(lineas):
            ultima = n == len(lineas) - 1 and not boton
            ctk.CTkLabel(self.tarjeta, text=texto, font=ctk.CTkFont(size=15), text_color=TXT,
                         wraplength=700, justify="left").pack(anchor="w", padx=18, pady=(0, 12 if ultima else 6))
        if boton:
            ctk.CTkButton(self.tarjeta, text=boton[0], height=40, width=160, fg_color=borde, command=boton[1]).pack(anchor="e", padx=18, pady=(2, 12))
        self.tarjeta.pack(side="bottom", fill="x", padx=14, pady=(0, 14), before=self.cuerpo)

    def ocultar_feedback(self):
        if self._id_ocultar:
            self.cancelar(self._id_ocultar)
            self._id_ocultar = None
        try:
            self.tarjeta.pack_forget()
        except tk.TclError:
            pass

    def feedback_acierto(self, siguiente=None, detalle="", ms=1100):
        """Felicita (con racha desde 3). Tras `ms` se oculta sola y llama a `siguiente`, si hay."""
        self.racha += 1
        self._mostrar_tarjeta("#064e3b", OK, felicitacion(self.racha), [detalle] if detalle else [])

        def listo():
            self._id_ocultar = None
            self.ocultar_feedback()
            if siguiente:
                siguiente()
        self._id_ocultar = self.despues(ms, listo)

    def feedback_fallo(self, siguiente, correcta="", explicacion="", titulo=None):
        """Aliento + respuesta correcta + explicación. No avanza solo: cada quien lee a su ritmo."""
        self.racha = 0
        lineas = ([f"✔ {correcta}"] if correcta else []) + ([f"💡 {explicacion}"] if explicacion else [])
        usado = []

        def seguir():
            if usado:
                return
            usado.append(True)
            self.ocultar_feedback()
            siguiente()
        self._mostrar_tarjeta("#450a0a", BAD, titulo or animo(), lineas, ("Continuar ▶", seguir))

    def _cerrar_partida(self):
        """Cierra la partida: oculta la tarjeta, cancela los temporizadores y limpia el cuerpo.
        Devuelve False (sin hacer nada) si ya estaba cerrada."""
        if self.finalizado:
            return False
        self.ocultar_feedback()
        self.finalizado = True
        for i in self._ids:
            self.cancelar(i)
        self.limpiar()
        self.lbl_estado.configure(text="")
        return True

    def terminar(self, fraccion, detalle=""):
        if not self._cerrar_partida():
            return
        estrellas = 3 if fraccion >= 0.9 else 2 if fraccion >= 0.6 else 1 if fraccion > 0 else 0
        ctk.CTkLabel(self.cuerpo, text="⭐" * estrellas + "☆" * (3 - estrellas), font=ctk.CTkFont(size=52)).pack(pady=(80, 10))
        ctk.CTkLabel(self.cuerpo, text=f"Resultado: {round(fraccion * 100)}%", font=ctk.CTkFont(size=28, weight="bold")).pack(pady=10)
        if detalle:
            ctk.CTkLabel(self.cuerpo, text=detalle, font=ctk.CTkFont(size=18, weight="bold"), text_color=TXT).pack(pady=(0, 6))
        msg = ("¡Excelente trabajo, así se hace! 🏆" if fraccion >= 0.9 else "¡Muy bien! Ya casi lo dominas 💪" if fraccion >= 0.6
               else "¡Buen intento! Cada práctica suma 🌱" if fraccion > 0 else "No lograste puntos esta vez. Repasa y vuelve a intentarlo: ¡sí se puede! 💪")
        ctk.CTkLabel(self.cuerpo, text=msg, font=ctk.CTkFont(size=16), text_color=MUTED, wraplength=600).pack(pady=5)
        ctk.CTkButton(self.cuerpo, text="Cerrar", height=44, width=200, fg_color=self.color, command=self.destroy).pack(pady=30)
        try:
            self._on_finish(fraccion)
        except Exception:
            pass

    def cerrar(self):
        if not self.finalizado:
            self._abandonar()
        self.destroy()

    def _abandonar(self):
        self._cerrar_partida()
        try:
            self._on_finish(0.0)
        except Exception:
            pass

    def construir(self):
        raise NotImplementedError

    def boton_opcion(self, parent, texto, comando, **kw):
        return ctk.CTkButton(parent, text=texto, height=54, corner_radius=12, fg_color=CARD, hover_color=SIDE,
                             font=ctk.CTkFont(size=16, weight="bold"), command=comando, **kw)


# ------------------------------------------------------------------------------
class QuizGame(JuegoBase):
    def construir(self):
        self.preg = random.sample(self.banco["preguntas"], min(8, len(self.banco["preguntas"])))
        self.i, self.vidas, self.aciertos = 0, 3, 0
        self.lbl_q = ctk.CTkLabel(self.cuerpo, text="", font=ctk.CTkFont(size=22, weight="bold"), wraplength=680)
        self.lbl_q.pack(pady=(40, 30))
        self.f_op = ctk.CTkFrame(self.cuerpo, fg_color="transparent")
        self.f_op.pack(fill="x", padx=40)
        self.mostrar()

    def mostrar(self):
        q, ok, malas, _ = desempacar_pregunta(self.preg[self.i])
        self.lbl_estado.configure(text=f"❤️ {self.vidas}   ✅ {self.aciertos}   {self.i + 1}/{len(self.preg)}")
        self.lbl_q.configure(text=q)
        for w in self.f_op.winfo_children():
            w.destroy()
        ops = [ok] + malas
        random.shuffle(ops)
        self.botones = []
        for o in ops:
            b = self.boton_opcion(self.f_op, o, None)
            b.configure(command=lambda b=b, o=o: self.responder(b, o))
            b.pack(fill="x", pady=7)
            self.botones.append(b)

    def responder(self, btn, op):
        _, ok, _, expl = desempacar_pregunta(self.preg[self.i])
        for b in self.botones:
            b.configure(state="disabled")
            if b.cget("text") == ok:
                b.configure(fg_color=OK)
        if op == ok:
            self.aciertos += 1
        else:
            self.vidas -= 1
            btn.configure(fg_color=BAD)
        self.lbl_estado.configure(text=f"❤️ {self.vidas}   ✅ {self.aciertos}   {self.i + 1}/{len(self.preg)}")
        if op == ok:
            self.feedback_acierto(self.avanzar)
        else:
            self.feedback_fallo(self.avanzar, f"Respuesta: {ok}", expl)

    def avanzar(self):
        self.i += 1
        if self.vidas <= 0 or self.i >= len(self.preg):
            self.terminar(self.aciertos / len(self.preg), f"Acertaste {self.aciertos} de {len(self.preg)}")
        else:
            self.mostrar()


# ------------------------------------------------------------------------------
class VFGame(JuegoBase):
    TIEMPO = 8

    def construir(self):
        self.items = random.sample(self.banco["vf"], len(self.banco["vf"]))
        self.i, self.aciertos, self.tick_id = 0, 0, None
        self.lbl_t = ctk.CTkLabel(self.cuerpo, text="", font=ctk.CTkFont(size=44, weight="bold"), text_color=WARN)
        self.lbl_t.pack(pady=(30, 10))
        self.lbl_q = ctk.CTkLabel(self.cuerpo, text="", font=ctk.CTkFont(size=22, weight="bold"), wraplength=660)
        self.lbl_q.pack(pady=20)
        f = ctk.CTkFrame(self.cuerpo, fg_color="transparent"); f.pack(pady=20)
        self.b_v = ctk.CTkButton(f, text="✅ Cierto", width=240, height=80, fg_color=OK, font=ctk.CTkFont(size=22, weight="bold"), command=lambda: self.responder(True))
        self.b_f = ctk.CTkButton(f, text="❌ Falso", width=240, height=80, fg_color=BAD, font=ctk.CTkFont(size=22, weight="bold"), command=lambda: self.responder(False))
        self.b_v.grid(row=0, column=0, padx=15); self.b_f.grid(row=0, column=1, padx=15)
        self.mostrar()

    def mostrar(self):
        self.restante = self.TIEMPO
        self.abierta = True
        self.lbl_q.configure(text=self.items[self.i][0])
        self.lbl_estado.configure(text=f"✅ {self.aciertos}   {self.i + 1}/{len(self.items)}")
        self.b_v.configure(state="normal"); self.b_f.configure(state="normal")
        self.lbl_t.configure(text=str(self.restante))
        self.tick_id = self.despues(1000, self.tick)

    def tick(self):
        self.restante -= 1
        self.lbl_t.configure(text=str(max(self.restante, 0)))
        if self.restante <= 0:
            self.responder(None)
        else:
            self.tick_id = self.despues(1000, self.tick)

    def responder(self, valor):
        if not self.abierta:
            return
        self.abierta = False
        if self.tick_id:
            self.cancelar(self.tick_id)
        self.b_v.configure(state="disabled"); self.b_f.configure(state="disabled")
        _, correcta, expl = desempacar_vf(self.items[self.i])
        era = f"Era {'Cierto' if correcta else 'Falso'}"
        if valor == correcta:
            self.aciertos += 1
            self.lbl_estado.configure(text=f"✅ {self.aciertos}   {self.i + 1}/{len(self.items)}")
            self.feedback_acierto(self.avanzar)
        elif valor is None:
            self.feedback_fallo(self.avanzar, era, expl, titulo="⏰ Se acabó el tiempo")
        else:
            self.feedback_fallo(self.avanzar, era, expl)

    def avanzar(self):
        self.i += 1
        if self.i >= len(self.items):
            self.terminar(self.aciertos / len(self.items), f"Acertaste {self.aciertos} de {len(self.items)}")
        else:
            self.mostrar()


# ------------------------------------------------------------------------------
class MemoriaGame(JuegoBase):
    def construir(self):
        pares = random.sample(self.banco["parejas"], min(6, len(self.banco["parejas"])))
        self.cartas = [(k, t) for k, (a, b) in enumerate(pares) for t in (a, b)]
        random.shuffle(self.cartas)
        self.pares = pares
        self.npares, self.encontrados, self.fallos = len(pares), 0, 0
        self.primera, self.ocupado = None, False
        self.resueltas = set()
        ctk.CTkLabel(self.cuerpo, text="Une cada término con su definición", font=ctk.CTkFont(size=16), text_color=MUTED).pack(pady=(10, 10))
        grid = ctk.CTkFrame(self.cuerpo, fg_color="transparent"); grid.pack(fill="both", expand=True)
        for c in range(4):
            grid.grid_columnconfigure(c, weight=1)
        self.botones = []
        for idx, (_, texto) in enumerate(self.cartas):
            b = ctk.CTkButton(grid, text="❓", height=110, corner_radius=12, fg_color=CARD, hover_color=SIDE,
                              font=ctk.CTkFont(size=15, weight="bold"), command=lambda i=idx: self.voltear(i))
            b._text_label.configure(wraplength=130)
            b.grid(row=idx // 4, column=idx % 4, padx=6, pady=6, sticky="nsew")
            self.botones.append(b)
        self.actualizar()

    def actualizar(self):
        self.lbl_estado.configure(text=f"Parejas {self.encontrados}/{self.npares}   Fallos {self.fallos}")

    def voltear(self, i):
        if self.ocupado or i in self.resueltas or i == self.primera:
            return
        self.botones[i].configure(text=self.cartas[i][1], fg_color=self.color)
        if self.primera is None:
            self.primera = i
            return
        j, self.primera = self.primera, None
        if self.cartas[i][0] == self.cartas[j][0]:
            self.resueltas |= {i, j}
            self.encontrados += 1
            for k in (i, j):
                self.botones[k].configure(fg_color=OK, state="disabled")
            self.actualizar()
            termino, definicion = self.pares[self.cartas[i][0]]
            self.feedback_acierto(None, f"{termino}: {definicion}", ms=1800)
            if self.encontrados == self.npares:
                self.despues(1500, lambda: self.terminar(max(0.2, 1 - 0.08 * self.fallos), f"Fallos: {self.fallos}"))
        else:
            self.fallos += 1
            self.racha = 0  # sin explicación: decir qué carta era revelaría dónde está su pareja
            self.ocupado = True
            self.actualizar()
            self.despues(900, lambda: self.ocultar(i, j))

    def ocultar(self, i, j):
        for k in (i, j):
            self.botones[k].configure(text="❓", fg_color=CARD)
        self.ocupado = False


# ------------------------------------------------------------------------------
class AhorcadoGame(JuegoBase):
    MAX_ERRORES = 6
    LETRAS = "ABCDEFGHIJKLMNÑOPQRSTUVWXYZ"

    def construir(self):
        self.rondas = random.sample(self.banco["palabras"], min(3, len(self.banco["palabras"])))
        self.r, self.ganadas = 0, 0
        self.lbl_pista = ctk.CTkLabel(self.cuerpo, text="", font=ctk.CTkFont(size=16), text_color=MUTED)
        self.lbl_pista.pack(pady=(5, 0))
        self.canvas = tk.Canvas(self.cuerpo, width=200, height=170, bg=BG, highlightthickness=0)
        self.canvas.pack(pady=5)
        self.lbl_pal = ctk.CTkLabel(self.cuerpo, text="", font=ctk.CTkFont(family="Consolas", size=34, weight="bold"))
        self.lbl_pal.pack(pady=8)
        self.teclado = ctk.CTkFrame(self.cuerpo, fg_color="transparent"); self.teclado.pack(pady=10)
        self.teclas = {}
        for n, l in enumerate(self.LETRAS):
            b = ctk.CTkButton(self.teclado, text=l, width=58, height=44, fg_color=CARD, hover_color=SIDE,
                              font=ctk.CTkFont(size=16, weight="bold"), command=lambda l=l: self.letra(l))
            b.grid(row=n // 9, column=n % 9, padx=3, pady=3)
            self.teclas[l] = b
        self.nueva_ronda()

    def nueva_ronda(self):
        self.palabra, self.pista = self.rondas[self.r]
        self.usadas, self.errores, self.activa = set(), 0, True
        self.lbl_pista.configure(text=f"Pista: {self.pista}")
        for b in self.teclas.values():
            b.configure(state="normal", fg_color=CARD)
        self.dibujar(); self.refrescar()

    def refrescar(self):
        self.lbl_pal.configure(text=" ".join(c if _base(c) in self.usadas else "_" for c in self.palabra))
        self.lbl_estado.configure(text=f"Palabra {self.r + 1}/{len(self.rondas)}   ✅ {self.ganadas}")

    def dibujar(self):
        c = self.canvas
        c.delete("all")
        for x1, y1, x2, y2 in [(20, 160, 150, 160), (50, 160, 50, 15), (50, 15, 120, 15), (120, 15, 120, 35)]:
            c.create_line(x1, y1, x2, y2, fill=MUTED, width=4)
        partes = [lambda: c.create_oval(105, 35, 135, 65, outline=TXT, width=3),
                  lambda: c.create_line(120, 65, 120, 110, fill=TXT, width=3),
                  lambda: c.create_line(120, 75, 98, 95, fill=TXT, width=3),
                  lambda: c.create_line(120, 75, 142, 95, fill=TXT, width=3),
                  lambda: c.create_line(120, 110, 100, 140, fill=TXT, width=3),
                  lambda: c.create_line(120, 110, 140, 140, fill=TXT, width=3)]
        for p in partes[:self.errores]:
            p()

    def letra(self, l):
        if not self.activa:
            return
        b = self.teclas[l]
        b.configure(state="disabled")
        self.usadas.add(l)
        if any(_base(c) == l for c in self.palabra):
            b.configure(fg_color=OK)
        else:
            b.configure(fg_color=BAD)
            self.errores += 1
            self.dibujar()
        self.refrescar()
        if all(_base(c) in self.usadas for c in self.palabra):
            self.ganadas += 1
            self.fin_ronda(True)
        elif self.errores >= self.MAX_ERRORES:
            self.fin_ronda(False)

    def fin_ronda(self, ganada):
        self.activa = False
        self.lbl_estado.configure(text=f"Palabra {self.r + 1}/{len(self.rondas)}   ✅ {self.ganadas}")
        if ganada:
            self.feedback_acierto(self.siguiente, f"{self.palabra}: {self.pista}", ms=1600)
        else:
            self.feedback_fallo(self.siguiente, f"Era: {self.palabra}", f"Pista: {self.pista}")

    def siguiente(self):
        self.r += 1
        if self.r >= len(self.rondas):
            self.terminar(self.ganadas / len(self.rondas), f"Palabras: {self.ganadas} de {len(self.rondas)}")
        else:
            self.nueva_ronda()


# ------------------------------------------------------------------------------
class SecuenciaGame(JuegoBase):
    def construir(self):
        self.rondas = random.sample(self.banco["secuencias"], min(3, len(self.banco["secuencias"])))
        self.r, self.puntaje = 0, 0.0
        self.lbl_t = ctk.CTkLabel(self.cuerpo, text="", font=ctk.CTkFont(size=22, weight="bold"), wraplength=680)
        self.lbl_t.pack(pady=(15, 5))
        ctk.CTkLabel(self.cuerpo, text="Toca los pasos en el orden correcto", font=ctk.CTkFont(size=14), text_color=MUTED).pack()
        self.f_hechos = ctk.CTkFrame(self.cuerpo, fg_color=SIDE, corner_radius=12); self.f_hechos.pack(fill="x", padx=30, pady=15)
        self.lbl_hechos = ctk.CTkLabel(self.f_hechos, text="", font=ctk.CTkFont(size=15), justify="left", wraplength=640, anchor="w")
        self.lbl_hechos.pack(fill="x", padx=15, pady=12)
        self.f_op = ctk.CTkFrame(self.cuerpo, fg_color="transparent"); self.f_op.pack(fill="x", padx=40)
        self.nueva_ronda()

    def nueva_ronda(self):
        titulo, pasos = self.rondas[self.r]
        self.pasos, self.elegidos, self.errores = pasos, [], 0
        self.lbl_t.configure(text=titulo)
        self.lbl_estado.configure(text=f"Reto {self.r + 1}/{len(self.rondas)}")
        orden = list(pasos)
        for _ in range(10):
            random.shuffle(orden)
            if orden != pasos:
                break
        for w in self.f_op.winfo_children():
            w.destroy()
        self.botones = []
        for p in orden:
            b = self.boton_opcion(self.f_op, p, None)
            b.configure(command=lambda b=b, p=p: self.elegir(b, p))
            b.pack(fill="x", pady=5)
            self.botones.append(b)
        self.pintar()

    def pintar(self):
        self.lbl_hechos.configure(text="\n".join(f"{n + 1}. {p}" for n, p in enumerate(self.elegidos)) or "(aún no eliges ningún paso)")

    def elegir(self, btn, paso):
        if paso == self.pasos[len(self.elegidos)]:
            self.elegidos.append(paso)
            btn.configure(state="disabled", fg_color=OK)
            self.pintar()
            if len(self.elegidos) == len(self.pasos):
                self.puntaje += max(0.0, 1 - 0.25 * self.errores)
                self.feedback_acierto(self.siguiente, "Orden perfecto, sin errores 🎯" if self.errores == 0 else "")
        else:
            self.errores += 1
            self.racha = 0
            btn.configure(fg_color=BAD)
            self.despues(500, lambda: btn.configure(fg_color=CARD) if btn.cget("state") != "disabled" else None)

    def siguiente(self):
        self.r += 1
        if self.r >= len(self.rondas):
            self.terminar(self.puntaje / len(self.rondas))
        else:
            self.nueva_ronda()


# ------------------------------------------------------------------------------
class BurbujasGame(JuegoBase):
    W, H, R = 740, 400, 58

    def construir(self):
        self.preg = random.sample(self.banco["preguntas"], min(8, len(self.banco["preguntas"])))
        self.i, self.vidas, self.aciertos, self.activa = 0, 3, 0, False
        self.lbl_q = ctk.CTkLabel(self.cuerpo, text="", font=ctk.CTkFont(size=20, weight="bold"), wraplength=700)
        self.lbl_q.pack(pady=(8, 8))
        self.canvas = tk.Canvas(self.cuerpo, width=self.W, height=self.H, bg=SIDE, highlightthickness=0)
        self.canvas.pack()
        self.lbl_fb = ctk.CTkLabel(self.cuerpo, text="Revienta la burbuja con la respuesta correcta", font=ctk.CTkFont(size=15, weight="bold"), text_color=MUTED)
        self.lbl_fb.pack(pady=8)
        self.nueva_pregunta()
        self.despues(30, self.mover)

    def estado(self):
        self.lbl_estado.configure(text=f"❤️ {self.vidas}   ✅ {self.aciertos}   {self.i + 1}/{len(self.preg)}")

    def nueva_pregunta(self):
        q, ok, malas, _ = desempacar_pregunta(self.preg[self.i])
        self.lbl_q.configure(text=q)
        self.estado()
        self.canvas.delete("all")
        ops = [(ok, True)] + [(m, False) for m in malas]
        random.shuffle(ops)
        xs = [95, 280, 465, 650]
        colores = random.sample(PALETA_BURBUJAS, 4)
        self.burbujas = []
        for k, ((texto, es_ok), x) in enumerate(zip(ops, xs)):
            y = self.H + self.R + random.randint(0, 120)
            tag = f"b{k}"
            self.canvas.create_oval(x - self.R, y - self.R, x + self.R, y + self.R, fill=colores[k], outline="#ffffff", width=2, tags=(tag, "oval" + tag))
            self.canvas.create_text(x, y, text=texto, width=self.R * 1.6, fill="#0f172a", font=("Segoe UI", 11, "bold"), tags=(tag, "txt" + tag))
            self.canvas.tag_bind(tag, "<Button-1>", lambda e, k=k: self.click(k))
            self.burbujas.append({"tag": tag, "y": y, "vel": random.uniform(1.3, 2.1), "ok": es_ok})
        self.activa = True

    def mover(self):
        if self.activa:
            for b in self.burbujas:
                b["y"] -= b["vel"]
                self.canvas.move(b["tag"], 0, -b["vel"])
                if b["ok"] and b["y"] < -self.R:
                    self.activa = False
                    self.vidas -= 1
                    self.estado()
                    _, ok, _, expl = desempacar_pregunta(self.preg[self.i])
                    self.feedback_fallo(self.siguiente, f"Respuesta: {ok}", expl, titulo="💨 Se escapó la correcta")
                    break
        self.despues(30, self.mover)

    def click(self, k):
        if not self.activa:
            return
        self.activa = False
        b = self.burbujas[k]
        _, ok, _, expl = desempacar_pregunta(self.preg[self.i])
        if b["ok"]:
            self.aciertos += 1
            self.canvas.itemconfig("oval" + b["tag"], fill=OK)
            self.estado()
            self.feedback_acierto(self.siguiente)
        else:
            self.vidas -= 1
            self.canvas.itemconfig("oval" + b["tag"], fill=BAD)
            for o in self.burbujas:
                if o["ok"]:
                    self.canvas.itemconfig("oval" + o["tag"], fill=OK)
            self.estado()
            self.feedback_fallo(self.siguiente, f"Respuesta: {ok}", expl)

    def siguiente(self):
        self.i += 1
        if self.vidas <= 0 or self.i >= len(self.preg):
            self.terminar(self.aciertos / len(self.preg), f"Acertaste {self.aciertos} de {len(self.preg)}")
        else:
            self.nueva_pregunta()


# ------------------------------------------------------------------------------
class AdivinaGame(QuizGame):
    """Se lee la definición y se elige el término. Reutiliza las parejas del tema."""

    def construir(self):
        pares = self.banco["parejas"]
        preg = []
        for termino, definicion in pares:
            otros = [t for t, _ in pares if t != termino]
            preg.append((f"¿Qué término corresponde a esta definición?\n«{definicion}»", termino,
                         random.sample(otros, min(3, len(otros))), f"«{termino}»: {definicion}"))
        self.banco = dict(self.banco, preguntas=preg)
        super().construir()


# ------------------------------------------------------------------------------
class CazadorGame(JuegoBase):
    """Entre 6 afirmaciones hay que marcar las FALSAS y luego revisar."""

    def construir(self):
        vf = self.banco["vf"]
        falsas = [v for v in vf if not v[1]]
        verdaderas = [v for v in vf if v[1]]
        random.shuffle(falsas); random.shuffle(verdaderas)
        falsas = falsas[:3]
        self.items = falsas + verdaderas[:6 - len(falsas)]
        random.shuffle(self.items)
        self.marcadas, self.revisado, self.fallidas = set(), False, set()
        ctk.CTkLabel(self.cuerpo, text="Marca las afirmaciones FALSAS y presiona Revisar", font=ctk.CTkFont(size=17, weight="bold"), text_color=WARN).pack(pady=(10, 12))
        self.botones = []
        for i, item in enumerate(self.items):
            texto = item[0]
            b = ctk.CTkButton(self.cuerpo, text=texto, height=58, corner_radius=12, fg_color=CARD, hover_color=SIDE,
                              anchor="w", font=ctk.CTkFont(size=15, weight="bold"), command=lambda i=i: self.alternar(i))
            b._text_label.configure(wraplength=640, justify="left")
            b.pack(fill="x", padx=20, pady=5)
            self.botones.append(b)
        self.btn_rev = ctk.CTkButton(self.cuerpo, text="Revisar 🔍", height=46, width=220, fg_color=self.color, command=self.revisar)
        self.btn_rev.pack(pady=14)
        self.estado()

    def estado(self):
        self.lbl_estado.configure(text=f"🚩 Marcadas: {len(self.marcadas)}")

    def alternar(self, i):
        if self.revisado:
            self.explicar(i)
            return
        if i in self.marcadas:
            self.marcadas.discard(i)
            self.botones[i].configure(fg_color=CARD, text=self.items[i][0])
        else:
            self.marcadas.add(i)
            self.botones[i].configure(fg_color="#b45309", text="🚩 " + self.items[i][0])
        self.estado()

    def revisar(self):
        self.revisado = True
        aciertos = 0
        for i, item in enumerate(self.items):
            texto, verdadera, _ = desempacar_vf(item)
            correcto = (not verdadera) == (i in self.marcadas)
            aciertos += correcto
            if not correcto:
                self.fallidas.add(i)
            nota = "era VERDADERA" if verdadera else "era FALSA"
            self.botones[i].configure(fg_color=OK if correcto else BAD, text=f"{'✅' if correcto else '❌'} {texto}  ({nota})")
        self.lbl_estado.configure(text=f"✅ {aciertos}/{len(self.items)}")
        self.btn_rev.configure(text="Ver resultado", command=lambda: self.terminar(aciertos / len(self.items), f"Acertaste {aciertos} de {len(self.items)}"))
        if aciertos == len(self.items):
            self.feedback_acierto(None, "¡Ojo de águila, no se te escapó ninguna! 🦅", ms=3000)
        else:
            self._mostrar_tarjeta("#422006", WARN, "Toca cualquier afirmación para ver por qué 💡")

    def explicar(self, i):
        """Después de revisar: tocar una afirmación muestra por qué era verdadera o falsa."""
        _, verdadera, expl = desempacar_vf(self.items[i])
        era = "VERDADERA" if verdadera else "FALSA"
        lineas = [f"💡 {expl}"] if expl else []
        if i in self.fallidas:
            self._mostrar_tarjeta("#450a0a", BAD, f"❌ Era {era}", lineas)
        else:
            self._mostrar_tarjeta("#064e3b", OK, f"✅ Bien: era {era}", lineas)


# ------------------------------------------------------------------------------
class PartidaArena(JuegoBase):
    """Base de las partidas de la Arena (duelo, serpiente, Tetris): abandono, pantalla final y botones.
    on_finish recibe el resultado de la partida, o lo que devuelva _resultado_al_cerrar() si se cierra la ventana."""
    AUTOTICK = True  # temporizadores reales; las pruebas lo apagan para controlar el tiempo a mano

    def __init__(self, master, materia, nombre, color, on_finish, banco, on_revancha=None, corazones=None):
        # estos atributos van antes de super().__init__ porque JuegoBase.__init__ llama a construir()
        self._on_revancha, self._corazones = on_revancha, corazones or (lambda: 0)
        self._autotick = self.AUTOTICK
        self.resultado_final = None
        try:
            super().__init__(master, materia, nombre, color, on_finish, banco)
        except Exception:
            # si construir() falla la ventana ya existe: no debe quedar abierta, ni avisar de nada al cerrarse
            self.finalizado = True
            try:
                self.destroy()
            except Exception:
                pass
            raise

    def _resultado_al_cerrar(self):
        """Lo que se entrega a on_finish si el estudiante cierra la ventana a mitad de partida."""
        return None

    def _abandonar(self):
        resultado = self._resultado_al_cerrar()
        self._cerrar_partida()
        self.resultado_final = resultado
        try:
            self._on_finish(resultado)
        except Exception:
            pass

    def _pantalla_final(self, titulo, mensaje, lineas, etiqueta_revancha, resultado):
        """Cierra la partida y dibuja la pantalla final. `lineas` es una lista de (texto, tamaño, color o None)."""
        if not self._cerrar_partida():
            return
        self.resultado_final = resultado
        ctk.CTkLabel(self.cuerpo, text=titulo, font=ctk.CTkFont(size=40, weight="bold")).pack(pady=(50, 8))
        for texto, tamano, color in lineas:
            ctk.CTkLabel(self.cuerpo, text=texto, font=ctk.CTkFont(size=tamano, weight="bold"), text_color=color or TXT).pack(pady=4)
        ctk.CTkLabel(self.cuerpo, text=mensaje, font=ctk.CTkFont(size=16), text_color=MUTED, wraplength=600).pack(pady=4)
        restantes = self._corazones()
        activo = restantes > 0 and self._on_revancha is not None
        fila = ctk.CTkFrame(self.cuerpo, fg_color="transparent")
        fila.pack(pady=22)
        ctk.CTkButton(fila, text=etiqueta_revancha, height=44, width=210, fg_color=self.color if activo else CARD,
                      state="normal" if activo else "disabled", command=lambda: self._on_revancha()).grid(row=0, column=0, padx=8)
        ctk.CTkButton(fila, text="Cambiar de dinámica", height=44, width=210, fg_color=CARD, command=self.destroy).grid(row=0, column=1, padx=8)
        ctk.CTkLabel(self.cuerpo, text=arena.corazones_texto(restantes) if restantes > 0 else "Sin corazones: vuelven mañana",
                     font=ctk.CTkFont(size=16), text_color=MUTED).pack()
        try:
            self._on_finish(resultado)
        except Exception:
            pass


# ------------------------------------------------------------------------------
class DueloGame(PartidaArena):
    """Duelo de preguntas contra un robot (Arena): 100 PV cada uno y 2 minutos de tiempo activo.
    Las reglas viven en arena.Duelo; aquí solo está la ventana. No está en TIPOS: no es una misión del profesor.
    on_finish recibe "victoria", "empate", "derrota" o "abandono" (cierre de la ventana)."""
    GUARDA_CLIC = 0.3  # segundos tras abrir una ronda en que se ignoran los clics: el 2.º clic de un doble clic en Continuar cae sobre la pregunta nueva

    def __init__(self, master, materia, nombre, color, on_finish, banco, on_revancha=None, corazones=None, rng=None):
        self._rng, self._guarda = rng, self.GUARDA_CLIC     # antes de super().__init__: construir() los usa
        super().__init__(master, materia, nombre, color, on_finish, banco, on_revancha, corazones)

    def construir(self):
        self.duelo = arena.Duelo(self.banco["preguntas"], self._rng)
        self.pregunta_abierta, self.t_pregunta, self.robot, self._actual, self.botones = False, 0, None, None, []
        self.resultado_final = None
        marcador = ctk.CTkFrame(self.cuerpo, fg_color=SIDE, corner_radius=12)
        marcador.pack(fill="x", pady=(4, 6))
        marcador.grid_columnconfigure((0, 1), weight=1, uniform="pv")
        self.lbl_pv_jugador = ctk.CTkLabel(marcador, text="", font=ctk.CTkFont(size=15, weight="bold"))
        self.lbl_pv_jugador.grid(row=0, column=0, sticky="w", padx=14, pady=(8, 2))
        self.barra_jugador = ctk.CTkProgressBar(marcador, progress_color=OK, height=14)
        self.barra_jugador.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))
        self.lbl_pv_robot = ctk.CTkLabel(marcador, text="", font=ctk.CTkFont(size=15, weight="bold"))
        self.lbl_pv_robot.grid(row=0, column=1, sticky="w", padx=14, pady=(8, 2))
        self.barra_robot = ctk.CTkProgressBar(marcador, progress_color=BAD, height=14)
        self.barra_robot.grid(row=1, column=1, sticky="ew", padx=14, pady=(0, 10))
        self.lbl_t = ctk.CTkLabel(self.cuerpo, text="", font=ctk.CTkFont(size=34, weight="bold"), text_color=WARN)
        self.lbl_t.pack(pady=(4, 0))
        self.lbl_q = ctk.CTkLabel(self.cuerpo, text="", font=ctk.CTkFont(size=20, weight="bold"), wraplength=680)
        self.lbl_q.pack(pady=(6, 10))
        self.f_op = ctk.CTkFrame(self.cuerpo, fg_color="transparent")
        self.f_op.pack(fill="x", padx=40)
        self._refrescar_marcador()
        self._abrir_ronda()
        if self._autotick:
            self.despues(1000, self._tick)

    # -- pantalla ---------------------------------------------------------------
    def _refrescar_marcador(self):
        for lbl, barra, nombre, pv in ((self.lbl_pv_jugador, self.barra_jugador, "🧑 Tú", self.duelo.pv_jugador),
                                       (self.lbl_pv_robot, self.barra_robot, "🤖 Rival", self.duelo.pv_robot)):
            lbl.configure(text=f"{nombre}   {pv}/{arena.PV_INICIAL}")
            barra.set(pv / arena.PV_INICIAL)

    def _refrescar_reloj(self):
        self.lbl_estado.configure(text=f"⏱ {int(self.duelo.tiempo_restante)} s   Ronda {self.duelo.ronda}/{len(self.duelo.preguntas)}")
        self.lbl_t.configure(text=str(max(0, arena.TIEMPO_RONDA - self.t_pregunta)))

    # -- una ronda ----------------------------------------------------------------
    def _abrir_ronda(self):
        item = self.duelo.siguiente_pregunta()
        if item is None:
            self._fin()
            return
        self._actual = desempacar_pregunta(item)
        q, ok, malas, _ = self._actual
        self.robot = self.duelo.jugada_robot()    # lo que hará el robot se sortea ahora; el jugador no lo ve
        self.t_pregunta, self.pregunta_abierta = 0, True
        self.lbl_q.configure(text=q)
        for w in self.f_op.winfo_children():
            w.destroy()
        opciones = [ok] + list(malas)
        random.shuffle(opciones)
        self.botones = []
        for o in opciones:
            b = self.boton_opcion(self.f_op, o, None)
            b.configure(command=lambda b=b, o=o: self.responder(b, o))
            b.pack(fill="x", pady=6)
            self.botones.append(b)
        self._refrescar_reloj()
        self._no_antes_de = time.monotonic() + self._guarda   # cuenta desde que las opciones ya están en pantalla

    def responder(self, btn, opcion):
        if not self.pregunta_abierta or self.finalizado or time.monotonic() < self._no_antes_de:
            return                                          # un segundo clic (o uno recién abierta la ronda) no cuenta
        self._resolver(opcion == self._actual[1], float(self.t_pregunta), btn)

    def _resolver(self, correcta, t, btn=None, tiempo_agotado=False):
        self.pregunta_abierta = False
        _, ok, _, expl = self._actual
        for b in self.botones:
            b.configure(state="disabled")
            if b.cget("text") == ok:
                b.configure(fg_color=OK)
        if btn is not None and not correcta:
            btn.configure(fg_color=BAD)
        quien, dano = self.duelo.resolver(correcta, t, self.robot)
        self._refrescar_marcador()
        if correcta:
            nota = f"¡Golpe! −{dano} PV al rival" if quien == "jugador" else f"El rival fue más rápido y te golpea −{dano} PV"
            self.feedback_acierto(self._siguiente, nota)
            return
        golpe = f"el rival te golpea −{dano} PV" if quien == "robot" else ""
        if tiempo_agotado:
            titulo = "Se acabó el tiempo" + (f": {golpe}" if golpe else "")
        else:
            titulo = f"El rival te golpea −{dano} PV" if golpe else None
        self.feedback_fallo(self._siguiente, f"Respuesta: {ok}", expl, titulo)

    def _siguiente(self):
        if self.duelo.terminado:
            self._fin()
        else:
            self._abrir_ronda()

    def _tick(self):
        """Pasa un segundo. Solo cuenta con una pregunta abierta: leer la tarjeta de feedback no gasta tiempo."""
        if self.finalizado:
            return
        if self.pregunta_abierta:
            self.t_pregunta += 1
            self.duelo.gastar_tiempo(1)
            self._refrescar_reloj()
            if self.duelo.terminado:                        # se acabó el reloj del duelo
                self.pregunta_abierta = False
                self._fin()
                return
            if self.t_pregunta >= arena.TIEMPO_RONDA:      # sin responder: cuenta como fallo
                self._resolver(False, float(arena.TIEMPO_RONDA), tiempo_agotado=True)
        if self._autotick:
            self.despues(1000, self._tick)

    # -- final ----------------------------------------------------------------------
    def _fin(self):
        resultado = self.duelo.resultado()
        self.pregunta_abierta = False
        titulo, mensaje = {"victoria": ("🏆 ¡Victoria!", "¡Así se hace! Ganaste el duelo."),
                           "empate": ("🤝 Empate", "¡Muy parejo! Nadie pudo con nadie."),
                           "derrota": ("💪 ¡Casi!", "Buen duelo. Cada partida te hace más fuerte: ¡a la revancha!")}[resultado]
        self._pantalla_final(titulo, mensaje, [(f"Tú {self.duelo.pv_jugador} PV  ·  Rival {self.duelo.pv_robot} PV", 18, None),
                                               (f"Premio: +{arena.premio(resultado)} 🪙", 22, WARN)], "Revancha (−1 ❤️)", resultado)

    def _resultado_al_cerrar(self):
        """Cerrar la ventana a mitad de partida es abandono, pero si el duelo ya estaba decidido (falta solo la
        pantalla final) se entrega su resultado real: el premio ya estaba ganado."""
        return self.duelo.resultado() if self.duelo.terminado else "abandono"


# ------------------------------------------------------------------------------
class SerpienteGame(PartidaArena):
    """Serpiente clásica de la Arena: 20 × 20, un paso cada 0,14 s y 2 minutos de reloj. El puntaje son las frutas.
    No es una misión del profesor. on_finish recibe el puntaje (entero) o None si se cierra la ventana a mitad."""
    PASO_MS = 140
    CELDA_MAX = 24
    LADO = 20
    TECLAS = {"Up": "arriba", "w": "arriba", "W": "arriba", "Down": "abajo", "s": "abajo", "S": "abajo",
              "Left": "izq", "a": "izq", "A": "izq", "Right": "der", "d": "der", "D": "der"}

    def __init__(self, master, materia, nombre, color, on_finish, banco, on_revancha=None, corazones=None, record=0, rng=None):
        self._record, self._rng = record, rng          # antes de super().__init__: construir() los usa
        super().__init__(master, materia, nombre, color, on_finish, banco, on_revancha, corazones)

    def construir(self):
        self.juego = serpiente.Serpiente(self.LADO, self.LADO, self._rng)
        self.tiempo_restante = arena.ARCADE_TIEMPO
        self.celda = max(12, min(self.CELDA_MAX, (self.alto_ventana - 150) // self.LADO))
        self.celda_px = max(1, int(self.celda * self.escala))   # tamaño real en píxeles de cada celda
        lado = self.celda_px * self.LADO
        self.canvas = tk.Canvas(self.cuerpo, width=lado, height=lado, bg=SIDE, highlightthickness=0)
        self.canvas.pack(pady=8)
        self.canvas.bind("<Button-1>", lambda e: self.focus_force())
        self.bind("<KeyPress>", lambda e: self.tecla(e.keysym))
        self._dibujar()
        if self._autotick:
            self.despues(self.PASO_MS, self._paso)
            self.despues(1000, self._tick)

    def _dibujar(self):
        c, k = self.canvas, self.celda_px
        c.delete("all")
        if self.juego.comida is not None:
            x, y = self.juego.comida
            c.create_oval(x * k + 3, y * k + 3, (x + 1) * k - 3, (y + 1) * k - 3, fill=BAD, outline="")
        for i, (x, y) in enumerate(self.juego.cuerpo):
            c.create_rectangle(x * k + 1, y * k + 1, (x + 1) * k - 1, (y + 1) * k - 1, fill="#a7f3d0" if i == 0 else OK, outline="")
        self.lbl_estado.configure(text=f"⏱ {self.tiempo_restante} s   🍎 {self.juego.puntaje}   🏅 Récord: {self._record}")

    def tecla(self, nombre):
        if self.finalizado:
            return
        direccion = self.TECLAS.get(nombre)
        if direccion:
            self.juego.girar(direccion)

    def _paso(self):
        if self.finalizado:
            return
        self.juego.paso()
        if not self.juego.viva:
            self._fin("¡Llenaste el tablero!" if self.juego.comida is None else "Chocaste")
            return
        self._dibujar()
        if self._autotick:
            self.despues(self.PASO_MS, self._paso)

    def _tick(self):
        if self.finalizado:
            return
        self.tiempo_restante -= 1
        if self.tiempo_restante <= 0:
            self._fin("Se acabó el tiempo")
            return
        self._dibujar()
        if self._autotick:
            self.despues(1000, self._tick)

    def _fin(self, motivo):
        puntaje = self.juego.puntaje
        nuevo = puntaje > self._record and puntaje > 0
        self._pantalla_final("🐍 ¡Buena partida!", "¡Superaste tu mejor marca!" if nuevo else "¡Buen intento! ¿Quieres superar tu récord?",
                             [(motivo, 18, MUTED), (f"Frutas: {puntaje}", 26, None), (f"Premio: +{arena.premio_arcade('serpiente', puntaje)} 🪙", 22, WARN),
                              ("🏅 ¡Nuevo récord!" if nuevo else f"Récord: {self._record}", 16, OK if nuevo else MUTED)],
                             "Jugar otra (−1 ❤️)", puntaje)


# ------------------------------------------------------------------------------
class TetrisGame(PartidaArena):
    """Tetris clásico de la Arena: 10 × 20, gravedad que acelera con las líneas y 2 minutos de reloj.
    El puntaje son las líneas completadas. on_finish recibe el puntaje (entero) o None si se cierra la ventana a mitad.
    Teclas: ← → mueven, ↑ rota, ↓ baja una fila, Espacio deja caer la pieza."""
    CELDA_MAX = 28
    COLORES = {"I": "#38bdf8", "O": "#fbbf24", "T": "#a78bfa", "S": "#34d399", "Z": "#fb7185", "J": "#60a5fa", "L": "#fb923c"}

    def __init__(self, master, materia, nombre, color, on_finish, banco, on_revancha=None, corazones=None, record=0, rng=None):
        self._record, self._rng = record, rng          # antes de super().__init__: construir() los usa
        super().__init__(master, materia, nombre, color, on_finish, banco, on_revancha, corazones)

    def construir(self):
        self.juego = tetris.Tetris(self._rng)
        self.tiempo_restante = arena.ARCADE_TIEMPO
        self._id_gravedad = None
        self.celda = max(12, min(self.CELDA_MAX, (self.alto_ventana - 150) // tetris.ALTO))
        self.celda_px = max(1, int(self.celda * self.escala))   # tamaño real en píxeles de cada celda
        fila = ctk.CTkFrame(self.cuerpo, fg_color="transparent")
        fila.pack(pady=8)
        self.canvas = tk.Canvas(fila, width=self.celda_px * tetris.ANCHO, height=self.celda_px * tetris.ALTO, bg=SIDE, highlightthickness=0)
        self.canvas.pack(side="left", padx=(0, 18))
        lateral = ctk.CTkFrame(fila, fg_color="transparent")
        lateral.pack(side="left", anchor="n")
        ctk.CTkLabel(lateral, text="Siguiente", font=ctk.CTkFont(size=14, weight="bold"), text_color=MUTED).pack()
        self.canvas_sig = tk.Canvas(lateral, width=self.celda_px * 4, height=self.celda_px * 4, bg=SIDE, highlightthickness=0)
        self.canvas_sig.pack(pady=8)
        self.lbl_lineas = ctk.CTkLabel(lateral, text="", font=ctk.CTkFont(size=20, weight="bold"))
        self.lbl_lineas.pack(pady=12)
        self.canvas.bind("<Button-1>", lambda e: self.focus_force())
        self.bind("<KeyPress>", lambda e: self.tecla(e.keysym))
        self._dibujar()
        if self._autotick:
            self._programar_gravedad()
            self.despues(1000, self._tick)

    # -- dibujo -----------------------------------------------------------------------
    def _celda(self, canvas, x, y, tipo):
        k = self.celda_px
        canvas.create_rectangle(x * k + 1, y * k + 1, (x + 1) * k - 1, (y + 1) * k - 1, fill=self.COLORES[tipo], outline="")

    def _dibujar(self):
        self.canvas.delete("all")
        for y, fila in enumerate(self.juego.tablero):
            for x, tipo in enumerate(fila):
                if tipo is not None:
                    self._celda(self.canvas, x, y, tipo)
        for x, y in self.juego.celdas_pieza():
            self._celda(self.canvas, x, y, self.juego.pieza.tipo)
        self.canvas_sig.delete("all")
        for x, y in tetris.celdas_de(self.juego.siguiente, 0, 0, 0):
            self._celda(self.canvas_sig, x, y, self.juego.siguiente)
        self.lbl_lineas.configure(text=f"Líneas\n{self.juego.lineas}")
        self.lbl_estado.configure(text=f"⏱ {self.tiempo_restante} s   📏 {self.juego.lineas}   🏅 Récord: {self._record}")

    # -- gravedad y reloj -----------------------------------------------------------------
    def _programar_gravedad(self):
        self._id_gravedad = self.despues(int(self.juego.intervalo() * 1000), self._paso)

    def _reiniciar_gravedad(self):
        """Tras bajar a mano, la gravedad vuelve a esperar un intervalo completo."""
        if not self._autotick:
            return
        if self._id_gravedad is not None:
            self.cancelar(self._id_gravedad)
        self._programar_gravedad()

    def _revisar_fin(self):
        if self.juego.terminado:
            self._fin("Te quedaste sin espacio")
            return True
        return False

    def _paso(self):
        if self.finalizado:
            return
        self.juego.bajar()
        if self._revisar_fin():
            return
        self._dibujar()
        if self._autotick:
            self._programar_gravedad()

    def _tick(self):
        if self.finalizado:
            return
        self.tiempo_restante -= 1
        if self.tiempo_restante <= 0:
            self._fin("Se acabó el tiempo")
            return
        self._dibujar()
        if self._autotick:
            self.despues(1000, self._tick)

    # -- teclas y final -----------------------------------------------------------------------
    def tecla(self, nombre):
        if self.finalizado:
            return
        juego = self.juego
        if nombre == "Left":
            juego.mover(-1)
        elif nombre == "Right":
            juego.mover(1)
        elif nombre == "Up":
            juego.rotar()
        elif nombre == "Down":
            juego.bajar()
            self._reiniciar_gravedad()
        elif nombre == "space":
            juego.caida_instantanea()
            self._reiniciar_gravedad()
        else:
            return
        if not self._revisar_fin():
            self._dibujar()

    def _fin(self, motivo):
        puntaje = self.juego.lineas
        nuevo = puntaje > self._record and puntaje > 0
        self._pantalla_final("🧱 ¡Buena partida!", "¡Superaste tu mejor marca!" if nuevo else "¡Buen intento! ¿Quieres superar tu récord?",
                             [(motivo, 18, MUTED), (f"Líneas: {puntaje}", 26, None), (f"Premio: +{arena.premio_arcade('tetris', puntaje)} 🪙", 22, WARN),
                              ("🏅 ¡Nuevo récord!" if nuevo else f"Récord: {self._record}", 16, OK if nuevo else MUTED)],
                             "Jugar otra (−1 ❤️)", puntaje)


# ==============================================================================
# CATÁLOGO PÚBLICO
# ==============================================================================
TIPOS = {
    "quiz": ("🧠", "Quiz Relámpago", "Preguntas de opción múltiple. Tienes 3 vidas.", QuizGame),
    "vf": ("⚡", "Cierto o Falso", "Decide rápido: 8 segundos por afirmación.", VFGame),
    "memoria": ("🃏", "Memoria de Parejas", "Une cada término con su definición.", MemoriaGame),
    "ahorcado": ("🔤", "Ahorcado", "Adivina 3 palabras usando la pista.", AhorcadoGame),
    "secuencia": ("🔢", "Ordena los Pasos", "Toca los pasos en el orden correcto.", SecuenciaGame),
    "burbujas": ("🫧", "Burbujas", "Revienta la burbuja con la respuesta correcta antes de que se escape.", BurbujasGame),
    "adivina": ("🕵️", "Adivina el Término", "Lee la definición y elige el término correcto.", AdivinaGame),
    "cazador": ("🎯", "Cazador de Errores", "Encuentra las afirmaciones falsas.", CazadorGame),
}

GRADOS = sorted(BANCOS, key=int)  # grados con contenido, p. ej. ["11"]


def etiqueta_grado(grado):
    return f"{grado}°"


def temas_de(grado, materia):
    return list(BANCOS.get(grado, {}).get(materia, {}))


def info_tipo(juego_id):
    ic, nom, desc, _ = TIPOS[juego_id]
    return {"id": juego_id, "icono": ic, "nombre": nom, "desc": desc}


def juegos_de(tema):
    """Los 8 juegos disponibles para un tema (todos usan solo el contenido de ese tema)."""
    return [{"id": t, "icono": ic, "nombre": f"{nom}: {tema}", "desc": desc} for t, (ic, nom, desc, _) in TIPOS.items()]


def lanzar_juego(master, grado, materia, tema, juego_id, color, on_finish, banco=None):
    """Abre el juego en una ventana nueva. on_finish(fraccion 0..1) al terminar.
    banco: contenido personalizado por el profesor; si no hay, se usa el del tema."""
    banco = banco or BANCOS.get(grado, {}).get(materia, {}).get(tema)
    if not banco or juego_id not in TIPOS:
        return None
    ic, nom, _, clase = TIPOS[juego_id]
    return clase(master, materia, f"{nom}: {tema}", color, on_finish, banco)


def lanzar_duelo(master, materia, pool, color, on_finish, on_revancha=None, corazones=None, rng=None):
    """Abre un duelo de la Arena con las preguntas de `pool`. on_finish(resultado) al terminar o abandonar;
    corazones() devuelve cuántos quedan (activa o desactiva la revancha)."""
    return DueloGame(master, materia, "Duelo de preguntas", color, on_finish, {"preguntas": pool}, on_revancha, corazones, rng)


def lanzar_serpiente(master, color, on_finish, on_revancha=None, corazones=None, record=0, rng=None):
    """Abre la Serpiente de la Arena. on_finish(puntaje) al terminar, o on_finish(None) si se abandona;
    record es el mejor puntaje del estudiante (para avisar de un récord nuevo)."""
    return SerpienteGame(master, "Arena", "Serpiente", color, on_finish, {}, on_revancha, corazones, record, rng)


def lanzar_tetris(master, color, on_finish, on_revancha=None, corazones=None, record=0, rng=None):
    """Abre el Tetris de la Arena. on_finish(líneas) al terminar, o on_finish(None) si se abandona;
    record es el mejor puntaje del estudiante (para avisar de un récord nuevo)."""
    return TetrisGame(master, "Arena", "Tetris", color, on_finish, {}, on_revancha, corazones, record, rng)
