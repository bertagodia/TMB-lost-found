# Primer experimento de recuperación

## Decisión que se quiere informar

¿Las fotografías mejoran la recuperación frente a texto estructurado y búsqueda
textual, y qué correspondencias se pierden al filtrar estrictamente fecha y línea?

La demo incluida es una prueba funcional construida deliberadamente. No se debe
ajustar el modelo y después presentar sus resultados sobre esa demo como validación.

## Recogida propuesta, pendiente de acordar

Usar objetos cotidianos propios y fotografías sin personas, documentos ni datos
personales. Registrar un identificador por objeto físico. Crear grupos de objetos
parecidos para que la tarea no se reduzca a distinguir paraguas de mochilas.

Por objeto, recoger fotos con distintos ángulos, iluminación y fondos. Mantener la
identidad común en todas las fotos. Para una consulta con fotografía, reservar una
toma diferente a la indexada; no usar la misma imagen ni un recorte suyo como test.

Pedir descripciones independientes, incluyendo español y catalán cuando sea
posible. Identificar idioma, categoría, detalle y origen de la consulta. Si las
personas describen la foto del inventario, marcar ese sesgo en vez de ocultarlo.
Las consultas generadas automáticamente deben identificarse y evaluarse aparte.

Fechas, líneas y sentidos pueden simularse para pruebas de sensibilidad, sin
pretender reproducir la distribución de retrasos de TMB. Distinguir siempre
pérdida, hallazgo y recepción. Incluir metadatos desconocidos e imprecisos.

## Partición y variantes

Separar desarrollo y evaluación por identidad del objeto físico. Mantener consultas
y fotografías de un mismo objeto dentro de una partición. Registrar versión del
dataset, modelo, revisión, política, ventana, umbral y parámetros por ejecución.

Comparar sobre las mismas consultas e inventario:

1. Texto BM25, con política flexible y estricta.
2. Texto de consulta contra fotografías.
3. Fusión de rankings de texto e imagen.
4. Cuando existan fotos de consulta: imagen sola y texto+imagen.

En las variantes visuales, informar de cobertura de imágenes y del efecto sobre
objetos sin foto. No comparar silenciosamente subconjuntos distintos. Evaluar por
separado la agregación entre múltiples fotos: el máximo puede favorecer objetos
con más fotografías.

## Registro de resultados

Separar recall del filtrado y recall@k final. Medir precision@k, candidatos
incorrectos, correspondencias omitidas y falsas alarmas para consultas sin match.
Para métricas globales a umbral, declarar cuál es la unidad (par consulta-objeto)
y la población de pares; no confundirlas con precision@k.

Presentar resultados por categoría, idioma, calidad de descripción y fotografía,
acompañados de tamaños de muestra. Medir latencia de indexación y consulta por
separado, con hardware, memoria, estado frío/caliente y tiempo de revisión humana.
Un score de similitud no es una probabilidad de propiedad.

Los umbrales se ajustan solo con desarrollo. Incorporar casos sin correspondencia
pero con objetos muy parecidos: un sistema que siempre propone vecinos no sabe
abstenerse. Con poca muestra, informar incertidumbre y evitar conclusiones generales.

## Dependencias de TMB

- Disponibilidad, significado y calidad de fecha/línea/sentido de hallazgo.
- Protocolo permitido de captura y atributos reservados.
- Datos anonimizados o material autorizado para una validación posterior.
- Disponibilidad de revisores y definición de candidato útil.
- Idiomas, tiempos y equipamiento previstos para la operación.

El próximo avance medible será ejecutar el modelo sobre un primer lote de fotos
propias, comprobar indexación y consultas y después construir el conjunto de
evaluación independiente. No requiere esperar a un dataset real de TMB.
