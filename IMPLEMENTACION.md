# print-agent — Guía de implementación e integración

Microservicio de impresión genérico. Cualquier sistema (POS, bot, ERP) le manda trabajos por HTTP y él los encola, reintenta y envía a la impresora. El sistema cliente **no necesita saber nada de ESC/POS ni del protocolo de la impresora**.

---

## 1. Despliegue

### Opción A — Imagen publicada en GHCR (recomendada para OMV)

```yaml
# docker-compose.deploy.yml
services:
  print-agent:
    image: ghcr.io/inquisitorinsider/print-agent:latest
    container_name: print-agent
    restart: unless-stopped
    pull_policy: always
    env_file: .env
    ports:
      - "8000:8000"
    volumes:
      - print-agent-data:/data
    networks:
      - pos-net

networks:
  pos-net:
    name: pos-net

volumes:
  print-agent-data:
    name: print-agent-data
```

```bash
docker compose -f docker-compose.deploy.yml up -d
```

### Opción B — Build desde fuentes

```bash
docker compose up -d --build
```

### Variables de entorno (`.env`)

Solo son la **semilla para la primera ejecución**. Una vez guardado desde la interfaz web (`/data/settings.json`), las variables de entorno se ignoran.

| Variable | Defecto | Descripción |
|---|---|---|
| `ADMIN_USER` | `admin` | Usuario para la interfaz web |
| `ADMIN_PASSWORD` | *(vacío)* | Si se define, la web pide autenticación |
| `PRINTER_NAME` | `principal` | Nombre de la impresora semilla |
| `SMB_HOST` | *(vacío)* | IP del PC Windows que comparte la impresora |
| `SMB_SHARE` | *(vacío)* | Nombre exacto del recurso compartido |
| `SMB_USER` / `SMB_PASS` | *(vacío)* | Credenciales Windows (vacío = comparte abierta) |
| `SMB_DOMAIN` | `WORKGROUP` | Dominio Windows |
| `SMB_IP` | *(vacío)* | IP explícita si el nombre no resuelve |
| `CONN_TYPE` | `smb` | Tipo de conexión: `smb`, `raw`, `lpr` |
| `RAW_HOST` | *(vacío)* | IP para conexión RAW (puerto 9100) |
| `RAW_PORT` | `9100` | Puerto RAW |
| `LPR_HOST` | *(vacío)* | IP para cola LPR |
| `LPR_PORT` | `515` | Puerto LPR |
| `LPR_QUEUE` | *(vacío)* | Nombre de la cola LPR |
| `PRINT_MODE` | `escpos` | `escpos` (recomendado) o `text` |
| `PAPER_WIDTH_CHARS` | `48` | Ancho del papel en caracteres (80 mm = 48) |
| `CODEPAGE` | `cp850` | Codepage para acentos (`cp850` para español) |
| `CUT_PAPER` | `true` | Corte automático al imprimir |
| `OPEN_DRAWER` | `false` | Abrir cajón al imprimir |
| `CLIENT_NAME` | `sistema` | Nombre del cliente/token semilla |
| `PRINT_TOKEN` | *(vacío)* | Token semilla (si vacío, servicio abierto en LAN) |
| `RETRY_DELAY_SECONDS` | `15` | Segundos entre reintentos |
| `MAX_ATTEMPTS` | `0` | Máx. intentos (0 = reintentar para siempre) |
| `KEEP_DONE` | `200` | Trabajos impresos a conservar en historial |

---

## 2. Interfaz web de administración

`http://IP_DEL_HOST:8000`

Desde aquí se gestiona todo sin tocar archivos:

- **Impresoras** — añadir, editar, eliminar, cambiar la por defecto, ticket de prueba por impresora.
- **Clientes / tokens** — un cliente por sistema. Si no hay ninguno, el servicio queda abierto en la red local.
- **Reintentos y retención** — ajustar sin reiniciar el contenedor.
- **Estado de la cola** — ver trabajos pendientes, fallidos e historial de los últimos 15 impresos.
- **Reencolar fallidos / limpiar fallidos** — operación con un botón.

Todo se persiste en `/data/settings.json` y se aplica al instante.

---

## 3. API para los sistemas que imprimen

### Autenticación

Si hay clientes configurados, todos los envíos requieren cabecera:

```
Authorization: Bearer <token-del-cliente>
```

Si no hay clientes configurados, el endpoint está abierto en la red local (sin cabecera).

---

### `POST /print` — Encolar un trabajo

Responde `202 Accepted` inmediatamente. La impresión ocurre en segundo plano con reintentos.

```http
POST /print
Content-Type: application/json
Authorization: Bearer TU_TOKEN
```

**Campos del cuerpo:**

| Campo | Tipo | Descripción |
|---|---|---|
| `printer` | string | Nombre de la impresora (omitir = usa la por defecto) |
| `copies` | int | Número de copias (defecto: 1) |
| `blocks` | array | Documento por bloques *(ver sección 4)* |
| `raw` | object | Contenido crudo *(ver sección 5)* |
| `source` | string | Opcional. Identificador del origen (normalmente lo da el token) |

Solo se usa `blocks` **o** `raw`, nunca los dos.

**Respuesta:**

```json
{
  "accepted": true,
  "job_id": "20240615-143022-a3f8c1",
  "printer": "caja",
  "source": "sistema-pos"
}
```

---

### `GET /printers` — Listar impresoras disponibles

Sin autenticación.

```json
{
  "default": "caja",
  "printers": ["caja", "cocina", "barra"]
}
```

---

### `GET /health` — Estado del servicio

Sin autenticación.

```json
{
  "status": "ok",
  "pending": 0,
  "failed": 0,
  "last_ok": "2024-06-15T14:30:22",
  "last_error": null,
  "printers": ["caja", "cocina"]
}
```

---

## 4. Documento por bloques (recomendado)

El sistema describe el contenido del ticket; el agente lo convierte a ESC/POS. **No necesitas conocer comandos de impresora.**

### Tipos de bloque

#### `text` — Texto libre

```json
{
  "type": "text",
  "text": "RUTA80",
  "align": "center",
  "bold": true,
  "underline": false,
  "size": "double"
}
```

| Campo | Valores | Defecto |
|---|---|---|
| `text` | string | `""` |
| `align` | `left` / `center` / `right` | `left` |
| `bold` | boolean | `false` |
| `underline` | boolean | `false` |
| `size` | `normal` / `double` / `double_h` / `double_w` | `normal` |

El texto se envuelve automáticamente al ancho del papel.

---

#### `row` — Dos columnas justificadas (ítem + precio)

```json
{
  "type": "row",
  "left": "2 x 1/4 Pollo a la brasa",
  "right": "37.80",
  "bold": true
}
```

Si el texto de la izquierda no cabe, se envuelve y el valor de la derecha queda en la última línea alineado a la derecha.

---

#### `line` — Línea divisoria a todo el ancho

```json
{ "type": "line", "char": "=" }
```

`char` es el carácter a repetir (defecto: `-`).

---

#### `feed` — Saltos de línea

```json
{ "type": "feed", "lines": 2 }
```

---

#### `cut` — Corte de papel

```json
{ "type": "cut", "mode": "partial" }
```

`mode`: `partial` (defecto) o `full`. Solo funciona en modo `escpos` con impresoras que soportan corte por ESC/POS.

---

#### `drawer` — Pulso para abrir cajón de dinero

```json
{ "type": "drawer" }
```

---

#### `qr` — Código QR

```json
{ "type": "qr", "data": "https://ruta80.pe/p/1042", "size": 6 }
```

`size`: 1–16 (defecto: 6). Solo en modo `escpos`.

---

#### `barcode` — Código de barras

```json
{
  "type": "barcode",
  "data": "123456789012",
  "symbology": "CODE128",
  "height": 80,
  "hri": true
}
```

| Campo | Valores | Defecto |
|---|---|---|
| `symbology` | `CODE128` / `CODE39` / `EAN13` | `CODE128` |
| `height` | 1–255 | `80` |
| `hri` | boolean (mostrar texto debajo) | `true` |

Solo en modo `escpos`.

---

### Ejemplo completo de ticket

```json
{
  "printer": "caja",
  "copies": 1,
  "blocks": [
    { "type": "text",    "text": "RUTA80",              "align": "center", "bold": true, "size": "double" },
    { "type": "text",    "text": "Av. Ejemplo 123",     "align": "center" },
    { "type": "line",    "char": "=" },
    { "type": "text",    "text": "Pedido #1042",        "bold": true },
    { "type": "text",    "text": "Mesa 4" },
    { "type": "line" },
    { "type": "row",     "left": "2 x 1/4 Pollo brasa", "right": "37.80", "bold": true },
    { "type": "text",    "text": "   > con aji extra" },
    { "type": "row",     "left": "1 x Inca Kola 1L",    "right": "7.00" },
    { "type": "line" },
    { "type": "row",     "left": "TOTAL S/",             "right": "44.80", "bold": true },
    { "type": "qr",      "data": "https://ruta80.pe/p/1042", "size": 6 },
    { "type": "feed",    "lines": 2 },
    { "type": "cut" }
  ]
}
```

---

## 5. Modo crudo (`raw`)

Para sistemas que ya generan el contenido formateado.

### Texto plano

```json
{
  "printer": "cocina",
  "raw": {
    "text": "COMANDA COCINA\nMesa 4\n2 x Pollo\n1 x Gaseosa",
    "cut": true
  }
}
```

`cut`: si se incluye corte al final (defecto: `true`). Solo tiene efecto en modo `escpos`.

### ESC/POS en base64

Para sistemas que ya generan bytes ESC/POS y solo necesitan el transporte:

```json
{
  "printer": "caja",
  "raw": { "escpos_base64": "G0AAUlVUQTgwCg==" }
}
```

---

## 6. Tipos de conexión de impresoras

### RAW TCP (puerto 9100) — recomendado para print servers de red

Para print servers (D-Link, TP-Link, etc.) e impresoras con interfaz LAN/Wi-Fi. En D-Link: USB1=9100, USB2=9101, USB3=9102.

Configurar en la web:
- **Tipo de conexión:** RAW
- **Host/IP:** IP del print server
- **Puerto:** 9100 (o el que corresponda)

### LPR / LPD (puerto 515)

El mismo protocolo con el que agregas la impresora en Windows. Requiere el **nombre de cola** exacto (el mismo que usas al agregar la impresora en Windows).

### SMB — impresora compartida desde Windows

Requiere `smbclient` instalado en el host (ya incluido en la imagen Docker). Usa el nombre de recurso compartido exacto del PC Windows.

### Modos de impresión

| Modo | Descripción | Cuándo usar |
|---|---|---|
| `escpos` | Bytes ESC/POS directos | Cola "Generic / Text Only" en Windows. Habilita negritas, QR, barcode, corte de papel. **Recomendado.** |
| `text` | Texto plano codificado | Cola con driver del fabricante en Windows. Sin corte ni gráficos. |

---

## 7. Ejemplos de integración

### JavaScript / Node.js

```js
async function imprimir(printer, bloques, token) {
  const res = await fetch("http://IP_DEL_HOST:8000/print", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`,
    },
    body: JSON.stringify({ printer, blocks: bloques }),
  });
  if (!res.ok) throw new Error(`print-agent: ${res.status}`);
  return res.json(); // { accepted, job_id, printer, source }
}
```

### Python

```python
import requests

def imprimir(printer: str, bloques: list, token: str, host: str = "http://IP_DEL_HOST:8000"):
    resp = requests.post(
        f"{host}/print",
        headers={"Authorization": f"Bearer {token}"},
        json={"printer": printer, "blocks": bloques},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()
```

### PHP

```php
function imprimir(string $printer, array $bloques, string $token, string $host = 'http://IP_DEL_HOST:8000'): array {
    $ch = curl_init("$host/print");
    curl_setopt_array($ch, [
        CURLOPT_POST => true,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER => [
            'Content-Type: application/json',
            "Authorization: Bearer $token",
        ],
        CURLOPT_POSTFIELDS => json_encode(['printer' => $printer, 'blocks' => $bloques]),
        CURLOPT_TIMEOUT => 10,
    ]);
    $body = curl_exec($ch);
    $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    if ($code !== 202) throw new RuntimeException("print-agent: $code");
    return json_decode($body, true);
}
```

### cURL (pruebas)

```bash
# Ticket de prueba (requiere autenticación de admin)
curl -u admin:TU_PASSWORD -X POST http://IP_DEL_HOST:8000/api/test \
  -H "Content-Type: application/json" -d '{"printer":"caja"}'

# Trabajo real
curl -X POST http://IP_DEL_HOST:8000/print \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TU_TOKEN" \
  -d @test/sample_blocks.json

# Estado
curl http://IP_DEL_HOST:8000/health
```

---

## 8. Comportamiento de la cola

- Cada trabajo se guarda en disco antes de responder `202`. **Ningún trabajo se pierde** aunque el contenedor se reinicie o la impresora esté apagada.
- El agente reintenta cada `retry_delay_seconds` segundos hasta que la impresora responda.
- Si `max_attempts` > 0 y se agotan los intentos, el trabajo pasa a `failed`. Desde la interfaz web se puede reencolar o limpiar.
- `copies` > 1 envía el mismo trabajo N veces seguidas a la impresora en el mismo ciclo.

---

## 9. Red entre contenedores

Si el sistema cliente también corre en Docker y quiere llamar al agente por nombre (`http://print-agent:8000`) en lugar de por IP, ambos contenedores deben compartir la misma red Docker:

```yaml
# En el docker-compose del sistema cliente:
networks:
  pos-net:
    external: true   # la misma red que levantó print-agent
```

Si no, llamar por la IP del host es suficiente.
