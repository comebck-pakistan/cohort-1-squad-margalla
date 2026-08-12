/**
 * Phone-number normalization for WhatsApp linking.
 *
 * Rules (kept identical to the backend and dashboard implementations):
 *   - Trim whitespace.
 *   - Remove a single optional leading "+".
 *   - Remove spaces, hyphens, and parentheses.
 *   - The remaining value must be digits only (letters/others rejected).
 *   - Require 8-15 digits (international number with country code).
 *   - Never auto-add a country code.
 *
 * @param {string} raw
 * @returns {{ ok: boolean, digits?: string, error?: string }}
 */
function normalizePhoneNumber(raw) {
  if (raw === null || raw === undefined) return { ok: false, error: 'empty' };
  const s = String(raw).trim();
  if (s === '') return { ok: false, error: 'empty' };
  // Remove separators first, then a single leading "+" (handles "(+92) 300...").
  let stripped = s.replace(/[\s()\-]/g, '');
  if (stripped.startsWith('+')) stripped = stripped.slice(1);
  if (!/^[0-9]+$/.test(stripped)) return { ok: false, error: 'invalid_chars' };
  if (stripped.length < 8 || stripped.length > 15) return { ok: false, error: 'invalid_length' };
  return { ok: true, digits: stripped };
}

module.exports = { normalizePhoneNumber };
