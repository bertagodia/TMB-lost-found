# Configuración local para cada persona

**Prototipo completo:** para UI + PostgreSQL + búsqueda sigue [PROTOTYPE.md](PROTOTYPE.md).
Las instrucciones de abajo describen también el modo anterior de extracción/JSON sin `DATABASE_URL`.

Esta guía permite ejecutar el prototipo completo en tu propio ordenador: interfaz
WP4, servidor Python y extracción de imágenes con Ollama. Cada persona necesita
su propia instalación, copia del repositorio y modelo descargado.

El navegador se conecta a `http://127.0.0.1:8001` y Python llama a Ollama en
`http://127.0.0.1:11434`. Ambos servicios deben ejecutarse en el mismo ordenador.
Los registros y fotos de prueba son locales: no se sincronizan entre compañeros.
No necesitas PostgreSQL, Docker, Node.js, claves de API ni un archivo `.env` para
este flujo. Necesitas Internet para descargar herramientas, dependencias y modelo;
la inferencia posterior se ejecuta localmente.

## 1. Instalar las herramientas

Instala:

- [Git](https://git-scm.com/downloads).
- [Python 3.11 o superior](https://www.python.org/downloads/), con `pip` y `venv`.
- [Ollama para tu sistema operativo](https://ollama.com/download).
- Un navegador actualizado.

En Windows, el instalador de Python debe proporcionar el comando `py`; abre una
terminal nueva después de instalar las herramientas. En macOS y Linux usaremos
`python3`. Comprueba las versiones:

**Windows — PowerShell**

```powershell
git --version
py -3 --version
ollama --version
```

**macOS / Linux — terminal**

```bash
git --version
python3 --version
ollama --version
```

Si Python es anterior a 3.11, instala una versión compatible antes de continuar.
La instalación de Ollama depende del sistema: sigue su
[guía oficial](https://github.com/ollama/ollama/blob/main/docs/quickstart.mdx).
En Windows/macOS, abre la aplicación Ollama. En Linux puede estar ya iniciado
como servicio; el paso 4 explica cómo comprobarlo.

El modelo usa varios GB de memoria; deja espacio libre en disco para su descarga
y margen de RAM para el navegador y el sistema. Nuestro ensayo local se hizo en
un equipo de aproximadamente 16 GB de RAM y CPU, sin aceleración GPU. Esto es una
referencia de prueba, no un requisito mínimo garantizado. El tiempo varía mucho
según el equipo, la imagen y si el modelo está cargado.

## 2. Obtener la versión de main

Para una copia nueva, ejecuta lo mismo en cualquiera de los sistemas:

```bash
git clone --branch main https://github.com/bertagodia/TMB-lost-found.git
cd TMB-lost-found
```

Si ya tienes el repositorio, entra en su carpeta y comprueba primero:

```bash
git status --short
```

Si aparecen cambios locales, guárdalos en tu rama de trabajo antes de cambiar de
rama. Cuando tu copia esté limpia:

```bash
git switch main
git pull --ff-only origin main
```

Si Git indica que las ramas han divergido, resuelve la situación siguiendo la
[guía de Git](docs/git.md); no uses un reset para descartar trabajo.

**Los comandos siguientes se ejecutan desde la raíz del repositorio**, donde están
`backend/`, `client/`, `search/` y este archivo.

## 3. Crear el entorno Python e instalar dependencias

Cada persona crea su propio `.venv`; no se comparte ni se sube a Git. Los comandos
usan directamente su intérprete, así no hace falta activar el entorno ni cambiar
la política de scripts de PowerShell. Python documenta este uso en su
[guía de entornos virtuales](https://docs.python.org/3/library/venv.html).

**Windows — PowerShell**

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
```

**macOS / Linux**

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r backend/requirements.txt
```

Las dependencias de extracción son Pillow y Pydantic, con las versiones indicadas
en `search/requirements.txt`. Si Debian/Ubuntu indica que falta `venv` o
`ensurepip`, instala el paquete de `venv` correspondiente a tu versión de Python
(por ejemplo `python3-venv`) y repite la creación del entorno.

## 4. Iniciar Ollama y descargar el modelo

Comprueba que Ollama responde:

```bash
ollama list
```

Si no puede conectar, abre la aplicación Ollama o ejecuta en otra terminal:

```bash
ollama serve
```

Deja esa terminal abierta mientras uses la extracción. Si aparece que el puerto
11434 ya está ocupado, puede haber una instancia de Ollama funcionando: comprueba
`ollama list` antes de intentar iniciar otra.

Descarga el modelo **una vez por ordenador**:

```bash
ollama pull qwen3-vl:2b-instruct
ollama list
```

La lista debe incluir exactamente `qwen3-vl:2b-instruct`. El primer comando puede
tardar según tu conexión. Descargar el modelo no inicia el servidor de la UI.
No hace falta ejecutar `ollama run` ni dejar una conversación con el modelo abierta.

## 5. Iniciar el servidor de la aplicación

En otra terminal, desde la raíz del repositorio:

**Windows — PowerShell**

```powershell
.\.venv\Scripts\python.exe -m backend.server --port 8001
```

**macOS / Linux**

```bash
./.venv/bin/python -m backend.server --port 8001
```

Debe aparecer:

```text
WP4 + Ollama: http://127.0.0.1:8001
```

Mantén esta terminal abierta y visita **http://127.0.0.1:8001**. Usa este servidor
para abrir la UI; `python -m http.server`, abrir `index.html` directamente o servir
solo `client/` no proporciona la API de extracción.

Puedes abrir **http://127.0.0.1:8001/api/health** para comprobar que responde:

```json
{"model":"qwen3-vl:2b-instruct","status":"ready"}
```

Este endpoint confirma que funciona el servidor Python; **no comprueba** que el
modelo esté instalado ni que Ollama pueda extraer una foto. La prueba siguiente
comprueba el recorrido real.

## 6. Probar una extracción completa

1. En la pestaña de operarios, introduce una línea y vehículo de prueba, por ejemplo
   `TEST` y `001`. Confírmalos y continúa a las fotos. No necesitas NFC.
2. Añade dos fotografías del mismo objeto. Desde un ordenador puedes elegir archivos;
   en algunos dispositivos el selector puede abrir la cámara.
3. Continúa a **Detalls**. La extracción empieza automáticamente con la primera foto.
   La segunda se adjunta al registro, pero todavía no se analiza.
4. Espera a que se rellenen los campos. El panel muestra tiempo transcurrido y el
   nombre reconocido. Puedes escribir durante la espera; se conservan tus cambios.
5. Revisa tipo, varios colores, material y descripción. Corrige los errores y rellena
   los campos inciertos. Marca **He revisat i corregit els camps**, revisa y guarda.

Admite JPEG, PNG y WebP estáticos, hasta 20 MiB y 25 megapíxeles por imagen. Los JPG
MPO de móviles también funcionan: se usa su imagen principal. No necesitas convertir
los archivos proporcionados para la prueba de la botella.

El nombre y la descripción automáticos se generan en inglés; las etiquetas actuales
del formulario son placeholders. La extracción puede equivocarse incluso sin avisos.
Un resultado insuficiente o sensible deja los campos vacíos para completarlos a mano.
La pantalla ciudadana guarda declaraciones localmente; su búsqueda aún no está
conectada a este flujo.

## 7. Arrancar los días siguientes y actualizar

No necesitas recrear `.venv` ni volver a descargar el modelo cada día:

1. Comprueba que Ollama está abierto (`ollama list`).
2. Entra en la carpeta del repositorio.
3. Ejecuta el comando del paso 5 y abre `http://127.0.0.1:8001`.

Para actualizar, detén el servidor Python con `Ctrl+C`, comprueba que tu copia esté
limpia, ejecuta `git pull --ff-only origin main` **estando en main**, repite la
instalación de `search/requirements.txt` del paso 3 y arranca de nuevo. Recarga la
página después de cada reinicio: el token local de la sesión cambia.

`Ctrl+C` detiene el servidor, sin borrar datos. Si iniciaste Ollama con `ollama serve`,
puedes detenerlo con `Ctrl+C` en su terminal. Para liberar el modelo de la memoria
manteniendo Ollama abierto:

```bash
ollama stop qwen3-vl:2b-instruct
```

La siguiente extracción necesitará volver a cargarlo.

## 8. Dónde se guardan los datos y cómo trabajar en equipo

- `artifacts/wp4/extractions/`: borradores automáticos, procedencia y tiempos.
- `artifacts/wp4/records/`: registros confirmados con las fotografías originales.
- En el navegador: cola de envíos, historial y declaraciones ciudadanas locales.
- `.venv/`: dependencias Python; el modelo lo almacena Ollama fuera del repositorio.

`artifacts/` y `.venv/` están ignorados por Git. Clonar o hacer `git pull` no descarga
las fotos de otro compañero, su modelo ni sus registros. El dataset del benchmark
tampoco es necesario para probar la UI: puedes usar tus propias fotografías.
Guardar un registro confirma su almacenamiento local, no su entrega a TMB ni su
inclusión automática en el índice de búsqueda.

Puedes elegir otra carpeta añadiendo `--data-dir artifacts/pruebas-personales` al
comando de arranque. Las rutas relativas se resuelven desde la carpeta de ejecución.
Cambiar de carpeta no migra datos existentes. Para conservar registros, guarda una
copia de la carpeta de datos correspondiente.

El servidor escucha exclusivamente en `127.0.0.1`: cada persona abre su propia
instancia en su ordenador. Un móvil u otro ordenador no puede conectarse usando
esa URL, y cambiarla por la IP de tu portátil no habilita acceso remoto. El prototipo
actual no implementa alojamiento compartido, autenticación ni despliegue público.

## 9. Solución de problemas

| Síntoma | Qué comprobar |
| --- | --- |
| `No module named backend`, `PIL` o `pydantic` | Ejecuta desde la raíz y usa el Python de `.venv` del paso 5. Repite la instalación de dependencias. |
| `ollama` no se reconoce | Revisa la instalación y abre una terminal nueva. |
| No conecta con Ollama | Comprueba `ollama list`, la aplicación/servicio y el puerto local 11434. La URL de Ollama está fijada al mismo ordenador. |
| Ollama devuelve HTTP 404 o modelo no encontrado | Ejecuta `ollama pull qwen3-vl:2b-instruct` y comprueba el nombre en `ollama list`. |
| `Address already in use` al arrancar Python | Puede estar ya iniciado. Comprueba `/api/health`; si necesitas otra instancia, usa `--port 8002` y abre la URL con ese puerto. |
| Error de token o “Recarrega la pàgina” | Recarga después de reiniciar el servidor. Usa UI y API en el mismo origen. |
| La UI busca una API antigua | En la consola del navegador ejecuta `localStorage.removeItem('tmb_api_base_url')` y recarga. |
| La extracción tarda uno o dos minutos | Puede ocurrir en CPU, con carga del equipo o tras una pausa. El límite por llamada es 300 s; mira el contador y los tiempos del JSON. |
| HTTP 409 / extracción en curso | Espera a que termine la petición anterior y reintenta. Evita ejecutar benchmarks y extracciones de la UI a la vez. |
| JPG rechazado o imagen inválida | Actualiza main. Comprueba formato real, tamaño y resolución; renombrar una extensión no convierte el archivo. MPO está soportado. |
| Campos vacíos o datos incorrectos | Revisa avisos y calidad de la foto. Completa o corrige manualmente; la revisión es obligatoria. |

El servidor pide a Ollama mantener el modelo cargado durante 15 minutos de
inactividad. Esto evita algunas recargas, pero ocupa RAM y no garantiza rapidez.
En nuestras pruebas hubo extracciones con el modelo cargado de unos 18–32 s y
una petición de 71,5 s tras una pausa; no son tiempos garantizados para otro equipo.
`ollama ps` permite comprobar si el modelo está cargado y el uso de CPU/GPU.
Los resultados idénticos pueden salir de caché: la UI lo indica. Los JSON nuevos
incluyen tiempos de preprocesamiento, llamada al modelo y las métricas disponibles
de carga, evaluación y generación.

## 10. Verificación opcional para desarrollo

Con el intérprete de tu `.venv`, ejecuta:

**Windows — PowerShell**

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s search/tests -v
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
```

**macOS / Linux**

```bash
./.venv/bin/python -m unittest discover -s search/tests -v
./.venv/bin/python -m unittest discover -s backend/tests -v
```

Estos tests simulan las llamadas a Ollama; no requieren descargar el modelo ni
prueban su precisión. Para evaluar reconocimiento con fotos, sigue el
[benchmark de visión](search/benchmarks/README.md). Consulta también el
[contrato del backend](backend/README.md) y las
[instrucciones de búsqueda por CLI](search/README.md).
