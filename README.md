# TMB — Objetos perdidos

Proyecto para mejorar el registro, la búsqueda y la devolución de objetos perdidos.
La interfaz WP4 está en `client/`. El backbone WP5 de extracción con Ollama,
revisión y búsqueda textual está en `search/`. La API local FastAPI conecta ambos
formularios a PostgreSQL; sigue [backend/README.md](backend/README.md) para instalar
dependencias, configurar la base y arrancar. Visita http://127.0.0.1:8001 y `/docs`.
Consulta [search/README.md](search/README.md) para probar la búsqueda por CLI
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

La app se comunica con la API; no accede directamente a PostgreSQL.
PostgreSQL sustituirá a SharePoint según la decisión comunicada por el equipo.
La interfaz WP4 usa HTML, CSS y JavaScript. El contrato de la API local está
documentado en OpenAPI; el despliegue de producción sigue pendiente.

## Empezar

Para instalar y arrancar el servidor en el ordenador de cada persona (Windows,
macOS o Linux), sigue la [guía SETUP.md](SETUP.md).

Instala Git, abre una terminal y ejecuta:

```bash
git clone https://github.com/bertagodia/TMB-lost-found.git
cd TMB-lost-found
```

Si ya tienes una copia, no la clones otra vez: sigue la [guía de Git](docs/git.md)
para actualizarla y crear tu rama de trabajo desde `main`.

La interfaz WP4 usa el backend local para extracción y persistencia en PostgreSQL.
La API de producción y la integración HTTP de búsqueda siguen pendientes.
Los cambios de campos o API se acordarán entre equipos antes de integrarlos.
