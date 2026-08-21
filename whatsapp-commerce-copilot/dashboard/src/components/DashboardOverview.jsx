import React, { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import { API_URL } from '../config';
import {
  MessageSquare, ShoppingCart, Wallet, AlertTriangle, RefreshCw, CalendarDays,
} from 'lucide-react';
import { formatPkr, formatPkrFull, formatTime } from '../format';

// The merchant leaves this screen open while orders arrive over WhatsApp, so it
// refreshes itself. Kept slow enough to stay cheap; a manual refresh is always
// available and never blocked by the timer.
const REFRESH_MS = 25000;

const RANGES = [
  { id: 'today', label: 'Today' },
  { id: 'yesterday', label: 'Yesterday' },
  { id: '7d', label: 'Last 7 days' },
  { id: '30d', label: 'Last 30 days' },
  { id: 'all', label: 'All time' },
];

const ACTIVITY_COLORS = {
  order_confirmed: 'var(--success)',
  order_cancelled: 'var(--danger)',
  escalation: '#F59E0B',
  conversation_started: 'var(--accent-primary)',
};

const panelStyle = {
  backgroundColor: 'var(--bg-panel)',
  border: '1px solid var(--border-color)',
  borderRadius: '16px',
  boxShadow: 'var(--shadow-sm)',
};

function MetricCard({ icon, label, value, title, support }) {
  // Basis kept well under a quarter of a 1280px laptop's content width so all
  // four cards share one row there, and fall to 2x2 on narrower screens.
  return (
    <div style={{ ...panelStyle, padding: '1.25rem 1.5rem', flex: '1 1 180px', minWidth: '170px' }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem',
        color: 'var(--text-muted)', fontSize: '0.7rem', fontWeight: 700,
        textTransform: 'uppercase', letterSpacing: '0.5px',
      }}>
        {icon}<span>{label}</span>
      </div>
      {/* nowrap so a value like "PKR 9,000" never breaks across lines on a
          narrower laptop; long amounts are compacted by formatPkr instead */}
      <div title={title} style={{
        fontSize: '1.75rem', fontWeight: 700, color: 'var(--text-primary)',
        lineHeight: 1.15, whiteSpace: 'nowrap',
      }}>
        {value}
      </div>
      {support && (
        <div style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
          {support}
        </div>
      )}
    </div>
  );
}

const DashboardOverview = ({ storeId, onOpenConversation }) => {
  const [range, setRange] = useState('7d');
  const [customStart, setCustomStart] = useState('');
  const [customEnd, setCustomEnd] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);

  // Monotonic request id: only the newest request may write state, so a slow
  // response for an old store or date range can never overwrite fresh data.
  const requestSeq = useRef(0);
  const inFlight = useRef(false);

  const usingCustom = Boolean(customStart && customEnd);

  const load = useCallback(async ({ showSpinner = true } = {}) => {
    if (inFlight.current) return;           // never overlap refreshes
    inFlight.current = true;
    const seq = ++requestSeq.current;
    const params = usingCustom
      ? { start_date: customStart, end_date: customEnd, activity_limit: 10 }
      : { range, activity_limit: 10 };
    try {
      if (showSpinner) setLoading(true);
      const res = await axios.get(`${API_URL}/stores/${storeId}/dashboard/overview`, { params });
      if (seq !== requestSeq.current) return;   // stale
      setData(res.data);
      setError(null);
      setLastUpdated(new Date());
    } catch (err) {
      if (seq !== requestSeq.current) return;
      // Keep the last good data on screen during a background failure.
      console.error('Failed to load dashboard overview', err);
      setError('Could not refresh dashboard data.');
    } finally {
      inFlight.current = false;
      if (seq === requestSeq.current && showSpinner) setLoading(false);
    }
  }, [storeId, range, customStart, customEnd, usingCustom]);

  // Store or range change → discard anything in flight and reload.
  useEffect(() => {
    requestSeq.current += 1;
    inFlight.current = false;
    setData(null);
    load();
  }, [storeId, range, customStart, customEnd]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-refresh without disturbing the selected range.
  useEffect(() => {
    const timer = setInterval(() => load({ showSpinner: false }), REFRESH_MS);
    return () => clearInterval(timer);
  }, [load]);

  const metrics = data?.metrics;
  const activity = data?.activity ?? [];
  const attention = data?.attention_items ?? [];

  return (
    <div style={{ flex: 1, padding: '0 2.5rem 2.5rem', overflowY: 'auto' }}>
      {/* Filter bar */}
      <div style={{
        ...panelStyle, padding: '0.75rem 1rem', marginBottom: '1.5rem',
        display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap',
      }}>
        <span style={{
          display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--text-muted)',
          fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px',
        }}>
          <CalendarDays size={14} aria-hidden="true" /> Filter
        </span>

        <div role="group" aria-label="Date range" style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
          {RANGES.map((r) => {
            const active = !usingCustom && range === r.id;
            return (
              <button
                key={r.id}
                type="button"
                aria-pressed={active}
                onClick={() => { setCustomStart(''); setCustomEnd(''); setRange(r.id); }}
                style={{
                  padding: '0.35rem 0.85rem', borderRadius: '8px', fontSize: '0.8125rem',
                  fontWeight: 600, cursor: 'pointer',
                  border: `1px solid ${active ? 'var(--text-primary)' : 'var(--border-color)'}`,
                  background: active ? 'var(--text-primary)' : 'var(--bg-panel)',
                  color: active ? '#FFFFFF' : 'var(--text-secondary)',
                }}
              >
                {r.label}
              </button>
            );
          })}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginLeft: 'auto' }}>
          <label htmlFor="dash-start" className="sr-only" style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>From</label>
          <input id="dash-start" type="date" aria-label="Start date" value={customStart}
                 onChange={(e) => setCustomStart(e.target.value)} />
          <span style={{ color: 'var(--text-muted)' }}>→</span>
          <label htmlFor="dash-end" className="sr-only" style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>To</label>
          <input id="dash-end" type="date" aria-label="End date" value={customEnd}
                 onChange={(e) => setCustomEnd(e.target.value)} />
          <button type="button" onClick={() => load()} aria-label="Refresh dashboard"
                  style={{
                    display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer',
                    padding: '0.4rem 0.8rem', borderRadius: '8px', fontSize: '0.8125rem',
                    fontWeight: 600, border: '1px solid var(--border-color)',
                    background: 'var(--bg-panel-hover)', color: 'var(--text-secondary)',
                  }}>
            <RefreshCw size={14} aria-hidden="true" /> Refresh
          </button>
        </div>
      </div>

      {error && (
        <div role="alert" style={{
          marginBottom: '1rem', padding: '0.75rem 1rem', borderRadius: '10px',
          border: '1px solid rgba(239,68,68,0.25)', background: 'rgba(239,68,68,0.06)',
          color: 'var(--danger)', fontSize: '0.8125rem',
        }}>
          {error}{data ? ' Showing the last successful update.' : ''}
        </div>
      )}

      {loading && !data ? (
        <div style={{ ...panelStyle, padding: '3rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
          Loading dashboard…
        </div>
      ) : (
        <>
          {/* Summary cards */}
          <div style={{ display: 'flex', gap: '1.25rem', flexWrap: 'wrap', marginBottom: '1.5rem' }}>
            <MetricCard
              icon={<MessageSquare size={14} aria-hidden="true" />}
              label="Conversations Handled"
              value={metrics?.conversations_handled ?? 0}
              support={`${metrics?.inbound_messages ?? 0} customer messages`}
            />
            <MetricCard
              icon={<ShoppingCart size={14} aria-hidden="true" />}
              label="Orders Confirmed"
              value={metrics?.orders_confirmed ?? 0}
              support={metrics?.orders_cancelled
                ? `${metrics.orders_cancelled} cancelled in this period`
                : 'Excludes cancelled orders'}
            />
            <MetricCard
              icon={<Wallet size={14} aria-hidden="true" />}
              label="Revenue (PKR)"
              value={formatPkr(metrics?.revenue_pkr)}
              title={formatPkrFull(metrics?.revenue_pkr)}
              support="From confirmed orders only"
            />
            <MetricCard
              icon={<AlertTriangle size={14} aria-hidden="true" />}
              label="Needs Attention"
              value={metrics?.needs_attention ?? 0}
              support={metrics?.needs_attention ? 'Unresolved escalations' : 'Nothing pending'}
            />
          </div>

          {/* Lower panels */}
          <div style={{ display: 'flex', gap: '1.25rem', flexWrap: 'wrap', alignItems: 'flex-start' }}>
            <section aria-label="Activity" style={{ ...panelStyle, flex: '2 1 420px', minWidth: '320px', padding: '1.5rem' }}>
              <h2 style={{ fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '1.25rem' }}>
                Activity
              </h2>
              {activity.length === 0 ? (
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                  No activity in this period yet.
                </p>
              ) : (
                <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.9rem' }}>
                  {activity.map((item) => (
                    <li key={item.id} style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem' }}>
                      <span aria-hidden="true" style={{
                        width: '8px', height: '8px', borderRadius: '50%', marginTop: '0.4rem', flexShrink: 0,
                        backgroundColor: ACTIVITY_COLORS[item.type] || 'var(--text-muted)',
                      }} />
                      <span style={{ flex: 1, fontSize: '0.875rem', color: 'var(--text-primary)' }}>
                        {item.description}
                      </span>
                      <time dateTime={item.created_at}
                            style={{ fontSize: '0.75rem', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                        {formatTime(item.created_at)}
                      </time>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section aria-label="Needs your attention" style={{ ...panelStyle, flex: '1 1 320px', minWidth: '300px', padding: '1.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem' }}>
                <h2 style={{ fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  Needs Your Attention
                </h2>
                <span style={{
                  fontSize: '0.7rem', fontWeight: 700, padding: '0.2rem 0.6rem', borderRadius: '999px',
                  background: attention.length ? 'rgba(239,68,68,0.1)' : 'rgba(16,185,129,0.1)',
                  color: attention.length ? 'var(--danger)' : 'var(--success)',
                }}>
                  {attention.length} open
                </span>
              </div>

              {attention.length === 0 ? (
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                  Nothing needs attention.
                </p>
              ) : (
                <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column' }}>
                  {attention.map((item) => (
                    <li key={item.id} style={{
                      display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
                      gap: '0.75rem', padding: '0.85rem 0', borderBottom: '1px solid var(--border-color-light)',
                    }}>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                          {(item.reason || '').replace(/_/g, ' ')}
                        </div>
                        {item.summary && (
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.15rem' }}>
                            {item.summary}
                          </div>
                        )}
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                          {item.customer_phone_masked} · {formatTime(item.created_at)} · {item.status}
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => onOpenConversation?.(item.conversation_id)}
                        style={{
                          flexShrink: 0, padding: '0.35rem 0.8rem', borderRadius: '8px',
                          fontSize: '0.75rem', fontWeight: 600, cursor: 'pointer',
                          border: '1px solid var(--border-color)', background: 'var(--bg-panel)',
                          color: 'var(--text-primary)',
                        }}
                      >
                        Open conversation
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              <button
                type="button"
                onClick={() => onOpenConversation?.(null)}
                style={{
                  marginTop: '1rem', background: 'none', border: 'none', padding: 0,
                  color: 'var(--accent-primary)', fontWeight: 600, fontSize: '0.8125rem', cursor: 'pointer',
                }}
              >
                View all escalations →
              </button>
            </section>
          </div>

          <div style={{ marginTop: '1.25rem', textAlign: 'right', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            {lastUpdated
              ? `Last updated ${lastUpdated.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })} · auto-refreshes every ${REFRESH_MS / 1000}s`
              : 'Not yet updated'}
            {data?.period?.timezone ? ` · times in ${data.period.timezone}` : ''}
          </div>
        </>
      )}
    </div>
  );
};

export default DashboardOverview;
