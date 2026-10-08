# Base de datos

Carpeta del equipo de PostgreSQL. Aquí se añadirán el esquema, las migraciones,
los datos ficticios necesarios para desarrollo y las instrucciones de arranque.

El [borrador del modelo y las operaciones](modelo-y-operaciones.md) reúne una
propuesta concreta para revisar con backend. Todavía no es un contrato aprobado.

El [backbone de datos v0.1](BACKBONE.md) amplía esa propuesta con los campos,
relaciones y reglas requeridos por la extracción y revisión actuales de `main`.
Incluye cuatro tablas iniciales de inventario, dos posteriores para declaraciones
y contactos, mapeo desde la UI y pruebas de aceptación. Las diferencias respecto
al borrador anterior están señaladas para acordarlas con backend; todavía no hay
una migración implementada.

Primer trabajo: acordar con backend los datos de objetos, hallazgos, ubicaciones y
referencias a fotografías. Diferenciar fecha de pérdida, hallazgo y recepción.
Los valores desconocidos deben poder representarse sin inventar información.

PostgreSQL es la base objetivo; todavía no está implementada. La migración desde
SharePoint se diseñará cuando se conozcan sus datos y adjuntos.

Las credenciales se guardan localmente en `.env`, nunca en Git. Cada cambio de
esquema compartido se recogerá en una migración nueva.
