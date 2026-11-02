"""IA local y gratuita para Neon OS.

Usa Ollama (https://ollama.com, gratis, corre en el computador y sin internet) si está
instalado y con un modelo descargado. Si no lo está, todo sigue funcionando en "modo básico":
  - Profesor: comandos sencillos ("quita la palabra X", "cambia A por B", "agrega palabra ...").
  - Estudiante: el tutor busca en los apuntes de los temas de la materia.

Para activar la IA completa:   ollama pull qwen2.5:3b     (o llama3.2:3b)
Modelo fijo opcional: variable de entorno NEON_MODELO.
"""
import copy
import json
import os
import queue
import re
import threading
import time
import unicodedata

import requests

HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
if not HOST.startswith("http"):
    HOST = "http://" + HOST
PREFERIDOS = ["qwen2.5:3b", "llama3.2:3b", "llama3.2", "qwen2.5", "gemma2", "phi3", "mistral", "llama3"]
_cache = {"t": 0.0, "m": None}


def norm(t):
    """Minúsculas y sin tildes, para comparar textos."""
    return "".join(c for c in unicodedata.normalize("NFD", str(t)) if unicodedata.category(c) != "Mn").lower().strip()


# ==============================================================================
# CONEXIÓN CON OLLAMA
# ==============================================================================
def modelo_disponible(forzar=False):
    """Nombre del modelo instalado en Ollama o None si no hay IA local lista."""
    if not forzar and time.time() - _cache["t"] < 15:
        return _cache["m"]
    modelo = None
    try:
        nombres = [m["name"] for m in requests.get(HOST + "/api/tags", timeout=1.5).json().get("models", [])]
        pedido = os.environ.get("NEON_MODELO")
        if pedido and pedido in nombres:
            modelo = pedido
        else:
            for pref in PREFERIDOS:
                modelo = next((n for n in nombres if n.startswith(pref)), None)
                if modelo:
                    break
            modelo = modelo or (nombres[0] if nombres else None)
    except (requests.RequestException, ValueError, KeyError):
        modelo = None
    _cache.update(t=time.time(), m=modelo)
    return modelo


def estado_texto():
    m = modelo_disponible()
    return f"🟢 IA local activa ({m})" if m else "🟡 Modo básico (sin IA instalada). Instala Ollama para la IA completa."


def _chat(mensajes, formato_json=False, timeout=180):
    modelo = modelo_disponible()
    if not modelo:
        raise RuntimeError("Sin modelo de IA local")
    cuerpo = {"model": modelo, "messages": mensajes, "stream": False, "options": {"temperature": 0.3}}
    if formato_json:
        cuerpo["format"] = "json"
    r = requests.post(HOST + "/api/chat", json=cuerpo, timeout=timeout)
    r.raise_for_status()
    return r.json()["message"]["content"]


def en_hilo(widget, trabajo, listo):
    """Ejecuta trabajo() en un hilo y llama listo(resultado, error) en el hilo de la interfaz."""
    q = queue.Queue()

    def correr():
        try:
            q.put((trabajo(), None))
        except Exception as e:  # noqa: BLE001 - se informa a la interfaz
            q.put((None, e))

    def revisar():
        try:
            if not widget.winfo_exists():
                return
            res, err = q.get_nowait()
        except queue.Empty:
            try:
                widget.after(150, revisar)
            except Exception:
                pass
            return
        listo(res, err)

    threading.Thread(target=correr, daemon=True).start()
    widget.after(150, revisar)


# ==============================================================================
# VALIDACIÓN Y EDICIÓN DE UN JUEGO (banco de contenido de un tema)
# ==============================================================================
MINIMOS = {"preguntas": 4, "vf": 4, "parejas": 4, "palabras": 1, "secuencias": 1}
NOMBRES = {"preguntas": "preguntas", "vf": "verdadero/falso", "parejas": "parejas término–definición",
           "palabras": "palabras del ahorcado", "secuencias": "secuencias"}


def validar_banco(b):
    """Lista de problemas; vacía si el contenido sirve para los 8 juegos."""
    p = []
    for k, n in MINIMOS.items():
        if len(b.get(k, [])) < n:
            p.append(f"quedarían menos de {n} en «{NOMBRES[k]}»")
    for q in b.get("preguntas", []):  # (pregunta, correcta, [3 malas]) + explicación opcional
        if len(q) not in (3, 4) or len(q[2]) != 3 or len({q[1], *q[2]}) != 4 or (len(q) == 4 and not isinstance(q[3], str)):
            p.append(f"pregunta mal formada: {q[0]}")
    for v in b.get("vf", []):  # (afirmación, es_verdadera) + explicación opcional
        if len(v) not in (2, 3) or not isinstance(v[1], bool) or (len(v) == 3 and not isinstance(v[2], str)):
            p.append(f"afirmación mal formada: {v[0]}")
    t = [x[0] for x in b.get("parejas", [])]
    d = [x[1] for x in b.get("parejas", [])]
    if len(set(map(norm, t))) != len(t) or len(set(map(norm, d))) != len(d):
        p.append("hay parejas con términos o definiciones repetidos")
    for w, _ in b.get("palabras", []):
        if not re.fullmatch(r"[A-ZÁÉÍÓÚÜÑ]{3,}", w):
            p.append(f"palabra no válida para el ahorcado: {w} (una sola palabra, solo letras)")
    for ti, pasos in b.get("secuencias", []):
        if len(pasos) < 3 or len(set(pasos)) != len(pasos):
            p.append(f"secuencia «{ti}» necesita 3 o más pasos distintos")
    return p


def resumen_texto(b):
    """El contenido del juego en texto legible (para que el profesor sepa qué puede quitar)."""
    L = ["PREGUNTAS"] + [f"  • {q[0]}  →  {q[1]}" + (f"\n      💡 {q[3]}" if len(q) > 3 else "") for q in b["preguntas"]]
    L += ["", "VERDADERO / FALSO"] + [f"  • {v[0]}  →  {'Verdadero' if v[1] else 'Falso'}" + (f"\n      💡 {v[2]}" if len(v) > 2 else "") for v in b["vf"]]
    L += ["", "PAREJAS"] + [f"  • {t}  =  {d}" for t, d in b["parejas"]]
    L += ["", "PALABRAS (AHORCADO)"] + [f"  • {w}  ({pista})" for w, pista in b["palabras"]]
    L += ["", "SECUENCIAS"] + [f"  • {ti}: " + " → ".join(pasos) for ti, pasos in b["secuencias"]]
    return "\n".join(L)


def _textos(seccion, item):
    if seccion == "preguntas": return [item[0], item[1]]
    if seccion == "vf": return [item[0]]
    if seccion == "parejas": return [item[0], item[1]]
    if seccion == "palabras": return [item[0], item[1]]
    return [item[0], *item[1]]


def _como_bool(v):
    return v if isinstance(v, bool) else norm(v) in ("true", "verdadero", "verdadera", "cierto", "si", "1")


def _aplicar_una(b, op):
    tipo = norm(op["op"])
    if tipo == "quitar":
        txt = norm(op["texto"])
        if len(txt) < 3:
            raise ValueError("texto muy corto")
        quitados = {}
        for sec in MINIMOS:
            antes = len(b[sec])
            b[sec] = [it for it in b[sec] if not any(txt in norm(s) for s in _textos(sec, it))]
            if len(b[sec]) != antes:
                quitados[sec] = antes - len(b[sec])
        if not quitados:
            return f"ℹ️ No encontré «{op['texto']}» en este juego."
        det = ", ".join(f"{n} de {NOMBRES[s]}" for s, n in quitados.items())
        return f"✅ Quité «{op['texto']}»: {det}."
    if tipo == "reemplazar":
        patron = re.compile(re.escape(op["buscar"]), re.IGNORECASE)
        cuenta = [0]

        def cambiar(x):
            if isinstance(x, str):
                nuevo, n = patron.subn(op["por"], x)
                cuenta[0] += n
                return nuevo
            if isinstance(x, list):
                return [cambiar(i) for i in x]
            return x
        for sec in MINIMOS:
            b[sec] = cambiar(b[sec])
        if not cuenta[0]:
            return f"ℹ️ No encontré «{op['buscar']}»."
        return f"✅ Cambié «{op['buscar']}» por «{op['por']}» ({cuenta[0]} veces)."
    if tipo == "agregar_pregunta":
        nueva = [op["pregunta"].strip(), op["correcta"].strip(), [m.strip() for m in op["incorrectas"]]]
        if str(op.get("explicacion") or "").strip():
            nueva.append(op["explicacion"].strip())
        b["preguntas"].append(nueva)
        return f"✅ Agregué la pregunta «{op['pregunta']}»."
    if tipo == "agregar_vf":
        nueva = [op["afirmacion"].strip(), _como_bool(op["verdadera"])]
        if str(op.get("explicacion") or "").strip():
            nueva.append(op["explicacion"].strip())
        b["vf"].append(nueva)
        return f"✅ Agregué la afirmación «{op['afirmacion']}»."
    if tipo == "agregar_pareja":
        b["parejas"].append([op["termino"].strip(), op["definicion"].strip()])
        return f"✅ Agregué la pareja «{op['termino']}»."
    if tipo == "agregar_palabra":
        b["palabras"].append([op["palabra"].strip().upper(), op["pista"].strip()])
        return f"✅ Agregué la palabra {op['palabra'].strip().upper()}."
    if tipo == "agregar_secuencia":
        b["secuencias"].append([op["titulo"].strip(), [s.strip() for s in op["pasos"]]])
        return f"✅ Agregué la secuencia «{op['titulo']}»."
    raise ValueError("operación desconocida")


def aplicar_operaciones(banco, ops):
    """Aplica una por una; rechaza las que dejarían el juego dañado. Devuelve (banco, informes)."""
    actual, informes = copy.deepcopy(banco), []
    for op in ops:
        try:
            intento = copy.deepcopy(actual)
            msg = _aplicar_una(intento, op)
        except (KeyError, TypeError, ValueError, AttributeError):
            informes.append(f"⚠️ No pude aplicar «{op.get('op') if isinstance(op, dict) else op}» (datos incompletos).")
            continue
        prob = validar_banco(intento)
        if prob:
            informes.append("⚠️ No lo hice: " + prob[0] + (". Agrega contenido nuevo antes de quitar más." if "quedarían" in prob[0] else "."))
            continue
        actual = intento
        informes.append(msg)
    return actual, informes


AYUDA_BASICA = (
    "Sin IA instalada entiendo comandos así (separa varios con «;»):\n"
    "  • quita la palabra enzima\n"
    "  • cambia Newton por Galileo\n"
    "  • agrega palabra: ENZIMA = Acelera reacciones en el cuerpo\n"
    "  • agrega pareja: Término = Definición\n"
    "  • agrega afirmación: El agua hierve a 100 °C | verdadero | A nivel del mar (la explicación es opcional)\n"
    "  • agrega pregunta: ¿Pregunta? | correcta | mala1 | mala2 | mala3 | explicación (opcional)\n"
    "    (dentro de una explicación no uses «;», porque separa comandos)\n"
    "Para escribirlo en lenguaje libre instala Ollama (gratis): ollama pull qwen2.5:3b"
)


def interpretar_basico(instruccion):
    """Traduce comandos simples a operaciones, sin IA."""
    ops, avisos = [], []
    for parte in re.split(r"[;\n]+", instruccion):
        t = parte.strip()
        if not t:
            continue
        m = re.match(r"(?i)^(?:quita|quitar|elimina|eliminar|borra|borrar|saca|sacar)\s+(?:(?:la|el|lo|los|las)\s+)?(?:(?:palabra|pregunta|término|termino|tema|concepto|afirmación|afirmacion)\s+)?[\"“«']?(.+?)[\"”»']?$", t)
        if m:
            ops.append({"op": "quitar", "texto": m.group(1)}); continue
        m = re.match(r"(?i)^(?:cambia|cambiar|reemplaza|reemplazar)\s+[\"“«']?(.+?)[\"”»']?\s+(?:por|con)\s+[\"“«']?(.+?)[\"”»']?$", t)
        if m:
            ops.append({"op": "reemplazar", "buscar": m.group(1), "por": m.group(2)}); continue
        m = re.match(r"(?i)^agrega(?:r)?\s+(?:la\s+)?palabra\s*:?\s*(\S+)\s*[:=\-]\s*(.+)$", t)
        if m:
            ops.append({"op": "agregar_palabra", "palabra": m.group(1), "pista": m.group(2)}); continue
        m = re.match(r"(?i)^agrega(?:r)?\s+(?:una\s+)?(?:pareja|término|termino)\s*:?\s*(.+?)\s*=\s*(.+)$", t)
        if m:
            ops.append({"op": "agregar_pareja", "termino": m.group(1), "definicion": m.group(2)}); continue
        m = re.match(r"(?i)^agrega(?:r)?\s+(?:una\s+)?(?:afirmación|afirmacion|verdadero/falso)\s*:?\s*(.+?)\s*\|\s*(\w+)(?:\s*\|\s*(.+))?$", t)
        if m:
            op = {"op": "agregar_vf", "afirmacion": m.group(1), "verdadera": m.group(2)}
            if m.group(3):
                op["explicacion"] = m.group(3).strip()
            ops.append(op); continue
        m = re.match(r"(?i)^agrega(?:r)?\s+(?:una\s+)?pregunta\s*:?\s*(.+)$", t)
        if m:
            campos = [c.strip() for c in m.group(1).split("|")]
            if len(campos) in (5, 6):
                op = {"op": "agregar_pregunta", "pregunta": campos[0], "correcta": campos[1], "incorrectas": campos[2:5]}
                if len(campos) == 6 and campos[5]:
                    op["explicacion"] = campos[5]
                ops.append(op); continue
        avisos.append(f"❓ No entendí: «{t}»")
    if avisos:
        avisos.append(AYUDA_BASICA)
    return ops, avisos


_SISTEMA_EDICION = """Eres un asistente que ayuda a un profesor colombiano a ajustar un juego educativo de {materia} (grado {grado}), tema «{tema}».
El profesor te da una instrucción y tú respondes SOLO con JSON: {{"mensaje": "explicación breve en español", "operaciones": [ ... ]}}.
Operaciones permitidas:
 {{"op":"quitar","texto":"palabra o frase a eliminar de todo el juego"}}
 {{"op":"reemplazar","buscar":"texto","por":"texto nuevo"}}
 {{"op":"agregar_pregunta","pregunta":"...","correcta":"...","incorrectas":["a","b","c"],"explicacion":"por qué es esa, en una frase"}}   (opciones cortas)
 {{"op":"agregar_vf","afirmacion":"...","verdadera":true,"explicacion":"por qué es verdadera o falsa, en una frase"}}
 {{"op":"agregar_pareja","termino":"...","definicion":"..."}}
 {{"op":"agregar_palabra","palabra":"UNASOLAPALABRA","pista":"..."}}
 {{"op":"agregar_secuencia","titulo":"...","pasos":["paso 1","paso 2","paso 3","paso 4"]}}
Reglas: contenido correcto, de nivel grado {grado}, en español (en Inglés, las preguntas van en inglés), situaciones reales.
Si pide quitar algo, usa "quitar". Si no puedes hacer lo pedido, devuelve operaciones vacías y explícalo en "mensaje".
Contenido actual del juego:
{contenido}"""


def editar_banco(banco, instruccion, materia, tema, grado):
    """Devuelve (nuevo_banco, informes, modo) donde modo es 'ia' o 'basico'."""
    informes = []
    if modelo_disponible():
        try:
            crudo = _chat([
                {"role": "system", "content": _SISTEMA_EDICION.format(materia=materia, grado=grado, tema=tema, contenido=resumen_texto(banco))},
                {"role": "user", "content": instruccion},
            ], formato_json=True)
            datos = json.loads(crudo)
            ops = [o for o in (datos.get("operaciones") or []) if isinstance(o, dict) and "op" in o]
            nuevo, inf = aplicar_operaciones(banco, ops)
            if datos.get("mensaje"):
                informes.append(f"🤖 {datos['mensaje']}")
            return nuevo, informes + inf, "ia"
        except (requests.RequestException, ValueError, KeyError, RuntimeError):
            informes.append("⚠️ La IA local no respondió bien; probé con el modo básico.")
    ops, avisos = interpretar_basico(instruccion)
    nuevo, inf = aplicar_operaciones(banco, ops)
    return nuevo, informes + inf + avisos, "basico"


# ==============================================================================
# TUTOR PARA ESTUDIANTES
# ==============================================================================
_VACIAS = {"que", "como", "cual", "cuales", "cuando", "donde", "quien", "para", "porque", "sobre", "esto", "esta", "este", "esos", "esas",
           "explica", "explicame", "dime", "significa", "significado", "puedes", "hola", "gracias", "entiendo", "ejemplo", "ejemplos", "tema", "clase", "favor", "quiero", "saber", "algo"}


def _buscar_apuntes(pregunta, bancos_materia, maximo=3):
    claves = [w[:5] for w in re.findall(r"[a-z0-9ñ]+", norm(pregunta)) if len(w) >= 4 and w not in _VACIAS]
    if not claves:
        return []
    candidatos = []
    for tema, b in bancos_materia.items():
        for t, d in b["parejas"]:
            candidatos.append((f"{t}: {d}", f"{t} {d}", tema))
        for w, pista in b["palabras"]:
            candidatos.append((f"{w.capitalize()}: {pista}", f"{w} {pista}", tema))
        for q, ok, *_ in b["preguntas"]:
            candidatos.append((f"{q} → {ok}", f"{q} {ok}", tema))
        for ti, pasos in b["secuencias"]:
            candidatos.append((f"{ti}: " + " → ".join(pasos), f"{ti} {' '.join(pasos)}", tema))
    puntuados = []
    for texto, base, tema in candidatos:
        n = norm(base)
        puntos = sum(1 for k in claves if k in n)
        if puntos:
            puntuados.append((puntos, texto, tema))
    puntuados.sort(key=lambda x: -x[0])
    vistos, res = set(), []
    for _, texto, tema in puntuados:
        if texto not in vistos:
            vistos.add(texto)
            res.append(f"📘 {texto}  (tema: {tema})")
        if len(res) == maximo:
            break
    return res


_SISTEMA_TUTOR = """Eres un tutor amable de {materia} para estudiantes de grado {grado} en Colombia. Explica con claridad, paso a paso, con ejemplos de la vida real y en español{extra}.
Responde en máximo 150 palabras. Si la pregunta no tiene que ver con {materia} o con estudiar, redirige con cariño al tema de la clase. Si no estás seguro de algo, dilo en vez de inventar."""


def responder_tutor(pregunta, materia, grado, historial, bancos_materia):
    """historial: lista de (rol, texto) con rol 'user' o 'assistant'."""
    if modelo_disponible():
        try:
            extra = ". Como es Inglés, responde en español pero incluye los ejemplos en inglés" if materia == "Inglés" else ""
            msgs = [{"role": "system", "content": _SISTEMA_TUTOR.format(materia=materia, grado=grado, extra=extra)}]
            msgs += [{"role": r, "content": t} for r, t in historial[-6:]]
            msgs.append({"role": "user", "content": pregunta})
            return _chat(msgs).strip()
        except (requests.RequestException, ValueError, KeyError, RuntimeError):
            pass
    hallazgos = _buscar_apuntes(pregunta, bancos_materia)
    if hallazgos:
        return "Esto encontré en los apuntes de la clase:\n" + "\n".join(hallazgos) + "\n\n(Modo básico: con Ollama instalado te lo explico con más detalle.)"
    return ("No encontré eso en los apuntes básicos de la clase. 🤔\n"
            "Prueba con una palabra clave del tema (por ejemplo «derivada» o «mitosis»). "
            "Para respuestas completas, pide que instalen Ollama (gratis): ollama pull qwen2.5:3b")
