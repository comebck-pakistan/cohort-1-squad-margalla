const test = require('node:test');
const assert = require('node:assert/strict');
const {
  getSkipReason,
  normalizeCustomerNumber,
  mapConnectionState,
} = require('../src/webhook-handler');

test('filters group, broadcast, protocol, history, and stale traffic', () => {
  const now = Math.floor(Date.now() / 1000);
  assert.equal(getSkipReason({ key: { remoteJid: '123@g.us' } }, now), 'group');
  assert.equal(getSkipReason({ key: { remoteJid: 'status@broadcast' } }, now), 'broadcast');
  assert.equal(getSkipReason({
    key: { remoteJid: '923001234567@s.whatsapp.net' },
    type: 'append',
  }, now), 'history_sync');
  assert.equal(getSkipReason({
    key: { remoteJid: '923001234567@s.whatsapp.net' },
    message: { reactionMessage: {} },
  }, now), 'protocol_or_reaction');
  assert.equal(getSkipReason({
    key: { remoteJid: '923001234567@s.whatsapp.net' },
    messageTimestamp: now - 1000,
  }, now), 'stale');
});

test('accepts recent direct messages', () => {
  const now = Math.floor(Date.now() / 1000);
  assert.equal(getSkipReason({
    key: { remoteJid: '923001234567@s.whatsapp.net' },
    messageTimestamp: now,
    message: { conversation: 'hello' },
  }, now), null);
});

test('normalizes phone identity and prefers remoteJidAlt for LIDs', () => {
  assert.equal(normalizeCustomerNumber({
    key: {
      remoteJid: '12345@lid',
      remoteJidAlt: '923001234567@s.whatsapp.net',
    },
  }), '923001234567');
  assert.equal(normalizeCustomerNumber({
    key: { remoteJid: '923111111111@c.us' },
  }), '923111111111');
  assert.equal(normalizeCustomerNumber({
    key: { remoteJid: '12345@lid' },
  }), null);
});

test('maps Evolution connection states', () => {
  assert.equal(mapConnectionState('open'), 'connected');
  assert.equal(mapConnectionState('connecting'), 'initializing');
  assert.equal(mapConnectionState('close'), 'disconnected');
});
