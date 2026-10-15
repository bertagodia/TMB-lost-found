const assignments = await fetch('origin-options.json').then(response => {if (!response.ok) throw new Error('No es poden carregar els orígens');return response.json();});
const stationAssignments=assignments.station, depotAssignments=assignments.depot;
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
locationSelect.addEventListener('change', updateDestination);
window.addEventListener('tmb:registration-reset', () => {
  updateOriginKind('station');
});

updateOriginKind(kindInput.value);
