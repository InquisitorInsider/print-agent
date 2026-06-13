"""Cola persistente en disco con reintentos. Ningún trabajo se pierde.

Cada trabajo guarda a qué impresora va ('printer') y qué sistema lo mandó
('source'), y se rutea a la impresora correcta al imprimir.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime

from . import config, printer, settings

PENDING = os.path.join(config.DATA_DIR, "pending")
DONE = os.path.join(config.DATA_DIR, "done")
FAILED = os.path.join(config.DATA_DIR, "failed")

_lock = threading.Lock()
_last_error: str | None = None
_last_ok: str | None = None


def _ensure_dirs() -> None:
    for d in (PENDING, DONE, FAILED):
        os.makedirs(d, exist_ok=True)


def enqueue(content: dict, printer_name: str = "", source: str = "", copies: int = 1) -> str:
    """Encola un trabajo de impresión. content = {"blocks":[...]} o {"raw":{...}}."""
    _ensure_dirs()
    job_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    job = {
        "job_id": job_id,
        "printer": (printer_name or "").strip(),
        "source": (source or "").strip(),
        "copies": max(1, int(copies or 1)),
        "content": content,
        "attempts": 0,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "next_try": 0,
        "last_error": None,
    }
    path = os.path.join(PENDING, job_id + ".json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)  # escritura atómica
    return job_id


def _list_pending() -> list[str]:
    if not os.path.isdir(PENDING):
        return []
    return sorted(f for f in os.listdir(PENDING) if f.endswith(".json"))


def _process_one(filename: str) -> None:
    global _last_error, _last_ok
    path = os.path.join(PENDING, filename)
    try:
        with open(path, encoding="utf-8") as f:
            job = json.load(f)
    except (OSError, json.JSONDecodeError):
        return

    if time.time() < job.get("next_try", 0):
        return

    printer_cfg = settings.get_printer(job.get("printer"))
    try:
        if printer_cfg is None:
            wanted = job.get("printer") or "(por defecto)"
            raise printer.PrinterError(f"No existe la impresora '{wanted}'")
        for _ in range(job.get("copies", 1)):
            printer.print_job(job["content"], printer_cfg)
    except Exception as exc:  # noqa: BLE001  capturamos todo para reintentar
        job["attempts"] = job.get("attempts", 0) + 1
        job["last_error"] = str(exc)
        job["next_try"] = time.time() + int(settings.get("retry_delay_seconds") or 15)
        _last_error = f"[{datetime.now().isoformat(timespec='seconds')}] {exc}"
        max_attempts = int(settings.get("max_attempts") or 0)
        if max_attempts and job["attempts"] >= max_attempts:
            with _lock:
                os.replace(path, os.path.join(FAILED, filename))
        else:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(job, f, ensure_ascii=False, indent=2)
        return

    _last_ok = datetime.now().isoformat(timespec="seconds")
    job["printed_at"] = _last_ok
    with _lock:
        try:
            with open(os.path.join(DONE, filename), "w", encoding="utf-8") as f:
                json.dump(job, f, ensure_ascii=False, indent=2)
            os.unlink(path)
        except OSError:
            pass
    _purge_done()


def _purge_done() -> None:
    keep = int(settings.get("keep_done") or 200)
    if keep <= 0:
        return
    try:
        files = sorted(f for f in os.listdir(DONE) if f.endswith(".json"))
    except OSError:
        return
    for fn in files[:-keep] if len(files) > keep else []:
        try:
            os.unlink(os.path.join(DONE, fn))
        except OSError:
            pass


def _worker_loop() -> None:
    _ensure_dirs()
    global _last_error
    while True:
        try:
            for filename in _list_pending():
                _process_one(filename)
        except Exception as exc:  # noqa: BLE001
            _last_error = f"worker: {exc}"
        time.sleep(config.POLL_INTERVAL_SECONDS)


def start_worker() -> None:
    _ensure_dirs()
    threading.Thread(target=_worker_loop, name="print-worker", daemon=True).start()


def _read_dir(path: str, limit: int | None = None) -> list[dict]:
    if not os.path.isdir(path):
        return []
    files = sorted((f for f in os.listdir(path) if f.endswith(".json")), reverse=True)
    if limit:
        files = files[:limit]
    out = []
    for fn in files:
        try:
            with open(os.path.join(path, fn), encoding="utf-8") as f:
                job = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        out.append({
            "job_id": job.get("job_id"),
            "printer": job.get("printer") or "(defecto)",
            "source": job.get("source") or "—",
            "attempts": job.get("attempts", 0),
            "created_at": job.get("created_at"),
            "printed_at": job.get("printed_at"),
            "last_error": job.get("last_error"),
        })
    return out


def jobs() -> dict:
    _ensure_dirs()
    return {
        "pending": _read_dir(PENDING),
        "failed": _read_dir(FAILED),
        "done": _read_dir(DONE, limit=15),
    }


def retry_failed() -> int:
    _ensure_dirs()
    moved = 0
    for fn in [f for f in os.listdir(FAILED) if f.endswith(".json")]:
        src = os.path.join(FAILED, fn)
        try:
            with open(src, encoding="utf-8") as f:
                job = json.load(f)
            job["attempts"] = 0
            job["next_try"] = 0
            with open(os.path.join(PENDING, fn), "w", encoding="utf-8") as f:
                json.dump(job, f, ensure_ascii=False, indent=2)
            os.unlink(src)
            moved += 1
        except (OSError, json.JSONDecodeError):
            continue
    return moved


def clear_failed() -> int:
    _ensure_dirs()
    removed = 0
    for fn in [f for f in os.listdir(FAILED) if f.endswith(".json")]:
        try:
            os.unlink(os.path.join(FAILED, fn))
            removed += 1
        except OSError:
            continue
    return removed


def stats() -> dict:
    _ensure_dirs()
    return {
        "pending": len(_list_pending()),
        "failed": len([f for f in os.listdir(FAILED) if f.endswith(".json")]),
        "last_ok": _last_ok,
        "last_error": _last_error,
    }
