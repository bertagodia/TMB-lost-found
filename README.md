# TMB — Objetos perdidos

**Prototipo 0.1:** empieza por [SETUP.md](SETUP.md), la guía paso a paso de instalación. Consulta [PROTOTYPE.md](PROTOTYPE.md) para funcionalidades y detalles de UI + PostgreSQL + búsqueda.

Proyecto para mejorar el registro, la búsqueda y la devolución de objetos perdidos.
La interfaz WP4 está en `client/`. El backbone WP5 de extracción con Ollama,
revisión y búsqueda textual está en `search/`. Para abrir el sistema completo,
configura PostgreSQL y Ollama siguiendo [SETUP.md](SETUP.md). Consulta [search/README.md](search/README.md) para probarlo por CLI
y conocer el mapeo previsto desde los formularios WP4.

## Dónde trabaja cada equipo

```text
TMB-lost-found/
├── database/   # Equipo de base de datos: PostgreSQL y migraciones
├── client/     # Equipo de aplicación: la futura app
├── backend/    # API que conecta la app, la base de datos y la búsqueda
├── search/     # Búsqueda y procesamiento de imágenes
└── docs/       # Guía de colaboración con Git
```

| Área | Trabajo |
|---|---|
| [Base de datos](database/README.md) | Diseñar tablas, relaciones, consultas y migraciones de PostgreSQL |
| [Aplicación](client/README.md) | Desarrollar pantallas, formularios y captura de fotografías |
| [Backend](backend/README.md) | Acordar e implementar la API compartida entre los equipos |
| [Búsqueda e imágenes](search/README.md) | Procesar imágenes y recuperar candidatos a partir de una reclamación |

La app se comunica con la API Python, que accede a PostgreSQL.
La interfaz WP4 usa HTML, CSS y JavaScript. El contrato del prototipo está
documentado en [PROTOTYPE.md](PROTOTYPE.md).

## Empezar

Para instalar y arrancar el prototipo completo, sigue [SETUP.md](SETUP.md).

Instala Git, abre una terminal y ejecuta:

```bash
git clone --branch main https://github.com/bertagodia/TMB-lost-found.git
cd TMB-lost-found
```

Si ya tienes una copia, no la clones otra vez: sigue la [guía de Git](docs/git.md)
para conservar tus cambios antes de seguir las instrucciones de [SETUP.md](SETUP.md).

La interfaz WP4 usa el backend local para extracción y registro. La persistencia PostgreSQL y la búsqueda ya están conectadas en el prototipo local. La API de
producción sigue pendiente. Cada equipo
añadirá las dependencias e instrucciones de ejecución cuando implemente su parte.
Los cambios de campos o API se acordarán entre equipos antes de integrarlos.
