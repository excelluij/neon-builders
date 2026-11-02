"""Almacenamiento local de Neon OS con SQLite (viene con Python, no requiere instalar nada).

Guarda en un solo archivo (neon_os.db, junto a la app): usuarios, misiones publicadas
y el progreso de cada persona (monedas, diamantes, vidas, racha, avatar...). Con ese mismo archivo se arma
el ranking de estudiantes, así que todos deben abrir el mismo neon_os.db (mismo equipo o carpeta compartida).
Para otra ubicación (por ejemplo en pruebas) define la variable de entorno NEON_DB.

Cuentas de demostración: ya NO se siembran con una clave escrita en el código. Si defines NEON_DEMO_CLAVE (mínimo 8 caracteres), una
base vacía recibe las cuentas «camilo» (profesor) y «daniel» (estudiante) con esa clave. Para quitar las que quedaron de versiones
anteriores con la clave antigua:   python almacen.py --cuentas-demo   y   python almacen.py --retirar-cuentas-demo --si

Administradores: las dos cuentas de ADMINISTRADORES existen siempre (se crean solas al iniciar). Su «usuario» es el propio correo y
nacen SIN contraseña: en el primer acceso reciben un código por correo y ahí crean la suya (no hay claves escritas en el código).
Si el correo no funcionara:   python almacen.py --clave-admin correo@ejemplo.com   (pide la contraseña en la consola).

Reiniciar a las personas inscritas (con copia previa):   python almacen.py --reiniciar-personas --si
"""
import getpass
import hashlib
import hmac
import json
import os
import pathlib
import secrets
import sqlite3
import sys
import time

import rutas

if __name__ == "__main__":      # `python almacen.py --cuentas-demo ...`: lee el .env antes de calcular RUTA (NEON_DB puede estar ahí)
    import entorno
    entorno.cargar_env()

RUTA = os.environ.get("NEON_DB") or os.path.join(rutas.carpeta_app(), "neon_os.db")
MATERIAS = ["Química", "Física", "Matemáticas", "Ciencias", "Sociales", "Inglés"]
DEMO_USUARIOS = ("camilo", "daniel")
MIN_CLAVE_DEMO = 8
CLAVE_DEMO_ANTIGUA = "123"        # solo sirve para RECONOCER y retirar las cuentas demo viejas; ya no se siembra con ella
ADMINISTRADORES = ("luisbaco2005@gmail.com", "dsandovaltorres05@gmail.com")   # cuentas de administrador predeterminadas (el usuario es el correo)
SIN_CLAVE = "!"                   # marca de «aún no tiene contraseña»: no es un hash válido, así que ninguna clave coincide
MIN_CLAVE_ADMIN = 8
TABLAS_DE_PERSONAS = ("usuarios", "verificaciones", "progreso", "ranking_ocultos", "codigos_profesor")


def _con():
    con = sqlite3.connect(RUTA)
    con.row_factory = sqlite3.Row
    return con


def _hash(clave, sal=None):
    sal = sal or secrets.token_hex(8)
    h = hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), sal.encode(), 120_000).hex()
    return f"{sal}${h}"


def iniciar():
    """Crea las tablas si no existen y siembra las cuentas de demostración la primera vez."""
    with _con() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS usuarios (
                usuario TEXT PRIMARY KEY, clave TEXT NOT NULL, rol TEXT NOT NULL,
                materia TEXT, correo TEXT, grado TEXT, verificado INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS verificaciones (
                usuario TEXT PRIMARY KEY, codigo_hash TEXT NOT NULL, sal TEXT NOT NULL, expira REAL NOT NULL,
                intentos INTEGER NOT NULL DEFAULT 0, ultimo_envio REAL NOT NULL,
                creado REAL, envios INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS misiones (
                id INTEGER PRIMARY KEY AUTOINCREMENT, materia TEXT NOT NULL, datos TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS progreso (
                usuario TEXT PRIMARY KEY, datos TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS ranking_ocultos (
                usuario TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS codigos_profesor (
                huella TEXT PRIMARY KEY);
        """)
        # una base anterior a la verificación de correo no tiene la columna: se agrega y las cuentas existentes quedan verificadas
        if "verificado" not in [f[1] for f in con.execute("PRAGMA table_info(usuarios)")]:
            con.execute("ALTER TABLE usuarios ADD COLUMN verificado INTEGER NOT NULL DEFAULT 1")
        columnas = [f[1] for f in con.execute("PRAGMA table_info(verificaciones)")]      # tabla de una versión anterior de la pieza
        if "creado" not in columnas:
            con.execute("ALTER TABLE verificaciones ADD COLUMN creado REAL")
        if "envios" not in columnas:
            con.execute("ALTER TABLE verificaciones ADD COLUMN envios INTEGER NOT NULL DEFAULT 1")
        if "prof_huella" not in columnas:
            con.execute("ALTER TABLE verificaciones ADD COLUMN prof_huella TEXT")
        if con.execute("SELECT COUNT(*) FROM usuarios WHERE rol <> 'Administrador'").fetchone()[0] == 0:
            _sembrar_demo(con)
        _asegurar_administradores(con)


def _asegurar_administradores(con):
    """Crea las cuentas de ADMINISTRADORES que falten, sin contraseña, y les deja lista su «verificación de primer acceso»: un
    código ya vencido que nunca coincide, para que «Enviar código» funcione desde el primer clic. Las que ya existen no se tocan."""
    for correo in ADMINISTRADORES:
        con.execute("INSERT OR IGNORE INTO usuarios (usuario, clave, rol, materia, correo, grado, verificado)"
                    " VALUES (?, ?, 'Administrador', NULL, ?, NULL, 0)", (correo, SIN_CLAVE, correo))
        _sembrar_activacion(con, correo)


def _sembrar_activacion(con, usuario):
    """Deja la verificación de primer acceso de un administrador SIN contraseña (si ya la tiene, o ya hay una en curso, no hace nada)."""
    con.execute("""INSERT OR IGNORE INTO verificaciones (usuario, codigo_hash, sal, expira, intentos, ultimo_envio, creado, envios, prof_huella)
                   SELECT ?, '', '', 0, 0, 0, 0, 0, NULL
                   WHERE EXISTS (SELECT 1 FROM usuarios WHERE usuario = ? AND rol = 'Administrador' AND verificado = 0)""", (usuario, usuario))


def preparar_activacion(usuario):
    """Para un administrador sin contraseña que se quedó sin su fila de verificación: la vuelve a dejar lista."""
    with _con() as con:
        _sembrar_activacion(con, usuario)


def _sembrar_demo(con):
    """Cuentas de demostración OPCIONALES: solo si el entorno trae NEON_DEMO_CLAVE (y es de al menos MIN_CLAVE_DEMO caracteres)."""
    clave = os.environ.get("NEON_DEMO_CLAVE", "").strip()
    if not clave:
        return
    if len(clave) < MIN_CLAVE_DEMO:
        print(f"[Neon OS] NEON_DEMO_CLAVE es demasiado corta (mínimo {MIN_CLAVE_DEMO} caracteres): no se crean cuentas de demostración.",
              file=sys.stderr)
        return
    con.executemany("INSERT INTO usuarios (usuario, clave, rol, materia, correo, grado) VALUES (?,?,?,?,?,?)", [
        ("camilo", _hash(clave), "Profesor", "Física", "camilo@edu.co", None),
        ("daniel", _hash(clave), "Estudiante", None, "daniel@edu.co", "11"),
    ])


# ----------------------------------------------------------------- usuarios
def obtener_usuario(usuario):
    with _con() as con:
        f = con.execute("SELECT * FROM usuarios WHERE usuario = ?", (usuario,)).fetchone()
    if f is None:
        return None
    return {"role": f["rol"], "materia": f["materia"], "correo": f["correo"], "grado": f["grado"], "verificado": bool(f["verificado"])}


def verificar_clave(usuario, clave):
    with _con() as con:
        f = con.execute("SELECT clave FROM usuarios WHERE usuario = ?", (usuario,)).fetchone()
    if f is None:
        return False
    if "$" not in f["clave"]:                      # SIN_CLAVE: la cuenta aún no tiene contraseña
        return False
    sal = f["clave"].split("$", 1)[0]
    return hmac.compare_digest(f["clave"], _hash(clave, sal))


def crear_usuario(usuario, correo, clave, rol, materia=None, grado=None, verificado=True):
    """Devuelve False si el usuario ya existe. Las cuentas nuevas del registro se crean con registrar_pendiente."""
    try:
        with _con() as con:
            con.execute("INSERT INTO usuarios (usuario, clave, rol, materia, correo, grado, verificado) VALUES (?,?,?,?,?,?,?)",
                        (usuario, _hash(clave), rol, materia, correo, grado, 1 if verificado else 0))
        return True
    except sqlite3.IntegrityError:
        return False


# ------------------------------------------------------------ verificación de correo
def _normalizar_correo(correo):
    return str(correo).strip().lower()


def correo_en_uso(correo):
    """¿Algún usuario (verificado o pendiente) tiene ya este correo? No distingue mayúsculas ni espacios."""
    with _con() as con:
        return con.execute("SELECT 1 FROM usuarios WHERE lower(trim(correo)) = ?", (_normalizar_correo(correo),)).fetchone() is not None


def reservar_codigo_profesor(huella):
    """Anota la huella de un código de profesor recién generado. False si ya se había entregado alguno igual (se genera otro):
    así dos profesores nunca reciben el mismo código, ni siquiera tras verificarse o reenviarse."""
    with _con() as con:
        return con.execute("INSERT OR IGNORE INTO codigos_profesor (huella) VALUES (?)", (huella,)).rowcount == 1


def registrar_pendiente(usuario, correo, clave, rol, materia, grado, codigo_hash, sal, ahora, vigencia_s, prof_huella=None):
    """Crea la cuenta SIN verificar y su verificación en una sola transacción (BEGIN IMMEDIATE: dos registros a la vez
    se turnan). Devuelve "ok", "usuario_existe" o "correo_existe"; si algo falla se deshace todo y se re-lanza.
    `prof_huella`: huella del código de profesor entregado por correo (solo profesores)."""
    correo = _normalizar_correo(correo)
    clave_hash = _hash(clave)                       # fuera de la transacción: no retiene el bloqueo de escritura
    con = sqlite3.connect(RUTA, timeout=10)
    con.isolation_level = None                      # transacción manual
    try:
        con.execute("BEGIN IMMEDIATE")
        try:
            if con.execute("SELECT 1 FROM usuarios WHERE usuario = ?", (usuario,)).fetchone():
                resultado = "usuario_existe"
            elif con.execute("SELECT 1 FROM usuarios WHERE lower(trim(correo)) = ?", (correo,)).fetchone():
                resultado = "correo_existe"
            else:
                for tabla in ("progreso", "ranking_ocultos"):    # restos de una cuenta anterior con ese nombre: una cuenta nueva empieza de cero
                    con.execute(f"DELETE FROM {tabla} WHERE usuario = ?", (usuario,))
                con.execute("INSERT INTO usuarios (usuario, clave, rol, materia, correo, grado, verificado) VALUES (?,?,?,?,?,?,0)",
                            (usuario, clave_hash, rol, materia, correo, grado))
                con.execute("INSERT INTO verificaciones (usuario, codigo_hash, sal, expira, intentos, ultimo_envio, creado, envios, prof_huella)"
                            " VALUES (?,?,?,?,0,?,?,1,?)", (usuario, codigo_hash, sal, ahora + vigencia_s, ahora, ahora, prof_huella))
                resultado = "ok"
            con.execute("COMMIT")
            return resultado
        except BaseException:
            con.execute("ROLLBACK")
            raise
    finally:
        con.close()


def datos_verificacion(usuario):
    """Datos de la verificación pendiente de la cuenta (None si no hay: no existe o ya está verificada)."""
    with _con() as con:
        f = con.execute("""SELECT v.codigo_hash, v.sal, v.expira, v.intentos, v.ultimo_envio, v.creado, v.envios, v.prof_huella,
                                  u.correo, u.verificado, u.rol
                           FROM verificaciones v JOIN usuarios u ON u.usuario = v.usuario WHERE v.usuario = ?""", (usuario,)).fetchone()
    return None if f is None else dict(f) | {"verificado": bool(f["verificado"])}


def consumir_intento(usuario, maximo):
    """Descuenta un intento de forma atómica (un solo UPDATE). Devuelve los intentos usados, o None si ya se alcanzó el
    máximo o no hay verificación pendiente."""
    with _con() as con:
        cur = con.execute("UPDATE verificaciones SET intentos = intentos + 1 WHERE usuario = ? AND intentos < ?", (usuario, maximo))
        if cur.rowcount != 1:
            return None
        return con.execute("SELECT intentos FROM verificaciones WHERE usuario = ?", (usuario,)).fetchone()[0]


def reservar_envio(usuario, ahora, espera_s, maximo_envios=None):
    """Reserva de forma atómica el próximo envío: solo si pasaron `espera_s` segundos desde el último (y el reloj no
    retrocedió). Devuelve el `ultimo_envio` anterior, None si todavía no toca o no hay verificación, o "limite" si la
    cuenta ya recibió `maximo_envios` códigos. Dos solicitudes simultáneas no pueden ganar las dos."""
    con = sqlite3.connect(RUTA, timeout=10)
    con.isolation_level = None
    try:
        con.execute("BEGIN IMMEDIATE")
        try:
            f = con.execute("SELECT ultimo_envio, envios FROM verificaciones WHERE usuario = ?", (usuario,)).fetchone()
            previo = None
            if f is not None:
                if maximo_envios is not None and f[1] >= maximo_envios:
                    previo = "limite"
                elif ahora - f[0] >= espera_s:
                    con.execute("UPDATE verificaciones SET ultimo_envio = ?, envios = envios + 1 WHERE usuario = ?", (ahora, usuario))
                    previo = f[0]
            con.execute("COMMIT")
            return previo
        except BaseException:
            con.execute("ROLLBACK")
            raise
    finally:
        con.close()


def restaurar_envio(usuario, previo):
    """Deshace una reserva cuando el proveedor falló: no se gasta la espera de reenvío ni uno de los envíos del tope."""
    with _con() as con:
        con.execute("UPDATE verificaciones SET ultimo_envio = ?, envios = MAX(envios - 1, 1) WHERE usuario = ?", (previo, usuario))


def renovar_codigo(usuario, codigo_hash, sal, expira, ahora, prof_huella=None):
    """Código nuevo: invalida el anterior (y el código de profesor anterior), reinicia los intentos y la espera de reenvío."""
    with _con() as con:
        cur = con.execute("UPDATE verificaciones SET codigo_hash = ?, sal = ?, expira = ?, intentos = 0, ultimo_envio = ?, prof_huella = ?"
                          " WHERE usuario = ?", (codigo_hash, sal, expira, ahora, prof_huella, usuario))
    return cur.rowcount == 1


def marcar_verificado(usuario, codigo_hash=None, clave=None):
    """Marca la cuenta como verificada. Con `codigo_hash` solo si la cuenta sigue pendiente Y ese es todavía su código
    vigente, todo en una sola sentencia: un reenvío que llegó en medio, o una verificación hecha en otra ventana, la anulan.
    Con `clave` (primer acceso de un administrador) guarda además esa contraseña, en la misma sentencia."""
    clave_hash = None if clave is None else _hash(clave)
    with _con() as con:
        if codigo_hash is None:
            cur = con.execute("UPDATE usuarios SET verificado = 1, clave = COALESCE(?, clave) WHERE usuario = ?", (clave_hash, usuario))
            con.execute("DELETE FROM verificaciones WHERE usuario = ?", (usuario,))
        else:
            cur = con.execute("""UPDATE usuarios SET verificado = 1, clave = COALESCE(?, clave) WHERE usuario = ? AND verificado = 0
                                 AND EXISTS (SELECT 1 FROM verificaciones WHERE usuario = ? AND codigo_hash = ?)""",
                              (clave_hash, usuario, usuario, codigo_hash))
            if cur.rowcount == 1:
                con.execute("DELETE FROM verificaciones WHERE usuario = ?", (usuario,))
    return cur.rowcount == 1


def cancelar_pendiente(usuario):
    """Borra una cuenta que NO está verificada (nunca una verificada ni una de administrador) y su verificación."""
    with _con() as con:
        cur = con.execute("DELETE FROM usuarios WHERE usuario = ? AND verificado = 0 AND rol <> 'Administrador'", (usuario,))
        if cur.rowcount == 1:
            con.execute("DELETE FROM verificaciones WHERE usuario = ?", (usuario,))
    return cur.rowcount == 1


def limpiar_no_verificados(ahora, caduca_s):
    """Borra las cuentas sin verificar creadas hace más de `caduca_s` segundos (reenviar el código no las mantiene vivas;
    una fila antigua sin `creado` usa su último envío). Una sola sentencia: no toca una cuenta que se verificó entre medias.
    Las de administrador nunca caducan. Devuelve cuántas."""
    with _con() as con:
        cur = con.execute("""DELETE FROM usuarios WHERE verificado = 0 AND rol <> 'Administrador' AND usuario IN
                             (SELECT usuario FROM verificaciones WHERE COALESCE(creado, ultimo_envio) < ?)""", (ahora - caduca_s,))
        con.execute("DELETE FROM verificaciones WHERE usuario NOT IN (SELECT usuario FROM usuarios)")
    return cur.rowcount


# ------------------------------------------- retirar las cuentas demo que quedaron con la clave antigua
def _solo_lectura(ruta):
    """Abre la base SIN poder modificarla (ni crearla): None si el archivo no existe."""
    if not os.path.exists(ruta):
        return None
    return sqlite3.connect(pathlib.Path(ruta).resolve().as_uri() + "?mode=ro", uri=True)


def _demo_con_clave_antigua(con):
    """[(usuario, clave_guardada)] de camilo/daniel que todavía aceptan la clave antigua. No se toca nada más."""
    try:
        filas = con.execute("SELECT usuario, clave FROM usuarios WHERE usuario IN (?, ?)", DEMO_USUARIOS).fetchall()
    except sqlite3.DatabaseError:                       # no es una base de Neon OS
        return []
    return [(u, c) for u, c in filas
            if isinstance(c, str) and hmac.compare_digest(c, _hash(CLAVE_DEMO_ANTIGUA, c.split("$", 1)[0]))]


def cuentas_demo_con_clave_antigua(ruta=None):
    """Nombres de las cuentas demo (camilo, daniel) que todavía tienen la clave antigua. Solo lee: no modifica la base."""
    con = _solo_lectura(ruta or RUTA)
    if con is None:
        return []
    try:
        return [u for u, _ in _demo_con_clave_antigua(con)]
    finally:
        con.close()


def retirar_cuentas_demo(ruta=None):
    """Borra esas cuentas (y su progreso, verificación y marca de ranking). Solo las que SIGUEN con la clave antigua: una cuenta
    cuya clave ya se cambió no se toca. Devuelve los nombres retirados."""
    ruta = ruta or RUTA
    con = _solo_lectura(ruta)
    if con is None:
        return []
    try:
        candidatas = _demo_con_clave_antigua(con)
    finally:
        con.close()
    retiradas = []
    escritura = sqlite3.connect(ruta, timeout=10)
    try:
        with escritura:                                   # una sola transacción
            tablas = {f[0] for f in escritura.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            for usuario, clave in candidatas:
                # se vuelve a comprobar la clave guardada al borrar: si cambió entre medias, no se borra nada
                if escritura.execute("DELETE FROM usuarios WHERE usuario = ? AND clave = ?", (usuario, clave)).rowcount != 1:
                    continue
                for tabla in ("progreso", "ranking_ocultos", "verificaciones"):
                    if tabla in tablas:
                        escritura.execute(f"DELETE FROM {tabla} WHERE usuario = ?", (usuario,))
                retiradas.append(usuario)
    finally:
        escritura.close()
    return retiradas


# ------------------------------------------- administradores y reinicio de las personas inscritas
def asignar_clave_admin(correo, clave):
    """Guarda la contraseña de un administrador SIN pasar por el correo (la usa quien tiene acceso a esta carpeta, por si el proveedor
    de correo no funciona). Devuelve False si el correo no es de un administrador o la contraseña es demasiado corta."""
    correo = _normalizar_correo(correo)
    if correo not in ADMINISTRADORES or len(clave) < MIN_CLAVE_ADMIN:
        return False
    iniciar()
    with _con() as con:
        con.execute("UPDATE usuarios SET clave = ?, verificado = 1 WHERE usuario = ?", (_hash(clave), correo))
        con.execute("DELETE FROM verificaciones WHERE usuario = ?", (correo,))
    return True


def copia_de_seguridad(etiqueta="copia"):
    """Copia la base completa junto a la original (neon_os_<etiqueta>_AAAAMMDD-HHMMSS.db) y devuelve su ruta."""
    base, _ = os.path.splitext(RUTA)
    destino = f"{base}_{etiqueta}_{time.strftime('%Y%m%d-%H%M%S')}.db"
    origen, copia = sqlite3.connect(RUTA), sqlite3.connect(destino)
    try:
        origen.backup(copia)
    finally:
        copia.close()
        origen.close()
    return destino


def contar_personas():
    """Cuántas personas (sin contar a los administradores) hay inscritas."""
    iniciar()
    with _con() as con:
        return con.execute("SELECT COUNT(*) FROM usuarios WHERE rol <> 'Administrador'").fetchone()[0]


def reiniciar_personas():
    """Deja la base sin personas inscritas: borra usuarios, progreso, verificaciones, ocultos del ranking y códigos de profesor, y
    vuelve a crear a los administradores sin contraseña. Conserva las misiones. Antes hace una copia; devuelve su ruta."""
    iniciar()
    copia = copia_de_seguridad("copia_antes_de_reiniciar")
    with _con() as con:
        for tabla in TABLAS_DE_PERSONAS:
            con.execute(f"DELETE FROM {tabla}")
        _asegurar_administradores(con)
    return copia


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--reiniciar-personas"]:
        n = contar_personas()
        if "--si" not in argv:
            print(f"Se borrarían {n} persona(s) inscrita(s) con su progreso en {RUTA} (las misiones se conservan). Cierra la app y repite "
                  "el comando con --si para confirmar; antes se guarda una copia.")
            return 2
        print(f"Reiniciado: {n} persona(s) borrada(s). Copia previa: {reiniciar_personas()}")
        return 0
    if argv[:1] == ["--clave-admin"] and len(argv) == 2:
        if _normalizar_correo(argv[1]) not in ADMINISTRADORES:
            print("Ese correo no es de un administrador. Los administradores son: " + ", ".join(ADMINISTRADORES))
            return 1
        clave = getpass.getpass(f"Contraseña nueva para {argv[1]} (mínimo {MIN_CLAVE_ADMIN} caracteres): ")
        if clave != getpass.getpass("Repítela: "):
            print("No coinciden: no se cambió nada.")
            return 1
        if not asignar_clave_admin(argv[1], clave):
            print(f"La contraseña es demasiado corta (mínimo {MIN_CLAVE_ADMIN} caracteres): no se cambió nada.")
            return 1
        print("✅ Contraseña guardada. Ya puedes entrar como administrador con tu correo y esa contraseña.")
        return 0
    if argv[:1] == ["--cuentas-demo"]:
        nombres = cuentas_demo_con_clave_antigua()
        print(f"Cuentas de demostración con la clave antigua en {RUTA}: {', '.join(nombres)}" if nombres
              else "No hay cuentas de demostración con la clave antigua.")
        return 0
    if argv[:1] == ["--retirar-cuentas-demo"]:
        nombres = cuentas_demo_con_clave_antigua()
        if not nombres:
            print("No hay cuentas de demostración con la clave antigua.")
            return 0
        if "--si" not in argv:
            print(f"Se retirarían (con su progreso): {', '.join(nombres)}. Cierra la app, haz una copia de {RUTA} "
                  "y repite el comando con --si para confirmar.")
            return 2
        print(f"Cuentas de demostración retiradas: {', '.join(retirar_cuentas_demo())}")
        return 0
    print("Uso:\n  python almacen.py --cuentas-demo                    lista las cuentas demo que aún tienen la clave antigua\n"
          "  python almacen.py --retirar-cuentas-demo [--si]     las borra (sin --si solo muestra cuáles)\n"
          "  python almacen.py --reiniciar-personas [--si]       borra a todas las personas inscritas (antes guarda una copia)\n"
          "  python almacen.py --clave-admin correo              pone la contraseña de un administrador sin usar el correo")
    return 2


# ----------------------------------------------------------------- misiones
def cargar_misiones():
    """{materia: [mision, ...]} con el id de la base en mision['id']."""
    todas = {m: [] for m in MATERIAS}
    with _con() as con:
        for f in con.execute("SELECT id, materia, datos FROM misiones ORDER BY id"):
            m = json.loads(f["datos"])
            m["id"] = f["id"]
            todas.setdefault(f["materia"], []).append(m)
    return todas


def guardar_mision(materia, mision):
    datos = {k: v for k, v in mision.items() if k != "id"}
    with _con() as con:
        cur = con.execute("INSERT INTO misiones (materia, datos) VALUES (?, ?)", (materia, json.dumps(datos, ensure_ascii=False)))
    mision["id"] = cur.lastrowid
    return mision["id"]


# ----------------------------------------------------------------- progreso
def cargar_progreso(usuario):
    with _con() as con:
        f = con.execute("SELECT datos FROM progreso WHERE usuario = ?", (usuario,)).fetchone()
    return None if f is None else json.loads(f["datos"])


def guardar_progreso(usuario, datos):
    with _con() as con:
        con.execute("INSERT INTO progreso (usuario, datos) VALUES (?, ?) ON CONFLICT(usuario) DO UPDATE SET datos = excluded.datos",
                    (usuario, json.dumps(datos, ensure_ascii=False)))


# ------------------------------------------------------------------ ranking
# El puntaje es "puntos" (monedas ganadas en total: no baja al comprar). Los progresos guardados antes de que
# existiera el contador no lo traen: para ellos se usan las monedas que tenían.
def armar_ranking(filas):
    """[(usuario, puntos)] -> [(puesto, usuario, puntos)] de mayor a menor.
    Solo entra quien tiene al menos 1 punto. Los empates comparten puesto (1, 2, 2, 4...)."""
    con_puntos = sorted(((u, p) for u, p in filas if p > 0), key=lambda f: (-f[1], f[0]))
    ranking, puesto, anterior = [], 0, None
    for n, (usuario, puntos) in enumerate(con_puntos, 1):
        if puntos != anterior:
            puesto, anterior = n, puntos
        ranking.append((puesto, usuario, puntos))
    return ranking


def recortar_top(ranking, limite=10):
    """Los del puesto 1 al `limite`. Si varios empatan en el último puesto del top, entran todos."""
    return [fila for fila in ranking if fila[0] <= limite]


def puntos_para_entrar(ranking, limite=10):
    """Puntaje mínimo para aparecer en el top: el del último de un top lleno, o 1 si todavía hay sitio."""
    top = recortar_top(ranking, limite)
    return top[-1][2] if len(top) >= limite else 1


def _puntos_de(datos):
    try:
        return int(datos.get("puntos", datos.get("coins", 0)) or 0)
    except (TypeError, ValueError):
        return 0


def ranking_estudiantes(grado=None):
    """Ranking completo de estudiantes (sin los ocultos): [(puesto, usuario, puntos)]. grado=None -> todos los grados."""
    with _con() as con:
        filas = con.execute(
            """SELECT u.usuario, p.datos FROM usuarios u LEFT JOIN progreso p ON p.usuario = u.usuario
               WHERE u.rol = 'Estudiante' AND u.verificado = 1 AND (? IS NULL OR u.grado = ?)
                 AND u.usuario NOT IN (SELECT usuario FROM ranking_ocultos)""", (grado, grado)).fetchall()
    puntajes = []
    for f in filas:
        try:
            datos = json.loads(f["datos"]) if f["datos"] else {}
        except ValueError:
            datos = {}
        puntajes.append((f["usuario"], _puntos_de(datos)))
    return armar_ranking(puntajes)


def ocultos_del_ranking():
    with _con() as con:
        return [f["usuario"] for f in con.execute("SELECT usuario FROM ranking_ocultos ORDER BY usuario")]


def ocultar_del_ranking(usuario):
    with _con() as con:
        con.execute("INSERT OR IGNORE INTO ranking_ocultos (usuario) VALUES (?)", (usuario,))


def restaurar_al_ranking(usuario):
    with _con() as con:
        con.execute("DELETE FROM ranking_ocultos WHERE usuario = ?", (usuario,))


if __name__ == "__main__":
    sys.exit(main())
