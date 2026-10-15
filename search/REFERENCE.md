> Para instalar y probar la versión actual, empieza por [README.md](README.md).
> Este documento conserva el diseño, contratos y referencia detallada de la CLI.

# Búsqueda y procesamiento de imágenes — wp5

## Enfoque adoptado: comparación texto–texto

Las fotografías de los objetos encontrados se transformarán en atributos y una
descripción textual. El buscador comparará esa representación con la descripción
del cliente, enriquecida con los atributos de su fotografía si la aporta.

Aquí **extracción de características** significa extraer información semántica
visible: categoría, color, material aparente, marca legible y detalles distintivos.
No significa comparar vectores visuales ni comparar directamente texto e imagen.
La primera implementación usa Ollama local con un modelo configurable. Su calidad
está pendiente de evaluar; `qwen3-vl:2b-instruct` es el modelo predeterminado para experimentar.

```text
Foto del operario → atributos y descripción → revisión del operario → texto indexado
                                                                         ↑
Formulario del cliente → texto de consulta → búsqueda textual → candidatos
                              ↑
Foto opcional del cliente → atributos y descripción
```

Fecha, línea y sentido se recogen en campos independientes y se usan para acotar
o priorizar candidatos. Nunca se infieren de la fotografía. Una coincidencia
solo propone un candidato: no acredita propiedad ni autoriza una devolución.

## Hipótesis y condiciones de funcionamiento

La hipótesis del equipo es que no habrá más de dos objetos parecidos por línea
y día. **No está validada** y debe medirse con datos de TMB, definiendo qué se
considera parecido y separando las categorías. Una ventana de ±2 días abarca
cinco días, por lo que puede contener más de dos candidatos similares.

Se evaluará el filtrado por línea y fecha de hallazgo respecto a la fecha de
pérdida declarada, inicialmente con una ventana experimental de ±2 días. El
hallazgo puede producirse más tarde; la fecha de recepción o registro no debe
sustituirlo. Los metadatos desconocidos o aproximados requieren un tratamiento
flexible para evitar descartar el objeto correcto. El sentido será una señal
secundaria, no una exclusión automática.

La conversión a texto simplifica la recuperación, pero puede perder detalles
visuales o introducir atributos erróneos. Su utilidad se comprobará midiendo
tanto los errores de extracción como los candidatos que recupera el buscador.

## Procesamiento de imágenes previsto

- Procesar las fotos al incorporarlas y conservar el resultado para no repetir
  la extracción en cada búsqueda. Permitir reprocesarlas al cambiar el modelo.
- Extraer solo atributos visibles; dejar como desconocido lo que no pueda
  determinarse. Una foto insuficiente debe permitir continuar con texto manual.
- Permitir al operario corregir la descripción antes de usarla como texto revisado.
- Conservar por separado el texto original, la extracción automática y las
  correcciones, con la procedencia, versión del modelo y estado de revisión.
- Si el cliente aporta texto y foto contradictorios, conservar ambas fuentes y
  señalar la discrepancia, sin sobrescribir silenciosamente su descripción.
- Excluir del texto de búsqueda datos personales y atributos reservados para
  acreditar propiedad. Las fotografías y evidencias tendrán acceso restringido.

La extracción básica ya genera atributos y un borrador textual con procedencia.
El componente incorpora revisión por CLI, persistencia JSON y extracción por
lotes reanudable. La interfaz de aplicación pertenece a WP4 (`client/`). La detección automática de contradicciones
sigue pendiente; las discrepancias se resuelven explícitamente por el usuario. El motor de búsqueda solo recibe texto y
metadatos; no recibe las imágenes directamente.

## Estado actual y responsabilidades

Ya existe un motor textual BM25, independiente de la app y PostgreSQL.
Requiere Python 3.11 o posterior y no necesita instalar dependencias.
La extracción opcional necesita las dependencias de `requirements.txt` y Ollama
ejecutándose con un modelo local de visión. No hay búsqueda semántica textual.

| Área | Responsabilidad prevista |
|---|---|
| Equipo de search e imágenes | Extracción semántica, preparación del texto, recuperación, ranking y evaluación |
| Backend y base de datos | Persistencia en PostgreSQL, referencias a imágenes, trazabilidad e integración del inventario con el buscador |
| Equipo de cliente | Formulario, foto opcional, presentación de candidatos autorizados e interfaz de revisión para operarios |

BM25 será la referencia inicial. Si la evaluación muestra fallos por sinónimos o
diferencias de redacción, se comparará con embeddings **textuales** o recuperación
híbrida. No se necesita incorporar una base vectorial independiente para empezar.

## Archivos

- `models.py`: objetos, consultas y resultados compartidos con backend.
- `engine.py`: búsqueda textual BM25 y tratamiento de metadatos.
- `extraction.py`: extracción de atributos, preparación de imagen y comando CLI.
- `requirements.txt`: dependencias opcionales de extracción (Pillow y Pydantic).
- `__init__.py`: importaciones públicas del componente.

## Extraer atributos de una fotografía

Desde la raíz del repositorio, crea un entorno Python e instala las dependencias:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r search/requirements.txt
```

En Windows, activa el entorno con `.venv\Scripts\Activate.ps1` en PowerShell.
Instala [Ollama](https://ollama.com/download) y descarga un modelo con visión:

```bash
ollama pull qwen3-vl:2b-instruct
ollama serve
```

Si la aplicación de Ollama ya mantiene el servicio iniciado, no ejecutes un
segundo `ollama serve`. La descarga del modelo requiere conexión y espacio en
disco; la velocidad de inferencia depende del equipo. No se descarga ningún
modelo automáticamente desde nuestro código.

En otra terminal con el entorno activado, procesa una imagen local:

```bash
python -m search.extraction data/roboflow/selected50/images/OBJ-001.jpg --model qwen3-vl:2b-instruct --output data/extractions/OBJ-001.json
```

Sustituye la ruta si no tienes el dataset local. Para una foto del cliente añade
`--source claimant`; por defecto se registra `operator`. `--timeout 300` permite
ampliar la espera. El archivo de salida no se sobrescribe si ya existe.

El JSON contiene:

- `attributes`: categoría, colores, material, marca, detalles distintivos,
  calidad (`usable`, `insufficient`, `ambiguous`), señal de contenido sensible y
  problemas observados. Los valores desconocidos son `null` o listas vacías.
- `draft_search_text`: concatenación de atributos conocidos, sin los avisos.
  Queda vacío si la foto es insuficiente, ambigua o marcada como sensible.
- Procedencia (`operator` o `claimant`), SHA-256 del original, nombre del modelo,
  versiones del prompt y preprocesamiento, fecha UTC y tiempo total de extracción.
- `review_status: pending`: la salida automática siempre necesita revisión.

Ejemplo de integración para desarrollo, después de revisar el resultado:

```python
from search.extraction import extract_image
from search import FoundObject

result = extract_image("data/roboflow/selected50/images/OBJ-001.jpg", model="qwen3-vl:2b-instruct")
print(result.model_dump_json(indent=2))
# Tras revisar y corregir manualmente el borrador:
reviewed_text = input("Descripción revisada (vacía para no indexar): ").strip()
if reviewed_text:
    obj = FoundObject(id="OBJ-001", description=reviewed_text)
```

Para una reclamación se aplica la misma extracción con `source="claimant"`.
La combinación con el texto del formulario debe preservar ambas fuentes; esta
versión no fusiona ni resuelve contradicciones automáticamente.

### Límites de esta primera versión

- Acepta una imagen JPEG, PNG o WebP estática de hasta 20 MiB y 25 megapíxeles.
  Corrige orientación EXIF, compone transparencias sobre blanco y reduce a un
  máximo de 1024 píxeles por lado manteniendo proporciones. Envía un JPEG sin
  metadatos y conserva el original intacto. Puede perder detalles pequeños.
- Se conecta únicamente a `127.0.0.1:11434`, sin claves de API ni lectura de `.env`.
  Utiliza un modelo descargado localmente, no un modelo cloud.
- Valida el JSON con un esquema estricto, pero esto no garantiza atributos
  correctos. El prompt pide excluir información personal; **no es un detector
  fiable de datos personales**. Revisar antes de indexar o mostrar resultados.
- La etiqueta del modelo puede cambiar al descargarlo de nuevo. La extracción
  integrada guarda su digest de Ollama; la CLI individual solo guarda la etiqueta.
- Esta CLI de extracción individual no guarda en PostgreSQL ni actualiza el índice.
  La CLI del prototipo descrita más abajo añade lotes y persistencia local.
  No calcula confianza calibrada ni acredita propiedad. Las correcciones deben
  guardarse separadas de la extracción original en la futura integración.

Referencias de implementación: [visión en Ollama](https://docs.ollama.com/capabilities/vision),
[salidas estructuradas](https://docs.ollama.com/capabilities/structured-outputs) y
[modelo Qwen3-VL 2B Instruct](https://ollama.com/library/qwen3-vl:2b-instruct).

## Probar desde la raíz del repositorio

Abre Python con `python3` (o `python` en Windows) y pega este ejemplo. Los dos
objetos son ficticios y solo existen en memoria; no se guarda ningún inventario.

```python
from datetime import date
from search import FoundObject, SearchEngine, SearchQuery

objects = [
    FoundObject(
        id="ejemplo-1",
        description="Mochila negra con cremallera roja",
        found_date=date(2026, 9, 14),
        found_line="L3",
        date_quality="confirmed",
    ),
    FoundObject(
        id="ejemplo-2",
        description="Paraguas amarillo con mango de madera",
    ),
]
engine = SearchEngine(objects)
query = SearchQuery(
    description="mochila negra cremallera roja",
    lost_date=date(2026, 9, 11),
    line="L3",
)

result = engine.search(query)
for candidate in result.candidates:
    print(candidate.object_id, candidate.text_score, candidate.signals)

strict = engine.search(query, policy="strict", window_days=2)
print("Excluidos por filtros:", strict.excluded_ids)
```

La búsqueda flexible devuelve `ejemplo-1`. La estricta lo excluye porque se
halló tres días después de la pérdida simulada. Esto comprueba una regla del
programa; no demuestra rendimiento real con objetos de TMB.

## Contrato para backend

Backend proporcionará los registros como `FoundObject`, tras obtenerlos de
PostgreSQL, y transformará el formulario de la app en `SearchQuery`.

| Entrada | Significado |
|---|---|
| `FoundObject.id` | Identificador único del objeto físico |
| `FoundObject.description` | Texto utilizable para búsqueda, manual o preparado a partir de la extracción revisada; puede estar vacío si se desconoce |
| `FoundObject.found_date` | Fecha de hallazgo, nunca fecha de recepción |
| `FoundObject.date_quality` | `confirmed`, `approximate` o `unknown` |
| `FoundObject.found_line`, `found_direction` | Línea y sentido del hallazgo, no del almacén |
| `SearchQuery.description` | Texto de consulta; en el flujo previsto podrá combinar la descripción del formulario con atributos de una foto opcional |
| `SearchQuery.lost_date` | Fecha declarada de pérdida |
| `SearchQuery.date_approximate` | Indica si la fecha declarada es aproximada |
| `SearchQuery.line`, `direction` | Línea y sentido declarados por la persona |

Las fechas son `datetime.date`. Se usa `None` para fechas/lugares desconocidos.
Una fecha desconocida lleva precisión `unknown`; una fecha informada requiere
`confirmed` o `approximate`. No se inventan fechas para completar el contrato.

La salida incluye IDs de candidatos, puntuación textual, señales de metadatos e
IDs descartados. Backend podrá recuperar los detalles autorizados por esos IDs.
La salida no acredita propiedad ni disponibilidad física para entrega.

El motor trabaja sobre una instantánea: al cambiar el inventario hay que crear
una nueva instancia. La CLI del prototipo reconstruye la instantánea en cada búsqueda a partir de los
registros aprobados. La integración con la base queda para el trabajo con backend.

## Comportamiento y límites

- `soft`, por defecto: conserva el inventario, incluso con metadatos distintos.
- `strict`: descarta línea conocida distinta o fecha de hallazgo fuera de ±N días.
  Conserva metadatos desconocidos y no excluye por sentido. Es experimental y
  puede perder correspondencias, especialmente con fechas aproximadas.
- Ordena por relevancia textual; fecha, línea y sentido solo desempatan por ahora.
  Los pesos de desempate son provisionales.
- No propone candidatos basándose únicamente en fecha o línea.
- `limit` controla el número de resultados y `min_text_score` permite experimentar
  con abstención. El umbral no está calibrado ni es una probabilidad.
- Los acentos y mayúsculas se normalizan. El ranking no incorpora comprensión
  semántica, sinónimos ni corrección de errores. La extracción de imágenes es un
  paso separado y previo al buscador.
- Un objeto sin descripción no es recuperable por esta referencia textual.
- BM25 depende del inventario: los scores no se comparan como probabilidades ni
  se deben trasladar umbrales entre datasets sin evaluación.

## Próximos pasos y evaluación

1. Acordar los atributos y el formato de salida de la extracción, incluyendo
   procedencia, revisión y tratamiento de datos desconocidos.
2. Usar la selección local de 50 referencias de Roboflow, cuando esté disponible
   en `data/roboflow/selected50/`, para generar descripciones desde sus imágenes.
   Los datos están excluidos de Git y no son registros reales de TMB.
3. Preparar consultas independientes de las descripciones indexadas. Las
   descripciones existentes, redactadas viendo las fotos, sirven para desarrollo
   pero no como consultas independientes para medir calidad.
4. Comparar texto manual y texto extraído con el mismo buscador BM25. Evaluar
   por separado consultas solo de texto y consultas con foto opcional. No usar
   la misma foto de inventario como única prueba de la modalidad con foto: se
   necesitarán imágenes independientes del mismo objeto.
5. Medir precisión y recall de candidatos, `precision@k`, `recall@k`, falsos
   positivos, falsos negativos y tiempo de revisión, separados por categoría y
   calidad de descripción. Evaluar umbrales y casos sin correspondencia para
   permitir no proponer candidatos.
6. Medir atributos omitidos o inventados, tiempo de corrección, latencia y coste
   por imagen. Separar los descartes debidos a filtros de los fallos del ranking.
7. Validar con TMB la densidad de objetos parecidos y los retrasos de hallazgo
   antes de adoptar filtros estrictos. Los 50 ejemplos no validan esa hipótesis.

Las variantes del mismo original deben permanecer en la misma partición si se
divide el dataset para ajustar y evaluar. Los objetivos numéricos se fijarán
tras obtener una línea base. La calidad de recuperación y los errores de
adjudicación de propiedad se evaluarán por separado.


## Prototipo local completo

La CLI `python -m search` conecta importación, extracción opcional, revisión,
persistencia y búsqueda. Es una herramienta local para operarios/desarrolladores,
no una interfaz pública para reclamantes. Usa un único escritor a la vez: los
archivos se sustituyen atómicamente, pero no hay bloqueo entre procesos.

### Demo sin Ollama ni dependencias opcionales

Desde la raíz del repositorio, usando Python 3.11 o posterior:

```bash
python -m search --store artifacts/search/demo.json import search/fixtures/objects.json
python -m search --store artifacts/search/demo.json list
python -m search --store artifacts/search/demo.json review DEMO-001 --reviewer demo --text "Mochila negra con cremallera roja"
python -m search --store artifacts/search/demo.json review DEMO-002 --reviewer demo --text "Paraguas amarillo con mango de madera"
python -m search --store artifacts/search/demo.json review DEMO-003 --reviewer demo --text "Mochila azul con bolsillo blanco"
python -m search --store artifacts/search/demo.json search "mochila negra cremallera roja" --lost-date 2026-09-11 --line L3
python -m search --store artifacts/search/demo.json evaluate search/fixtures/queries.json --output reports/search/demo.json
```

Los fixtures son ficticios y comprueban funcionamiento, no calidad real de
recuperación. La importación no aprueba descripciones ni sobrescribe IDs. Si ya
importaste la demo, continúa desde `list`; para otro experimento usa otro `--store`.
`--store` siempre va antes del subcomando. Sin él, se usa
`artifacts/search/inventory.json`. `artifacts/`, `reports/` y `data/` no se versionan.

### Procesar y revisar las 50 imágenes locales

Instala las dependencias opcionales e inicia Ollama según las instrucciones de
arriba. Importa `objects.json` para conservar las rutas de las fotos:

```bash
python -m search import data/roboflow/selected50/objects.json
python -m search extract --model qwen3-vl:2b-instruct --timeout 300
python -m search show OBJ-001
```

Cada imagen completada se guarda inmediatamente. Repetir `extract` omite las
extracciones ya guardadas con el mismo hash de imagen, digest del modelo y
versiones de prompt/preprocesamiento. Los fallos se muestran por objeto y dejan
continuar el lote; el comando devuelve código 1 si alguno falla. `--id OBJ-001`
limita el lote a un objeto y puede repetirse. Un modelo o configuración nuevos
producen otra versión sin borrar la extracción anterior ni sus revisiones.

Tras inspeccionar la foto y el resultado, copia la clave `key` de la extracción
que revisaste y aprueba únicamente texto corregido y apto para búsqueda:

```bash
python -m search review OBJ-001 --reviewer operario --source extraction --extraction-key CLAVE_DE_LA_EXTRACCION --text "Mochila gris y negra con cordón cruzado" --seconds 25
python -m search search "mochila negra con cordón" --output reports/search/consulta.json
```

`--seconds` permite registrar el tiempo real de revisión; no se inventa si se
omite. Si la imagen falla, usa `review` con `--source manual` y una descripción
manual. `review OBJ-001 --reviewer operario --reject` retira el objeto del índice
revisado. Las revisiones se añaden al historial; no borran las fuentes originales.
Reprocesar no aprueba automáticamente el borrador nuevo: permanece vigente la
última revisión hasta que el operario registre otra.

### Consulta con foto opcional

```bash
python -m search photo /ruta/foto-cliente.jpg --model qwen3-vl:2b-instruct --output artifacts/search/foto-cliente.json
```

Inspecciona ambos textos y resuelve manualmente contradicciones. No hay detector
automático ni inferencia de propiedad. Para incorporar solo atributos revisados:

```bash
python -m search search "Mi mochila negra" --photo-result artifacts/search/foto-cliente.json --photo-action combine --reviewed-photo-text "Cremallera roja" --output reports/search/consulta-con-foto.json
```

Si la foto contradice la descripción o es insuficiente, `--photo-action ignore`
permite buscar solo el texto original. Sin una decisión explícita, el comando
rechaza la combinación. El informe conserva el texto original, extracción,
decisión y texto revisado por separado. Trata estos informes como datos locales
restringidos: no se deben publicar directamente como respuestas de la futura API.

### Evaluación y significado de métricas

`evaluate` recibe una lista JSON con `id`, `query` (campos de `SearchQuery`) y
`relevant_ids` (lista vacía para casos sin correspondencia). Admite `category`,
`description_quality` y `modality` para separar resultados. El formato mínimo está
en `fixtures/queries.json`. Para consultas con foto prepara el texto combinado
tras la revisión y etiqueta `modality` como `text_photo`; la evaluación no llama
al modelo. Las consultas reales deben redactarse sin copiar las descripciones
indexadas, usando fotos independientes cuando se evalúe la modalidad con foto.

Por defecto compara tres variantes sobre las mismas consultas:

- `manual`: descripciones originales importadas, solo como referencia offline.
- `extraction`: última revisión aprobada de una extracción por objeto.
- `reviewed`: última revisión aprobada, manual o de extracción; índice de la CLI.

Una última revisión rechazada excluye el objeto de ambos índices revisados. La
variante manual puede contener texto sin revisar y nunca se usa en `search`.
El informe muestra cuántos objetos están indexados en cada variante: no compares
calidad final hasta que hayas revisado los objetos necesarios en ambas variantes.

Se calculan precision@1/3/5 (aciertos divididos por k, incluso con menos de k
resultados) y recall@1/3/5 (aciertos divididos por relevantes). El recall de casos
sin correspondencia es `null` y se excluye de su media; esos casos tienen además
una tasa de consultas con candidatos falsos. Se listan falsos positivos y
negativos, relevantes excluidos por filtros, relevantes sin indexar y fallos de
ranking. También se registran latencia del buscador, tiempos de extracción y
revisión disponibles, y hashes de inventario/consultas para identificar la corrida.
El coste monetario local no se estima: se informa como desconocido.

`--policy strict --window-days 2` permite comparar filtros; `--min-text-score`
permite explorar abstención. Ajusta umbrales en desarrollo y congélalos antes de
evaluar. Mantén variantes de un mismo original/identidad en la misma partición.
Los metadatos de la selección Roboflow siguen siendo desconocidos; prueba reglas
de fechas con fixtures sintéticos y no los presentes como evidencia de TMB.

Los errores de atributos requieren anotación humana, no se deducen del ranking.
Opcionalmente pasa `--annotations ruta/anotaciones.json` con una lista como:

```json
[
  {
    "object_id": "OBJ-001",
    "extraction_key": "CLAVE_DE_LA_EXTRACCION",
    "omitted_attributes": ["cordón frontal"],
    "invented_attributes": ["marca"]
  }
]
```

Sin anotaciones, los errores se muestran como desconocidos, no como cero.

### Archivos y futura integración

- `storage.py`: esquema JSON versión 1, historial de revisiones y adaptación a `FoundObject`.
- `pipeline.py`: caché, digest de Ollama y extracción por lotes.
- `cli.py`, `__main__.py`: comandos del prototipo.
- `evaluation.py`: métricas y diagnósticos de recuperación.
- `fixtures/`: inventario y consultas sintéticos, disponibles sin el dataset local.
- `tests/`: pruebas de contratos, revisión, búsqueda, evaluación y extracción simulada.

Backend podrá sustituir `Inventory` por un adaptador PostgreSQL que entregue los
mismos `FoundObject` aprobados. Debe mantener separados texto original,
extracciones versionadas y revisiones, conservar fechas desconocidas y reconstruir
la instantánea cuando cambie el inventario. La autorización de detalles e imágenes
pertenece a backend; la búsqueda no acredita propiedad ni autoriza devoluciones.

```bash
python -m unittest discover -s search/tests -v
```

Las pruebas del flujo textual no necesitan dependencias externas; las de imágenes
se omiten si no están instaladas Pillow y Pydantic. Ollama se simula en las pruebas:
un resultado correcto de tests no demuestra calidad ni latencia de inferencia real.
