"""Envío de correos de Neon OS por SMTP (Brevo, Gmail, Outlook o cualquier proveedor con SMTP).

Toda la configuración sale de variables de entorno: nada de credenciales en el código ni en archivos del proyecto.
Sin base de datos ni interfaz. Ver docs/CORREO.md para configurar el proveedor.

Comandos (los ejecuta quien tenga sus credenciales; las pruebas automáticas nunca envían correos reales):
    python correo.py --config            qué variables están definidas (sin mostrar sus valores)
    python correo.py --probar destino    envía un correo de prueba real
"""
import math
import os
import re
import smtplib
import ssl
import sys
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import parseaddr

# Dirección ASCII sencilla (parte local «dot-atom» + dominio con puntos): sin espacios, saltos de línea, comas, comillas,
# paréntesis ni corchetes. Evita inyección de cabeceras y que direcciones distintas (p. ej. «a(1)@x.co») lleguen al mismo buzón.
_ATEXT = r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"
_ETIQUETA = r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
DIRECCION_RE = re.compile(rf"{_ATEXT}(?:\.{_ATEXT})*@(?:{_ETIQUETA}\.)+{_ETIQUETA}")
ASUNTO = "Tu código de verificación de Neon OS"
VARIABLES_OBLIGATORIAS = ("NEON_SMTP_HOST", "NEON_SMTP_USUARIO", "NEON_SMTP_CLAVE", "NEON_SMTP_REMITENTE")
VARIABLES_OPCIONALES = ("NEON_SMTP_PUERTO", "NEON_SMTP_SEGURIDAD", "NEON_SMTP_TIMEOUT", "NEON_CORREO_MODO")


class ErrorCorreo(Exception):
    """Error al configurar o enviar. `mensaje` está pensado para mostrarse al usuario (nunca contiene secretos)."""

    def __init__(self, mensaje, reintentable=True):
        super().__init__(mensaje)
        self.mensaje, self.reintentable = mensaje, reintentable


@dataclass(frozen=True)
class Config:
    host: str = ""
    puerto: int = 0
    usuario: str = ""
    clave: str = field(default="", repr=False)    # fuera del repr: no debe aparecer en registros ni en trazas
    remitente: str = ""
    seguridad: str = "starttls"
    timeout: float = 15.0
    modo: str = "smtp"                            # "smtp" (producción) o "consola" (desarrollo: imprime el código)


def cargar_config(env=None):
    """Lee la configuración del entorno. None si falta alguna variable obligatoria (modo smtp);
    ErrorCorreo (no reintentable) si hay un valor inválido."""
    env = os.environ if env is None else env

    def valor(nombre, defecto=""):
        return str(env.get(nombre, defecto)).strip()

    modo = valor("NEON_CORREO_MODO", "smtp").lower()
    if modo not in ("smtp", "consola"):
        raise ErrorCorreo("NEON_CORREO_MODO debe ser «smtp» o «consola».", False)
    if modo == "consola":
        return Config(modo="consola")
    host, usuario, clave, remitente = (valor(n) for n in VARIABLES_OBLIGATORIAS)
    if not (host and usuario and clave and remitente):
        return None
    if re.search(r"[\r\n]", remitente) or not DIRECCION_RE.fullmatch(parseaddr(remitente)[1]):
        raise ErrorCorreo("NEON_SMTP_REMITENTE no es una dirección de correo válida.", False)
    seguridad = valor("NEON_SMTP_SEGURIDAD", "starttls").lower()
    if seguridad not in ("starttls", "ssl"):
        raise ErrorCorreo("NEON_SMTP_SEGURIDAD debe ser «starttls» o «ssl».", False)
    try:
        puerto = int(valor("NEON_SMTP_PUERTO", "465" if seguridad == "ssl" else "587"))
        timeout = float(valor("NEON_SMTP_TIMEOUT", "15"))
    except ValueError:
        raise ErrorCorreo("NEON_SMTP_PUERTO y NEON_SMTP_TIMEOUT deben ser números.", False) from None
    if not 1 <= puerto <= 65535 or not math.isfinite(timeout) or timeout <= 0:
        raise ErrorCorreo("NEON_SMTP_PUERTO o NEON_SMTP_TIMEOUT fuera de rango.", False)
    return Config(host, puerto, usuario, clave, remitente, seguridad, timeout, "smtp")


def _validar_destino(destino):
    if not isinstance(destino, str) or not DIRECCION_RE.fullmatch(destino):
        raise ErrorCorreo("La dirección de destino no es válida.", False)


def construir_mensaje(destino, codigo, config, vigencia_min=10, prueba=False, codigo_profesor=None):
    _validar_destino(destino)
    mensaje = EmailMessage()
    mensaje["From"], mensaje["To"] = config.remitente, destino
    if prueba:
        mensaje["Subject"] = "Prueba de correo de Neon OS"
        mensaje.set_content("Hola,\n\nEste es un mensaje de prueba de Neon OS: el envío de correos está bien configurado.\n")
    elif codigo_profesor:
        mensaje["Subject"] = "Tu código de verificación y tu código de profesor de Neon OS"
        mensaje.set_content(f"Hola,\n\nPara activar tu cuenta de profesor escribe estos dos códigos en Neon OS:\n\n"
                            f"    Código de verificación:  {codigo}\n"
                            f"    Código de profesor:      {codigo_profesor}\n\n"
                            f"El código de verificación vale {vigencia_min} minutos. El código de profesor es solo tuyo: no lo compartas. "
                            "Si no fuiste tú quien se registró, ignora este mensaje.\n")
    else:
        mensaje["Subject"] = ASUNTO
        mensaje.set_content(f"Hola,\n\nTu código de verificación de Neon OS es:\n\n    {codigo}\n\n"
                            f"Es válido por {vigencia_min} minutos. Si no fuiste tú quien se registró, ignora este mensaje.\n")
    return mensaje


def _es_temporal(error):
    """¿El proveedor rechazó con un código 4xx (límite, greylisting, fallo pasajero)? Eso se reintenta más tarde."""
    if isinstance(error, smtplib.SMTPRecipientsRefused):
        codigos = [c for c, _ in error.recipients.values()]
        return bool(codigos) and all(isinstance(c, int) and 400 <= c < 500 for c in codigos)
    codigo = getattr(error, "smtp_code", None)
    return isinstance(codigo, int) and 400 <= codigo < 500


def _traducir(error):
    """Convierte una excepción de smtplib/red en un ErrorCorreo con un texto claro y sin secretos."""
    if isinstance(error, (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected)):
        return ErrorCorreo("No se pudo conectar con el servidor de correo.", True)
    # OJO: en Python 3.10 SMTPException es subclase de OSError, así que los tipos SMTP se revisan antes que OSError
    if isinstance(error, smtplib.SMTPException) and _es_temporal(error):         # antes que remitente/destinatario/login
        return ErrorCorreo("El proveedor limitó el envío por ahora; inténtalo más tarde.", True)
    if isinstance(error, smtplib.SMTPAuthenticationError):
        if b"unauthorized ip" in bytes(getattr(error, "smtp_error", b"") or b"").lower():     # Brevo: «525 5.7.1 Unauthorized IP address»
            return ErrorCorreo("El proveedor de correo no permite enviar desde esta conexión (dirección IP no autorizada). "
                               "Avisa al administrador: debe quitar el bloqueo por IP en el proveedor.", False)
        return ErrorCorreo("El proveedor rechazó las credenciales de correo configuradas.", False)
    if isinstance(error, smtplib.SMTPSenderRefused):
        return ErrorCorreo("El remitente configurado no está autorizado en el proveedor.", False)
    if isinstance(error, smtplib.SMTPRecipientsRefused):
        return ErrorCorreo("La dirección de correo fue rechazada por el proveedor.", False)
    if isinstance(error, smtplib.SMTPResponseException):
        return ErrorCorreo(f"El servidor de correo devolvió un error (código {error.smtp_code}).", True)
    if isinstance(error, smtplib.SMTPException):
        return ErrorCorreo("El servidor de correo devolvió un error.", True)
    return ErrorCorreo("No se pudo conectar con el servidor de correo.", True)    # OSError: red, tiempo agotado, TLS


def _cerrar(servidor):
    """Se despide (QUIT) y cierra. Un fallo al despedirse no cambia el resultado: el mensaje ya se entregó, o ya falló por otra causa."""
    try:
        servidor.quit()
    except Exception:  # noqa: BLE001
        pass
    finally:
        try:
            servidor.close()
        except Exception:  # noqa: BLE001
            pass


# Brevo se llamaba Sendinblue: según el nodo que responda el DNS (p. ej. el de Sudamérica), el certificado trae solo uno de
# los dos nombres. Se prueban ambos, siempre con la verificación completa del certificado y del nombre.
NOMBRES_BREVO = ("smtp-relay.brevo.com", "smtp-relay.sendinblue.com")


def _hosts_a_probar(host):
    if host.lower() in NOMBRES_BREVO:
        return [host] + [n for n in NOMBRES_BREVO if n != host.lower()]
    return [host]


def _enviar_a(host, mensaje, config, smtp_factory, contexto):
    if config.seguridad == "ssl":
        servidor = (smtp_factory or smtplib.SMTP_SSL)(host, config.puerto, timeout=config.timeout, context=contexto)
    else:
        servidor = (smtp_factory or smtplib.SMTP)(host, config.puerto, timeout=config.timeout)
    try:
        if config.seguridad != "ssl":
            servidor.starttls(context=contexto)
        servidor.login(config.usuario, config.clave)
        servidor.send_message(mensaje)
    finally:
        _cerrar(servidor)                             # el cierre ocurre siempre, aunque falle el envío


def _enviar_smtp(mensaje, config, smtp_factory):
    contexto = ssl.create_default_context()          # verifica el certificado y el nombre del servidor
    try:
        hosts = _hosts_a_probar(config.host)
        for i, host in enumerate(hosts):
            try:
                _enviar_a(host, mensaje, config, smtp_factory, contexto)
                break
            except ssl.SSLCertVerificationError:      # falla antes del login: no se envió nada, es seguro reintentar
                if i == len(hosts) - 1:
                    raise
    except ErrorCorreo:
        raise
    except (smtplib.SMTPException, OSError) as error:
        raise _traducir(error) from None
    except Exception:  # noqa: BLE001 - p. ej. una clave con caracteres no ASCII: sin traza ni texto que pueda contenerla
        raise ErrorCorreo("No se pudo enviar el correo por un error inesperado del cliente de correo.", False) from None


def _config_o_error(config):
    config = cargar_config() if config is None else config
    if config is None:
        raise ErrorCorreo("El envío de correos no está configurado: define NEON_SMTP_HOST, NEON_SMTP_USUARIO, "
                          "NEON_SMTP_CLAVE y NEON_SMTP_REMITENTE (ver docs/CORREO.md).", False)
    return config


def enviar_codigo(destino, codigo, config=None, smtp_factory=None, vigencia_min=10, codigo_profesor=None):
    """Envía el código de verificación (y, a los profesores, su código de profesor en el mismo correo). En modo «consola»
    (solo desarrollo, pedido explícitamente) lo imprime y no envía nada. Lanza ErrorCorreo si falla; en modo smtp los
    códigos nunca se imprimen ni se registran."""
    config = _config_o_error(config)
    _validar_destino(destino)
    if config.modo == "consola":
        print(f"[Neon OS · modo desarrollo] Código para {destino}: {codigo}", flush=True)
        if codigo_profesor:
            print(f"[Neon OS · modo desarrollo] Código de profesor para {destino}: {codigo_profesor}", flush=True)
        return
    _enviar_smtp(construir_mensaje(destino, codigo, config, vigencia_min, codigo_profesor=codigo_profesor), config, smtp_factory)


def enviar_prueba(destino, config=None, smtp_factory=None):
    """Envía el correo de prueba. Devuelve True si se envió; False en modo «consola» (desarrollo), donde no se envía nada."""
    config = _config_o_error(config)
    if config.modo == "consola":
        return False
    _enviar_smtp(construir_mensaje(destino, "", config, prueba=True), config, smtp_factory)
    return True


def main(argv=None, smtp_factory=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--config"]:
        try:
            config = cargar_config()
        except ErrorCorreo as error:
            print(f"❌ {error.mensaje}")
            return 1
        print("Variables obligatorias (solo se muestra si están definidas, nunca su valor):")
        for nombre in VARIABLES_OBLIGATORIAS:
            print(f"  {nombre}: {'definida' if str(os.environ.get(nombre, '')).strip() else 'falta'}")
        print("Opcionales:")
        for nombre in VARIABLES_OPCIONALES:
            print(f"  {nombre}: {'definida' if str(os.environ.get(nombre, '')).strip() else 'no definida (valor por defecto)'}")
        if config is None:
            print("❌ El envío de correos no está listo: faltan variables obligatorias.")
            return 1
        print("✅ Modo desarrollo (consola): no se enviará ningún correo." if config.modo == "consola" else "✅ Configuración completa.")
        return 0
    if len(argv) == 2 and argv[0] == "--probar":
        try:
            enviado = enviar_prueba(argv[1], smtp_factory=smtp_factory)
        except ErrorCorreo as error:
            print(f"❌ {error.mensaje}")
            return 1
        if not enviado:
            print("ℹ️ Modo desarrollo (NEON_CORREO_MODO=consola): no se envió nada. Quita esa variable para probar el envío real.")
            return 1
        print(f"✅ Correo de prueba enviado a {argv[1]}. Revisa la bandeja (y el spam).")
        return 0
    print("Uso:\n  python correo.py --config             comprueba qué variables están definidas\n"
          "  python correo.py --probar destino     envía un correo de prueba real")
    return 2


if __name__ == "__main__":
    for _flujo in (sys.stdout, sys.stderr):          # la consola de Windows (cp1252) no puede imprimir ✅/❌
        if hasattr(_flujo, "reconfigure"):
            _flujo.reconfigure(errors="replace")
    import entorno                                  # lee el .env junto a la app (lo del sistema tiene prioridad)
    for _linea in entorno.describir(entorno.cargar_env(avisar=False)):
        print(_linea)
    sys.exit(main())
