# Git para empezar a trabajar en equipo

**Git** guarda el historial del código. **GitHub** aloja la copia compartida.
Una **rama** separa tu trabajo; un **commit** guarda tus cambios localmente y
**push** los sube. Una **Pull request** pide al equipo que revise e integre cambios.

## 1. Actualizar tu copia

Abre la terminal dentro de `TMB-lost-found` y comprueba si hay cambios pendientes:

```bash
git status
```

Si tienes modificaciones, guárdalas primero en tu rama con los pasos del apartado
3. No cambies de rama ni descartes archivos sin entender qué se perdería.
Con tu trabajo guardado:

```bash
git fetch origin
git switch main
git pull --ff-only
```

Si Git impide continuar, pide ayuda al equipo. No uses opciones para forzarlo.

## 2. Crear una rama propia

Desde `main`, utiliza un nombre descriptivo y distinto para cada tarea:

```bash
git switch -c equipo-db/ana-modelo-objetos
```

Para aplicación podrías usar `equipo-app/ana-formulario`. `main` es la referencia
compartida. Las ramas WP3 y WP4 son ramas de trabajo, no directorios del proyecto.

## 3. Guardar y subir

Revisa los cambios y añade únicamente los archivos de tu tarea. Ejemplo:

```bash
git status
git diff
git add database/README.md
git commit -m "Describe el modelo de objetos"
git push -u origin HEAD
```

Sustituye el archivo y el mensaje por los de tu trabajo. Si es tu primer commit y
Git pide tu identidad, configura tu nombre y correo reales en esta copia:

```bash
git config user.name "Tu nombre"
git config user.email "tu-correo@example.com"
```

Después repite el commit. Necesitas permiso de acceso para subir a GitHub; si no
lo tienes, contacta con la persona responsable del repositorio.

## 4. Pedir revisión

En GitHub abre una **Pull request** desde tu rama hacia `main`. Explica qué has
cambiado y cómo lo has comprobado. Coordina los cambios de API con el otro equipo.
Después de integrar el trabajo, vuelve al apartado 1 para empezar otra tarea.

Si aparecen conflictos, resolvedlos juntos. No uses `push --force` ni borres
archivos para ocultarlos. No subas `.env`, contraseñas, fotografías privadas,
datos reales de TMB, entornos virtuales o dependencias descargadas.

Git comparte código y migraciones, no el contenido de tu base de datos local.
