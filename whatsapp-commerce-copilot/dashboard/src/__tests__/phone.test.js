import { describe, it, expect } from 'vitest';
import { normalizePhoneNumber } from '../phone';

describe('normalizePhoneNumber', () => {
  it('normalizes formatted numbers to digits only', () => {
    expect(normalizePhoneNumber('+92 300-1234567')).toEqual({ ok: true, digits: '923001234567' });
    expect(normalizePhoneNumber('(+92) 300 1234567')).toEqual({ ok: true, digits: '923001234567' });
    expect(normalizePhoneNumber('923001234567')).toEqual({ ok: true, digits: '923001234567' });
  });

  it('rejects letters and unsupported characters', () => {
    expect(normalizePhoneNumber('92abc1234567').ok).toBe(false);
    expect(normalizePhoneNumber('92.300.1234567').ok).toBe(false);
  });

  it('rejects too-short and too-long numbers', () => {
    expect(normalizePhoneNumber('1234567').ok).toBe(false);
    expect(normalizePhoneNumber('1234567890123456').ok).toBe(false);
    expect(normalizePhoneNumber('12345678').ok).toBe(true);
    expect(normalizePhoneNumber('123456789012345').ok).toBe(true);
  });

  it('treats empty input as not-ok', () => {
    expect(normalizePhoneNumber('').ok).toBe(false);
    expect(normalizePhoneNumber('   ').ok).toBe(false);
    expect(normalizePhoneNumber(null).ok).toBe(false);
  });
});
