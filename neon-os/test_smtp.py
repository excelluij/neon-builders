"""Diagnóstico SMTP por fases. Ejecutar: python -u test_smtp.py
No imprime la clave; solo longitud, prefijo no secreto y problemas de formato."""
import smtplib
import socket
import ssl
from pathlib import Path

ENV = Path(__file__).parent / ".env"
TIMEOUT = 10


def leer_env(ruta):
    datos = {}
    for linea in ruta.read_text(encoding="utf-8-sig").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            k, v = linea.split("=", 1)
            datos[k.strip()] = v
    return datos


print("FASE 1: leer .env ->", ENV, "existe:", ENV.exists())
cfg = leer_env(ENV)
host = cfg.get("NEON_SMTP_HOST", "").strip()
puerto = int(cfg.get("NEON_SMTP_PUERTO", "587").strip() or 587)
usuario = cfg.get("NEON_SMTP_USUARIO", "")
clave = cfg.get("NEON_SMTP_CLAVE", "")
print("  host:", host, "| puerto:", puerto)
print("  usuario:", repr(usuario), "(espacios/comillas sobrantes:", usuario != usuario.strip() or usuario[:1] in "\"'", ")")
print("  clave: longitud", len(clave), "| empieza por 'xsmtpsib-':", clave.strip().startswith("xsmtpsib-"),
      "| espacios/comillas sobrantes:", clave != clave.strip() or clave[:1] in "\"'")
print("  remitente:", repr(cfg.get("NEON_SMTP_REMITENTE", "")))

print("FASE 2: conexión TCP...")
socket.create_connection((host, puerto), timeout=TIMEOUT).close()
print("  OK")

print("FASE 3: STARTTLS...")
s = smtplib.SMTP(host, puerto, timeout=TIMEOUT)
s.ehlo()
s.starttls(context=ssl.create_default_context())
s.ehlo()
print("  OK")

print("FASE 4: login...")
try:
    s.login(usuario.strip().strip("\"'"), clave.strip().strip("\"'"))
    print("  LOGIN OK")
except smtplib.SMTPAuthenticationError as e:
    print("  LOGIN FALLÓ:", e.smtp_code, e.smtp_error)
finally:
    s.quit()
