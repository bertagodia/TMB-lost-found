const response = await fetch('./location-assignment-data.json');
if (!response.ok) throw new Error('No es poden carregar les assignacions d’estacions.');
const assignments = await response.json();

const locationSelect = document.querySelector('#originLocation');
const kindInput = document.querySelector('#originKind');
const destinationInput = document.querySelector('#originDestination');
const locationLabel = document.querySelector('#originLocationLabel');
const assignmentLabel = document.querySelector('#originAssignment');
const originPanel = document.querySelector('#originPanel');
const originTabs = [...document.querySelectorAll('.origin-tab')];

function updateOriginKind(kind) {
  const isStation = kind === 'station';
  const label = isStation ? 'Estació' : 'Cotxera';
  const locations = isStation
    ? Object.values(assignments.stations).flat()
    : Object.keys(assignments.depots);
  kindInput.value = kind;
  locationLabel.textContent = label;
  locationSelect.replaceChildren(new Option(`Selecciona ${label.toLowerCase()}`, ''));
  for (const name of locations) locationSelect.add(new Option(name, name));
  destinationInput.value = '';
  assignmentLabel.textContent = 'L’estació de destinació es mostrarà en seleccionar l’origen.';
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
  window.dispatchEvent(new Event('tmb:origin-change'));
}

function updateDestination() {
  const destination = kindInput.value === 'station'
    ? Object.entries(assignments.stations).find(([, locations]) => locations.includes(locationSelect.value))?.[0]
    : assignments.depots[locationSelect.value];
  destinationInput.value = destination || '';
  assignmentLabel.classList.toggle('assigned', Boolean(destination));
  assignmentLabel.textContent = destination
    ? `Estació de destinació assignada automàticament: ${destination}`
    : locationSelect.value
      ? 'No s’ha trobat cap estació de destinació per a aquest origen.'
      : 'L’estació de destinació es mostrarà en seleccionar l’origen.';
  window.dispatchEvent(new Event('tmb:origin-change'));
}

export function getOrigin() {
  if (!locationSelect.value || !destinationInput.value) return null;
  return {
    kind: kindInput.value,
    location: locationSelect.value,
    destination: destinationInput.value,
  };
}

originTabs.forEach((tab) => {
  tab.addEventListener('click', () => updateOriginKind(tab.dataset.originKind));
});
locationSelect.addEventListener('change', updateDestination);
window.addEventListener('tmb:registration-reset', () => updateOriginKind('station'));

updateOriginKind(kindInput.value || 'station');
