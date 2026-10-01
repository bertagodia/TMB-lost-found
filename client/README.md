# Client de registre TMB Lost & Found

Primera versió funcional del flux de registre per a un dispositiu Android compartit.
És una aplicació web instal·lable (PWA) sense dependències externes: es pot provar
amb qualsevol servidor HTTP estàtic i empaquetar més endavant amb Capacitor si cal.

## Executar

Des de `client/`, serveix els fitxers:

```bash
python3 -m http.server 4173
```

Obre `http://localhost:4173`. La càmera i Web NFC requereixen HTTPS en un mòbil
(excepte `localhost`). Per provar el flux sense tag, usa el formulari de vehicle manual.

## Arquitectura

- `index.html`: flux de quatre passos: vehicle, dues fotos, detalls i revisió.
- `app.js`: adaptadors separats `NfcVehicleReader`, `ApiClient` i `LocalQueue`.
- `styles.css`: llenguatge visual responsive centralitzat.
- `manifest.webmanifest`: instal·lació com a PWA.

Les llistes de color, tipus i material són configuració editable a `CONFIG`.
Les fotos es guarden temporalment com a data URLs a la cua local per al mode offline;
en producció cal valorar IndexedDB per a fitxers grans.

## Integració pendent

Per defecte, `CONFIG.apiBaseUrl` és buit: no es fa cap petició ni s’inventa cap API.
Quan backend publiqui el contracte, defineix `localStorage.setItem('tmb_api_base_url',
'https://...')`; el client enviarà `POST /lost-found` amb ID únic, vehicle, fotos,
etiquetes, descripció i `capturedAt`. Cal acordar format, autenticació, mida de fotos
i respostes d’error amb backend.

Web NFC espera provisionalment un registre de text JSON (`{"line":"H12","vehicle":"3421"}`)
o usa el número de sèrie del tag. Aquest format està encapsulat a `parseVehiclePayload`.
La detecció automàtica de fotos fosques o borroses encara no s’activa; la revisió manual
queda preparada per afegir un `PhotoQualityChecker`.
