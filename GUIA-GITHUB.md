# Subir print-agent a GitHub y desplegarlo en OMV (paso a paso)

Objetivo: dejar el proyecto en GitHub para que **GitHub construya la imagen
solo** y la publique. Luego, en tu OMV, desplegar es solo pegar un compose corto
y pulsar **Up** — sin copiar archivos ni compilar en el servidor.

Hazlo una vez en este orden:

1. Crear la cuenta de GitHub.
2. Crear el repositorio (público) y subir el proyecto.
3. Esperar a que la imagen se construya y dejarla pública.
4. Desplegar en OMV con la imagen.

---

## Parte 1 · Crear la cuenta de GitHub

1. Entra a **https://github.com/signup**.
2. **Email:** escribe tu correo (puedes usar `alexmc78@gmail.com`) → **Continue**.
3. **Password:** crea una contraseña fuerte → **Continue**.
4. **Username:** elige un nombre de usuario. Apúntalo: lo usaremos en el compose.
   - Solo letras, números y guiones. Ej.: `ruta80`, `alexmc78`.
   - Si dice que está ocupado, prueba otra variante.
5. Resuelve el captcha de verificación → **Create account**.
6. GitHub te envía un **código al correo**. Ábrelo y escríbelo para verificar.
7. Cuando pregunte por el plan, elige **Free** (gratis). El resto de preguntas
   (para qué lo usarás, etc.) puedes saltarlas.

> Apunta tu **usuario** y tu **contraseña**. El usuario, en minúsculas, es lo que
> reemplazarás como `TU-USUARIO` más adelante.

---

## Parte 2 · Crear el repositorio y subir el proyecto

### 2.1 Crear el repositorio

1. Arriba a la derecha pulsa el **+** → **New repository**.
2. **Repository name:** `print-agent`.
3. **Description** (opcional): `Servicio de impresión genérico`.
4. Marca **Public**.
5. **No** marques "Add a README" (el proyecto ya trae uno).
6. Pulsa **Create repository**.

### 2.2 Subir los archivos (sin instalar nada)

La página nueva del repo muestra un enlace **"uploading an existing file"**
(o ve a **Add file → Upload files**).

1. Abre la carpeta `print-agent/` de tu PC.
2. **Selecciona todo el contenido** y arrástralo a la zona de subida del
   navegador. GitHub respeta las subcarpetas (`app/`, `test/`).
   - **Importante:** sube también el archivo **`.env.example`**, pero **NUNCA**
     subas un archivo `.env` con claves reales. (El `.gitignore` ya lo evita,
     pero al subir por web tú eliges los archivos, así que ojo.)
3. Abajo, en **Commit changes**, deja el mensaje por defecto y pulsa
   **Commit changes**.

> ¿La carpeta oculta `.github` no se subió al arrastrar? Créala a mano:
> **Add file → Create new file**, y en el nombre escribe exactamente:
> `.github/workflows/docker-publish.yml`
> Pega dentro el contenido del archivo del proyecto y pulsa **Commit changes**.
> Esa carpeta es la que hace que la imagen se construya sola, así que verifica
> que esté presente.

---

## Parte 3 · Construir la imagen y dejarla pública

### 3.1 Ver la construcción

1. En el repo, abre la pestaña **Actions**.
2. Verás un proceso llamado **"Construir y publicar imagen Docker"** corriendo
   (círculo amarillo). Espera 2–4 min hasta que quede en **verde** ✓.
   - Si está en rojo, ábrelo para ver el error y me lo dices.

### 3.2 Hacer pública la imagen (una sola vez)

Por defecto la imagen recién publicada queda **privada**. Para que OMV la baje
sin login, hazla pública:

1. Entra a tu perfil: **https://github.com/TU-USUARIO** → pestaña **Packages**.
2. Abre el paquete **print-agent**.
3. **Package settings** (engranaje / "Settings", a la derecha).
4. Baja hasta **Danger Zone → Change visibility** → **Public** → confirma
   escribiendo el nombre.

Tu imagen ya está disponible en:
`ghcr.io/TU-USUARIO/print-agent:latest`

---

## Parte 4 · Desplegar en OMV (con la imagen)

Ahora desplegar es muy corto. **No** necesitas subir `app/` ni `Dockerfile` al
servidor: solo el compose y el `.env`.

1. En tu PC abre el archivo **`docker-compose.deploy.yml`** del proyecto y
   cambia `TU-USUARIO` por tu usuario de GitHub **en minúsculas**. Copia ese
   texto.
2. En OMV: **Services → Compose → Files → Add (+)**.
   - **Name:** `print-agent`.
   - Pega el contenido del `docker-compose.deploy.yml` (ya editado). **Save**.
3. Crea el `.env` en la carpeta de esa stack (igual que en
   `DESPLIEGUE-OMV.md`, Parte 2). Aquí pones tus claves reales (impresora,
   `ADMIN_PASSWORD`, tokens). El `.env` vive solo en tu servidor, nunca en GitHub.
4. Selecciona `print-agent` y pulsa **Up** (▲). OMV **descarga** la imagen de
   GHCR y la levanta (sin compilar).
5. Comprueba: `http://IP_DEL_OMV:8000/health` y configura por la web
   `http://IP_DEL_OMV:8000`.

---

## Cómo actualizar el agente en el futuro

El flujo queda automático:

1. Cambias el código y subes los archivos al repo (igual que en la Parte 2.2, o
   editando el archivo en GitHub y **Commit changes**).
2. GitHub reconstruye la imagen solo (pestaña **Actions** → verde).
3. En OMV: **Services → Compose** → selecciona `print-agent` → **Pull** (baja la
   nueva imagen) y luego **Up**. Listo, sin tocar el servidor a mano.

Tu cola y tu configuración (`/data`) se conservan en cada actualización.

---

## Notas de seguridad

- El repo es público: **cualquiera puede ver el código** (está bien, no hay
  secretos en él). Lo que **nunca** se sube es el `.env` con tus claves.
- Si algún día subes por error un archivo con claves, cámbialas: en GitHub el
  historial queda guardado.
- La protección de la web (`ADMIN_PASSWORD`) y los tokens de cliente viven solo
  en el `.env` de tu servidor.
