"""Configuración base del agente de impresión.

El agente es GENÉRICO: cualquier sistema (POS, bot, etc.) puede mandarle
trabajos de impresión. Estos valores de entorno son solo la SEMILLA inicial
para la primera vez. Una vez que guardas desde la interfaz web (impresoras y
clientes), mandan los valores de /data/settings.json.
"""
import os


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


# --- Servidor HTTP ---
HOST = _get("HOST", "0.0.0.0")
PORT = _get_int("PORT", 8000)

# --- Almacenamiento ---
DATA_DIR = _get("DATA_DIR", "/data")

# --- Cola y reintentos (globales) ---
RETRY_DELAY_SECONDS = _get_int("RETRY_DELAY_SECONDS", 15)
MAX_ATTEMPTS = _get_int("MAX_ATTEMPTS", 0)        # 0 = reintentar indefinidamente
POLL_INTERVAL_SECONDS = _get_int("POLL_INTERVAL_SECONDS", 2)
KEEP_DONE = _get_int("KEEP_DONE", 200)            # cuántos impresos conservar (purga)

# --- Protección de la interfaz web (opcional) ---
ADMIN_USER = _get("ADMIN_USER", "admin")
ADMIN_PASSWORD = _get("ADMIN_PASSWORD")           # si se define, la web pide usuario/clave

# --- Semilla de UNA impresora por defecto (primera ejecución) ---
# Después se gestionan todas desde la web. Si SMB_HOST viene vacío, no se
# crea ninguna impresora semilla.
SEED_PRINTER = {
    "name": _get("PRINTER_NAME", "principal"),
    "conn_type": _get("CONN_TYPE", "smb").lower(),
    "raw_host": _get("RAW_HOST"),
    "raw_port": _get_int("RAW_PORT", 9100),
    "lpr_host": _get("LPR_HOST"),
    "lpr_port": _get_int("LPR_PORT", 515),
    "lpr_queue": _get("LPR_QUEUE"),
    "smb_host": _get("SMB_HOST"),
    "smb_share": _get("SMB_SHARE"),
    "smb_user": _get("SMB_USER"),
    "smb_pass": _get("SMB_PASS"),
    "smb_domain": _get("SMB_DOMAIN", "WORKGROUP"),
    "smb_ip": _get("SMB_IP"),
    "print_mode": _get("PRINT_MODE", "escpos").lower(),
    "paper_width_chars": _get_int("PAPER_WIDTH_CHARS", 48),
    "codepage": _get("CODEPAGE", "cp850"),
    "cut_paper": _get("CUT_PAPER", "true").lower() == "true",
    "open_drawer": _get("OPEN_DRAWER", "false").lower() == "true",
}

# --- Semilla de UN cliente/token por defecto (primera ejecución) ---
# Si defines PRINT_TOKEN, se crea un cliente semilla con ese token.
SEED_CLIENT_NAME = _get("CLIENT_NAME", "sistema")
SEED_CLIENT_TOKEN = _get("PRINT_TOKEN")

# Defaults globales de cola/reintentos persistidos en settings.json
GLOBAL_DEFAULTS = {
    "retry_delay_seconds": RETRY_DELAY_SECONDS,
    "max_attempts": MAX_ATTEMPTS,
    "keep_done": KEEP_DONE,
}
