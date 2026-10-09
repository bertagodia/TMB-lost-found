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

El servidor escolta a localhost:8001. Les pestanyes encara no tenen autenticació
ni separació real de permisos. No és un servei públic de TMB.

## Fitxers

- `index.html`, `app.js`, `styles.css`: interfície sense framework.
- `form-options.json`: vocabulari compartit amb backend.
- `tests/prototype.cjs`: prova Playwright del flux complet amb servidor real.
- `manifest.webmanifest`: metadades de la interfície.

La cua offline d’operaris conserva peticions pendents quan hi ha espai al navegador.
L’historial local només desa resums, sense duplicar els bytes de les fotografies.
L’inventari del servidor permet comprovar els registres des de qualsevol navegador
d’aquest equip.
