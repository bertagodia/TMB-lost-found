const stationAssignments = Object.fromEntries(
  [
    [
      'La Sagrera',
      `Alfons X
Arc de Triomf
Artigues | Sant Adrià
Bac de Roda
Badalona Pompeu Fabra
Barceloneta
Baró de Viver
Besòs
Besòs Mar
Bogatell
Bon Pastor
Camp de l'Arpa
Can Cuiàs
Can Peixauet
Can Zam
Casa de l'Aigua
Ciutadella | Vila Olímpica
Ciutat Meridiana
Clot
Congrés
El Carmel
El Coll | La Teixonera
El Maresme | Fòrum
Encants
Església Major
Fabra i Puig
Fondo
Girona
Glòries
Gorg
Guinardó | Hospital de Sant Pau
Horta
Jaume I
Joanic
La Pau
La Sagrera
La Salut
Llacuna
Llefià
Llucmajor
Maragall
Marina
Monumental
Navas
Onze de Setembre
Pep Ventura
Poblenou
Sagrada Família
Sant Andreu
Sant Antoni
Sant Genís
Sant Martí
Sant Pau | Dos de Maig
Sant Roc
Santa Coloma
Santa Rosa
Selva de Mar
Singuerlín
Tetuan
Torras i Bages
Torre Baró | Vallbona
Trinitat Nova
Trinitat Vella
Urquinaona
Verdaguer
Verneda
Via Júlia
Vilapicina
Virrei Amat`,
    ],
    [
      'Espanya',
      `Aeroport T1
Aeroport T2
Av. Carrilet
Badal
Bellvitge
Can Boixeres
Can Serra
Can Tries | Gornal
Can Vidalet
Cèntric
Ciutat de la Justícia
Collblanc
Cornellà Centre
El Prat Estació
Entença
Espanya
Europa | Fira
Fira
Florida
Foc
Foneria
Gavarra
Hospital Clínic
Hospital de Bellvitge
Hostafrancs
Les Moreres
Mas Blau
Mercabarna
Mercat Nou
Paral·lel
Parc de Montjuïc
Parc Logístic
Parc Nou
Plaça de Sants
Port Comercial | La Factoria
Provençana
Pubilla Cases
Rambla Just Oliveras
Rocafort
Sant Ildefons
Santa Eulàlia
Sants Estació
Torrassa
Universitat
Urgell
ZAL | Riu Vell
Zona Franca
Zona Universitària`,
    ],
    [
      'Diagonal',
      `Canyelles
Catalunya
Diagonal
Drassanes
Fontana
Les Corts
Lesseps
Liceu
Maria Cristina
Montbau
Mundet
Palau Reial
Passeig de Gràcia
Penitents
Plaça del Centre
Poble Sec
Roquetes
Tarragona
Vall d'Hebron
Vallcarca
Valldaura`,
    ],
  ].flatMap(([central, names]) =>
    names.split('\n').map((name) => [name, central]),
  ),
);

const depotAssignments = {
  'Santa Eulàlia': 'Espanya',
  'Triangle Ferroviari (La Sagrera)': 'La Sagrera',
  'Sant Genís': 'Diagonal',
  'Trinitat Nova': 'La Sagrera',
  'Can Boixeres': 'Espanya',
  Vilapicina: 'La Sagrera',
  'Can Zam': 'La Sagrera',
  'Zona Franca': 'Espanya',
  'Funicular de Montjuïc (sense cotxera)': 'Espanya',
};

const locationSelect = document.querySelector('#originLocation');
const kindInput = document.querySelector('#originKind');
const destinationInput = document.querySelector('#originDestination');
const locationLabel = document.querySelector('#originLocationLabel');
const assignmentLabel = document.querySelector('#originAssignment');
const originPanel = document.querySelector('#originPanel');
const originTabs = [...document.querySelectorAll('.origin-tab')];

function updateOriginKind(kind) {
  const isStation = kind === 'station';
  const assignments = isStation ? stationAssignments : depotAssignments;
  const label = isStation ? 'Estació' : 'Cotxera';
  kindInput.value = kind;
  locationLabel.textContent = label;
  locationSelect.replaceChildren(new Option(`Selecciona ${label.toLowerCase()}`, ''));
  for (const name of Object.keys(assignments)) {
    locationSelect.add(new Option(name, name));
  }
  destinationInput.value = '';
  assignmentLabel.textContent = 'La central de destinació es mostrarà en seleccionar l’origen.';
  assignmentLabel.classList.remove('assigned');
  originTabs.forEach((tab) => {
    const selected = tab.dataset.originKind === kind;
    tab.classList.toggle('active', selected);
    tab.setAttribute('aria-selected', String(selected));
  });
  originPanel.setAttribute(
    'aria-labelledby',
    isStation ? 'stationOriginTab' : 'depotOriginTab',
  );
}

function updateDestination() {
  const assignments = kindInput.value === 'station' ? stationAssignments : depotAssignments;
  const destination = assignments[locationSelect.value];
  destinationInput.value = destination || '';
  assignmentLabel.classList.toggle('assigned', Boolean(destination));
  assignmentLabel.textContent = destination
    ? `Etiqueta assignada automàticament: ${destination}`
    : locationSelect.value
      ? 'No s’ha trobat una estació central per a aquest origen.'
      : 'La central de destinació es mostrarà en seleccionar l’origen.';
}

originTabs.forEach((tab) => {
  tab.addEventListener('click', () => updateOriginKind(tab.dataset.originKind));
});
locationSelect.addEventListener('change', () => {
  updateDestination();
  if (
    kindInput.value === 'station' &&
    document.querySelector('#metroTab').classList.contains('active')
  ) {
    const stationInput = document.querySelector('#manualVehicle');
    stationInput.value = locationSelect.value;
    stationInput.dispatchEvent(new Event('input', { bubbles: true }));
  }
});
document.querySelector('#metroTab').addEventListener('click', () => {
  if (kindInput.value === 'station' && locationSelect.value) {
    const stationInput = document.querySelector('#manualVehicle');
    stationInput.value = locationSelect.value;
    stationInput.dispatchEvent(new Event('input', { bubbles: true }));
  }
});
window.addEventListener('tmb:registration-reset', () => {
  updateOriginKind('station');
});

updateOriginKind(kindInput.value);
