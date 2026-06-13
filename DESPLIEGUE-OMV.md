# Desplegar print-agent en OpenMediaVault (Compose)

Manual corto para dejar el agente corriendo en tu OMV usando el plugin
**Compose** (omv-extras). No necesitas SSH.

---

## 0. Requisitos (una sola vez)

- **omv-extras** instalado.
- En **System → Plugins**: instala `openmediavault-compose`.
- En **Services → Compose → Settings**: define la carpeta de datos de Compose
  (apunta a un disco de datos, p. ej. `/srv/dev-disk-by-uuid-XXXX/appdata`).
  Pulsa **Save**. Esa será la base donde vivirá la stack.

---

## 1. Subir los archivos del agente

El compose se **compila desde la carpeta** (usa `build: .`), así que el OMV
necesita tener todos los archivos juntos: `docker-compose.yml`, `Dockerfile`,
`requirements.txt` y la carpeta `app/`.

La forma más cómoda sin SSH es por **SMB**:

1. **Services → SMB/CIFS → Shares**: comparte la carpeta `appdata` de Compose
   (o crea un Shared Folder que apunte ahí) y dale acceso a tu usuario.
2. Desde tu PC (Linux Mint o Windows), abre esa carpeta compartida por red.
3. Copia **toda la carpeta `print-agent/`** (con `app/`, `Dockerfile`, etc.)
   dentro de `appdata/compose/` o donde guardes las stacks.

> Alternativa: usa el plugin **File Manager** de OMV para subir los archivos.

Al terminar debes tener algo así en el OMV:

```
.../appdata/compose/print-agent/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env                ← lo creas en el paso 2
└── app/
    ├── main.py  config.py  settings.py  printer.py  queue.py  ui.py
```

---

## 2. Crear el `.env`

En esa misma carpeta `print-agent/`, copia `.env.example` a `.env`.
Puedes dejarlo casi vacío y configurar todo después por la web. Lo mínimo útil:

```ini
ADMIN_USER=admin
ADMIN_PASSWORD=pon-una-clave        # protege la interfaz web

# Impresora semilla (opcional; también la puedes añadir luego por la web)
PRINTER_NAME=caja
SMB_HOST=192.168.1.50               # IP del PC Windows que comparte la impresora
SMB_SHARE=TICKETERA                 # nombre exacto del recurso compartido
SMB_USER=                           # vacío si la comparte es abierta
SMB_PASS=
PRINT_MODE=escpos
PAPER_WIDTH_CHARS=48
CODEPAGE=cp850
CUT_PAPER=true

# Token semilla para un sistema (opcional)
CLIENT_NAME=sistema-pos
PRINT_TOKEN=                        # pega aquí un token, o créalo luego por la web
```

---

## 3. Registrar la stack en Compose

1. **Services → Compose → Files** y pulsa **Add (+)**.
2. **Name:** `print-agent`.
3. En el cuerpo, pega el contenido de tu `docker-compose.yml`
   (el que está en la carpeta). **Save**.
4. OMV te muestra la ruta de la stack. **Importante:** debe ser la **misma
   carpeta** donde subiste `Dockerfile` y `app/` en el paso 1. Si Compose creó
   una carpeta distinta, mueve ahí tus archivos (o ajusta la ruta) para que el
   `build: .` encuentre el `Dockerfile`.

---

## 4. Levantar

1. En **Services → Compose → Files**, selecciona `print-agent`.
2. Pulsa **Up** (▲). La primera vez **compila la imagen** (tarda 1–3 min).
3. Verás el contenedor activo en **Services → Compose**.

Comprueba que responde, desde un navegador en la misma red:

```
http://IP_DEL_OMV:8000/health
```

Debe devolver algo como `{"status":"ok","pending":0,"failed":0,...}`.

---

## 5. Configurar y probar

1. Abre **`http://IP_DEL_OMV:8000`** (pide usuario/clave si pusiste
   `ADMIN_PASSWORD`).
2. **Impresoras:** revisa o añade tus impresoras (caja, cocina…). Marca una
   por defecto. Botón **Imprimir prueba** → debe salir un ticket.
3. **Clientes / tokens:** crea un cliente por cada sistema (POS, bot) y genera
   su token. Cópialo: ese token va en el header `Authorization: Bearer <token>`
   de cada sistema.

---

## 6. Que otros sistemas le impriman

Cualquier sistema en tu red manda un `POST` al agente:

```
POST http://IP_DEL_OMV:8000/print
Authorization: Bearer <token-del-sistema>
Content-Type: application/json
```

con un documento por bloques o `raw` (ver `README.md`, secciones 2 y 3).

> Si el sistema corre en **otro contenedor del mismo OMV** y quieres llamarlo
> por nombre `http://print-agent:8000`, marca la red `pos-net` como `external`
> en ambos `docker-compose.yml`. Si no, usa siempre la **IP del OMV**.

---

## 7. Operación diaria

- **Ver estado / cola:** la web (`:8000`) muestra pendientes, fallidos, última
  impresión y los últimos tickets, en vivo.
- **Reintentar / vaciar fallidos:** botones en la web.
- **Actualizar el agente:** sube los archivos nuevos a la carpeta y, en
  **Services → Compose**, pulsa **Down** y luego **Up** (▲) — recompila.
- **Reiniciar:** **Down** / **Up** desde Compose. La cola y la config
  (`/data`) sobreviven gracias al volumen `print-agent-data`.

---

## Problemas frecuentes

- **`build` falla buscando el Dockerfile** → el `docker-compose.yml` y la
  carpeta `app/`/`Dockerfile` no están en la misma carpeta. Júntalos (paso 1/3).
- **No imprime, `/health` con error de smbclient** → revisa IP, recurso y
  usuario/clave de la impresora en la web.
- **No abre `:8000`** → confirma que el contenedor está **Up** y que el puerto
  8000 no está ocupado por otro servicio del OMV.
