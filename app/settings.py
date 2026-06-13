"""Ajustes en caliente, persistidos en /data/settings.json.

Estructura:
{
  "printers": [ {name, smb_host, smb_share, smb_user, smb_pass, smb_domain,
                 smb_ip, print_mode, paper_width_chars, codepage,
                 cut_paper, open_drawer}, ... ],
  "default_printer": "principal",
  "clients": [ {name, token}, ... ],
  "retry_delay_seconds": 15,
  "max_attempts": 0,
  "keep_done": 200
}

Los valores de config (semilla) solo se usan la primera vez para crear el
archivo. Después manda settings.json, editable desde la interfaz web.
"""
from __future__ import annotations

import json
import os
import threading

from . import config

_PATH = os.path.join(config.DATA_DIR, "settings.json")
_lock = threading.RLock()

_PRINTER_BOOL = {"cut_paper", "open_drawer"}
_PRINTER_INT = {"paper_width_chars"}
_GLOBAL_INT = {"retry_delay_seconds", "max_attempts", "keep_done"}

_data: dict = {}


# ----------------------------- coerción -----------------------------
def _coerce_printer(p: dict) -> dict:
    out = {
        "name": str(p.get("name", "")).strip(),
        "smb_host": str(p.get("smb_host", "")).strip(),
        "smb_share": str(p.get("smb_share", "")).strip(),
        "smb_user": str(p.get("smb_user", "")).strip(),
        "smb_pass": str(p.get("smb_pass", "")),
        "smb_domain": str(p.get("smb_domain", "WORKGROUP")).strip() or "WORKGROUP",
        "smb_ip": str(p.get("smb_ip", "")).strip(),
        "print_mode": (str(p.get("print_mode", "escpos")).strip().lower() or "escpos"),
        "codepage": str(p.get("codepage", "cp850")).strip() or "cp850",
    }
    try:
        out["paper_width_chars"] = int(p.get("paper_width_chars", 48))
    except (TypeError, ValueError):
        out["paper_width_chars"] = 48
    for b in _PRINTER_BOOL:
        v = p.get(b, False)
        out[b] = v if isinstance(v, bool) else str(v).strip().lower() in (
            "1", "true", "on", "yes", "si", "sí",
        )
    return out


def _coerce_client(c: dict) -> dict:
    return {
        "name": str(c.get("name", "")).strip(),
        "token": str(c.get("token", "")).strip(),
    }


# ----------------------------- carga / guardado -----------------------------
def _seed() -> dict:
    printers = []
    if config.SEED_PRINTER.get("smb_host"):
        printers.append(_coerce_printer(config.SEED_PRINTER))
    clients = []
    if config.SEED_CLIENT_TOKEN:
        clients.append({"name": config.SEED_CLIENT_NAME, "token": config.SEED_CLIENT_TOKEN})
    return {
        "printers": printers,
        "default_printer": printers[0]["name"] if printers else "",
        "clients": clients,
        **dict(config.GLOBAL_DEFAULTS),
    }


def load() -> None:
    global _data
    d = _seed()
    if os.path.exists(_PATH):
        try:
            with open(_PATH, encoding="utf-8") as f:
                stored = json.load(f)
            d["printers"] = [_coerce_printer(p) for p in stored.get("printers", []) if p.get("name")]
            d["clients"] = [_coerce_client(c) for c in stored.get("clients", []) if c.get("name")]
            d["default_printer"] = str(stored.get("default_printer", "")).strip()
            for k in _GLOBAL_INT:
                try:
                    d[k] = int(stored.get(k, config.GLOBAL_DEFAULTS[k]))
                except (TypeError, ValueError):
                    d[k] = config.GLOBAL_DEFAULTS[k]
        except (OSError, json.JSONDecodeError):
            pass
    # default_printer válido
    names = [p["name"] for p in d["printers"]]
    if d["default_printer"] not in names:
        d["default_printer"] = names[0] if names else ""
    _data = d
    _persist()


def _persist() -> None:
    os.makedirs(config.DATA_DIR, exist_ok=True)
    tmp = _PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _PATH)


# ----------------------------- impresoras -----------------------------
def list_printers() -> list[dict]:
    return [dict(p) for p in _data.get("printers", [])]


def get_printer(name: str | None) -> dict | None:
    """Devuelve la config de la impresora pedida, o la por defecto si name es vacío."""
    name = (name or "").strip()
    printers = _data.get("printers", [])
    if not name:
        name = _data.get("default_printer", "")
    for p in printers:
        if p["name"] == name:
            return dict(p)
    return None


def save_printer(p: dict) -> None:
    p = _coerce_printer(p)
    if not p["name"]:
        raise ValueError("la impresora necesita un nombre")
    with _lock:
        printers = _data.setdefault("printers", [])
        for i, existing in enumerate(printers):
            if existing["name"] == p["name"]:
                # secreto vacío => conservar el guardado
                if not p["smb_pass"]:
                    p["smb_pass"] = existing.get("smb_pass", "")
                printers[i] = p
                break
        else:
            printers.append(p)
        if not _data.get("default_printer"):
            _data["default_printer"] = p["name"]
        _persist()


def delete_printer(name: str) -> None:
    with _lock:
        _data["printers"] = [p for p in _data.get("printers", []) if p["name"] != name]
        names = [p["name"] for p in _data["printers"]]
        if _data.get("default_printer") not in names:
            _data["default_printer"] = names[0] if names else ""
        _persist()


def set_default_printer(name: str) -> None:
    with _lock:
        names = [p["name"] for p in _data.get("printers", [])]
        if name in names:
            _data["default_printer"] = name
            _persist()


def default_printer() -> str:
    return _data.get("default_printer", "")


# ----------------------------- clientes / tokens -----------------------------
def list_clients() -> list[dict]:
    return [dict(c) for c in _data.get("clients", [])]


def has_clients() -> bool:
    return any(c.get("token") for c in _data.get("clients", []))


def resolve_client(token: str | None) -> str | None:
    """Devuelve el nombre del cliente cuyo token coincide, o None."""
    token = (token or "").strip()
    if not token:
        return None
    for c in _data.get("clients", []):
        if c.get("token") and c["token"] == token:
            return c["name"]
    return None


def save_client(c: dict) -> None:
    c = _coerce_client(c)
    if not c["name"]:
        raise ValueError("el cliente necesita un nombre")
    with _lock:
        clients = _data.setdefault("clients", [])
        for i, existing in enumerate(clients):
            if existing["name"] == c["name"]:
                if not c["token"]:                       # token vacío => conservar
                    c["token"] = existing.get("token", "")
                clients[i] = c
                break
        else:
            clients.append(c)
        _persist()


def delete_client(name: str) -> None:
    with _lock:
        _data["clients"] = [c for c in _data.get("clients", []) if c["name"] != name]
        _persist()


# ----------------------------- globales -----------------------------
def get(key: str):
    return _data.get(key, config.GLOBAL_DEFAULTS.get(key))


def save_globals(updates: dict) -> None:
    with _lock:
        for k in _GLOBAL_INT:
            if k in updates:
                try:
                    _data[k] = int(updates[k])
                except (TypeError, ValueError):
                    pass
        _persist()


# ----------------------------- vistas -----------------------------
def public() -> dict:
    """Estado completo para la UI, ocultando secretos."""
    printers = []
    for p in _data.get("printers", []):
        q = dict(p)
        q["smb_pass"] = "***" if q.get("smb_pass") else ""
        printers.append(q)
    clients = []
    for c in _data.get("clients", []):
        clients.append({"name": c["name"], "token": "***" if c.get("token") else ""})
    return {
        "printers": printers,
        "default_printer": _data.get("default_printer", ""),
        "clients": clients,
        "retry_delay_seconds": _data.get("retry_delay_seconds"),
        "max_attempts": _data.get("max_attempts"),
        "keep_done": _data.get("keep_done"),
    }


load()
