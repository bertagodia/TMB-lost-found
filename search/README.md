# Búsqueda y procesamiento de imágenes — wp5

Primer paso: un motor textual de referencia, independiente de la app y PostgreSQL.
Python 3.11 o posterior; no requiere instalar dependencias.

## Archivos

- `models.py`: objetos, consultas y resultados compartidos con backend.
- `engine.py`: búsqueda textual BM25 y tratamiento de metadatos.
- `__init__.py`: importaciones públicas del componente.

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
| `FoundObject.description` | Texto utilizable para búsqueda; puede estar vacío si se desconoce |
| `FoundObject.found_date` | Fecha de hallazgo, nunca fecha de recepción |
| `FoundObject.date_quality` | `confirmed`, `approximate` o `unknown` |
| `FoundObject.found_line`, `found_direction` | Línea y sentido del hallazgo, no del almacén |
| `SearchQuery.description` | Descripción escrita en el formulario |
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
una nueva instancia. La actualización automática y la integración con la base
quedan para el trabajo conjunto con backend.

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
- Los acentos y mayúsculas se normalizan. No hay comprensión semántica, sinónimos,
  corrección de errores ni procesamiento de imágenes todavía.
- Un objeto sin descripción no es recuperable por esta referencia textual.
- BM25 depende del inventario: los scores no se comparan como probabilidades ni
  se deben trasladar umbrales entre datasets sin evaluación.

## Siguiente paso

Acordar este contrato con backend y preparar fotografías propias y descripciones
independientes. Después comparar la referencia textual con texto-imagen, midiendo
por separado los descartes del filtro y la calidad del ranking. La futura entrada
opcional de una imagen de consulta se añadirá cuando se implemente esa modalidad.
