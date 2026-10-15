# Benchmark de precisión visual

Compara el formulario anterior (`legacy`, prompt WP4 v2 congelado en
`wp4-fields-v2.json`) con el reconocimiento libre y mapeo actual (`current`).
No cambia el modelo ni activa recortes automáticos en la UI.
Los resultados locales iniciales están en [RESULTS.md](RESULTS.md).

`objects-v1.json` contiene 20 objetos / 21 fotos: 19 del conjunto local selected50
(mochilas, bolsos, carteras, gafas, teléfonos, relojes, llaves, auriculares,
batería externa y portátil) y dos vistas de la botella del usuario. Las referencias
son etiquetas visuales provisionales del asistente, no validadas independientemente
por una persona. La identidad de la botella fue confirmada por el usuario. Es un
conjunto de desarrollo, no una estimación general de precisión en producción.
No incluye imágenes ni fotos personales en Git. Conserva la atribución/licencia
original de selected50 al obtener o compartir sus fotografías.

## Ejecutar

Instala `search/requirements.txt`, inicia Ollama y usa rutas a los datos locales:

```bash
python -m search.accuracy \
  --images /ruta/selected50 \
  --personal /ruta/fotos-botella \
  --variants legacy current \
  --output reports/vision-full
```

La carpeta personal contiene `IMG_1621.jpg` e `IMG_1622.jpg` originales. Para probar
solo imágenes del dataset sin esas fotos, usa `--ids OBJ-001,OBJ-007,OBJ-011` (u otros
IDs del manifiesto) y omite `--personal`. El hash comprueba que cada referencia
corresponde a la foto esperada antes de iniciar las llamadas. Para tus propias
imágenes, crea otro manifiesto con la misma estructura y pásalo con `--manifest`.

Las llamadas son secuenciales para no saturar el modelo. Una comparación completa
requiere 42 inferencias y puede tardar bastantes minutos en CPU. Evita extraer desde
la UI mientras se ejecuta el benchmark. Puedes interrumpir y repetir el mismo
comando: reutiliza resultados por imagen, digest del modelo, prompt, esquema,
preprocesamiento y recorte. Los errores se incluyen en las métricas y se reintentan
al reanudar. `--timeout` controla el límite por inferencia (300 s por defecto).

Para comparar modelos **ya instalados**, añade por ejemplo
`--models qwen3-vl:2b-instruct OTRO_MODELO_LOCAL`. No se descargan modelos solos.
Cada modelo se registra con su digest; no se mezclan ejecuciones si cambia.

## Experimento de recorte

```bash
python -m search.accuracy \
  --images /ruta/selected50 --personal /ruta/fotos-botella \
  --variants current --views full crop \
  --ids OBJ-001,OBJ-007,OBJ-024,IMG_1621,IMG_1622 \
  --output reports/vision-crops
```

Las cajas del manifiesto son `[left, top, right, bottom]` normalizadas de 0 a 1,
tras aplicar orientación EXIF. Se usan cajas del dataset con margen y cajas
revisadas visualmente para la botella. Se recorta antes de redimensionar a 1024 px.
Esto mide un recorte conocido, no un detector automático. Solo la caja elegida se
usa para preparar la entrada: nombres, colores y demás respuestas esperadas nunca
se pasan al modelo. Las originales no se modifican. La UI sigue usando la foto
completa hasta que las comparaciones justifiquen cambiarla.

## Leer los resultados

`report.json` contiene filas completas, versiones y resumen por modelo/variante/vista:

- Exactitud de categoría y coincidencia del nombre libre con las alternativas
  previstas. En el baseline se busca el nombre en la descripción. Una categoría
  `Altres` correcta no basta para acertar el nombre del objeto.
- Precisión de colores: proporción de colores predichos permitidos por la referencia.
  Recall: proporción de colores dominantes requeridos encontrados. Se toleran
  acentos opcionales; las equivalencias de color de la UI siguen siendo limitadas.
- Exactitud de material **solo** donde existe una referencia visual suficientemente
  clara. No se inventan materiales de referencia para completar el dataset.
- Errores, abstenciones y mediana del tiempo de inferencia original (incluye carga
  del modelo cuando corresponda; reusar la caché no se cuenta como inferencia rápida).

Las métricas son por foto; las dos vistas de la botella no son objetos independientes.
Un error o una abstención cuenta como fallo de categoría/nombre. Revisa también las
filas: una buena media puede ocultar una clase problemática. La comparación combina
cambios de prompt, esquema y categorías; no aísla el efecto de cada cambio.

Las afirmaciones inventadas no se pueden medir de forma fiable comparando frases.
`review-template.json` deja cada resultado como `null` (sin revisar). Haz una copia,
compara cada descripción/rasgo con la foto y sustituye `null` por una lista de
las afirmaciones sin respaldo, o `[]` si la revisaste y no encontraste ninguna.
Repite el comando con `--reviews /ruta/revision.json`: reutiliza inferencias y añade
las cifras de revisión al informe. Cero resultados revisados **no significa** cero
alucinaciones. Los avisos heurísticos tampoco sustituyen esta revisión.

Añade fotos nuevas y consigue validación humana de etiquetas antes de decidir un
cambio de modelo o estimar precisión real. La categoría de paraguas tiene tests de
mapeo, pero este conjunto aún no tiene una foto de paraguas para medir reconocimiento.
