# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Instalar dependencias (desarrollo local)
pip install -r requirements.txt

# Levantar en desarrollo (sin Docker)
DATA_DIR=./data uvicorn app.main:app --reload --port 8000

# Construir y levantar con Docker
docker compose up -d --build

# Despliegue en OMV (imagen pre-publicada en GHCR)
docker compose -f docker-compose.deploy.yml up -d

# Ver logs del contenedor
docker logs -f print-agent

# Enviar ticket de prueba
curl -X POST http://localhost:8000/api/test -H "Content-Type: application/json" -d '{"printer":"caja"}'

# Verificar estado de la cola
curl http://localhost:8000/health

# Enviar trabajo usando archivo de ejemplo
curl -X POST http://localhost:8000/print \
  -H "Content-Type: application/json" \
  -d @test/sample_blocks.json
```

No hay suite de tests automatizados. Los archivos `test/sample_blocks.json` y `test/sample_raw.json` son payloads de ejemplo para `curl`.

## Arquitectura

### Flujo principal

```
POST /print  →  main.py (_resolve_source)  →  queue.enqueue()  →  /data/pending/<job>.json
                                                                            ↓
                                                              queue._worker_loop() (hilo daemon)
                                                                            ↓
                                                              settings.get_printer(name)
                                                                            ↓
                                                              printer.print_job(content, cfg)
                                                                            ↓
                                                              /data/done/<job>.json (o failed/)
```

### Módulos (`app/`)

- **`main.py`** — FastAPI app. Define todos los endpoints. Auth de administración via HTTP Basic (`require_admin`). Auth de clientes via Bearer token (`_resolve_source`). Arranca la cola en `startup`.
- **`queue.py`** — Cola persistente en disco (`/data/pending/`, `/data/done/`, `/data/failed/`). Hilo daemon que procesa cada `POLL_INTERVAL_SECONDS`. Reintentos con backoff configurable. Escrituras atómicas (`os.replace`).
- **`printer.py`** — Renderiza el contenido (bloques → ESC/POS o texto plano) y envía a la impresora. Tres métodos de conexión: SMB (`smbclient`), RAW TCP (socket puerto 9100), LPR/LPD (RFC 1179, puerto 515).
- **`settings.py`** — Estado en caliente en `_data` (dict en memoria). Persiste en `/data/settings.json`. Se carga al importar el módulo (`load()` al final del archivo). Las variables de entorno son solo la **semilla** para la primera ejecución; después manda `settings.json`.
- **`config.py`** — Solo lee variables de entorno con `os.environ`. No tiene estado mutable.
- **`ui.py`** — HTML autocontenido (string `PAGE`) servido en `GET /`. Sin dependencias externas de frontend; toda la lógica de la UI está en JS embebido en esa misma cadena.

### Dos capas de autenticación

1. **Admin** (interfaz web y endpoints `/api/*`): HTTP Basic con `ADMIN_USER` / `ADMIN_PASSWORD`. Si `ADMIN_PASSWORD` está vacía, no hay protección.
2. **Clientes de impresión** (`POST /print`): Bearer token. Si no hay clientes configurados en `settings.json`, el endpoint queda abierto en la red local.

### Tipos de contenido que acepta `POST /print`

- **`blocks`**: lista de bloques tipados (`text`, `row`, `line`, `feed`, `cut`, `drawer`, `qr`, `barcode`). El agente convierte a ESC/POS o texto plano según `print_mode` de la impresora.
- **`raw`**: `{"text": "..."}` o `{"escpos_base64": "..."}` — el cliente ya formatea el contenido.

### Conexión a impresoras (campo `conn_type`)

| Valor | Protocolo | Cuándo usar |
|-------|-----------|-------------|
| `smb` | Samba / `smbclient` | Impresora compartida desde PC Windows |
| `raw` | TCP socket 9100 | Print server de red (D-Link), impresora con LAN |
| `lpr` | LPR/LPD RFC 1179 puerto 515 | Cola LPR igual que en Windows |

### Persistencia en `/data/`

- `settings.json` — configuración de impresoras, clientes y globales.
- `pending/<job_id>.json` — trabajos pendientes o con reintentos.
- `done/<job_id>.json` — impresos (purga automática al superar `keep_done`).
- `failed/<job_id>.json` — fallidos al agotar `max_attempts` (0 = infinito).

### Docker

La imagen se publica automáticamente en `ghcr.io/inquisitorinsider/print-agent` vía `.github/workflows/docker-publish.yml` al hacer push a `main`. El volumen `print-agent-data` persiste la cola y la configuración entre reinicios.
