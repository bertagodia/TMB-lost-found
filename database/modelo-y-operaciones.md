# Modelo de datos y operaciones para acordar con backend

**Estado:** borrador de trabajo, pendiente de revisión con backend. Ningún campo,
tabla u operación de este documento constituye todavía un contrato aprobado ni
una migración implementada.

## Alcance y vocabulario

El repositorio establece PostgreSQL como base objetivo. La aplicación hablará con
backend, y backend accederá a la base de datos y al componente de búsqueda. Por
ahora no se conocen el esquema de SharePoint, el almacenamiento de fotografías ni
el protocolo operativo de custodia y devolución.

- **Objeto:** una pieza física registrada. Tiene una identidad estable aunque se
  tomen varias fotografías.
- **Hallazgo:** información sobre cuándo y dónde se encontró el objeto. Puede ser
  parcial o desconocida.
- **Recepción:** primer momento documentado en que se recibió el objeto. No es
  sinónimo de fecha de hallazgo.
- **Pérdida:** fecha y lugar declarados por quien busca el objeto. Son datos de una
  consulta o reclamación, no atributos del objeto hallado.
- **Fotografía:** referencia a una imagen asociada a un objeto. La ubicación y las
  reglas de acceso al archivo siguen pendientes de decisión.

## Modelo conceptual propuesto

```text
objeto 1 ── 0..1 hallazgo
objeto 1 ── 0..N fotografia_objeto
```

La ubicación del hallazgo se representa inicialmente mediante línea y sentido
opcionales dentro de `hallazgo`. Separar una tabla de ubicaciones, o añadir estación
y ubicación actual de custodia, requiere conocer los datos y procesos reales.
La ubicación del hallazgo y la de custodia deben mantenerse distintas si se
incorpora esta última.

| Entidad | Campos propuestos | Reglas propuestas |
| --- | --- | --- |
| `objeto` | `id` UUID; `descripcion` texto; `recibido_en` fecha y hora con zona; `creado_en` fecha y hora con zona | `id` identifica al objeto, no a cada foto. `descripcion` es obligatoria y no vacía. `creado_en` lo genera el sistema; `recibido_en` solo refleja la recepción documentada y puede ser `NULL`. |
| `hallazgo` | `objeto_id` FK única; `fecha_hallazgo` fecha; `calidad_fecha` (`confirmada`, `aproximada`, `desconocida`); `linea_hallazgo` texto; `sentido_hallazgo` texto | Todos los datos observacionales pueden ser desconocidos. No utilizar `recibido_en` para completar `fecha_hallazgo`. Una fecha marcada como desconocida no debe contener una fecha inventada. |
| `fotografia_objeto` | `id` UUID; `objeto_id` FK; `referencia` texto | Cero o más fotos por objeto. La referencia apunta al archivo; no se deduce de ella la identidad del objeto. Evitar referencias duplicadas para el mismo objeto. |

`NULL` significa «no consta», no «no existe». La calidad `aproximada` expresa
incertidumbre, pero una sola fecha quizá no baste para representar un intervalo:
backend y el equipo de datos deben acordar ese caso antes de fijar restricciones.
Tampoco se presupone que el objeto tenga fotografía o metadatos de línea y sentido.

### Datos de una consulta de búsqueda

La primera consulta propuesta contiene `descripcion`, y opcionalmente
`fecha_perdida`, indicador de fecha aproximada, `linea`, `sentido` e imagen de
consulta. No se ha acordado guardar consultas o reclamaciones en PostgreSQL.
Si se decide persistirlas, hará falta diseñar otra entidad y acordar acceso,
retención y datos personales antes de crearla.

## Operaciones de datos propuestas para backend

Son operaciones del repositorio de datos, **no endpoints HTTP**. Backend decidirá
las rutas, permisos, formatos de petición/respuesta y códigos de error.

| Operación | Entrada | Salida y comportamiento esperado |
| --- | --- | --- |
| `crear_objeto` | Descripción, recepción opcional y hallazgo opcional | Devuelve el objeto con su `id` generado. Valida la descripción y conserva los campos desconocidos como `NULL`. |
| `obtener_objeto` | `id` | Devuelve el objeto, su hallazgo y referencias de fotos, o indica que no existe. |
| `actualizar_datos_objeto` | `id` y campos modificados | Devuelve el registro actualizado. Debe distinguir «campo omitido» de «poner `NULL`» y definir cómo evitar sobrescribir cambios simultáneos. |
| `agregar_referencia_foto` | `objeto_id` y referencia | Asocia otra fotografía al mismo objeto, tras verificar que el objeto existe. |
| `quitar_referencia_foto` | `id` de fotografía | Retira la asociación; la política para borrar el archivo físico queda pendiente. |
| `listar_inventario_para_busqueda` | Límite y cursor | Devuelve páginas estables de objetos con descripción, hallazgo y referencias de fotos para búsqueda o indexación. Incluye registros con fecha o ubicación desconocidas. |
| `obtener_objetos_por_ids` | Lista de IDs candidatos | Devuelve los registros existentes para que backend complete la respuesta tras el ranking de búsqueda. |

La base almacena y recupera hechos; el componente de búsqueda decide similitud,
ranking y política de filtrado. No se debe excluir en SQL un objeto solo porque
su fecha o línea de hallazgo sea desconocida. Una puntuación de similitud no
autoriza una devolución.

## Pendientes que hay que cerrar con backend

1. Confirmar campos, nombres y formato de intercambio, en especial si el hallazgo
   será entidad separada y cómo representar fechas aproximadas o intervalos.
2. Definir el catálogo de líneas/sentidos, qué significa «ubicación» y si se
   registrará también ubicación actual de custodia.
3. Decidir dónde se guardan las fotos y qué forma tendrá `referencia`.
4. Acordar quién puede crear o modificar registros y si hacen falta estado,
   historial de cambios, reclamaciones y operaciones de devolución.
5. Acordar si la búsqueda leerá un inventario paginado, un índice sincronizado o
   consultas directas a PostgreSQL; definir entonces índices y mecanismo de
   actualización del índice.
6. Obtener estructura y ejemplos autorizados de SharePoint antes de diseñar su
   importación. No incorporar datos reales ni adjuntos privados al repositorio.

Cuando se apruebe el contrato, el primer cambio técnico será una migración inicial,
seguida de datos ficticios reproducibles y de instrucciones para ejecutar PostgreSQL
en local. Cada cambio posterior del esquema compartido irá en una migración nueva.
