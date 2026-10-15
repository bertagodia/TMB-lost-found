# API local de WP4 + PostgreSQL + extracción

Sirve ambos formularios WP4 y persiste inventario, declaraciones, contactos,
fotografías y extracciones en PostgreSQL. Requiere Python 3.11+ y PostgreSQL 17.
Desde la raíz, con Docker Compose instalado:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.txt
export POSTGRES_PASSWORD='choose-a-local-password'
docker compose -f database/compose.yaml up -d --wait
export DATABASE_URL='postgresql://tmb:choose-a-local-password@127.0.0.1:55432/tmb'
python -m database.migrate
# Opcional: datos ficticios (sin imágenes reales).
# python -m database.seed --demo
# Solo para extracción automática; el registro manual funciona sin Ollama.
ollama pull qwen3-vl:2b-instruct
python -m backend.server --port 8001
```

Abre http://127.0.0.1:8001. `--model` selecciona otro modelo y `--data-dir`
cambia la carpeta de fotos, por defecto `artifacts/wp4/`. Conserva tanto esa
carpeta como el volumen PostgreSQL al reiniciar. La API escucha solo en loopback.

`DATABASE_URL` es obligatoria. Las migraciones se ejecutan explícitamente; la API
no crea ni reinicia bases al arrancar y no carga `.env` automáticamente. Puedes
usar un PostgreSQL local existente con una **base nueva vacía**. Mantén la misma
contraseña en Compose y la URL; codifica los caracteres especiales de la URL.
En PowerShell usa `$env:POSTGRES_PASSWORD='...'` y `$env:DATABASE_URL='...'`.

Abre `/docs` para el contrato OpenAPI interactivo. El arranque imprime un
`X-Local-Token`; cópialo en **Authorize**. WP4 lo recibe automáticamente. Tras
reiniciar, recarga la página para obtener el token nuevo.

## Rutas y ejemplos

Las operaciones de datos requieren `X-Local-Token`, Host local y mismo origen.
`/api/health`, `/docs` y la interfaz son accesibles sin token. `/api/health`
comprueba PostgreSQL y los checksums de las migraciones; devuelve 503 si no está
preparado. No comprueba que Ollama esté instalado.

| Método y ruta | Operación |
|---|---|
| `POST /api/objects` | Alta revisada con 1–2 fotos. |
| `POST /lost-found` | Alta compatible con WP4; responde 200 y `received-local`. |
| `GET /api/objects` y `GET /api/objects/{id}` | Listado y detalle con fotos y revisiones. |
| `POST /api/objects/{id}/reviews` | Nueva revisión, sin sobrescribir historial. |
| `PATCH /api/objects/{id}/status` | `registered`, `returned` o `archived`. |
| `POST /api/lost-reports` | Declaración con foto y contacto opcionales. |
| `GET /api/lost-reports` y `GET /api/lost-reports/{id}` | Listado y detalle sin contactos. |
| `GET /api/lost-reports/{id}/contact` | Contacto separado, o 404 si no existe. |
| `PATCH /api/lost-reports/{id}/status` | `open`, `closed` o `cancelled`. |
| `POST /api/extract` | Extraer foto principal y conservar el intento. |
| `GET /api/extractions/{id}` | Estado, campos propuestos y procedencia. |
| `GET /api/photos/{id}/content` | Descargar la imagen original por ID. |

Los listados devuelven `items`, `total`, `limit` (50 por defecto, máximo 100) y
`offset` (0 por defecto); admiten filtro `status`. Los resúmenes del listado no
cargan fotos ni revisiones: consulta el detalle. Las respuestas excluyen rutas
internas, hashes de envío y salidas brutas del modelo.

```bash
export LOCAL_API_TOKEN='copy-the-token-printed-at-startup'
curl http://127.0.0.1:8001/api/health
curl -H "X-Local-Token: $LOCAL_API_TOKEN" 'http://127.0.0.1:8001/api/objects?limit=10'
curl -H "X-Local-Token: $LOCAL_API_TOKEN" -H 'Content-Type: application/json' \
  -d '{"id":"report-test-1","description":"Motxilla grisa","incident":{"lossDate":"2026-10-08"},"contact":{"email":"test@example.invalid"}}' \
  http://127.0.0.1:8001/api/lost-reports
curl -X PATCH -H "X-Local-Token: $LOCAL_API_TOKEN" -H 'Content-Type: application/json' \
  -d '{"status":"closed"}' http://127.0.0.1:8001/api/lost-reports/report-test-1/status
```

Las altas canónicas devuelven 201 al crear y 200 en reintentos idénticos, con
`id`, `status`, `queued:false` y `duplicate`. El mismo ID con otro contenido
original devuelve 409, incluso tras una revisión o cambio de estado.
Los errores mantienen `error` y añaden `code`: validación 422, ausencia 404,
conflicto 409, token/origen 403, tamaño 413, tipo de petición 415, PostgreSQL 503
y fallo/timeout de Ollama 502/504. No se devuelve el cuerpo inválido ni el DSN.

No hay cuentas de usuario: el token da acceso a los datos locales de desarrollo,
no acredita la identidad de un operario. No se habilita CORS, borrado físico,
importación de JSON históricos ni búsqueda BM25 HTTP.

## Extracción automática

Al entrar en el paso Detalles, WP4 llama a `POST /api/extract` con:

```json
{"photo": {"data": "data:image/jpeg;base64,..."}}
```

Se analiza únicamente la foto principal, usando el preprocesamiento y transporte
local de `search/extraction.py`. El prompt específico está en
`search/form_extraction.py`. Primero pide un nombre libre y rasgos visibles en
inglés, después colores y material (con valores desconocidos permitidos). No
expone las categorías del formulario al modelo. El código mapea las observaciones
mediante `search/form-taxonomy.json` y devuelve los campos en el orden de la UI:

```json
{
  "fields": {
    "colors": ["Gris", "Taronja", "Negre"],
    "objectType": "Ampolla",
    "material": "Metall",
    "description": "water bottle. Cylindrical metal body. Black flip cap"
  }
}
```

La respuesta real incluye además `recognized_object`, `warnings`, `id`, calidad, señal de contenido sensible,
modelo/digest, versiones, hash de imagen, duración y `review_status: pending`.
Los valores de los selectores se validan contra `client/form-options.json`; la
descripción tiene un máximo de 250 caracteres. Los valores desconocidos son `[]`,
`null` o texto vacío. Una foto insuficiente, ambigua o sensible devuelve campos
vacíos, conservando el borrador original para trazabilidad.

El nombre libre se conserva en la descripción incluso si su categoría es `Altres`.
Las categorías incluyen `Ampolla` y `Paraigua`. Las etiquetas existentes son
placeholders; no hay una capa de traducción. La descripción procede del nombre y
los rasgos en inglés. Los colores equivalentes (por ejemplo silver/gray → Gris)
se unifican. Material desconocido queda vacío; una contradicción explícita entre
material y una descripción del cuerpo también lo vacía y muestra un aviso.
Esta comprobación es una heurística limitada, no una verificación visual ni una
medida de confianza. Hay que revisar todos los campos antes de guardar.

La UI consume las claves JSON, no sus posiciones. Conserva los cambios manuales
hechos durante la espera, descarta respuestas tardías de una foto sustituida y
requiere confirmar la revisión antes de guardar. La inferencia se limita a una
petición a la vez por proceso; una segunda petición simultánea recibe 409 y puede
reintentarse. Cada petición crea un ID de intento y una foto preparada propios. El resultado se reutiliza por hash de imagen, digest del modelo y
versiones del prompt/preprocesamiento. Cambiar el prompt, esquema o taxonomía
invalida la caché. El tiempo de espera es de 300 segundos.

Para evitar recargar el modelo entre pruebas cercanas, cada extracción WP4 pide
a Ollama conservarlo en memoria durante 15 minutos de inactividad. Después puede
descargarse; la siguiente petición será más lenta. Esto mantiene RAM ocupada más
tiempo, no acelera por sí solo el procesamiento en CPU. La UI muestra el tiempo
transcurrido de la petición actual, distinguiendo resultados guardados. El JSON
de extracciones nuevas incluye `timings`: preprocesamiento, llamada completa al
modelo y, si Ollama los informa, carga, evaluación del prompt y generación.
Los tiempos de Ollama pueden no sumar toda la espera de la petición. Los resultados
antiguos en caché pueden no tener este desglose; no se inventa retrospectivamente.

La segunda foto permanece en el registro; la extracción multivista continúa como
trabajo futuro. No se envían contactos, vehículo ni fechas a Ollama.

Se aceptan JPEG, PNG y WebP estáticos. Los JPEG de tipo MPO (con imágenes
auxiliares dentro del mismo archivo `.jpg`) usan únicamente su imagen principal.
No hace falta convertirlos: el preprocesamiento conserva el archivo original y
genera una copia JPEG para el modelo.

## Registros revisados

`POST /lost-found` recibe el payload actual: `id`, `photos`, `vehicle`, `details`,
`reviewed:true`, `capturedAt` y `extractionId` opcional. Los datos originales, las
fotos y la primera revisión se confirman conjuntamente en PostgreSQL. Se acepta
la cola antigua con `details.color`. El ID de extracción es una referencia opaca;
no tiene por qué ser un hash de 64 caracteres. Debe corresponder a una extracción
correcta de la foto principal del mismo objeto.

`capturedAt` se guarda como fecha del cliente; ni esa fecha ni la línea del
vehículo se convierten automáticamente en contexto de hallazgo. `found_date`,
`date_quality`, `found_line`, `found_direction`, `found_location` y `received_at`
son campos explícitos opcionales del alta. La fecha desconocida sigue siendo NULL.

Las revisiones usan `{details, status, extraction_id?, reviewer_ref?, review_seconds?}`.
El número de revisión se asigna bajo bloqueo en PostgreSQL. El estado de
transporte `received-local` no se copia al estado físico del objeto.

`POST /api/lost-reports` recibe el formulario ciudadano: `id`, `description`,
`createdAt`, `incident`, `filters`, `referencePhoto` y `contact`. Solo la descripción
y el ID son obligatorios en la API. La interfaz mantiene sus campos de contacto
obligatorios. `incident.lossDate` vacío y `filters.objectType` vacío representan
valores desconocidos. `incident` admite además `line`, `direction` y
`dateApproximate` explícitos, sin deducirlos del texto de ubicación.

Las dos colas conservan peticiones pendientes hasta recibir confirmación. La cola
ciudadana nueva reintenta al abrir la página y al recuperar conexión; los borradores
antiguos `saved-local` no se envían automáticamente. La confirmación indica
persistencia local en PostgreSQL, no entrega al sistema real de TMB.

La inferencia se realiza fuera de las transacciones. Los intentos fallidos y sus
fotos se conservan para trazabilidad; se puede registrar manualmente sin vincular
ese intento. Los resultados en caché generan un intento nuevo para cada foto.
Los adjuntos de un alta fallida o duplicada se limpian si no están asociados ni
auditados; las fotos de extracciones abandonadas requieren una política futura.
Los datos ficticios de `database.seed` no tienen archivos de imagen y devolverán
404 al intentar descargarlos.

## Verificación

```bash
python -m pip install -r backend/requirements-dev.txt
export TEST_DATABASE_URL="$DATABASE_URL"
python -m unittest discover -s database/tests -v
python -m unittest discover -s search/tests -v
python -m unittest discover -s backend/tests -v
node --check client/app.js
node --test client/tests/sync.test.mjs
```

Usa un rol local con CREATEDB: los tests crean y eliminan solo bases `tmb_test_<uuid>`.
Nunca vacían DATABASE_URL. Las pruebas comprueban esquema, múltiples colores, exclusión de borradores no
utilizables, caché, procedencia, idempotencia y compatibilidad con la cola antigua.
La extracción en estas pruebas es simulada; para una prueba real usa la interfaz
con Ollama iniciado.

Prueba completa de ambos formularios en navegador (crea su propia base y API
temporal, detiene/reinicia el backend y comprueba reintentos y persistencia):

```bash
python -m playwright install chromium
python -m unittest discover -s client/tests -p 'test_browser.py' -v
```

Si ya tienes Google Chrome instalado, puedes omitir la descarga y ejecutar el
último comando con `BROWSER_CHANNEL=chrome`. Requiere el mismo TEST_DATABASE_URL
de los tests HTTP. Las llamadas de extracción del navegador se simulan.

Para comparar precisión visual, prompt anterior/actual, modelos y recortes, consulta
[el benchmark de visión](../search/benchmarks/README.md). Los tests anteriores
comprueban el contrato del sistema; no demuestran que el modelo describa bien una foto.
