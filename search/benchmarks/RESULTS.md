# Resultado local — 8 de octubre de 2026

Se compararon 20 objetos / 21 fotos del manifiesto `objects-v1.json`, con el mismo
modelo local `qwen3-vl:2b-instruct`, temperatura 0 y fotos completas. Referencias
visuales provisionales del asistente, sin validación humana independiente. Es un
conjunto de desarrollo pequeño; no representa precisión de producción. Las dos
fotos de la botella corresponden al mismo objeto.

| Medida por foto | Formulario anterior (v2) | Reconocimiento libre + mapeo (v3) |
| --- | ---: | ---: |
| Categoría rellenada correctamente | 7/21 (33,3%) | 20/21 (95,2%) |
| Nombre coincide con alternativas de referencia | 11/21 (52,4%) | 20/21 (95,2%) |
| Precisión de colores permitidos | 39,0% | 70,5% |
| Recall de colores dominantes | 68,8% | 93,8% |
| Mediana de inferencia | 20,6 s | 18,5 s |
| Errores de ejecución | 0 | 0 |
| Abstenciones | 1 | 1 |

La exactitud mide los campos finales que recibe la UI, incluyendo el filtro de
calidad. El teléfono dañado OBJ-024 fue reconocido como teléfono en el borrador,
pero ambos prompts lo marcaron como `insufficient`, dejando vacíos los campos.
Por tanto se cuenta como fallo/abstención, no como acierto de la UI.
La medida de nombre usa patrones de texto, no una evaluación semántica completa;
puede penalizar errores ortográficos. Material solo tiene referencias para tres
fotos de dos objetos: no permite concluir precisión general de material.

Ambas vistas de la botella ahora producen `water bottle` → `Ampolla`, material
`Metall` y los colores gris, naranja y negro. Todavía añaden blanco indebidamente.
El prompt anterior devolvía `Bossa`, y una descripción inventaba vidrio y 0,5 L.

## Recorte controlado

Se compararon cinco fotos de cuatro objetos: OBJ-001, OBJ-007, OBJ-024 y las dos
vistas de la botella, con el prompt actual. Se utilizaron cajas conocidas, no un
sistema de detección automática. Esta ejecución volvió a medir las fotos completas
para compararlas con los recortes dentro del mismo experimento.

| Medida | Foto completa | Recorte |
| --- | ---: | ---: |
| Categoría correcta | 4/5 | 4/5 |
| Precisión de colores | 71,4% | 66,7% |
| Recall de colores | 90,0% | 90,0% |
| Mediana de inferencia | 25,1 s | 16,6 s |

El recorte redujo tiempo en este ensayo, pero no mejoró precisión. Se mantiene la
foto completa en la UI. Los tiempos son observaciones de una pasada local, no
benchmarks de hardware controlados; pueden incluir carga inicial del modelo.

## Detalles inventados y límites

Se hizo una revisión visual puntual del asistente sobre ocho descripciones,
registrada por clave de ejecución en `reports/vision-full/assistant-spot-review.json`.
No es una muestra aleatoria ni una revisión humana independiente. En las seis
salidas actuales revisadas se detectaron dos detalles sin respaldo: un supuesto
cargador/base junto al reloj OBJ-032 (es su caja) y un eje dentado en OBJ-036 que
no se aprecia en la foto. Las dos salidas antiguas revisadas son las de la botella,
ambas incorrectas. No se calcula una tasa global de alucinación a partir de esta
revisión parcial. Los casos no revisados siguen como `null`, no como correctos.

La mejora combina reconocimiento libre, orden de extracción, idioma del prompt,
esquema y mapeo/categorías; este ensayo no aísla qué proporción corresponde a cada
cambio. No se ha cambiado ni comparado otro modelo. El runner permite hacerlo con
`--models`, manteniendo imágenes, referencias, variantes y recortes constantes.
Falta una prueba con fotos nuevas y etiquetas validadas por una persona, más
referencias de materiales y categorías ausentes como paraguas.

## Reproducción y trazabilidad

Consulta [README.md](README.md) para los comandos. Los informes completos locales
son `reports/vision-full/report.json` y `reports/vision-crops/report.json` (ignorados
por Git; no incluyen bytes de imagen). Cada fila registra campos, observaciones,
tiempo, errores, hash de imagen, digest del modelo, variantes y configuración del
recorte; las inferencias se conservan para reanudar sin repetirlas.

- Digest del modelo: `ea422f1e73652a95479954d8572d3c8c6022f628ce2d38a1a04aae1b7f2d5300`.
- Prompt/esquema/taxonomía actuales: `wp4-recognition-v3-59d209e7702d-b8c9730c9195`.
- Preprocesamiento: `rgb-exif-mpo-primary-1024-jpeg90-v2`.
- Baseline: prompt y esquema congelados en `wp4-fields-v2.json`.

Además del ensayo visual, pasaron 31 tests de Python y las comprobaciones de
navegador para preservar ediciones manuales, ignorar respuestas de fotos antiguas,
mostrar avisos y nuevas categorías, y exigir revisión. Estas pruebas funcionales
no se incluyen en las cifras de precisión visual.
