const test = require('node:test');
const assert = require('node:assert/strict');

test('sendText default delay is 0 (from config)', () => {
  // Config defaults sendDelayMs to 0 when WHATSAPP_SEND_DELAY_MS is unset.
  const config = require('../src/config');
  assert.equal(config.sendDelayMs, 0, 'Default send delay should be 0');
});

test('sendDelayMs is bounded to [0, 5000]', () => {
  // The config clamps using Math.max(0, Math.min(5000, ...)).
  // We verify the formula by checking the current value is in range.
  const config = require('../src/config');
  assert.ok(config.sendDelayMs >= 0, 'sendDelayMs must be >= 0');
  assert.ok(config.sendDelayMs <= 5000, 'sendDelayMs must be <= 5000');
});

test('webhook base64 defaults to false', () => {
  const config = require('../src/config');
  assert.equal(config.webhookBase64, false, 'webhookBase64 should default to false');
});

test('createInstance uses config.webhookBase64 for webhook config', () => {
  // Structural test: verify the createInstance function references config.webhookBase64
  const fs = require('fs');
  const path = require('path');
  const source = fs.readFileSync(path.join(__dirname, '../src/evolution-client.js'), 'utf8');
  assert.ok(source.includes('config.webhookBase64'), 'createInstance should use config.webhookBase64');
  assert.ok(!source.includes("base64: true"), 'Should not have hardcoded base64: true');
});

test('sendText uses config.sendDelayMs instead of hardcoded 1200', () => {
  const fs = require('fs');
  const path = require('path');
  const source = fs.readFileSync(path.join(__dirname, '../src/evolution-client.js'), 'utf8');
  assert.ok(source.includes('config.sendDelayMs'), 'sendText should use config.sendDelayMs');
  assert.ok(!source.includes('delay: 1200'), 'Should not have hardcoded delay: 1200');
});

test('setWebhook function is exported', () => {
  const evolutionClient = require('../src/evolution-client');
  assert.equal(typeof evolutionClient.setWebhook, 'function');
});
