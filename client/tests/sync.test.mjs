import assert from 'node:assert/strict';
import test from 'node:test';
import {CitizenReportStore, syncPending} from '../sync.mjs';

function storage() {
  const values = new Map();
  return {getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value)};
}

test('citizen reports survive an outage and reload, then acknowledge an idempotent retry', async () => {
  const disk = storage();
  const queue = new CitizenReportStore(disk);
  queue.save({id: 'citizen-1', status: 'pending', contact: {email: 'test@example.invalid'}});
  const offline = await syncPending(queue, async () => { throw new Error('offline'); });
  assert.equal(offline.sent, 0);
  const reloaded = new CitizenReportStore(disk);
  assert.equal(reloaded.all()[0].id, 'citizen-1');
  const received = [];
  const online = await syncPending(reloaded, async record => {
    received.push(record.id);
    return {id: record.id, queued: false, duplicate: true};
  });
  assert.equal(online.sent, 1);
  assert.deepEqual(received, ['citizen-1']);
  assert.equal(reloaded.all().length, 0);
  assert.equal(reloaded.records()[0].status, 'sent');
});

test('an unconfirmed or mismatched receipt never removes a pending item', async () => {
  for (const receipt of [{}, {id: 'other', queued: false}, {id: 'a', queued: true}]) {
    const queue = new CitizenReportStore(storage());
    queue.save({id: 'a', status: 'pending'});
    const result = await syncPending(queue, async () => receipt);
    assert.equal(result.sent, 0);
    assert.equal(queue.all().length, 1);
  }
});

test('operator queue keeps its stable IDs and stops at a failed submission', async () => {
  const records = [{id: 'operator-1'}, {id: 'operator-2'}];
  const queue = {all: () => records, remove: id => records.splice(records.findIndex(r => r.id === id), 1)};
  const history = [];
  const first = await syncPending(queue, async record => {
    if (record.id === 'operator-2') throw new Error('database down');
    return {id: record.id, queued: false};
  }, record => history.push(record.id));
  assert.equal(first.sent, 1);
  assert.deepEqual(records, [{id: 'operator-2'}]);
  const retried = await syncPending(queue, async record => ({id: record.id, queued: false}), record => history.push(record.id));
  assert.equal(retried.sent, 1);
  assert.deepEqual(history, ['operator-1', 'operator-2']);
});

test('old citizen drafts are not automatically imported into PostgreSQL', async () => {
  const queue = new CitizenReportStore(storage());
  queue.save({id: 'old', status: 'saved-local'});
  queue.save({id: 'new', status: 'pending'});
  const submitted = [];
  await syncPending(queue, async record => {
    submitted.push(record.id);
    return {id: record.id, queued: false};
  });
  assert.deepEqual(submitted, ['new']);
  assert.equal(queue.records().find(record => record.id === 'old').status, 'saved-local');
});

test('new reports arriving during synchronization are delivered without another online event', async () => {
  const queue = new CitizenReportStore(storage());
  queue.save({id: 'first', status: 'pending'});
  const result = await syncPending(queue, async record => {
    if (record.id === 'first') queue.save({id: 'second', status: 'pending'});
    return {id: record.id, queued: false};
  });
  assert.equal(result.sent, 2);
  assert.equal(queue.all().length, 0);
});

test('storage failures preserve the pending record for a later idempotent retry', async () => {
  const disk = storage();
  const queue = new CitizenReportStore(disk);
  queue.save({id: 'a', status: 'pending'});
  disk.setItem = () => { throw new Error('quota'); };
  const result = await syncPending(queue, async record => ({id: record.id, queued: false}));
  assert.equal(result.sent, 0);
  assert.equal(queue.all()[0].id, 'a');
});
