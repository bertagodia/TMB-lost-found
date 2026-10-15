const $ = selector => document.querySelector(selector);
const matchApi = {
  async request(payload) {
    const response = await fetch('/api/matches', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Local-Token': document.querySelector('meta[name="local-token"]').content
      },
      body: JSON.stringify(payload)
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `L’API ha respost amb ${response.status}.`);
    return result;
  }
};

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function formatDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? 'Data no disponible'
    : new Intl.DateTimeFormat('ca-ES', { dateStyle: 'medium' }).format(date);
}

function daysSince(dateValue) {
  const date = new Date(dateValue);
  if (Number.isNaN(date.getTime())) return '—';
  const start = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return `${Math.max(0, Math.floor((today - start) / 86400000))} dies`;
}

function fact(label, value) {
  const wrapper = element('div', 'match-fact');
  wrapper.append(element('dt', '', label), element('dd', '', value || '—'));
  return wrapper;
}

function matchStatus(match) {
  if (match.returned_at) return { label: 'Retornat', className: 'returned' };
  if (match.destination) return { label: 'Enviat', className: 'sent' };
  return { label: 'Match confirmat', className: 'matched' };
}

function render(data) {
  const form = $('#newMatchForm');
  const objectSelect = form.elements.objectId;
  const reportSelect = form.elements.reportId;
  objectSelect.replaceChildren(new Option('Tria un objecte trobat', ''));
  reportSelect.replaceChildren(new Option('Tria una declaració', ''));
  for (const item of data.objects) {
    objectSelect.add(new Option(`${item.object_type || 'Objecte'} · ${item.description}`, item.id));
  }
  for (const item of data.reports) {
    reportSelect.add(new Option(`${item.original_description} · ${formatDate(item.lost_date)}`, item.id));
  }
  const canLink = data.objects.length > 0 && data.reports.length > 0;
  objectSelect.disabled = !data.objects.length;
  reportSelect.disabled = !data.reports.length;
  form.querySelector('button[type="submit"]').disabled = !canLink;

  const list = $('#matchList');
  list.replaceChildren();
  const sentCount = data.matches.filter(item => item.destination).length;
  $('#matchSummary').textContent =
    `${data.matches.length} coincidències confirmades · ${sentCount} enviaments registrats`;
  $('#emptyMatch').hidden = data.matches.length > 0;

  for (const match of data.matches) {
    const status = matchStatus(match);
    const card = element('article', 'match-card');
    card.dataset.status = status.className;
    const heading = element('div', 'match-card-heading');
    const title = element('div');
    title.append(
      element('p', 'section-kicker', match.object_type || 'Objecte'),
      element('h3', '', match.description || 'Descripció no disponible')
    );
    heading.append(title, element('span', `match-status ${status.className}`, status.label));
    card.append(heading);

    const facts = element('dl', 'match-facts');
    facts.append(
      fact('Referència de l’objecte', match.object_id),
      fact('Dies des de l’entrada', daysSince(match.received_at || match.object_created_at)),
      fact('Trobat el', formatDate(match.object_created_at)),
      fact('On s’ha trobat', match.found_location),
      fact('On s’envia', match.destination || 'Encara no s’ha enviat'),
      fact('Enviat el', formatDate(match.sent_at)),
      fact('Retornat el', formatDate(match.returned_at))
    );
    card.append(facts);

    const report = element('section', 'match-linked-report');
    report.append(
      element('strong', '', 'Declaració vinculada'),
      element('p', '', match.report_description),
      element('small', '', `Pèrdua: ${formatDate(match.lost_date)} · ${match.location_text || 'Lloc no indicat'}`)
    );
    const contact = element('dl', 'match-contact-details');
    for (const [label, value] of [
      ['Nom', match.contact_name],
      ['Correu electrònic', match.contact_email],
      ['Telèfon', match.contact_phone]
    ]) {
      contact.append(element('dt', '', label), element('dd', '', value || 'No indicat'));
    }
    report.append(element('strong', '', 'Contacte del sol·licitant'), contact);
    card.append(report);

    const controls = element('div', 'match-controls');
    const locationForm = element('form', 'match-location-form');
    locationForm.dataset.objectId = match.object_id;
    locationForm.dataset.reportId = match.report_id;
    const foundLabel = element('label', '', 'On s’ha trobat');
    const foundInput = element('input');
    foundInput.name = 'foundLocation';
    foundInput.maxLength = 160;
    foundInput.required = true;
    foundInput.value = match.found_location || '';
    foundLabel.append(foundInput);
    const destinationLabel = element('label', '', 'On s’envia / ubicació actual');
    const destinationInput = element('input');
    destinationInput.name = 'destination';
    destinationInput.maxLength = 160;
    destinationInput.placeholder = 'Encara no enviat';
    destinationInput.value = match.destination || '';
    destinationLabel.append(destinationInput);
    const saveButton = element('button', 'secondary-button', 'Desar ubicacions');
    saveButton.type = 'submit';
    locationForm.append(foundLabel, destinationLabel, saveButton);
    controls.append(locationForm);

    for (const [action, label] of [
      [match.returned_at ? 'reopen' : 'return', match.returned_at ? 'Reobrir seguiment' : 'Marcar com a retornat'],
      ['unlink', 'Treure aquesta coincidència']
    ]) {
      if (action === 'return' && !match.destination) continue;
      const button = element('button', 'secondary-button', label);
      button.type = 'button';
      button.dataset.action = action;
      button.dataset.objectId = match.object_id;
      button.dataset.reportId = match.report_id;
      controls.append(button);
    }
    card.append(controls);
    list.append(card);
  }
}

async function loadMatches() {
  const feedback = $('#matchFeedback');
  $('#refreshMatches').disabled = true;
  feedback.textContent = 'Carregant dades del servidor…';
  try {
    render(await matchApi.request({ action: 'list' }));
    feedback.textContent = '';
  } catch (error) {
    feedback.textContent = `No s’han pogut carregar les coincidències: ${error.message}`;
  } finally {
    $('#refreshMatches').disabled = false;
  }
}

async function perform(action, values) {
  const feedback = $('#matchFeedback');
  try {
    await matchApi.request({ action, ...values });
    feedback.textContent = 'Canvis desats al servidor.';
    await loadMatches();
  } catch (error) {
    feedback.textContent = `No s’ha pogut completar l’acció: ${error.message}`;
  }
}

$('#matchTab').addEventListener('click', loadMatches);
$('#refreshMatches').addEventListener('click', loadMatches);
$('#newMatchForm').addEventListener('submit', event => {
  event.preventDefault();
  const values = new FormData(event.currentTarget);
  perform('link', { objectId: values.get('objectId'), reportId: values.get('reportId') });
});
$('#matchList').addEventListener('submit', event => {
  if (!event.target.matches('.match-location-form')) return;
  event.preventDefault();
  const values = new FormData(event.target);
  perform('update', {
    objectId: event.target.dataset.objectId,
    reportId: event.target.dataset.reportId,
    foundLocation: values.get('foundLocation'),
    destination: values.get('destination')
  });
});
$('#matchList').addEventListener('click', event => {
  const button = event.target.closest('button[data-action]');
  if (!button) return;
  perform(button.dataset.action, {
    objectId: button.dataset.objectId,
    reportId: button.dataset.reportId
  });
});
