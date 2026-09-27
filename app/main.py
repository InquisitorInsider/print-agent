"""API + interfaz web del agente de impresión GENÉRICO.

Cualquier sistema (POS, bot, ERP, etc.) puede mandar trabajos de impresión.
El agente no sabe nada del negocio: solo recibe documentos por bloques o
contenido crudo, los encola y los imprime en la impresora indicada.

API para sistemas que imprimen:
  POST /print        -> encolar un trabajo de TEXTO (blocks o raw), rápido.
                        Header opcional: Authorization: Bearer <token-del-cliente>
  POST /print-image  -> encolar una IMAGEN (PNG/JPG en base64), más lento
                        (rasterizado ESC/POS). Mismo header de auth.
  GET  /printers     -> lista de nombres de impresoras disponibles
  GET  /health       -> salud del servicio y de la cola

Interfaz / administración (protegida con ADMIN_PASSWORD si se define):
  GET  /                  -> interfaz web de configuración
  GET/POST/DELETE /api/printers   -> gestionar impresoras
  GET/POST/DELETE /api/clients    -> gestionar clientes/tokens
  GET/POST        /api/globals    -> reintentos/retención
  GET  /api/status        -> estado de la cola + trabajos
  POST /api/test          -> ticket de prueba (a una impresora)
  POST /api/test-image    -> imagen de prueba (a una impresora)
  POST /api/retry|/api/clear -> reencolar / borrar fallidos
"""
from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from . import config, queue, settings, ui

app = FastAPI(title="print-agent", version="3.0.0", docs_url="/docs")
_basic = HTTPBasic(auto_error=False)


# ---------- Auth de administración (interfaz web / API de config) ----------
def require_admin(creds: HTTPBasicCredentials | None = Depends(_basic)) -> None:
    if not config.ADMIN_PASSWORD:
        return
    ok = (
        creds is not None
        and secrets.compare_digest(creds.username, config.ADMIN_USER)
        and secrets.compare_digest(creds.password, config.ADMIN_PASSWORD)
    )
    if not ok:
        raise HTTPException(
            status_code=401, detail="No autorizado",
            headers={"WWW-Authenticate": "Basic"},
        )


# ---------- Modelo del trabajo de impresión (genérico) ----------
class PrintJob(BaseModel):
    printer: str | None = None          # nombre de la impresora (vacío = por defecto)
    copies: int | None = 1
    blocks: list[Any] | None = None     # documento por bloques
    raw: dict[str, Any] | None = None   # {"text": ...} o {"escpos_base64": ...}
    source: str | None = None           # opcional; normalmente lo da el token
    model_config = {"extra": "ignore"}


class ImagePrintJob(BaseModel):
    printer: str | None = None
    copies: int | None = 1
    image_base64: str                   # PNG/JPG completo, codificado en base64
    width_dots: int | None = None       # override; si no, usa el de la impresora
    cut: bool | None = True
    feed_after: int | None = 1
    source: str | None = None
    model_config = {"extra": "ignore"}


def _resolve_source(authorization: str | None, explicit: str | None) -> str:
    """Autentica por token (si hay clientes) y devuelve el nombre del origen."""
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if settings.has_clients():
        name = settings.resolve_client(token)
        if not name:
            raise HTTPException(status_code=401, detail="Token inválido o ausente")
        return name
    # Sin clientes configurados: abierto en la red local.
    return (explicit or "").strip() or "anónimo"


# ---------- Endpoints para sistemas que imprimen ----------
@app.post("/print", status_code=202)
def print_endpoint(job: PrintJob, authorization: str | None = Header(default=None)) -> dict:
    source = _resolve_source(authorization, job.source)
    if not job.blocks and not job.raw:
        raise HTTPException(status_code=400, detail="Falta 'blocks' o 'raw'")
    content: dict = {}
    if job.raw:
        content["raw"] = job.raw
    else:
        content["blocks"] = job.blocks
    job_id = queue.enqueue(content, printer_name=job.printer or "",
                           source=source, copies=job.copies or 1)
    return {"accepted": True, "job_id": job_id, "printer": job.printer or settings.default_printer(),
            "source": source}


@app.post("/print-image", status_code=202)
def print_image_endpoint(job: ImagePrintJob, authorization: str | None = Header(default=None)) -> dict:
    source = _resolve_source(authorization, job.source)
    if not job.image_base64:
        raise HTTPException(status_code=400, detail="Falta 'image_base64'")
    content = {"image": {
        "base64": job.image_base64,
        "width_dots": job.width_dots,
        "cut": job.cut if job.cut is not None else True,
        "feed_after": job.feed_after if job.feed_after is not None else 1,
    }}
    job_id = queue.enqueue(content, printer_name=job.printer or "",
                           source=source, copies=job.copies or 1)
    return {"accepted": True, "job_id": job_id, "printer": job.printer or settings.default_printer(),
            "source": source}


@app.get("/printers")
def list_printer_names() -> dict:
    return {
        "default": settings.default_printer(),
        "printers": [p["name"] for p in settings.list_printers()],
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok", **queue.stats(),
            "printers": [p["name"] for p in settings.list_printers()]}


# ---------- Interfaz web ----------
@app.get("/", response_class=HTMLResponse)
def admin_page(_: None = Depends(require_admin)) -> str:
    return ui.PAGE


# ---------- API de configuración (administración) ----------
@app.get("/api/settings")
def api_settings(_: None = Depends(require_admin)) -> dict:
    return settings.public()


@app.post("/api/printers")
def api_save_printer(p: dict, _: None = Depends(require_admin)) -> dict:
    try:
        settings.save_printer(p)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if p.get("make_default"):
        settings.set_default_printer(str(p.get("name", "")).strip())
    return settings.public()


@app.delete("/api/printers/{name}")
def api_delete_printer(name: str, _: None = Depends(require_admin)) -> dict:
    settings.delete_printer(name)
    return settings.public()


@app.post("/api/clients")
def api_save_client(c: dict, _: None = Depends(require_admin)) -> dict:
    try:
        settings.save_client(c)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return settings.public()


@app.delete("/api/clients/{name}")
def api_delete_client(name: str, _: None = Depends(require_admin)) -> dict:
    settings.delete_client(name)
    return settings.public()


@app.post("/api/globals")
def api_globals(payload: dict, _: None = Depends(require_admin)) -> dict:
    settings.save_globals(payload)
    return settings.public()


@app.get("/api/status")
def api_status(_: None = Depends(require_admin)) -> dict:
    return {**queue.stats(), "jobs": queue.jobs()}


@app.post("/api/test", status_code=202)
def api_test(payload: dict | None = None, _: None = Depends(require_admin)) -> dict:
    name = (payload or {}).get("printer", "") if payload else ""
    job_id = queue.enqueue(_sample_doc(name or settings.default_printer()),
                           printer_name=name, source="prueba")
    return {"accepted": True, "job_id": job_id}


@app.post("/api/test-image", status_code=202)
def api_test_image(payload: dict | None = None, _: None = Depends(require_admin)) -> dict:
    name = (payload or {}).get("printer", "") if payload else ""
    printer_cfg = settings.get_printer(name) or {}
    width = int(printer_cfg.get("image_width_dots") or 0) or (
        384 if int(printer_cfg.get("paper_width_chars") or 48) <= 32 else 576)
    content = {"image": {"base64": _sample_image_base64(width), "cut": True, "feed_after": 1}}
    job_id = queue.enqueue(content, printer_name=name, source="prueba")
    return {"accepted": True, "job_id": job_id}


@app.post("/api/retry")
def api_retry(_: None = Depends(require_admin)) -> dict:
    return {"moved": queue.retry_failed()}


@app.post("/api/clear")
def api_clear(_: None = Depends(require_admin)) -> dict:
    return {"removed": queue.clear_failed()}


def _sample_image_base64(width: int) -> str:
    """Genera un PNG de prueba simple (texto + patrón) para 'Probar imagen',
    sin depender de que el usuario tenga a mano un archivo real."""
    import base64
    import io

    from PIL import Image, ImageDraw

    height = max(80, width // 3)
    img = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, width - 1, height - 1], outline=0, width=3)
    text = "PRUEBA DE IMAGEN"
    bbox = draw.textbbox((0, 0), text)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((width - tw) // 2, (height - th) // 2), text, fill=0)
    draw.line([(0, height - 1), (width, 0)], fill=0, width=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _sample_doc(printer_name: str) -> dict:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {"blocks": [
        {"type": "text", "text": "TICKET DE PRUEBA", "align": "center",
         "bold": True, "size": "double"},
        {"type": "text", "text": "print-agent", "align": "center"},
        {"type": "line", "char": "="},
        {"type": "text", "text": f"Impresora: {printer_name or '(por defecto)'}"},
        {"type": "text", "text": f"Fecha:     {now}"},
        {"type": "line"},
        {"type": "row", "left": "2 x Articulo de ejemplo", "right": "20.00", "bold": True},
        {"type": "row", "left": "1 x Otro articulo", "right": "5.50"},
        {"type": "line"},
        {"type": "row", "left": "TOTAL", "right": "25.50", "bold": True},
        {"type": "text", "text": "Acentos: ñ á é í ó ú ¿? ¡!"},
        {"type": "qr", "data": "https://print-agent.local/test", "size": 6},
        {"type": "feed", "lines": 1},
        {"type": "text", "text": "Configuracion correcta :)", "align": "center"},
        {"type": "feed", "lines": 2},
        {"type": "cut"},
    ]}


@app.on_event("startup")
def _startup() -> None:
    settings.load()
    queue.start_worker()
