"""Reglas de la verificación de correo de Neon OS: registro, código de 6 dígitos, reenvío y cancelación.

Los profesores reciben en ese mismo correo un segundo código, el «código de profesor»: único, aleatorio y distinto para cada
profesor (ya no hay un código fijo compartido). Los administradores (almacen.ADMINISTRADORES) nacen sin contraseña: su primer
acceso es esta misma verificación y, junto con el código, eligen su contraseña.

Todo con reloj y emisor inyectables (para probar sin esperar ni enviar correos reales). El envío real está en
correo.py y la base de datos en almacen.py. Ver docs/CORREO.md.
"""
import hashlib
import hmac
import math
import secrets
import time
from typing import NamedTuple

import almacen
from correo import DIRECCION_RE, ErrorCorreo, cargar_config, enviar_codigo

LARGO = 6                    # dígitos del código
VIGENCIA_S = 600             # el código vale 10 minutos (ahora < expira)
MAX_INTENTOS = 5             # intentos por código
MAX_ENVIOS = 5               # códigos por cuenta pendiente (el inicial + 4 reenvíos): acota correos y adivinanzas
ROLES = ("Estudiante", "Profesor")   # el administrador no se registra
ESPERA_REENVIO_S = 60        # segundos entre dos envíos
CADUCA_PENDIENTE_S = 86400   # una cuenta sin verificar se borra a las 24 h
ITERACIONES = 100_000
ALFABETO_PROFESOR = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # sin I, L, O, 0 ni 1: no se confunden al copiarlas del correo
LARGO_PROFESOR = 10                                      # se muestra como XXXXX-XXXXX
_SAL_PROFESOR = b"neon-os/codigo-de-profesor/v1"

MENSAJES = {
    "datos": "Completa todos los campos.",
    "correo_invalido": "Escribe un correo electrónico válido.",
    "config": "El envío de correos no está configurado. Avisa al administrador.",
    "usuario_existe": "Ese usuario ya existe.",
    "correo_existe": "Ese correo ya está registrado.",
    "envio": "No se pudo enviar el correo. Inténtalo de nuevo.",
    "no_existe": "No encontramos esa cuenta.",
    "ya_verificada": "Esa cuenta ya está verificada. Inicia sesión.",
    "vencido": "El código venció. Pide uno nuevo.",
    "intentos": "Demasiados intentos. Pide un código nuevo.",
    "formato": f"Escribe los {LARGO} dígitos del código.",
    "clave": "La contraseña no es correcta.",
    "limite": "Ya se enviaron el máximo de códigos para esta cuenta. Cancela el registro y vuelve a registrarte más tarde.",
    "formato_profesor": "Escribe tu código de profesor: las 10 letras y números que llegaron a tu correo.",
    "clave_corta": f"Crea una contraseña de al menos {almacen.MIN_CLAVE_ADMIN} caracteres.",
    "no_cancelable": "Las cuentas de administrador no se pueden cancelar.",
}


class Resultado(NamedTuple):
    ok: bool
    mensaje: str
    codigo: str          # ok, datos, correo_invalido, config, usuario_existe, correo_existe, envio, no_existe, ya_verificada,
    segundos: int = 0    # vencido, intentos, formato, formato_profesor, clave_corta, incorrecto, espera, clave, limite, no_cancelable.
                         # `segundos`: espera restante ("espera")


def _fallo(codigo, mensaje=None, segundos=0):
    return Resultado(False, mensaje or MENSAJES[codigo], codigo, segundos)


def correo_valido(correo):
    return (isinstance(correo, str) and len(correo) <= 254 and DIRECCION_RE.fullmatch(correo) is not None
            and len(correo.split("@")[0]) <= 64)


def mascara_correo(correo):
    local, _, dominio = str(correo).partition("@")
    return f"{local[:1]}***@{dominio}" if dominio else "***"


def generar_codigo():
    return f"{secrets.randbelow(10 ** LARGO):0{LARGO}d}"


def hash_codigo(codigo, sal):
    return hashlib.pbkdf2_hmac("sha256", codigo.encode(), sal.encode(), ITERACIONES).hex()


def generar_codigo_profesor():
    """Código de profesor aleatorio (50 bits, `secrets`), con el formato XXXXX-XXXXX."""
    c = "".join(secrets.choice(ALFABETO_PROFESOR) for _ in range(LARGO_PROFESOR))
    return f"{c[:5]}-{c[5:]}"


def normalizar_codigo_profesor(texto):
    """Mayúsculas y sin guiones ni espacios: así vale escribirlo con o sin guion, en minúsculas o pegado con espacios."""
    return "".join(str(texto or "").upper().replace("-", "").split())


def codigo_profesor_valido(texto):
    """¿Tiene la forma de un código de profesor (10 caracteres del alfabeto)? No dice si es el correcto."""
    normal = normalizar_codigo_profesor(texto)
    return len(normal) == LARGO_PROFESOR and all(c in ALFABETO_PROFESOR for c in normal)


def huella_codigo_profesor(texto):
    """Huella lenta del código (pbkdf2): es lo único que se guarda, nunca el código. Sin sal por cuenta, para poder comprobar que
    ningún otro profesor recibió el mismo código."""
    return hashlib.pbkdf2_hmac("sha256", normalizar_codigo_profesor(texto).encode(), _SAL_PROFESOR, ITERACIONES).hex()


def _nuevo_codigo_profesor():
    """(código, huella) de un código de profesor que nunca se había entregado a nadie."""
    for _ in range(20):
        codigo = generar_codigo_profesor()
        huella = huella_codigo_profesor(codigo)
        if almacen.reservar_codigo_profesor(huella):
            return codigo, huella
    raise RuntimeError("No se pudo generar un código de profesor único.")


def _espera(ultimo_envio, ahora):
    """Segundos que faltan para poder reenviar (0 si ya se puede). Si el reloj retrocede nunca pasa de ESPERA_REENVIO_S."""
    restante = ESPERA_REENVIO_S - (ahora - ultimo_envio)
    return 0 if restante <= 0 else min(ESPERA_REENVIO_S, math.ceil(restante))


def _resolver_config(config):
    if config is not None:
        return config, ""
    try:
        config = cargar_config()
    except ErrorCorreo as error:
        return None, f"La configuración del correo no es válida: {error.mensaje}"
    return (config, "") if config is not None else (None, MENSAJES["config"])


def _enviar(enviar, destino, codigo, config, codigo_profesor=None):
    """Envía y devuelve None si salió bien, o el texto del error (nunca incluye secretos ni el código)."""
    extra = {} if codigo_profesor is None else {"codigo_profesor": codigo_profesor}      # solo los profesores lo llevan
    try:
        (enviar or enviar_codigo)(destino, codigo, config, **extra)
    except ErrorCorreo as error:
        return error.mensaje
    except Exception:  # noqa: BLE001 - cualquier fallo del emisor deshace la operación, sin filtrar su texto
        return MENSAJES["envio"]
    return None


def _cuenta_cambio(usuario):
    """Si la cuenta desapareció o se verificó mientras tanto (otra ventana, la limpieza), ese es el resultado correcto."""
    cuenta = almacen.obtener_usuario(usuario)
    if cuenta is None:
        return _fallo("no_existe")
    if cuenta["verificado"]:
        return _fallo("ya_verificada")
    return None


def _aviso_desarrollo(config):
    return " (modo desarrollo: el código está en la consola)" if config.modo == "consola" else ""


def iniciar_registro(usuario, correo, clave, rol, materia=None, grado=None, *, enviar=None, reloj=time.time, config=None):
    """Crea la cuenta SIN verificar y envía el código. Si el correo no está configurado no crea nada; si el envío
    falla, borra la cuenta pendiente para que el usuario pueda reintentar."""
    usuario, correo = (usuario or "").strip(), (correo or "").strip()
    if not usuario or not clave or rol not in ROLES:
        return _fallo("datos")
    if not correo_valido(correo):
        return _fallo("correo_invalido")
    config, error = _resolver_config(config)
    if config is None:
        return _fallo("config", error)
    ahora = reloj()
    almacen.limpiar_no_verificados(ahora, CADUCA_PENDIENTE_S)
    codigo, sal = generar_codigo(), secrets.token_hex(8)
    codigo_profesor, prof_huella = _nuevo_codigo_profesor() if rol == "Profesor" else (None, None)
    estado = almacen.registrar_pendiente(usuario, correo, clave, rol, materia, grado, hash_codigo(codigo, sal), sal, ahora, VIGENCIA_S, prof_huella)
    if estado != "ok":
        return _fallo(estado)
    fallo = _enviar(enviar, correo.lower(), codigo, config, codigo_profesor)
    if fallo:
        almacen.cancelar_pendiente(usuario)
        return _fallo("envio", fallo)
    return Resultado(True, f"Te enviamos un código de {LARGO} dígitos a {mascara_correo(correo.lower())}"
                           f"{' y tu código de profesor' if codigo_profesor else ''}. "
                           f"Escríbelo para activar tu cuenta.{_aviso_desarrollo(config)}", "ok")


def verificar(usuario, codigo, *, codigo_profesor=None, clave_nueva=None, reloj=time.time):
    """Comprueba el código del correo. Un profesor debe darlo junto con su `codigo_profesor` (los dos aciertan o ninguno vale, y
    cuenta un solo intento). Un administrador sin contraseña da además su `clave_nueva`, que se guarda al activarse la cuenta."""
    cuenta = almacen.obtener_usuario(usuario)
    if cuenta is None:
        return _fallo("no_existe")
    if cuenta["verificado"]:
        return _fallo("ya_verificada")
    codigo = (codigo or "").strip()
    if not (len(codigo) == LARGO and codigo.isascii() and codigo.isdigit()):
        return _fallo("formato")                                   # no gasta intentos
    es_profesor, es_admin = cuenta["role"] == "Profesor", cuenta["role"] == "Administrador"
    if es_profesor and not codigo_profesor_valido(codigo_profesor):
        return _fallo("formato_profesor")                          # tampoco
    if es_admin and len(clave_nueva or "") < almacen.MIN_CLAVE_ADMIN:
        return _fallo("clave_corta")                               # tampoco
    datos = almacen.datos_verificacion(usuario)
    if datos is None:
        return _fallo("no_existe")
    if reloj() >= datos["expira"]:
        return _fallo("vencido")                                   # tampoco gasta intentos
    usados = almacen.consumir_intento(usuario, MAX_INTENTOS)       # atómico: se descuenta ANTES de comparar
    if usados is None:
        return _cuenta_cambio(usuario) or _fallo("intentos")
    codigo_ok = hmac.compare_digest(hash_codigo(codigo, datos["sal"]), datos["codigo_hash"])
    profesor_ok = not es_profesor or hmac.compare_digest(huella_codigo_profesor(codigo_profesor), datos["prof_huella"] or "")
    if codigo_ok and profesor_ok:                                  # se calculan los dos: no se revela cuál falló por el tiempo
        if almacen.marcar_verificado(usuario, datos["codigo_hash"], clave=clave_nueva if es_admin else None):   # solo si sigue vigente
            if es_admin:
                return Resultado(True, "✅ Cuenta activada. Ya puedes iniciar sesión con tu contraseña.", "ok")
            return Resultado(True, "✅ Cuenta verificada. Ya puedes iniciar sesión.", "ok")
        return _cuenta_cambio(usuario) or _fallo("vencido")                 # un reenvío lo reemplazó mientras tanto
    quedan = MAX_INTENTOS - usados
    prefijo = "Código de verificación o de profesor incorrecto." if es_profesor else "Código incorrecto."
    if quedan <= 0:
        return _fallo("incorrecto", f"{prefijo} Agotaste los {MAX_INTENTOS} intentos: pide un código nuevo.")
    return _fallo("incorrecto", f"{prefijo} {'Te queda 1 intento' if quedan == 1 else f'Te quedan {quedan} intentos'}.")


def reenviar(usuario, *, enviar=None, reloj=time.time, config=None):
    """Código nuevo (invalida el anterior y reinicia los intentos). La espera se reserva de forma atómica antes de
    enviar; si el proveedor falla se restaura: el código anterior sigue valiendo y no se gasta la espera."""
    cuenta = almacen.obtener_usuario(usuario)
    if cuenta is None:
        return _fallo("no_existe")
    if cuenta["verificado"]:
        return _fallo("ya_verificada")
    es_profesor, es_admin = cuenta["role"] == "Profesor", cuenta["role"] == "Administrador"
    datos = almacen.datos_verificacion(usuario)
    if datos is None and es_admin:                                          # administrador sin contraseña y sin fila de verificación
        almacen.preparar_activacion(usuario)
        datos = almacen.datos_verificacion(usuario)
    if datos is None:
        return _fallo("no_existe")
    ahora = reloj()
    config, error = _resolver_config(config)
    if config is None:
        return _fallo("config", error)
    # los correos de los administradores son públicos: un tope de envíos dejaría a cualquiera bloquearles el acceso (queda la espera de 60 s)
    previo = almacen.reservar_envio(usuario, ahora, ESPERA_REENVIO_S, None if es_admin else MAX_ENVIOS)
    if previo == "limite":
        return _fallo("limite")
    if previo is None:
        datos = almacen.datos_verificacion(usuario)                         # se vuelve a leer: pudo cambiar o desaparecer
        if datos is None:
            return _cuenta_cambio(usuario) or _fallo("no_existe")
        espera = _espera(datos["ultimo_envio"], ahora) or ESPERA_REENVIO_S
        return _fallo("espera", f"Espera {espera} s para pedir otro código.", espera)
    codigo, sal = generar_codigo(), secrets.token_hex(8)
    codigo_profesor, prof_huella = _nuevo_codigo_profesor() if es_profesor else (None, None)     # el reenvío trae un código de profesor nuevo
    fallo = _enviar(enviar, datos["correo"], codigo, config, codigo_profesor)
    if fallo:
        almacen.restaurar_envio(usuario, previo)
        return _fallo("envio", fallo)
    if not almacen.renovar_codigo(usuario, hash_codigo(codigo, sal), sal, ahora + VIGENCIA_S, ahora, prof_huella):
        return _cuenta_cambio(usuario) or _fallo("no_existe")                # la cuenta desapareció durante el envío
    return Resultado(True, f"Te enviamos un código nuevo a {mascara_correo(datos['correo'])}.{_aviso_desarrollo(config)}", "ok")


def cancelar_registro(usuario, clave):
    """Borra una cuenta pendiente (pide su contraseña, para que nadie cancele la de otro). Nunca borra una verificada."""
    cuenta = almacen.obtener_usuario(usuario)
    if cuenta is None:
        return _fallo("no_existe")
    if cuenta["verificado"]:
        return _fallo("ya_verificada")
    if cuenta["role"] == "Administrador":
        return _fallo("no_cancelable")
    if not almacen.verificar_clave(usuario, clave or ""):
        return _fallo("clave")
    almacen.cancelar_pendiente(usuario)
    return Resultado(True, "Registro cancelado. Puedes empezar de nuevo.", "ok")


def segundos_para_reenviar(usuario, *, reloj=time.time):
    datos = almacen.datos_verificacion(usuario)
    return 0 if datos is None else _espera(datos["ultimo_envio"], reloj())
