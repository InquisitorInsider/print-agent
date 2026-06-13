# print-agent — Servicio de impresión genérico

Microservicio que imprime en impresoras térmicas (80 mm) los trabajos que le
mande **cualquier sistema** por HTTP. No sabe nada del negocio ni de qué sistema
lo llama: recibe un documento, lo encola y lo imprime con **reintentos** para
que **ningún ticket se pierda** aunque la impresora esté apagada, sin papel o el
PC dormido.

- API HTTP única: `POST /print`. La usan por igual tu **sistema nuevo**, el
  **WhatsApp bot** o cualquier otro programa. Ningún acoplamiento a un sistema.
- **Varias impresoras** con ruteo por nombre (`caja`, `cocina`, `barra`…).
- **Multi-cliente**: cada sistema usa su propio token y queda registrado en la
  cola quién mandó cada trabajo.
- Imprime a impresoras **compartidas desde Windows (SMB)** vía `smbclient`.
- Dos formas de describir lo que se imprime: **documento por bloques** (no
  necesitas saber ESC/POS) o **crudo** (texto / ESC/POS en base64).
- **Interfaz web** (`http://IP_DEL_HOST:8000`) para gestionar impresoras,
  clientes, reintentos, ticket de prueba y estado de la cola en vivo.

---

## 1. Cómo encaja

```
Sistema nuevo (POS) ─┐
WhatsApp bot ────────┼─HTTP POST /print─> print-agent ─SMB─> PC Windows ─> Impresora 80mm
Cualquier otro ──────┘                     (cola + reintentos)            (caja / cocina / …)
```

Cada sistema solo necesita saber la URL del agente y (opcional) su token. El
agente se encarga del formato físico, el ruteo a la impresora y los reintentos.

---

## 2. La API que usan los sistemas

### `POST /print`

Cabecera opcional de autenticación (si configuraste clientes):

```
Authorization: Bearer <token-del-cliente>
```

Cuerpo (JSON). Manda **`blocks`** (recomendado) **o** **`raw`**:

```json
{
  "printer": "caja",        // opcional; si se omite usa la impresora por defecto
  "copies": 1,              // opcional
  "blocks": [ ... ]         // documento por bloques  (o bien "raw": { ... })
}
```

Respuesta inmediata: `202 Accepted` con `{"accepted":true,"job_id":"...","printer":"caja","source":"sistema-pos"}`.
La impresión ocurre en segundo plano.

### Documento por bloques

El sistema describe el ticket; el agente lo convierte a ESC/POS. **No necesitas
conocer comandos de impresora.**

| Bloque    | Campos                                                                 |
|-----------|------------------------------------------------------------------------|
| `text`    | `text`, `align` (`left`/`center`/`right`), `bold`, `underline`, `size` (`normal`/`double`/`double_h`/`double_w`) |
| `row`     | `left`, `right` (justificados al ancho), `bold`                        |
| `line`    | `char` (por defecto `-`), ocupa todo el ancho                          |
| `feed`    | `lines` (número de saltos)                                             |
| `cut`     | `mode` (`partial`/`full`) — corte de papel                            |
| `drawer`  | abre el cajón de dinero                                                |
| `qr`      | `data`, `size` (1–16)                                                  |
| `barcode` | `data`, `symbology` (`CODE128`/`CODE39`/`EAN13`), `height`, `hri`      |

Ejemplo:

```json
{
  "printer": "caja",
  "blocks": [
    { "type": "text", "text": "RUTA80", "align": "center", "bold": true, "size": "double" },
    { "type": "line", "char": "=" },
    { "type": "row",  "left": "2 x 1/4 Pollo a la brasa", "right": "37.80", "bold": true },
    { "type": "text", "text": "   > con aji extra" },
    { "type": "row",  "left": "1 x Inca Kola 1L", "right": "7.00" },
    { "type": "line" },
    { "type": "row",  "left": "TOTAL S/", "right": "44.80", "bold": true },
    { "type": "qr",   "data": "https://ruta80.pe/p/1042", "size": 6 },
    { "type": "feed", "lines": 2 },
    { "type": "cut" }
  ]
}
```

### Modo crudo (`raw`)

Para sistemas que quieren control total del formato:

```json
{ "printer": "cocina", "raw": { "text": "PEDIDO #18\nMesa 4\n2 Pollo\n1 Gaseosa" } }
```

```json
{ "printer": "caja", "raw": { "escpos_base64": "G0AAUlVUQTgwCg==" } }
```

### Otros endpoints

| Método | Ruta         | Para qué                                       |
|--------|--------------|------------------------------------------------|
| GET    | `/printers`  | Lista de impresoras disponibles y la por defecto. |
| GET    | `/health`    | Estado del agente y de la cola.                |
| GET    | `/docs`      | Documentación interactiva (OpenAPI).           |

---

## 3. Ejemplos de integración

### Node (WhatsApp bot u otro)

```js
await fetch("http://IP_DEL_HOST:8000/print", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer EL_TOKEN_DEL_BOT"   // si configuraste clientes
  },
  body: JSON.stringify({
    printer: "caja",
    blocks: [
      { type: "text", text: "PEDIDO WHATSAPP", align: "center", bold: true, size: "double" },
      { type: "line", char: "=" },
      ...order.items.map(i => ({ type: "row", left: `${i.qty} x ${i.name}`, right: i.price.toFixed(2) })),
      { type: "line" },
      { type: "row", left: "TOTAL S/", right: order.total.toFixed(2), bold: true },
      { type: "feed", lines: 2 },
      { type: "cut" }
    ]
  })
});
```

### Python (sistema nuevo)

```python
import requests
requests.post("http://IP_DEL_HOST:8000/print",
  headers={"Authorization": "Bearer EL_TOKEN_DEL_POS"},
  json={"printer": "cocina",
        "blocks": [
          {"type": "text", "text": "COMANDA COCINA", "align": "center", "bold": True, "size": "double"},
          {"type": "line"},
          {"type": "text", "text": "Mesa 4"},
          {"type": "row", "left": "2 x 1/4 Pollo", "right": ""},
          {"type": "feed", "lines": 2}, {"type": "cut"}
        ]})
```

---

## 4. Configuración (interfaz web)

Abre **`http://IP_DEL_HOST:8000`**:

- **Impresoras:** añade cada impresora con su nombre (el que usarás en `printer`),
  IP del Windows, recurso compartido, usuario/clave, modo, ancho y codepage.
  Marca una como *por defecto*.
- **Clientes / tokens:** un cliente por sistema (POS, bot…). Genera su token y
  pégalo en ese sistema. Si no creas ninguno, el servicio queda **abierto en la
  red local**.
- **Reintentos y retención:** espera entre reintentos, máx. intentos (0 =
  infinito), cuántos impresos conservar.

Todo se guarda en `/data/settings.json` (volumen persistente) y se aplica al
instante. El `.env` solo siembra la primera ejecución.

### Driver de la impresora en Windows
- **Cola "Generic / Text Only" (RAW)** → modo `escpos`. La buena: negritas,
  QR, código de barras y **corte de papel**. Recomendado.
- **Cola con driver del fabricante** → modo `text` (texto plano, sin corte).

---

## 5. Desplegar (Docker)

> **Opción recomendada (más fácil):** publica el proyecto en GitHub y deja que
> construya la imagen sola; en OMV solo pegas `docker-compose.deploy.yml` (con
> tu usuario) + `.env` y pulsas Up. Guía completa en **`GUIA-GITHUB.md`**.
> Despliegue manual en OMV (build desde carpeta) en **`DESPLIEGUE-OMV.md`**.

Despliegue compilando desde la carpeta:

1. Copia esta carpeta completa (`Dockerfile`, `docker-compose.yml`,
   `requirements.txt`, carpeta `app/`) al host donde correrá (OMV, Raspberry Pi,
   un PC…).
2. Copia `.env.example` a `.env` (puedes dejarlo casi vacío y configurar por la web).
3. Levanta: `docker compose up -d --build`
   - En OpenMediaVault: plugin **Compose → Files → Add (+)**, pega los archivos
     en la carpeta de la stack y pulsa **Up**.
4. Comprueba: `http://IP_DEL_HOST:8000/health`

Si quieres que otro contenedor (p. ej. el bot) llame al agente por nombre
`http://print-agent:8000`, ambos deben compartir la red `pos-net`; marca esa red
como `external` en los dos `docker-compose.yml`. Si no, se llaman por la IP del host.

---

## 6. Probar

```bash
# Ticket de prueba (desde la web hay un botón, o por API de admin)
curl -X POST http://IP_DEL_HOST:8000/api/test -H "Content-Type: application/json" -d '{"printer":"caja"}'

# Enviar un documento de ejemplo
curl -X POST http://IP_DEL_HOST:8000/print \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer EL_TOKEN" \
  -d @test/sample_blocks.json

# Estado
curl http://IP_DEL_HOST:8000/health
```

---

## 7. Solución de problemas

- **No imprime, `/health` muestra `last_error` con smbclient**: revisa host,
  recurso y usuario/clave de esa impresora. Prueba desde el host:
  `smbclient -L //HOST -U usuario`.
- **El trabajo queda en `pending`**: la impresora o el Windows no responden; el
  agente reintenta cada `retry_delay_seconds`. En cuanto vuelvan, imprime.
- **`401 Token inválido`**: el sistema no mandó (o mandó mal) el `Authorization:
  Bearer <token>`. Revisa el token del cliente en la web.
- **Acentos con símbolos raros (modo escpos)**: ajusta el `codepage` de esa
  impresora (normalmente `cp850`). El agente ya manda el comando de tabla al
  hardware.
- **No corta el papel**: solo en modo `escpos`, con bloque `cut`, y si el modelo
  soporta corte por ESC/POS.
