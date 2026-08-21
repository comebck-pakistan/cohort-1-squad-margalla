/**
 * Display formatting helpers for the merchant dashboard.
 *
 * Kept out of the component files so they can be unit-tested and reused without
 * tripping React fast-refresh (a module should export components or plain
 * helpers, not both).
 */

/**
 * Format a PKR amount for a metric card.
 *
 * Large values are compacted so they fit the card ("PKR 153K"); the caller is
 * expected to expose the exact figure via `formatPkrFull` in a tooltip.
 */
export function formatPkr(value) {
  const n = Number(value) || 0;
  if (Math.abs(n) >= 1_000_000) return `PKR ${(n / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`;
  if (Math.abs(n) >= 100_000) return `PKR ${Math.round(n / 1000)}K`;
  return `PKR ${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
}

/** Exact PKR amount, always with thousands separators. */
export function formatPkrFull(value) {
  return `PKR ${(Number(value) || 0).toLocaleString('en-US', { maximumFractionDigits: 2 })}`;
}

/** Short, locale-aware timestamp for activity rows. Empty string when unusable. */
export function formatTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}
