# TMB — Objetos perdidos

Proyecto para mejorar el registro, la búsqueda y la devolución de objetos perdidos.
Esta es la estructura inicial de trabajo: las implementaciones temporales y los
tests del prototipo se han retirado. Se pueden consultar en el historial de Git.

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

La app se comunicará con la API; no accederá directamente a PostgreSQL.
PostgreSQL sustituirá a SharePoint según la decisión comunicada por el equipo.
La tecnología de la app y el contrato de la API están pendientes de acuerdo.

## Empezar

Instala Git, abre una terminal y ejecuta:

```bash
git clone https://github.com/bertagodia/TMB-lost-found.git
cd TMB-lost-found
```

Si ya tienes una copia, no la clones otra vez: sigue la [guía de Git](docs/git.md)
para actualizarla y crear tu rama de trabajo desde `main`.

Todavía no hay una app, base de datos o servidor listos para arrancar. Cada equipo
añadirá las dependencias e instrucciones de ejecución cuando implemente su parte.
Los cambios de campos o API se acordarán entre equipos antes de integrarlos.
