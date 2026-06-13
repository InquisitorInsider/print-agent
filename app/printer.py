"""Render de trabajos de impresión y envío a la impresora por smbclient.

El agente es genérico. Un trabajo puede venir de dos formas:

1) Documento por bloques (recomendado): el sistema describe el ticket con una
   lista de bloques y el agente los convierte a ESC/POS (o a texto plano si la
   impresora usa driver de fabricante). El sistema NO necesita conocer ESC/POS.

       {
         "blocks": [
           {"type": "text",    "text": "RUTA80", "align": "center",
                                "bold": true, "size": "double"},
           {"type": "line"},
           {"type": "row",     "left": "2 x Pollo", "right": "37.80", "bold": true},
           {"type": "text",    "text": "   > con ají"},
           {"type": "qr",      "data": "https://...", "size": 6},
           {"type": "barcode", "data": "123456789", "symbology": "CODE128"},
           {"type": "feed",    "lines": 2},
           {"type": "cut"},
           {"type": "drawer"}
         ]
       }

   Tipos de bloque:
     text     -> text, align(left|center|right), bold, underline,
                 size(normal|double|double_h|double_w)
     row      -> left, right (justificados al ancho), bold
     line     -> char (por defecto "-"), full width
     feed     -> lines (n saltos de línea)
     cut      -> corte de papel (mode: partial|full)
     drawer   -> pulso para cajón de dinero
     qr       -> data, size(1-16)
     barcode  -> data, symbology(CODE128|CODE39|EAN13), height, hri(bool)

2) Crudo (raw): el sistema manda contenido ya formateado.
       {"raw": {"text": "....."}}                 # texto plano
       {"raw": {"escpos_base64": "G1.../..="}}    # bytes ESC/POS en base64
"""
from __future__ import annotations

import base64
import os
import subprocess
import tempfile
import textwrap

# --- Comandos ESC/POS ---
ESC = b"\x1b"
GS = b"\x1d"
INIT = ESC + b"@"
ALIGN = {"left": ESC + b"a\x00", "center": ESC + b"a\x01", "right": ESC + b"a\x02"}
BOLD_ON, BOLD_OFF = ESC + b"E\x01", ESC + b"E\x00"
UL_ON, UL_OFF = ESC + b"-\x01", ESC + b"-\x00"
SIZE = {
    "normal": GS + b"!\x00",
    "double": GS + b"!\x11",     # alto + ancho doble
    "double_h": GS + b"!\x01",   # solo alto doble
    "double_w": GS + b"!\x10",   # solo ancho doble
}
FEED = b"\n"
CUT_PARTIAL = GS + b"V\x42\x00"
CUT_FULL = GS + b"V\x41\x00"
DRAWER = ESC + b"p\x00\x19\xfa"

# Mapa codepage -> tabla ESC/POS (comando ESC t n) para que el HARDWARE
# interprete bien los acentos. cp850 es lo habitual en español.
_CODEPAGE_TABLE = {
    "cp437": 0, "cp850": 2, "cp860": 3, "cp863": 4, "cp865": 5,
    "cp858": 19, "cp852": 18, "cp1252": 16, "windows-1252": 16,
}


# ----------------------------- helpers -----------------------------
def _enc(text: str, codepage: str) -> bytes:
    try:
        return str(text).encode(codepage, errors="replace")
    except LookupError:
        return str(text).encode("ascii", errors="replace")


def _wrap(text: str, width: int) -> list[str]:
    out: list[str] = []
    for line in str(text).split("\n"):
        out.extend(textwrap.wrap(line, width=width) or [""])
    return out


def _row(left: str, right: str, width: int) -> str:
    left, right = str(left), str(right)
    if len(left) + 1 + len(right) <= width:
        return left + right.rjust(width - len(left))
    # no cabe en una línea: izquierda envuelta y derecha alineada abajo
    lines = _wrap(left, width)
    if right:
        lines.append(right.rjust(width))
    return "\n".join(lines)


def _codepage_select(codepage: str) -> bytes:
    n = _CODEPAGE_TABLE.get((codepage or "").lower())
    return ESC + b"t" + bytes([n]) if n is not None else b""


# ----------------------------- QR y código de barras -----------------------------
def _qr(data: str, size: int = 6) -> bytes:
    raw = data.encode("utf-8", errors="replace")
    size = max(1, min(16, int(size or 6)))
    store_len = len(raw) + 3
    pl, ph = store_len & 0xFF, (store_len >> 8) & 0xFF
    out = bytearray()
    out += GS + b"(k\x04\x00\x31\x41\x32\x00"          # modelo 2
    out += GS + b"(k\x03\x00\x31\x43" + bytes([size])   # tamaño del módulo
    out += GS + b"(k\x03\x00\x31\x45\x30"               # corrección de errores L
    out += GS + b"(k" + bytes([pl, ph]) + b"\x31\x50\x30" + raw  # datos
    out += GS + b"(k\x03\x00\x31\x51\x30"               # imprimir
    return bytes(out)


def _barcode(data: str, symbology: str = "CODE128", height: int = 80, hri: bool = True) -> bytes:
    out = bytearray()
    out += GS + b"h" + bytes([max(1, min(255, int(height or 80)))])  # altura
    out += GS + b"w\x02"                                             # ancho módulo
    out += GS + b"H" + (b"\x02" if hri else b"\x00")                 # HRI debajo
    sym = (symbology or "CODE128").upper()
    if sym == "CODE128":
        payload = b"{B" + data.encode("ascii", errors="replace")
        out += GS + b"k\x49" + bytes([len(payload)]) + payload
    elif sym == "CODE39":
        payload = data.encode("ascii", errors="replace")
        out += GS + b"k\x04" + payload + b"\x00"
    elif sym == "EAN13":
        payload = data.encode("ascii", errors="replace")
        out += GS + b"k\x02" + payload + b"\x00"
    else:
        payload = b"{B" + data.encode("ascii", errors="replace")
        out += GS + b"k\x49" + bytes([len(payload)]) + payload
    return bytes(out)


# ----------------------------- render por bloques -----------------------------
def render_blocks_escpos(blocks: list, printer_cfg: dict) -> bytes:
    width = int(printer_cfg.get("paper_width_chars") or 48)
    codepage = printer_cfg.get("codepage") or "cp850"
    out = bytearray()
    out += INIT
    out += _codepage_select(codepage)

    for b in blocks or []:
        if isinstance(b, str):
            b = {"type": "text", "text": b}
        t = (b.get("type") or "text").lower()

        if t == "text":
            out += ALIGN.get(b.get("align", "left"), ALIGN["left"])
            if b.get("bold"):
                out += BOLD_ON
            if b.get("underline"):
                out += UL_ON
            out += SIZE.get(b.get("size", "normal"), SIZE["normal"])
            for line in _wrap(b.get("text", ""), width):
                out += _enc(line, codepage) + FEED
            out += SIZE["normal"]
            if b.get("underline"):
                out += UL_OFF
            if b.get("bold"):
                out += BOLD_OFF
            out += ALIGN["left"]

        elif t == "row":
            if b.get("bold"):
                out += BOLD_ON
            for line in _row(b.get("left", ""), b.get("right", ""), width).split("\n"):
                out += _enc(line, codepage) + FEED
            if b.get("bold"):
                out += BOLD_OFF

        elif t in ("line", "divider"):
            ch = (b.get("char") or "-")[:1]
            out += _enc(ch * width, codepage) + FEED

        elif t == "feed":
            out += FEED * max(1, int(b.get("lines", 1)))

        elif t == "qr":
            out += ALIGN.get(b.get("align", "center"), ALIGN["center"])
            out += _qr(b.get("data", ""), b.get("size", 6))
            out += FEED + ALIGN["left"]

        elif t == "barcode":
            out += ALIGN.get(b.get("align", "center"), ALIGN["center"])
            out += _barcode(b.get("data", ""), b.get("symbology", "CODE128"),
                            b.get("height", 80), b.get("hri", True))
            out += FEED + ALIGN["left"]

        elif t == "cut":
            out += CUT_FULL if (b.get("mode") == "full") else CUT_PARTIAL

        elif t == "drawer":
            out += DRAWER

    return bytes(out)


def render_blocks_text(blocks: list, printer_cfg: dict) -> bytes:
    """Versión texto plano (colas con driver de fabricante). Ignora ESC/POS."""
    width = int(printer_cfg.get("paper_width_chars") or 48)
    codepage = printer_cfg.get("codepage") or "cp850"
    lines: list[str] = []
    for b in blocks or []:
        if isinstance(b, str):
            b = {"type": "text", "text": b}
        t = (b.get("type") or "text").lower()
        if t == "text":
            for line in _wrap(b.get("text", ""), width):
                align = b.get("align", "left")
                lines.append(line.center(width) if align == "center"
                             else line.rjust(width) if align == "right" else line)
        elif t == "row":
            lines.extend(_row(b.get("left", ""), b.get("right", ""), width).split("\n"))
        elif t in ("line", "divider"):
            lines.append((b.get("char") or "-")[:1] * width)
        elif t == "feed":
            lines.extend([""] * max(1, int(b.get("lines", 1))))
        # qr/barcode/cut/drawer no aplican en texto plano
    return _enc("\n".join(lines) + "\n\n\n\n", codepage)


# ----------------------------- render raw -----------------------------
def render_raw(raw: dict, printer_cfg: dict) -> bytes:
    if "escpos_base64" in raw:
        return base64.b64decode(raw["escpos_base64"])
    text = raw.get("text", "")
    codepage = printer_cfg.get("codepage") or "cp850"
    payload = bytearray(INIT + _codepage_select(codepage))
    payload += _enc(text, codepage)
    if not text.endswith("\n"):
        payload += FEED
    if raw.get("cut", True) and (printer_cfg.get("print_mode") or "escpos") == "escpos":
        payload += FEED * 2 + CUT_PARTIAL
    return bytes(payload)


# ----------------------------- punto de entrada -----------------------------
def render(content: dict, printer_cfg: dict) -> bytes:
    """content: {"blocks": [...]} o {"raw": {...}}."""
    if content.get("raw"):
        return render_raw(content["raw"], printer_cfg)
    blocks = content.get("blocks") or []
    if (printer_cfg.get("print_mode") or "escpos").lower() == "text":
        return render_blocks_text(blocks, printer_cfg)
    return render_blocks_escpos(blocks, printer_cfg)


# ----------------------------- envío por SMB -----------------------------
class PrinterError(RuntimeError):
    pass


def send_to_printer(payload: bytes, printer_cfg: dict) -> None:
    host = printer_cfg.get("smb_host")
    share = printer_cfg.get("smb_share")
    if not host or not share:
        raise PrinterError(
            f"Impresora '{printer_cfg.get('name','?')}' sin host/recurso configurado"
        )

    with tempfile.NamedTemporaryFile(prefix="ticket_", suffix=".prn", delete=False) as f:
        f.write(payload)
        tmp_path = f.name
    try:
        cmd = ["smbclient", f"//{host}/{share}"]
        user = printer_cfg.get("smb_user")
        if user:
            cmd += ["-U", f"{user}%{printer_cfg.get('smb_pass','')}"]
        else:
            cmd += ["-N"]
        if printer_cfg.get("smb_domain"):
            cmd += ["-W", printer_cfg["smb_domain"]]
        if printer_cfg.get("smb_ip"):
            cmd += ["-I", printer_cfg["smb_ip"]]
        cmd += ["-c", f'print "{tmp_path}"']

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            raise PrinterError(
                f"smbclient falló (code {proc.returncode}): "
                f"{(proc.stderr or proc.stdout).strip()}"
            )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def print_job(content: dict, printer_cfg: dict) -> None:
    send_to_printer(render(content, printer_cfg), printer_cfg)
