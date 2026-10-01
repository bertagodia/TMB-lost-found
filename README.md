# TMB-lost-found

Laboratorio de búsqueda de objetos perdidos

Primer prototipo del componente de búsqueda para la propuesta de TMB. No es un
sistema operativo de TMB. Incluye ocho objetos y seis consultas **sintéticos**,
sin imágenes reales ni datos personales. «Dirección» se interpreta provisionalmente
como sentido de circulación del metro.

## Organización del repositorio

```text
TMB-lost-found/
├── pyproject.toml          # Dependencias, extras y comando lostfound
├── lostfound/
│   ├── __main__.py        # python -m lostfound
│   ├── cli.py             # Indexar, buscar, evaluar y servir
│   ├── config.py          # Rutas y lectura de configuraciones
│   ├── schemas.py         # Contratos de objetos, consultas y resultados
│   ├── data/              # Carga de inventarios y rutas de imágenes
│   ├── imaging/           # Preprocesamiento, calidad e interfaz de modelos
│   ├── indexing/          # Construcción y persistencia de índices
│   ├── search/            # BM25, señales, similitud visual y ranking
│   ├── evaluation/        # Ejecución, métricas e informes
│   └── api/               # Servidor HTTP local
├── web/                   # HTML, CSS y JavaScript separados
├── configs/               # Parámetros TOML de experimentos
├── data/
│   ├── demo/              # Ocho objetos y seis consultas sintéticos
│   └── private/           # Datos y fotos locales, excluidos de Git
├── tests/                 # Pruebas de componentes e integración HTTP
│   └── fixtures/          # Reservado para pequeñas muestras de prueba
├── docs/                  # Arquitectura, contratos y metodología
├── notebooks/             # Exploración; la lógica reutilizable va en lostfound/
├── artifacts/             # Índices y cachés generados, excluidos de Git
└── reports/               # Resultados generados, excluidos de Git
```

`lostfound/data/` contiene código; `data/` contiene datasets. La CLI, la API y el
evaluador utilizan el mismo `SearchEngine`. Los adaptadores de imagen implementan
`ImageTextEncoder`, de modo que cambiar el modelo no obliga a reescribir el motor.

- [Arquitectura y responsabilidades](docs/architecture.md)
- [Contrato de datos](docs/data-contract.md)
- [Plan experimental](docs/experiment-plan.md)

## Preparar el entorno

```bash
git clone https://github.com/bertagodia/TMB-lost-found.git
cd TMB-lost-found
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

La instalación base no añade dependencias de ejecución. Puedes ejecutar los
comandos desde la raíz con `python3 -m lostfound` sin instalar el paquete, o usar
`.venv/bin/lostfound` después de la instalación editable. El extra `images` instala
solo Pillow; el extra `vision` añade también el modelo y sus dependencias.

## Probar el formulario

Desde esta carpeta, con Python 3.11 o posterior:

```bash
python3 -m lostfound serve
```

Abre http://127.0.0.1:8000. La referencia textual usa BM25 y funciona sin instalar
dependencias. Prueba la consulta precargada con señales flexibles y después con
filtros estrictos: DEMO-001 se encontró tres días después de la pérdida simulada.
La interfaz es para revisión interna y pruebas locales: no es un catálogo público.

## Ejecutar experimentos

```bash
python3 -m lostfound search "Mochila negra cremallera roja bolsillo delantero" --date 2026-09-11 --line L3
python3 -m lostfound evaluate --policy soft --k 3
python3 -m lostfound evaluate --policy strict --window 2 --k 3
python3 -m unittest discover -s tests -v
```

También puedes cargar parámetros desde TOML; los argumentos explícitos prevalecen:

```bash
python3 -m lostfound --config configs/baseline.toml search "mochila negra"
python3 -m lostfound --config configs/baseline.toml evaluate --policy strict
```

Los TOML configuran modalidad, política, ventana, k y umbral para `search` y
`evaluate`. El evaluador por lotes todavía es textual: rechaza configuraciones
visuales. Los pesos internos de ranking siguen siendo constantes experimentales;
no se han recalibrado durante la reorganización.

La evaluación separa supervivencia al filtro, recall@k, precision@k, candidatos
falsos positivos, falsos negativos, falsas alarmas en consultas sin correspondencia
y latencia. Precision@k usa k como denominador, incluso con menos resultados.
Recall se promedia solo en consultas con correspondencia. Los casos están diseñados
para comprobar comportamiento; sus métricas **no representan calidad real**.
Los falsos positivos son candidatos incorrectos, nunca adjudicaciones incorrectas.

## Políticas de búsqueda

- `soft`: conserva todos los objetos y añade bonificaciones pequeñas por fecha,
  línea y sentido coincidentes. Una fecha aproximada tiene menos peso.
- `strict`: descarta discrepancias conocidas de línea o fechas de hallazgo fuera
  de ±N días. Mantiene los valores desconocidos. El sentido no excluye objetos.
- La fecha de recepción no sustituye a la de hallazgo. La línea es de hallazgo,
  no la del almacén o punto de concentración.
- Sin coincidencia textual no se propone un objeto solo por fecha o línea.
- `--min-score` aplica un umbral al contenido antes de las bonificaciones. Es
  específico de la modalidad y no está calibrado; debe ajustarse con validación.
- Un resultado vacío no prueba la ausencia del objeto. La política estricta es
  deliberadamente una variante experimental y puede perder correspondencias.

Los pesos, ventana, umbrales, agregación máxima entre fotos y constante RRF=60 son
decisiones provisionales. No son objetivos aprobados ni probabilidades de propiedad.

## Incorporar fotografías y activar visión

La extensión usa SigLIP2 como candidato experimental por su diseño multilingüe;
hay que medir español y catalán por separado. Todavía no se ha validado la
inferencia con pesos reales en este entorno. El formulario web sigue siendo textual;
la extensión visual se ejecuta por CLI.

1. Crea `data/private/objects.json`, siguiendo el esquema de `data/demo/objects.json`.
2. Guarda fotos propias de prueba, por ejemplo en `data/private/photos/mochila.jpg`.
3. En el objeto correspondiente añade `"images": ["photos/mochila.jpg"]`.
   Usa un ID por objeto físico aunque existan varias fotos. Fechas y lugares
   desconocidos son `null`; `found_date_quality` es `confirmed`, `approximate` o
   `unknown`. Marca `synthetic` según la procedencia efectiva.
4. Instala la extensión en un entorno virtual y construye el índice:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[vision]"
.venv/bin/python -m lostfound --data data/private/objects.json index
.venv/bin/python -m lostfound --data data/private/objects.json search "mochila negra con cremallera roja" --mode visual
.venv/bin/python -m lostfound --data data/private/objects.json search "mochila negra" --mode hybrid
```

La primera indexación descarga pesos y procesador de Hugging Face. La inferencia
se ejecuta localmente en CPU; no se envían las fotos a una API. Necesita espacio y
memoria para el modelo, y ruedas de las dependencias compatibles con tu Python.
El comando rechaza inventarios sin fotos antes de descargar el modelo.

Para comparar una foto aportada por el reclamante:

```bash
.venv/bin/python -m lostfound --data data/private/objects.json search "mochila negra" --mode visual --query-image data/private/referencia.jpg
.venv/bin/python -m lostfound --data data/private/objects.json search "referencia visual" --mode visual --query-image data/private/referencia.jpg --image-only
```

Texto+imagen usa una media experimental de similitudes. `--image-only` permite la
comparación usando solo la fotografía. Documenta si es una foto del objeto concreto
o una referencia de catálogo; ninguna modalidad acredita propiedad.

El índice se guarda por defecto en `artifacts/visual-index.json` y contiene vectores normalizados, hash del archivo, revisión del modelo y
versión del preprocesamiento. Reutiliza imágenes sin cambios y elimina entradas
retiradas al reindexar. No se actualiza automáticamente: reindexa tras modificar
el inventario o las fotografías. Antes de experimentar, conserva la revisión
resuelta del modelo; puedes fijarla con `index --revision HASH`.

Preparación: formatos JPEG/PNG/WEBP, límites de tamaño, orientación EXIF, composición
de transparencia sobre blanco, RGB y avisos de resolución/contraste. La copia en
memoria excluye EXIF; el archivo original **no se modifica**. No se detectan ni
ocultan documentos, nombres o caras: las pruebas requieren fotos sin datos
personales. No hay segmentación ni detección automática fiable de desenfoque.

`visual` devuelve solo objetos con imágenes indexadas. `hybrid` fusiona rankings
textual y visual mediante reciprocal rank fusion; permite recuperar objetos sin
foto por texto. Ninguna modalidad mezcla modelos o revisiones de embeddings.
La API web no admite cargas de archivos ni acceso a rutas locales arbitrarias.
El fichero `requirements-vision.txt` se conserva como entrada de compatibilidad;
la única definición de dependencias está en `pyproject.toml`.

## Qué falta validar

- Inferencia real, consumo, latencia y calidad de SigLIP2 con fotos representativas.
- Dataset independiente, descripciones humanas, distractores y casos sin match.
- Calidad por categoría, idioma, fotografía y precisión de fechas/lugares.
- Evaluación multimodal por lotes y tiempo de revisión humana (el evaluador actual
  es textual). Costes y precision/recall a umbral con datos etiquetados suficientes.
- Calibración de abstención. Un vecino visual siempre existe si hay imágenes;
  eso no implica que sea un candidato útil.
- Interfaz con imagen opcional, atributos reservados, roles, persistencia de
  reclamaciones y reactivación ante nuevos objetos, integración y operación.

No hay autenticación, base transaccional, autorización de devolución ni despliegue
productivo. El servidor escucha exclusivamente en loopback. El inventario de demo
no contiene atributos secretos para acreditar propiedad.

## Fuentes técnicas

- [SigLIP2, documentación oficial de Transformers 4.57.1](https://huggingface.co/docs/transformers/v4.57.1/en/model_doc/siglip2): API, normalización de texto y límite del codificador.
- [Modelo experimental de Google](https://huggingface.co/google/siglip2-base-patch16-224).

Los procedimientos y cifras operativas de TMB aportados por el equipo siguen
pendientes de validación. Este repositorio no introduce reglas de custodia.

## Desarrollo y comprobaciones

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q lostfound tests
```

Para ejecutar también las pruebas de preprocesamiento de imágenes, instala
`.[images]` y usa el Python del entorno virtual. Sin Pillow, esas pruebas se marcan
como omitidas; el resto no necesita descargar modelos. La prueba HTTP abre un
servidor temporal en `127.0.0.1`.

Trabaja sobre una rama, verifica las pruebas y revisa `git diff` antes de publicar.
Los `.gitkeep` conservan directorios vacíos; su contenido privado o generado se
excluye mediante `.gitignore`. No deben versionarse fotografías de usuarios,
credenciales, pesos ni índices. Los notebooks no sustituyen a los módulos probados.
