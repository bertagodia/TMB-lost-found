# Backend local de WP4 + extracción

**Modo integrado:** [PROTOTYPE.md](../PROTOTYPE.md) documenta PostgreSQL, inventario,
revisiones, búsqueda ciudadana y declaraciones. Define `DATABASE_URL` para activarlo.
Sin esa variable se conserva el modo JSON descrito a continuación.

Sirve la interfaz WP4 y conecta su formulario de operarios con Ollama. Desde la
raíz del repositorio, con Python 3.11+ y Ollama activo:

```bash
python -m pip install -r backend/requirements.txt
ollama pull qwen3-vl:2b-instruct
python -m backend.server --port 8001
```

Abre http://127.0.0.1:8001. `--model` selecciona otro modelo local y `--data-dir`
cambia `artifacts/wp4/`, la carpeta de datos predeterminada. Las rutas locales se
resuelven desde el directorio de ejecución. El servidor escucha solo en loopback;
esta versión no tiene autenticación de usuarios ni integración PostgreSQL.

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
reintentarse. El resultado se reutiliza por hash de imagen, digest del modelo y
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

`POST /lost-found` recibe el registro del operario con sus fotos, vehículo,
`details.colors` (lista), `objectType`, `material`, `description`, `reviewed`,
`capturedAt` y la referencia opcional `extractionId`. El backend valida las fotos y
campos y guarda el registro bajo `records/`. Los resultados automáticos se guardan
por separado bajo `extractions/`. No se interpretan las fechas de captura como
fechas de hallazgo. La cola antigua con `details.color` sigue siendo aceptada.

La respuesta `{"queued": false, "status": "received-local", "id": "..."}` confirma
el almacenamiento en este equipo. Repetir el mismo ID y contenido es idempotente;
cambiar su contenido devuelve 409. La UI solo retira un registro de la cola tras
la confirmación. Si falla la conexión, conserva la cola local para reintentar.

Las peticiones de escritura incluyen el token de la página en `X-Local-Token`.
Tras reiniciar el servidor, recarga la página. Se exige mismo origen y Host local;
no se habilita CORS. No sirve como API pública ni confirma entrega a TMB.

Los registros recibidos aún no se conectan automáticamente al índice BM25. La
pantalla ciudadana sigue guardando declaraciones localmente, con varios colores;
la búsqueda y sus resultados quedan para la siguiente integración.

## Verificación

```bash
python -m unittest discover -s search/tests -v
python -m unittest discover -s backend/tests -v
node --check client/app.js
```

Las pruebas comprueban esquema, múltiples colores, exclusión de borradores no
utilizables, caché, procedencia, idempotencia y compatibilidad con la cola antigua.
La extracción en estas pruebas es simulada; para una prueba real usa la interfaz
con Ollama iniciado.

Para comparar precisión visual, prompt anterior/actual, modelos y recortes, consulta
[el benchmark de visión](../search/benchmarks/README.md). Los tests anteriores
comprueban el contrato del sistema; no demuestran que el modelo describa bien una foto.
