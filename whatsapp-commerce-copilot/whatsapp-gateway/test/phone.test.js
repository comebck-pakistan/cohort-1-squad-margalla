const test = require('node:test');
const assert = require('node:assert/strict');
const { normalizePhoneNumber } = require('../src/phone');

test('normalizes formatted numbers to digits only', () => {
  assert.deepEqual(normalizePhoneNumber('+92 300-1234567'), { ok: true, digits: '923001234567' });
  assert.deepEqual(normalizePhoneNumber('(+92) 300 1234567'), { ok: true, digits: '923001234567' });
  assert.deepEqual(normalizePhoneNumber('923001234567'), { ok: true, digits: '923001234567' });
  assert.deepEqual(normalizePhoneNumber('  923001234567  '), { ok: true, digits: '923001234567' });
});

test('rejects letters and unsupported characters', () => {
  assert.equal(normalizePhoneNumber('92abc1234567').ok, false);
  assert.equal(normalizePhoneNumber('92300$1234').ok, false);
  assert.equal(normalizePhoneNumber('92.300.1234567').ok, false);
});

test('rejects too-short and too-long numbers', () => {
  assert.equal(normalizePhoneNumber('1234567').ok, false); // 7 digits
  assert.equal(normalizePhoneNumber('1234567890123456').ok, false); // 16 digits
  assert.equal(normalizePhoneNumber('12345678').ok, true); // 8 digits (min)
  assert.equal(normalizePhoneNumber('123456789012345').ok, true); // 15 digits (max)
});

test('treats empty/None as no phone provided', () => {
  assert.equal(normalizePhoneNumber('').ok, false);
  assert.equal(normalizePhoneNumber('   ').ok, false);
  assert.equal(normalizePhoneNumber(null).ok, false);
  assert.equal(normalizePhoneNumber(undefined).ok, false);
});
