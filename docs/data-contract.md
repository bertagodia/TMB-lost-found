# Contrato de datos del prototipo

`lostfound/schemas.py` documenta los tipos con `TypedDict`. Los tipos no constituyen
validación automática en ejecución. Actualmente se validan IDs duplicados,
descripciones, fechas ISO y límites de consulta; no es un esquema productivo completo.

## Inventario

Un archivo JSON contiene una lista de objetos. Ejemplo ficticio:

```json
{
  "id": "DEMO-001",
  "description": "Mochila negra con cremallera roja",
  "found_date": "2026-09-14",
  "found_date_quality": "confirmed",
  "received_date": "2026-09-14",
  "found_line": "L3",
  "found_direction": null,
  "images": ["photos/mochila-frontal.jpg", "photos/mochila-lateral.jpg"],
  "synthetic": true
}
```

- `id`: identidad del objeto físico; no generar un ID por fotografía.
- `description`: descripción utilizable para búsqueda, sin atributos reservados.
- `found_date`: fecha de hallazgo ISO o `null`. No es la fecha de recepción.
- `found_date_quality`: `confirmed`, `approximate` o `unknown`.
- `received_date`: fecha simplificada de recepción en esta demo. Un registro
  operativo necesitaría el instante de primera recepción documentada.
- `found_line` y `found_direction`: lugar/sentido del hallazgo, o `null`.
- `images`: rutas relativas al directorio del JSON, siempre dentro de él.
- `synthetic`: procedencia ficticia; no marcar datos reales como sintéticos.

La precisión de la línea, intervalos temporales y objetos compuestos no están
modelados aún. Ningún campo de esta demo establece un protocolo operativo de TMB.

## Consulta y resultado

`SearchQuery` contiene `description` y, opcionalmente, `date`, `date_approximate`,
`line` y `direction`. Para fecha/lugar desconocidos se omite el campo o se usa una
cadena vacía. La API valida la consulta antes de buscar. La imagen de consulta
es un argumento local de la CLI, no una ruta admitida por la API HTTP.

`SearchResult` contiene candidatos, IDs que sobrevivieron al filtrado, exclusiones,
política y modalidad. Cada candidato mantiene la puntuación de contenido, textual,
visual cuando existe, puntuación final y señales de metadatos.

Los scores no son probabilidades de propiedad. Un objeto con varias fotografías
produce un candidato. Los resultados no confirman ubicación física ni disponibilidad.

## Índice y evaluación

La firma global del índice registra modelo, revisión y versión de preprocesamiento.
Cada `ImageEmbedding` contiene ID del objeto, ruta, SHA-256, vector y comprobaciones
de calidad. El índice es un artefacto regenerable y queda fuera de Git.

Las consultas de evaluación añaden `id` y `relevant_ids`. Una lista vacía significa
que no hay correspondencia en el inventario de prueba. El `scenario` opcional
documenta qué se pretende comprobar. No se deriva la verdad de referencia a partir
del ranking del modelo.
