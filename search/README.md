# WP5 — Backbone de extracción y búsqueda

Componente Python para conectar la interfaz WP4 de `client/` con la extracción
local de atributos y la búsqueda de objetos. Una foto se convierte en un borrador
textual con **Qwen3-VL 2B Instruct mediante Ollama**. Tras revisión humana, el
buscador **BM25** compara ese texto con la descripción de una reclamación.

Este cambio incluye la biblioteca, persistencia JSON local, CLI y evaluación.
La interfaz es la de [WP4](../client/README.md); no se incluye una segunda UI de
pruebas. La conexión local WP4 → Ollama se inicia con `python -m backend.server --port 8001`.
El adaptador `form_extraction.py` genera los campos del formulario y permite revisión
antes de guardar. PostgreSQL y la búsqueda desde la pantalla ciudadana siguen pendientes.

## Instalación

Desde la raíz del repositorio, con Python 3.11 o posterior:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r search/requirements.txt
```

En Windows, crea el entorno con `python -m venv .venv` y actívalo con
`.venv\Scripts\Activate.ps1`. BM25, la persistencia y la CLI textual usan solo la
biblioteca estándar; Pillow y Pydantic se necesitan para fotografías.

Instala [Ollama](https://ollama.com/download), versión 0.12.7 o posterior, y descarga:

```bash
ollama pull qwen3-vl:2b-instruct
ollama list
```

Si el servicio no está activo, ejecuta `ollama serve` en otra terminal.
El componente usa exclusivamente `127.0.0.1:11434`, sin claves API ni lectura de
`.env`. No descarga modelos automáticamente. Puedes elegir otro modelo local con
visión usando `--model`, incluido `gemma3:4b`.

## Probar el backbone sin interfaz

### Extraer una fotografía

```bash
python -m search.extraction /ruta/objeto.jpg --output artifacts/search/extraccion.json
```

El modelo predeterminado es `qwen3-vl:2b-instruct` y la espera es de 300 segundos.
Admite JPEG (incluidos archivos MPO, usando solo su imagen principal), PNG y WebP
estático, hasta 20 MiB y 25 megapíxeles. Conserva el archivo original; las imágenes
auxiliares de un MPO no se analizan como vistas adicionales. El resultado incluye
atributos, borrador, hash del original, versiones del prompt/preprocesamiento,
modelo y duración. Siempre comienza con `review_status: pending`.

La salida individual no se sobrescribe. Para experimentar otra vez, usa otro
archivo. `--source claimant` identifica una foto del reclamante. Las extracciones
integradas en inventario registran además el digest del modelo para versionado y
caché; la extracción individual solo registra su nombre.

### Importar, revisar y buscar sin Ollama

```bash
python -m search --store artifacts/search/demo.json import search/fixtures/objects.json
python -m search --store artifacts/search/demo.json review DEMO-001 --reviewer tester --text "Mochila negra con cremallera roja"
python -m search --store artifacts/search/demo.json search "mochila negra cremallera roja"
```

Importa una sola vez por inventario: los IDs duplicados dan error sin sobrescribir
registros. Los objetos sin revisión aprobada no aparecen en `search`.
`--store` va antes del subcomando; por defecto se usa
`artifacts/search/inventory.json`.

### Procesar el dataset local

Si está disponible la selección local de 50 imágenes:

```bash
python -m search import data/roboflow/selected50/objects.json
python -m search extract --id OBJ-001
python -m search show OBJ-001
```

Copia el `key` de la extracción revisada y aprueba una descripción corregida:

```bash
python -m search review OBJ-001 --source extraction --extraction-key CLAVE --reviewer operario --text "Mochila gris y negra con cordón frontal"
python -m search search "mochila gris cordón"
```

Sin `--id`, `extract` procesa el inventario por lotes. Guarda cada imagen completada
y permite reanudar; reutiliza resultados solo si coinciden hash de imagen, digest
del modelo y versiones de extracción. Cambiar de Gemma a Qwen no borra resultados
ni revisiones anteriores. Un nuevo borrador no sustituye una revisión aprobada.

`data/`, `artifacts/` y `reports/` están excluidos de Git. Para utilizar el dataset
en otro equipo, copia la carpeta `selected50` con su `objects.json` e `images/`;
no se descarga al clonar. También puedes importar un JSON propio con registros
como `fixtures/objects.json`, añadiendo `image` con una ruta relativa al JSON.

## Conectar con la interfaz WP4 de main

Revisado contra el merge `8c97222` («WP4: html UI for first prototype»).
WP4 ya captura **dos fotos por objeto**, campos manuales y datos del vehículo.
`ApiClient.submit()` tiene un envío provisional a `POST /lost-found` cuando se
configura `tmb_api_base_url`; la declaración del ciudadano solo se guarda en
localStorage, sin búsqueda ni envío HTTP.

El adaptador de backend deberá realizar este mapeo, sin enviar contactos al modelo:

| Campo de WP4 | Tratamiento en backend/WP5 |
|---|---|
| Registro del operario `id` | ID estable del objeto; sincronización idempotente para no duplicarlo al reintentar. |
| `photos[].data` | Fotos en data URL: validar, decodificar y guardar con acceso restringido antes de llamar al extractor con una ruta local. Conservar ambas; la extracción actual procesa una imagen por llamada. |
| `details.objectType`, `color`, `material`, `description` | Conservar la entrada manual separada del borrador automático y la revisión; no aprobar automáticamente un resultado del modelo. |
| `vehicle.line` | Candidata a `found_line` si realmente describe la línea de hallazgo. `vehicle.vehicle` sigue siendo metadato del backend. |
| `capturedAt` | Momento del registro, **no fecha de hallazgo**. Si no se conoce el hallazgo, usar `found_date=None` y `date_quality='unknown'`. |
| Ciudadano `description` | Base de `SearchQuery.description`, preservando el texto original. |
| `incident.lossDate` | Convertir a `datetime.date` para `lost_date`, o `None` si falta. |
| `incident.location` | Texto libre de línea, vehículo o estación: no copiarlo ciegamente a `line`. Se necesita normalización o campos separados. |
| `filters.objectType`, `filters.color` | Etiquetas provisionales de la interfaz. Se consideran placeholders; su traducción o normalización lingüística queda fuera del alcance actual. |
| `referencePhoto` | Extracción separada con `source='claimant'`. Resolver discrepancias explícitamente; una foto de un objeto parecido no demuestra identidad. |
| `contact` | Gestión restringida de backend. No incorporarlo al texto indexado ni a la consulta al modelo. |

Las etiquetas catalanas de WP4 se consideran placeholders por ahora; no bloquean
esta entrega ni se añade tratamiento especial para ellas. BM25 sigue siendo una
búsqueda léxica, sin traducción ni comprensión de sinónimos.

Funciones disponibles para el adaptador:

```python
from search import FoundObject, SearchEngine, SearchQuery
from search.extraction import extract_image

extraction = extract_image("/ruta/local/objeto.jpg")
# Backend conserva extraction por separado y WP4 presenta el borrador para revisión.
# Solo después de recibir texto aprobado por el operario:
reviewed_text = "Mochila gris y negra con cordón frontal"
objects = [FoundObject(id="objeto-1", description=reviewed_text)]
result = SearchEngine(objects).search(SearchQuery(description="mochila gris"))
# Backend usa los IDs de result.candidates para devolver solo detalles autorizados.
```

`Inventory` en `storage.py` ofrece importación, revisiones y adaptación a
`FoundObject` para desarrollo local. Es un almacén de un solo escritor; no debe
usarse como sustituto de concurrencia, autorización o persistencia PostgreSQL.
El buscador usa una instantánea: hay que reconstruirlo cuando cambia el inventario.

La integración local de operarios está disponible: `POST /api/extract` devuelve
campos revisables y `POST /lost-found` guarda el registro confirmado. La extracción
se realiza antes del envío y sus errores permiten continuar manualmente. Consulta
[backend/README.md](../backend/README.md) para arrancar la UI conectada y conocer
el contrato. La búsqueda del ciudadano y la API de producción siguen pendientes.

El formulario usa ahora reconocimiento libre del objeto antes de mapear categorías,
con nombre conservado para `Altres`, colores múltiples y avisos de incertidumbre.
Esto es distinto del extractor genérico de la CLI. Para comparar el prompt anterior,
el actual, modelos locales y recortes sin modificar la UI, consulta el
[benchmark de precisión visual](benchmarks/README.md).

## Implementación futura: segunda fotografía

Aunque WP4 ya permite capturar dos perspectivas, WP5 todavía guarda una única
`image_path` por objeto y no combina varias extracciones. La ampliación propuesta:

1. Asociar una o dos fotos al **mismo ID físico**, con hash y procedencia por foto.
2. Extraer cada vista por separado y conservar ambos resultados versionados.
3. Mostrar las dos fotos y borradores en WP4 para una única revisión; resolver
   contradicciones sin sobrescribir fuentes silenciosamente.
4. Indexar una sola descripción aprobada por objeto, evitando candidatos duplicados.
5. Reprocesar solo la vista afectada cuando cambie una imagen o la configuración.

Una vista complementaria puede revelar asas, correas, cierres o detalles ocultos.
Dos imágenes casi iguales probablemente aporten menos. El beneficio aún no está
medido: comparar una frente a dos vistas en 10–15 objetos, evaluando errores de
categoría, detalles útiles, atributos inventados, tiempo de revisión y recuperación.
La selección actual tiene una vista por referencia; hacen falta segundas fotos
independientes del mismo objeto, no simples recortes o variantes aumentadas.

Dos extracciones independientes implican aproximadamente el doble de trabajo de
inferencia, aunque el tiempo real depende de caché y hardware. Como alternativa,
se puede evaluar una petición con ambas imágenes: su latencia y calidad no están
medidas. No hay fusión automática ni mejora cuantificada implementada todavía.

## Pruebas, evaluación y límites

```bash
python -m unittest discover -s search/tests -v
python -m search --store artifacts/search/demo.json evaluate search/fixtures/queries.json --variant manual --output reports/search/demo.json
```

Las pruebas usan almacenes temporales y simulan Ollama; las de imágenes se omiten
si faltan dependencias opcionales. La evaluación con fixtures comprueba el flujo,
no rendimiento real con TMB. Consulta [REFERENCE.md](REFERENCE.md) para los contratos,
consultas etiquetadas, métricas y comandos completos, incluida la foto del reclamante.

Comprobación local del 8 de octubre de 2026 con Qwen y prompt v2: OBJ-001 tardó
29,1 s, OBJ-011 20,0 s y OBJ-016 20,4 s, con el modelo ya cargado y JSON español
válido. No hubo timeouts en esas tres llamadas, pero hubo categorías imprecisas y
atributos que requieren revisión. No es un benchmark ni una garantía de latencia.

La búsqueda flexible es la predeterminada. `--policy strict` activa el filtro
experimental de línea y ±2 días, que puede perder coincidencias. Los scores no son
probabilidades. La extracción puede inventar atributos; la señal de contenido
sensible no es un detector fiable. Una coincidencia no acredita propiedad.

Si Ollama devuelve 404, comprueba `ollama list` y el nombre del modelo. Si no
conecta, inicia `ollama serve`. `--timeout` permite ajustar la espera hasta 600
segundos. Revisa y corrige siempre el borrador antes de indexarlo.
