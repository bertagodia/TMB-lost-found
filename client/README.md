# WP4 — Aplicació i interacció amb les persones usuàries

El WP4 s’encarrega de la part de l’aplicació amb què interactuen les persones: les
pantalles, els formularis, la captura d’imatges i la presentació clara de l’estat de
les sol·licituds. L’objectiu és que registrar o cercar un objecte sigui senzill des
del mòbil.

L’aplicació es planteja amb dues àrees: una d’ús intern per a TMB i una altra per a
les persones que han perdut un objecte. La primera s’està desenvolupant ara; la
segona és una funcionalitat prevista.

## Captura de la interfície actual

La imatge mostra la pantalla inicial de l’àrea TMB per identificar el vehicle i
començar un registre.

![Captura de la pantalla inicial del registre TMB](wp4-preview.png)

La fletxa de la capçalera obre el resum dels registres desats al dispositiu:

![Pestanya de registres oberta des de la fletxa](wp4-requests-preview.png)

En aquesta captura els dos registres apareixen com a pendents perquè l’API encara
no està connectada. Quan l’enviament estigui integrat, aquesta vista també podrà
indicar quins registres s’han enviat correctament.

## Àrea TMB: registre per part dels operaris

La primera part de l’aplicació està pensada per als operaris de TMB que registren
objectes trobats al final de la jornada. El flux permet:

- Identificar el vehicle amb NFC o, per a proves, introduir-ne manualment la línia i
	l’identificador.
- Fer i revisar dues fotografies de l’objecte.
- Extreure automàticament els camps de la foto principal amb Qwen/Ollama.
- Revisar un o més colors, el tipus d’objecte, el material i la descripció.
- Afegir una descripció opcional de fins a 250 caràcters.
- Revisar les dades i desar el registre al dispositiu si no hi ha connexió.
- Consultar un resum dels registres guardats i saber si estan pendents o s’han enviat.

El client disposa d’un backend local de proves que serveix la UI, crida Ollama i
desa registres en aquest equip. Si no respon, els registres queden a la cua del
navegador. No és encara una API de producció ni un servei de TMB.

## Pestanya «Soc usuari»: declarar un objecte perdut

La interfície ara inclou una pestanya separada per a les persones que han perdut un
objecte. El formulari permet descriure’l (fins a 500 caràcters), indicar la línia,
autobús o estació i la data de pèrdua, seleccionar tipus i diversos colors, afegir una foto de
referència opcional i proporcionar nom, correu electrònic i telèfon opcional.

Les declaracions s’emmagatzemen localment sota la clau
`tmb-lost-found-citizen-reports`, separada de la cua i l’historial dels operaris.
No s’envien a TMB ni es comparteixen amb altres dispositius. Aquesta és només una
persistència de prototip: no s’hi han d’introduir dades personals reals fins que
existeixi una API segura i una política de privacitat definida.

La pestanya de clients és actualment un formulari de declaració local; no fa cerques
ni mostra coincidències.

## Evolució prevista: cerca i coincidències

En una fase posterior, la declaració del client s’hauria d’enviar al backend perquè
es pugui connectar amb els components de cerca del projecte i mostrar possibles
coincidències. Cal acordar amb els equips de backend i cerca el contracte de dades,
la manera de presentar resultats i com es gestionaran les fotografies aportades.

La cerca de coincidències per a reclamants continua pendent; la connexió actual
implementa l’extracció i el desament dels registres dels operaris.

## Tecnologies i execució

El client actual utilitza HTML, CSS i JavaScript sense dependències externes. La
separació en fitxers manté la interfície independent de les integracions:

- `index.html`: pantalles i formularis del flux actual.
- `app.js`: lògica d’interfície i adaptadors per a NFC, cua local i API.
- `styles.css`: estils responsive i colors de la interfície.
- `manifest.webmanifest`: configuració per instal·lar el client com a PWA.

Per executar la UI **connectada**, des de l’arrel del repositori:

```bash
python -m pip install -r search/requirements.txt
ollama pull qwen3-vl:2b-instruct
# Inicia ollama serve en una altra terminal si no està actiu.
python -m backend.server --port 8001
```

Obre **http://127.0.0.1:8001**. No utilitzis `python -m http.server` per provar
l’extracció: només serveix fitxers i no implementa l’API. Si havies configurat
`tmb_api_base_url` al navegador, elimina aquest valor per utilitzar el servidor local
que serveix la pàgina. La UI i l’API han de compartir origen en aquesta versió.

1. Identifica el vehicle i afegeix les dues fotografies.
2. Entra a **Detalls**: la foto principal s’envia automàticament a Ollama.
3. El backend valida el JSON i retorna `colors`, `objectType`, `material`,
   `description`, en l’ordre del formulari. El client assigna per nom de camp.
4. Revisa els camps. Pots marcar diversos colors. Els canvis manuals fets durant
   l’extracció es conserven. Si falla, completa els camps manualment o reintenta.
5. Marca **He revisat i corregit els camps**, revisa el resum i desa el registre.

La segona fotografia s’adjunta al registre però no s’utilitza encara per inferir
atributs. La fusió de dues perspectives continua com a implementació futura.
Les opcions dels camps es comparteixen a `form-options.json`: són etiquetes
literals del prototip, sense capa de traducció. Els registres nous guarden
`details.colors` com una llista; l’historial també llegeix l’antic `details.color`.
Els colors de les declaracions ciutadanes es guarden a `filters.colors`.

El model identifica primer el nom lliure de l’objecte i després el backend el
relaciona amb una categoria. Hi ha opcions per a ampolles i paraigües. Un objecte
sense categoria conserva el nom a la descripció i queda com `Altres`. El nom i els
trets es generen en anglès; les etiquetes del formulari continuen sent placeholders.
La UI mostra el nom reconegut i avisos sobre camps desconeguts o contradiccions.
Un material incert o contradictori queda buit perquè el revisis. Un resultat sense
avisos també pot ser incorrecte. La foto completa continua sent l’entrada habitual;
els recortes es comparen separadament al [benchmark](../search/benchmarks/README.md).

Les extraccions es guarden separades dels camps revisats. El servidor desa dades a
`artifacts/wp4/` per defecte; `--data-dir` permet utilitzar una altra carpeta.
Reintentar el mateix ID i contingut no duplica registres; un ID amb contingut
diferent produeix un conflicte. «Enviada» a l’historial indica recepció pel servidor
local, no una entrega real a TMB. Consulta [backend/README.md](../backend/README.md).

En un mòbil, la càmera i Web NFC requereixen una
connexió HTTPS, excepte quan s’executa a `localhost`. El vehicle manual permet provar
el flux sense un tag NFC.

## Integracions pendents

- Evolucionar l’API local a una API de producció amb autenticació i PostgreSQL.
- Acordar el format dels tags NFC. La lectura actual accepta provisionalment text
	JSON (`{"line":"H12","vehicle":"3421"}`) o el número de sèrie del tag.
- Definir el contracte de cerca i la presentació de coincidències amb l’equip de
	cerca abans d’implementar el flux per a reclamants.
- La revisió de les fotografies és manual. La detecció automàtica de fotos fosques o
	borroses encara no està implementada.
- La cua offline desa les imatges al navegador; per a ús real cal valorar una
	persistència més adequada per a fitxers grans i la sincronització en segon pla.
