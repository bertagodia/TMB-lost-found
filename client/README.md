# WP4 — interfície del prototip integrat

La guia actual de funcionalitats, arrencada i proves és [PROTOTYPE.md](../PROTOTYPE.md).
Amb `DATABASE_URL`, la interfície desa objectes a PostgreSQL, permet revisar
l’inventari del servidor i cerca coincidències des de la pestanya ciutadana.
Les declaracions i contactes es desen separadament al servidor. La foto ciutadana
és només una referència; la cerca compara text i filtres.

L’extracció analitza la primera de les dues fotos amb Qwen/Ollama. Pots omplir
els camps manualment, revisar diversos colors i confirmar abans de desar.
L’inventari permet corregir, rebutjar, marcar com a retornat i reactivar objectes.
Les revisions es conserven i la cerca només mostra la darrera revisió aprovada
d’objectes actius.

La pestanya **Match** gestiona les coincidències desades al servidor: vincula
objectes actius i aprovats amb declaracions obertes, mostra el contacte de les
declaracions vinculades i desa ubicacions, enviaments i retorns a PostgreSQL.
Cal executar el servidor integrat amb `DATABASE_URL` i obrir la interfície a
`http://127.0.0.1:8001`; obrir `index.html` directament amb `file://` no connecta
amb l’API. Aquesta instància local no té autenticació.

El servidor escolta a localhost:8001. Les pestanyes encara no tenen autenticació
ni separació real de permisos. No és un servei públic de TMB.

## Fitxers

- `index.html`, `app.js`, `styles.css`: interfície sense framework.
- `location-assignment-data.json`, `location-assignment.js`, `location-assignment.css`:
  origins (stations/depot) and their assigned destination stations.
- `form-options.json`: vocabulari compartit amb backend.
- `tests/prototype.cjs`: prova Playwright del flux complet amb servidor real.
- `manifest.webmanifest`: metadades de la interfície.

La cua offline d’operaris conserva peticions pendents quan hi ha espai al navegador.
L’historial local només desa resums, sense duplicar els bytes de les fotografies.
L’inventari del servidor permet comprovar els registres des de qualsevol navegador
d’aquest equip.
