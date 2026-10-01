# Área del equipo de base de datos

Aquí se implementará el acceso a PostgreSQL. Por ahora esta carpeta solo delimita
el trabajo; no contiene una conexión ni un esquema implementados.

Archivos previstos cuando comience la implementación:

- `database.py`: conexión y sesiones.
- `models.py`: tablas y relaciones.
- `repository.py`: contrato que utilizará el backend para acceder al inventario.
- `postgres.py`: implementación de ese contrato con PostgreSQL.
- `json_repository.py`: adaptador de los datos de demostración.

Los cambios de esquema se guardarán en `migrations/`. La configuración local de la
base de datos y sus dependencias también quedan pendientes de implementación.

Coordinad con el equipo de backend los campos y operaciones del repositorio. El
equipo de cliente accede a los datos mediante la API, nunca directamente a la base.
