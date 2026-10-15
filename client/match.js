const $ = selector => document.querySelector(selector);
class MatchStore {
  constructor() { this.data={records:[],reports:[]}; }
  report(id) { return this.data.reports.find(item=>item.id===id); }
  async request(action='list', values={}) {
    const response=await fetch('/api/matches',{method:'POST',headers:{'Content-Type':'application/json','X-Local-Token':document.querySelector('meta[name="local-token"]').content},body:JSON.stringify({action,...values})});
    const data=await response.json();
    if(!response.ok) throw new Error(data.error||'No s’ha pogut connectar amb el servidor.');
    this.data=data;
  }
  link(recordId,reportId) { return this.request('link',{recordId,reportId}); }
  unlink(recordId,reportId) { return this.request('unlink',{recordId,reportId}); }
  updateLocation(recordId,foundLocation,destination) { return this.request('location',{recordId,foundLocation,destination,revision:this.revision(recordId)}); }
  setReturned(recordId,returned) { return this.request(returned?'return':'reopen',{recordId,revision:this.revision(recordId)}); }
  revision(id) { return this.data.records.find(item=>item.id===id)?.revision; }
}

function daysSince(dateValue) {
  const date = new Date(dateValue);
  if (Number.isNaN(date.getTime())) return null;
  const start = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.max(0, Math.floor((today - start) / 86400000));
}

function formatDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? 'Data no disponible'
    : new Intl.DateTimeFormat('ca-ES', { dateStyle: 'medium' }).format(date);
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function fact(label, value) {
  const wrapper = element('div', 'match-fact');
  wrapper.append(element('dt', '', label), element('dd', '', value || '—'));
  return wrapper;
}

function recordStatus(record) {
  if (record.returnedAt) return { label: 'Retornat', className: 'returned' };
  if (record.destination) return { label: 'Enviat', className: 'sent' };
  return { label: 'Match confirmat', className: 'matched' };
}

function updateDayCounts() {
  document.querySelectorAll('.match-days').forEach(value => {
    const days = daysSince(value.dataset.receivedAt);
    value.textContent = `${days ?? '—'} dies`;
  });
}

function render(store) {
  const list = $('#matchList');
  list.replaceChildren();
  const records = [...store.data.records].sort((a, b) =>
    (b.receivedAt || b.foundAt).localeCompare(a.receivedAt || a.foundAt));
  const confirmedRecords = records.filter(record => record.matchedReportIds.length > 0);
  const linkedCount = confirmedRecords.reduce(
    (count, record) => count + record.matchedReportIds.length, 0
  );
  const sentCount = confirmedRecords.filter(record => record.destination).length;
  $('#matchSummary').textContent =
    `${confirmedRecords.length} objectes amb match · ${linkedCount} coincidències confirmades · ${sentCount} enviats`;
  $('#emptyMatch').hidden = confirmedRecords.length > 0;

  const matchForm = $('#newMatchForm');
  const recordSelect = matchForm.elements.recordId;
  const reportSelect = matchForm.elements.reportId;
  recordSelect.replaceChildren(new Option('Tria un objecte trobat', ''));
  reportSelect.replaceChildren(new Option('Tria una declaració', ''));
  for (const record of records) {
    recordSelect.add(new Option(`${record.object} · ${formatDate(record.receivedAt || record.foundAt)}`, record.id));
  }
  for (const report of store.data.reports) {
    reportSelect.add(new Option(`${report.object} · ${formatDate(report.lostAt)}`, report.id));
  }
  const canConfirmMatch = records.length > 0 && store.data.reports.length > 0;
  recordSelect.disabled = records.length === 0;
  reportSelect.disabled = !canConfirmMatch;
  matchForm.querySelector('button[type="submit"]').disabled = !canConfirmMatch;

  for (const record of confirmedRecords) {
    const status = recordStatus(record);
    const card = element('article', 'match-card');
    card.dataset.status = status.className;
    const heading = element('div', 'match-card-heading');
    const titleGroup = element('div');
    titleGroup.append(element('p', 'section-kicker', record.type), element('h3', '', record.object));
    heading.append(titleGroup, element('span', `match-status ${status.className}`, status.label));
    card.append(heading);

    const facts = element('dl', 'match-facts');
    const receivedAt = record.receivedAt || record.foundAt;
    const dayCount = fact('Dies des de l’entrada', `${daysSince(receivedAt) ?? '—'} dies`);
    const dayValue = dayCount.querySelector('dd');
    dayValue.className = 'match-days';
    dayValue.dataset.receivedAt = receivedAt;
    facts.append(
      fact('Trobat el', formatDate(record.foundAt)),
      fact('Entrat al servidor', formatDate(receivedAt)),
      dayCount,
      fact('Origen del registre', record.originLocation
        ? `${record.originKind === 'depot' ? 'Cotxera' : record.originKind === 'station' ? 'Estació' : 'Origen'} · ${record.originLocation}`
        : 'No indicat'),
      fact('On s’ha trobat', record.foundLocation),
      fact('Central assignada (pendent d’enviament)',record.assignedDestination),
      fact('On s’envia', record.destination || 'Encara no s’ha enviat'),
      fact('Enviat el', record.sentAt ? formatDate(record.sentAt) : '—')
    );
    card.append(facts);

    for (const reportId of record.matchedReportIds) {
      const report = store.report(reportId);
      if (!report) continue;
      const matchInfo = element('div', 'match-linked-report');
      matchInfo.append(
        element('strong', '', 'Declaració vinculada'),
        element('p', '', report.object),
        element('small', '', `Pèrdua: ${formatDate(report.lostAt)} · ${report.lostLocation || 'Lloc no indicat'}`)
      );
      const contact = report.contact || {};
      const contactDetails = element('dl', 'match-contact-details');
      for (const [label, value] of [
        ['Nom', contact.name],
        ['Correu electrònic', contact.email],
        ['Telèfon', contact.phone]
      ]) {
        contactDetails.append(element('dt', '', label), element('dd', '', value || 'No indicat'));
      }
      matchInfo.append(element('strong', '', 'Contacte del sol·licitant'), contactDetails);
      const unlinkButton = element('button', 'secondary-button', 'Treure aquesta coincidència');
      unlinkButton.type = 'button';
      unlinkButton.dataset.action = 'unlink';
      unlinkButton.dataset.recordId = record.id;
      unlinkButton.dataset.reportId = report.id;
      matchInfo.append(unlinkButton);
      card.append(matchInfo);
    }

    const controls = element('div', 'match-controls');
    const locationForm = element('form', 'match-location-form');
    locationForm.dataset.recordId = record.id;
    const foundLabel = element('label', '', 'On s’ha trobat');
    const foundInput = element('input');
    foundInput.name = 'foundLocation';
    foundInput.maxLength = 160;
    foundInput.required = true;
    foundInput.value = record.foundLocation || '';
    foundLabel.append(foundInput);
    const destinationLabel = element('label', '', 'On s’envia / ubicació actual');
    const destinationInput = element('input');
    destinationInput.name = 'destination';
    destinationInput.maxLength = 160;
    destinationInput.placeholder = 'Encara no enviat';
    destinationInput.value = record.destination || '';
    destinationLabel.append(destinationInput);
    const saveButton = element('button', 'secondary-button', 'Desar ubicacions');
    saveButton.type = 'submit';
    locationForm.append(foundLabel, destinationLabel, saveButton);
    controls.append(locationForm);

    if (record.destination) {
      const returnedButton = element(
        'button',
        'match-return-button',
        record.returnedAt ? 'Reobrir seguiment' : 'Marcar com a retornat'
      );
      returnedButton.type = 'button';
      returnedButton.dataset.action = record.returnedAt ? 'reopen' : 'return';
      returnedButton.dataset.recordId = record.id;
      controls.append(returnedButton);
    }
    card.append(controls);
    list.append(card);
  }
}

function initializeMatch() {
  let store;
  try {
    store = new MatchStore();
  } catch (error) {
    $('#matchFeedback').textContent = `No s’han pogut carregar les dades del servidor: ${error.message}`;
    return;
  }

  window.addEventListener('tmb:match-open',async()=>{
    $('#matchFeedback').textContent='Carregant…';
    try {await store.request();render(store);$('#matchFeedback').textContent='';}
    catch(error){store.data={records:[],reports:[]};render(store);$('#matchFeedback').textContent=error.message;}
  });

  $('#matchList').addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.target;
    try {
      if (form.matches('.match-location-form')) {
        const values = new FormData(form);
        await store.updateLocation(form.dataset.recordId, values.get('foundLocation'), values.get('destination'));
        $('#matchFeedback').textContent = 'Ubicacions desades al servidor.';
      } else {
        return;
      }
      render(store);
    } catch (error) {
      $('#matchFeedback').textContent = error.message;
    }
  });

  $('#newMatchForm').addEventListener('submit', async event => {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const recordId = values.get('recordId');
    const reportId = values.get('reportId');
    try {
      if (!recordId || !reportId) {
        throw new Error('Tria un objecte i una declaració abans de confirmar el match.');
      }
      await store.link(recordId, reportId);
      $('#matchFeedback').textContent = 'Coincidència confirmada manualment.';
      $('#newMatchForm').reset();
      render(store);
    } catch (error) {
      $('#matchFeedback').textContent = error.message;
    }
  });

  $('#matchList').addEventListener('click', async event => {
    const button = event.target.closest('button[data-action]');
    if (!button) return;
    try {
      if (button.dataset.action === 'unlink') {
        await store.unlink(button.dataset.recordId, button.dataset.reportId);
        $('#matchFeedback').textContent = 'Coincidència eliminada.';
      } else if (button.dataset.action === 'return') {
        await store.setReturned(button.dataset.recordId, true);
        $('#matchFeedback').textContent = 'Objecte marcat com a retornat.';
      } else if (button.dataset.action === 'reopen') {
        await store.setReturned(button.dataset.recordId, false);
        $('#matchFeedback').textContent = 'Seguiment reobert.';
      }
      render(store);
    } catch (error) {
      $('#matchFeedback').textContent = error.message;
    }
  });

  render(store);
  window.setInterval(updateDayCounts, 60000);
  document.addEventListener('visibilitychange', updateDayCounts);
}

initializeMatch();
