// Storage and delivery are separate: only a matching server receipt clears a pending item.
export function confirmReceipt(record, result) {
  if (result?.queued !== false || result.id !== record.id) {
    throw new Error('El servidor no ha confirmat el registre.');
  }
}

export async function syncPending(queue, submit, onSent = () => {}) {
  let sent = 0;
  while (queue.all().length) {
    const record = queue.all()[0];
    try {
      const result = await submit(record);
      confirmReceipt(record, result);
      onSent(record, result);
      queue.remove(record.id);
      sent++;
    } catch (error) {
      return {sent, error};
    }
  }
  return {sent, error: null};
}

export class CitizenReportStore {
  constructor(storage = localStorage, key = 'tmb-lost-found-citizen-reports') {
    this.storage = storage;
    this.key = key;
  }
  records() { return JSON.parse(this.storage.getItem(this.key) || '[]'); }
  // Older saved-local drafts require explicit migration; never upload them automatically.
  all() { return this.records().filter(report => report.status === 'pending'); }
  save(report) {
    const reports = this.records().filter(item => item.id !== report.id);
    reports.push(report);
    this.storage.setItem(this.key, JSON.stringify(reports));
  }
  remove(id) {
    this.storage.setItem(this.key, JSON.stringify(this.records().map(report =>
      report.id === id ? {...report, status: 'sent'} : report)));
  }
}
