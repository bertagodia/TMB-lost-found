# Instalar y ejecutar el prototipo 0.1

Esta guía parte de un ordenador sin el proyecto instalado. Al terminar podrás
registrar un objeto con fotos, revisar sus datos y encontrarlo desde la pantalla
ciudadana. No necesitas conocimientos de bases de datos ni claves de API.

Cada persona tendrá **sus propios datos locales**. GitHub comparte el código,
no las fotos ni los registros de los compañeros.

## 1. Preparar el ordenador (solo la primera vez)

Instala estas herramientas desde sus páginas oficiales:

| Herramienta | Para qué sirve | Instalación |
|---|---|---|
| Git | Descargar el proyecto | https://git-scm.com/downloads |
| Python 3.11 o superior | Ejecutar el servidor | https://www.python.org/downloads/ |
| Docker Desktop | Ejecutar PostgreSQL sin configurarlo a mano | https://www.docker.com/products/docker-desktop/ |
| Ollama | Analizar fotos con un modelo local | https://ollama.com/download |

En Windows, habilita el lanzador de Python y la opción de añadir Python al PATH
si aparecen en el instalador. Docker puede pedir habilitar WSL 2 o reiniciar:
completa los pasos de su instalador. En Linux también puedes usar Docker Engine
con el complemento Compose si ya los tienes instalados.

Abre Docker Desktop y espera hasta que indique que está funcionando. Abre Ollama.
Necesitarás Internet para descargar herramientas, paquetes, PostgreSQL y el modelo.
Después, las pruebas se ejecutan localmente. No necesitas Node.js ni instalar
PostgreSQL por separado.

El modelo ocupa varios GB. Como referencia, hemos probado en un equipo con unos
16 GB de RAM y CPU, sin GPU; no es un mínimo garantizado. Deja memoria y disco
libres. La extracción puede tardar decenas de segundos o más según el ordenador.

Abre **PowerShell** en Windows o **Terminal** en macOS/Linux. Copia los comandos
sin los delimitadores del bloque. Pulsa Intro tras cada línea y espera a que
termine antes de continuar. Si aparece un error, consulta el apartado 9.

```text
git --version
docker --version
docker compose version
docker info
ollama --version
```

Los comandos deben mostrar versiones; `docker info` debe mostrar información del
servidor, sin errores de conexión. Comprueba también Python:

**Windows:**
```powershell
py -3 --version
```

**macOS / Linux:**
```bash
python3 --version
```

El resultado debe ser Python 3.11 o posterior. Tras instalar una herramienta,
cierra y vuelve a abrir la terminal si aún no reconoce su comando.

## 2. Descargar esta versión

La versión integrada está en la rama `prototype-integration`. Estos comandos de
GitHub requieren que esa rama esté publicada; si no existe todavía, pide al
responsable que la publique. La versión antigua de `main` no es equivalente.

Para una copia nueva, ejecuta:

```text
git clone --branch prototype-integration https://github.com/bertagodia/TMB-lost-found.git
cd TMB-lost-found
```

Si ya tienes una copia, abre una terminal en su carpeta y ejecuta primero
`git status --short`. Si muestra archivos, conserva tus cambios antes de cambiar
de rama; no los borres. Con la copia limpia:

```text
git fetch origin
git switch prototype-integration
git pull --ff-only origin prototype-integration
```

Para reproducir exactamente la entrega 0.1, una vez publicado también su tag:

```text
git fetch origin --tags
git switch --detach v0.1
```

El modo «detached HEAD» permite probar esa versión; para desarrollar cambios crea
una rama con `git switch -c mi-rama`.

**A partir de aquí, ejecuta todos los comandos desde la carpeta `TMB-lost-found`,**
donde están `SETUP.md`, `backend`, `client`, `database` y `search`. Puedes comprobar
su contenido con `dir` en Windows o `ls` en macOS/Linux.

## 3. Instalar los paquetes Python (solo la primera vez)

El entorno `.venv` guarda los paquetes de este proyecto sin modificar otros.
Usaremos su Python directamente: no tienes que activar el entorno.

**Windows — PowerShell:**
```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
```

**macOS / Linux:**
```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r backend/requirements.txt
```

Espera a que finalice sin errores. Estos paquetes incluyen el acceso a PostgreSQL
y el procesamiento de imágenes.

## 4. Descargar el modelo (solo la primera vez)

```text
ollama list
ollama pull qwen3-vl:2b-instruct
ollama list
```

La última lista debe incluir exactamente `qwen3-vl:2b-instruct`. La descarga puede
tardar varios minutos. Si no conecta con Ollama, abre su aplicación. Si no tienes
una aplicación o servicio activo, abre **otra terminal**, ejecuta `ollama serve`
y déjala abierta. No necesitas ejecutar `ollama run`.

## 5. Iniciar la base de datos y el servidor

Abre Docker Desktop si está cerrado. En la terminal del proyecto, configura una
contraseña local. Sustituye `CambiaEstaClave123` en **ambas líneas** por la misma
contraseña. Para evitar problemas al copiarla dentro de una URL, usa solo letras
y números para esta prueba local. Guarda tu contraseña: la necesitarás al reiniciar.
No subas contraseñas a GitHub.

**Windows — PowerShell:**
```powershell
$env:POSTGRES_PASSWORD = 'CambiaEstaClave123'
$env:DATABASE_URL = 'postgresql://tmb:CambiaEstaClave123@127.0.0.1:55432/tmb'
docker compose -f database/compose.yaml up -d --wait
docker compose -f database/compose.yaml ps
.\.venv\Scripts\python.exe -m backend.server --port 8001 --data-dir artifacts/prototype/storage
```

**macOS / Linux:**
```bash
export POSTGRES_PASSWORD='CambiaEstaClave123'
export DATABASE_URL='postgresql://tmb:CambiaEstaClave123@127.0.0.1:55432/tmb'
docker compose -f database/compose.yaml up -d --wait
docker compose -f database/compose.yaml ps
./.venv/bin/python -m backend.server --port 8001 --data-dir artifacts/prototype/storage
```

**Comprueba cada comando antes de seguir.** La primera ejecución descarga
PostgreSQL. `ps` debe mostrar el servicio `postgres` activo y saludable (`healthy`).
El último comando crea automáticamente las tablas necesarias y muestra:

```text
WP4 + Ollama: http://127.0.0.1:8001
```

Es normal que la terminal no vuelva a mostrar el cursor de comandos: está
atendiendo la aplicación. Déjala abierta. Las variables que acabas de definir
solo existen en esa terminal; el comando Python debe ejecutarse en ella.

La contraseña crea el usuario de PostgreSQL **la primera vez**. Cambiarla en las
variables después no cambia la contraseña de una base de datos ya creada.

## 6. Comprobar que funciona

Abre en el navegador **http://127.0.0.1:8001/api/health**. Debes ver estos valores
(el orden puede variar):

```json
{"model":"qwen3-vl:2b-instruct","status":"ready","storage":"postgres"}
```

**`storage` debe ser `postgres`.** Si aparece `json`, falta `DATABASE_URL`: detén
Python con Ctrl+C y repite el paso 5 en la misma terminal. El modo JSON no ofrece
el flujo completo de inventario y búsqueda. Este control comprueba el servidor y
la conexión a PostgreSQL; la siguiente prueba comprueba la extracción real.

Abre **http://127.0.0.1:8001**. No abras `client/index.html` directamente ni uses
`python -m http.server`: esos métodos no arrancan la API.

1. En **Operaris TMB**, introduce la línea `TEST` y el vehículo `001`.
2. Añade dos fotos del mismo objeto, por ejemplo una botella. Puedes usar tus
   propias imágenes JPEG, PNG o WebP estático.
3. Continúa a **Detalls** y espera la extracción. Solo se analiza la primera foto;
   ambas se guardan. Para probar sin esperar al modelo, pulsa **Omplir manualment**.
4. Revisa tipo, colores, material y descripción. Para una prueba fácil de encontrar,
   incluye `bottle` en la descripción de la botella. Marca la confirmación de
   revisión, continúa y guarda.
5. Abre **Inventari del servidor**: el objeto debe aparecer. Si solo figura como
   pendiente en el historial del navegador, todavía no está guardado en el servidor.
6. En **Soc usuari**, escribe `bottle`, deja los filtros sin seleccionar y pulsa
   **Cercar sense desar**. Debe aparecer el objeto con su foto.
7. Opcionalmente, prueba **Desar i cercar** con datos de contacto ficticios.
8. En el inventario, marca el objeto como devuelto y repite la búsqueda: debe dejar
   de aparecer. Puedes reactivarlo para continuar las pruebas.

La búsqueda actual compara palabras, no el significado general: no traduce entre
idiomas. Los textos extraídos son ingleses y las etiquetas del formulario siguen
siendo provisionales. Los colores y el tipo seleccionados restringen los resultados.
La foto del ciudadano se guarda como referencia, pero no participa en la búsqueda.
Consulta [las funcionalidades y límites](PROTOTYPE.md) y las
[mejoras pendientes](docs/PROTOTYPE_IMPROVEMENTS.md).

## 7. Parar y volver a arrancar otro día

Para parar Python, pulsa **Ctrl+C** en su terminal. Para parar PostgreSQL sin borrar
sus registros, ejecuta desde la carpeta del proyecto:

```text
docker compose -f database/compose.yaml stop
```

Si Compose solicita `POSTGRES_PASSWORD`, vuelve a definirla como en el paso 5.
Puedes cerrar Ollama o parar su terminal con Ctrl+C si la iniciaste tú.

Otro día:

1. Abre Docker Desktop y Ollama.
2. Abre una terminal y entra en la carpeta del proyecto: `cd TMB-lost-found`
   desde la carpeta que la contiene, o usa su ruta completa.
3. Repite **el paso 5**, con la **misma contraseña**. No repitas la instalación
   de paquetes ni la descarga del modelo.
4. Abre o recarga http://127.0.0.1:8001. Recarga después de cada reinicio del
   servidor porque cambia el token que usa la página para llamar a la API.

## 8. Datos, actualizaciones y trabajo en equipo

- PostgreSQL guarda objetos, revisiones y declaraciones en un volumen de Docker.
- `artifacts/prototype/storage/` guarda imágenes y datos de extracción.
- El navegador mantiene su historial y posibles envíos pendientes; el inventario
  del servidor es la referencia para comprobar que algo se ha guardado.
- `.venv/` contiene paquetes; Ollama almacena el modelo fuera del repositorio.

Parar los servicios no borra estos datos. **No uses `docker compose down -v` ni
borres el volumen para solucionar un error:** eso elimina la base de datos.
Una copia de seguridad completa necesita tanto PostgreSQL como la carpeta de
imágenes. No cambies `--data-dir` si quieres seguir usando las fotos registradas.
Los datos, fotos, entorno Python y modelo no se comparten al hacer `git push`.

Para actualizar la rama de desarrollo, para Python, comprueba `git status --short`
y conserva cualquier cambio propio antes de continuar:

```text
git switch prototype-integration
git pull --ff-only origin prototype-integration
```

Repite la instalación de `backend/requirements.txt` del paso 3 (no hace falta
recrear `.venv`) y arranca como en el paso 5. Las migraciones se aplican al arrancar.
Para mantener exactamente la entrega 0.1, sigue usando su tag sin actualizar.

Esta es una aplicación local de pruebas, sin cuentas ni permisos de operador.
No la publiques en Internet. Cada ordenador usa `127.0.0.1` para referirse a sí mismo.

## 9. Problemas frecuentes

| Problema | Qué hacer |
|---|---|
| Un comando «no se reconoce» | Instala la herramienta correspondiente y abre una terminal nueva. |
| Python anterior a 3.11 | Instala una versión compatible antes de crear `.venv`. |
| Linux: falta `venv` o `ensurepip` | En Ubuntu/Debian, instala `python3-venv` con `sudo apt install python3-venv` y repite el paso 3. |
| Docker no conecta con el daemon | Abre Docker Desktop, espera a que arranque y repite `docker info`. |
| Linux: permiso denegado al usar Docker | Completa la configuración de usuario indicada por la instalación de Docker antes de continuar. |
| PostgreSQL no llega a `healthy` | Ejecuta `docker compose -f database/compose.yaml logs --tail 50 postgres` y revisa el error. |
| Puerto 55432 ocupado | Hay otra base de datos usando el puerto. No borres sus datos; detén tu instancia anterior o pide ayuda para identificarla. |
| Error de contraseña de PostgreSQL | Usa la contraseña con la que se creó el volumen y comprueba que ambas variables coinciden. |
| `storage` muestra `json` | Define `DATABASE_URL` en la misma terminal donde ejecutas Python y reinícialo. |
| Puerto 8001 ocupado | Puede estar ya funcionando la app: abre su URL. Si es tu servidor anterior, páralo con Ctrl+C antes de iniciar otro. |
| Ollama no conecta | Abre Ollama o inicia `ollama serve` en otra terminal; comprueba `ollama list`. |
| Ollama devuelve HTTP 404 | Ejecuta `ollama pull qwen3-vl:2b-instruct` y confirma el nombre exacto con `ollama list`. |
| Extracción lenta | La primera carga suele tardar más. Mantén Ollama abierto o usa la entrada manual para probar el resto del flujo. |
| Imagen no compatible | Usa JPEG, PNG o WebP estático, hasta 20 MiB y 25 megapíxeles; HEIC no está admitido. |
| Búsqueda vacía | Comprueba que el objeto está registrado con revisión aprobada, usa una palabra de su descripción y elimina filtros de tipo/color. |
| Error tras reiniciar Python | Recarga la página para obtener el nuevo token local. |
| GitHub no encuentra `prototype-integration` o `v0.1` | La rama o el tag aún no se han publicado; pide al responsable que los suba. |

Si necesitas ayuda, comparte el comando ejecutado, el error y tu sistema operativo.
Oculta contraseñas y datos de contacto antes de copiar mensajes o capturas.
