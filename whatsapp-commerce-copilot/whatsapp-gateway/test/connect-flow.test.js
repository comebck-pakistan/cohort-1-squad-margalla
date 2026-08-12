const test = require('node:test');
const assert = require('node:assert/strict');
const { connectSession, waitForDeletion, extractState, isPairingFailure } = require('../src/connect-flow');
const { mapUpstreamError } = require('../src/upstream-error');

// Build a fake Evolution client that records which methods were called.
function makeClient(overrides = {}) {
  const calls = [];
  const record = (name) => (...args) => {
    calls.push({ name, args });
    const impl = overrides[name];
    if (typeof impl === 'function') return impl(...args);
    return Promise.resolve(impl);
  };
  return {
    calls,
    fetchInstance: record('fetchInstance'),
    getConnectionState: record('getConnectionState'),
    connectInstance: record('connectInstance'),
    deleteInstance: record('deleteInstance'),
    createInstance: record('createInstance'),
  };
}

const named = (calls) => calls.map((c) => c.name);

// ── Existing tests preserved ──────────────────────────────────────────

test('invalid phone returns 400 and never touches any instance', async () => {
  const client = makeClient();
  const res = await connectSession({ evolutionClient: client, storeId: 's1', phoneNumber: '92abc' });

  assert.equal(res.status, 400);
  assert.equal(res.body.error, 'invalid_phone_number');
  // No instance operations at all — validation happens first.
  assert.deepEqual(client.calls, []);
});

test('invalid phone never calls deleteInstance or createInstance', async () => {
  const client = makeClient({ fetchInstance: { name: 's1' } });
  const res = await connectSession({ evolutionClient: client, storeId: 's1', phoneNumber: '123' });

  assert.equal(res.status, 400);
  assert.ok(!named(client.calls).includes('deleteInstance'));
  assert.ok(!named(client.calls).includes('createInstance'));
  assert.ok(!named(client.calls).includes('fetchInstance'));
});

test('normalized digits reach Evolution createInstance', async () => {
  let received;
  const client = makeClient({
    fetchInstance: null, // no existing instance
    createInstance: (storeId, number) => {
      received = number;
      return { qrcode: { pairingCode: 'ABCD1234' } };
    },
    // After create, connection state is 'connecting' — code is valid
    getConnectionState: { instance: { state: 'connecting' } },
  });
  const res = await connectSession({
    evolutionClient: client,
    storeId: 's1',
    phoneNumber: '+92 300-1234567',
    recreateDelayMs: 0,
  });

  assert.equal(received, '923001234567');
  assert.equal(res.status, 200);
  assert.equal(res.body.pairing_code, 'ABCD1234');
});

test('QR mode (no phone) creates instance without a number', async () => {
  let received = 'UNSET';
  const client = makeClient({
    fetchInstance: null,
    createInstance: (storeId, number) => {
      received = number;
      return { qrcode: { base64: 'data:image/png;base64,QR' } };
    },
  });
  const res = await connectSession({ evolutionClient: client, storeId: 's1' });

  assert.equal(received, null);
  assert.equal(res.status, 200);
  assert.equal(res.body.qr_code, 'data:image/png;base64,QR');
});

test('never deletes an already-open instance in phone mode', async () => {
  const client = makeClient({
    fetchInstance: { name: 's1' },
    getConnectionState: { instance: { state: 'open' } },
  });
  const res = await connectSession({
    evolutionClient: client,
    storeId: 's1',
    phoneNumber: '923001234567',
    recreateDelayMs: 0,
  });

  assert.equal(res.status, 200);
  assert.equal(res.body.status, 'connected');
  assert.ok(!named(client.calls).includes('deleteInstance'));
  assert.ok(!named(client.calls).includes('createInstance'));
});

test('validation occurs before instance lookup', async () => {
  const client = makeClient({ fetchInstance: { name: 's1' } });
  await connectSession({ evolutionClient: client, storeId: 's1', phoneNumber: 'bad!' });
  // fetchInstance must not have run at all.
  assert.equal(client.calls.length, 0);
});

test('Evolution 400 maps to gateway 400', async () => {
  const err = new Error('Request failed');
  err.response = { status: 400, data: { message: 'raw evolution data' } };
  const client = makeClient({
    fetchInstance: null,
    createInstance: () => { throw err; },
  });
  const res = await connectSession({ evolutionClient: client, storeId: 's1', phoneNumber: '923001234567', recreateDelayMs: 0 });
  assert.equal(res.status, 400);
});

test('timeout maps to gateway 504', () => {
  const err = new Error('timeout of 30000ms exceeded');
  err.code = 'ECONNABORTED';
  assert.equal(mapUpstreamError(err).status, 504);
});

test('unexpected upstream error maps to gateway 502', () => {
  const err = new Error('socket hang up');
  assert.equal(mapUpstreamError(err).status, 502);
});

test('error responses never leak the phone number or raw Evolution data', async () => {
  const err = new Error('boom');
  err.response = { status: 500, data: { secret: 'RAW_EVOLUTION_BODY', apikey: 'SECRET_KEY' } };
  const client = makeClient({
    fetchInstance: null,
    createInstance: () => { throw err; },
  });
  const res = await connectSession({ evolutionClient: client, storeId: 's1', phoneNumber: '923001234567', recreateDelayMs: 0, maxAttempts: 1 });
  const serialized = JSON.stringify(res.body);
  assert.ok(!serialized.includes('923001234567'));
  assert.ok(!serialized.includes('RAW_EVOLUTION_BODY'));
  assert.ok(!serialized.includes('SECRET_KEY'));
  assert.equal(res.status, 502);
});

// ── NEW: Pairing lifecycle tests ──────────────────────────────────────

test('pairing code + connecting state remains valid', async () => {
  const client = makeClient({
    fetchInstance: null,
    createInstance: () => ({ qrcode: { pairingCode: 'VALID123', base64: null } }),
    getConnectionState: { instance: { state: 'connecting' } },
  });
  const res = await connectSession({
    evolutionClient: client,
    storeId: 's1',
    phoneNumber: '923001234567',
    recreateDelayMs: 0,
  });

  assert.equal(res.status, 200);
  assert.equal(res.body.pairing_code, 'VALID123');
  assert.equal(res.body.status, 'initializing');
});

test('pairing code + immediate close/428 is invalidated and retried', async () => {
  let createCount = 0;
  const client = makeClient({
    fetchInstance: (storeId) => {
      // After first delete, instance is gone
      return createCount > 0 ? null : null;
    },
    createInstance: () => {
      createCount++;
      return { qrcode: { pairingCode: `CODE${createCount}`, base64: null } };
    },
    getConnectionState: () => {
      // First attempt: socket closed. Second attempt: connecting.
      if (createCount <= 1) return { instance: { state: 'close' } };
      return { instance: { state: 'connecting' } };
    },
    deleteInstance: () => ({}),
  });

  const res = await connectSession({
    evolutionClient: client,
    storeId: 's1',
    phoneNumber: '923001234567',
    recreateDelayMs: 0,
    maxAttempts: 3,
  });

  assert.equal(res.status, 200);
  assert.equal(res.body.pairing_code, 'CODE2'); // Second attempt's code
  assert.equal(res.body.status, 'initializing');
  assert.ok(createCount >= 2, 'Should have retried');
});

test('dead code is never returned as successful', async () => {
  const client = makeClient({
    fetchInstance: null,
    createInstance: () => ({ qrcode: { pairingCode: 'DEADCODE', base64: null } }),
    getConnectionState: { instance: { state: 'close' } }, // Always dead
    deleteInstance: () => ({}),
  });

  const res = await connectSession({
    evolutionClient: client,
    storeId: 's1',
    phoneNumber: '923001234567',
    recreateDelayMs: 0,
    maxAttempts: 2,
  });

  // Should NOT contain the dead pairing code
  assert.equal(res.body.pairing_code, null);
  assert.equal(res.body.status, 'failed');
});

test('retry limit stops after max attempts', async () => {
  let createCount = 0;
  const client = makeClient({
    fetchInstance: null,
    createInstance: () => {
      createCount++;
      return { qrcode: { pairingCode: 'DEAD', base64: null } };
    },
    getConnectionState: { instance: { state: 'close' } },
    deleteInstance: () => ({}),
  });

  await connectSession({
    evolutionClient: client,
    storeId: 's1',
    phoneNumber: '923001234567',
    recreateDelayMs: 0,
    maxAttempts: 2,
  });

  assert.equal(createCount, 2, 'Should stop after maxAttempts');
});

test('open instance is never deleted during pairing retry', async () => {
  const client = makeClient({
    fetchInstance: { name: 's1' },
    getConnectionState: { instance: { state: 'open' } },
  });

  const res = await connectSession({
    evolutionClient: client,
    storeId: 's1',
    phoneNumber: '923001234567',
    recreateDelayMs: 0,
  });

  assert.equal(res.body.status, 'connected');
  assert.ok(!named(client.calls).includes('deleteInstance'));
});

test('connected event during pairing returns connected status with no code', async () => {
  const client = makeClient({
    fetchInstance: null,
    createInstance: () => ({ qrcode: { pairingCode: 'FAST', base64: null } }),
    getConnectionState: { instance: { state: 'open' } }, // Paired immediately
  });

  const res = await connectSession({
    evolutionClient: client,
    storeId: 's1',
    phoneNumber: '923001234567',
    recreateDelayMs: 0,
  });

  assert.equal(res.body.status, 'connected');
  assert.equal(res.body.pairing_code, null);
});

test('QR path still works after pairing infrastructure changes', async () => {
  const client = makeClient({
    fetchInstance: null,
    createInstance: (storeId, number) => {
      assert.equal(number, null, 'QR mode should not pass a number');
      return { qrcode: { base64: 'QR_DATA' } };
    },
  });

  const res = await connectSession({ evolutionClient: client, storeId: 's1' });
  assert.equal(res.status, 200);
  assert.equal(res.body.qr_code, 'QR_DATA');
  assert.equal(res.body.pairing_code, null);
});

// ── Utility function tests ────────────────────────────────────────────

test('extractState handles various response shapes', () => {
  assert.equal(extractState({ instance: { state: 'open' } }), 'open');
  assert.equal(extractState({ state: 'connecting' }), 'connecting');
  assert.equal(extractState(null), 'close');
  assert.equal(extractState({}), 'close');
});

test('isPairingFailure detects 428 and 515 errors', () => {
  const err428 = new Error('test');
  err428.response = { status: 428 };
  assert.ok(isPairingFailure(err428));

  const err515 = new Error('stream:error code 515');
  assert.ok(isPairingFailure(err515));

  const errClosed = new Error('Connection Closed');
  assert.ok(isPairingFailure(errClosed));

  const errNormal = new Error('network timeout');
  assert.ok(!isPairingFailure(errNormal));
});
