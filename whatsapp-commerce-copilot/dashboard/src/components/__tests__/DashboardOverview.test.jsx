import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));

import axios from 'axios';
import DashboardOverview from '../DashboardOverview';
import { formatPkr, formatPkrFull } from '../../format';

const OVERVIEW = {
  store_id: 's1',
  period: { range: '7d', start: '2026-08-14T19:00:00+00:00', end: '2026-08-21T19:00:00+00:00', timezone: 'Asia/Karachi' },
  metrics: {
    conversations_handled: 4, inbound_messages: 11,
    orders_confirmed: 3, orders_cancelled: 1,
    revenue_pkr: 12700, needs_attention: 1,
  },
  activity: [
    { id: 'order:o1', type: 'order_confirmed', description: 'Order confirmed — Lawn Suit ×2 · PKR 9,000',
      created_at: '2026-08-21T09:00:00+00:00', order_id: 'o1', conversation_id: 'c1' },
    { id: 'handoff:h1', type: 'escalation', description: 'Escalated to you — complaint',
      created_at: '2026-08-21T08:00:00+00:00', conversation_id: 'c1' },
  ],
  attention_items: [
    { id: 'h1', conversation_id: 'c1', reason: 'complaint', summary: 'Delivery delay',
      status: 'pending', customer_phone_masked: '+92 300 XXXXXXX', created_at: '2026-08-21T08:00:00+00:00' },
  ],
  generated_at: '2026-08-21T09:30:00+00:00',
};

const EMPTY = {
  ...OVERVIEW,
  metrics: { conversations_handled: 0, inbound_messages: 0, orders_confirmed: 0, orders_cancelled: 0, revenue_pkr: 0, needs_attention: 0 },
  activity: [], attention_items: [],
};

const lastParams = () => axios.get.mock.calls.at(-1)[1].params;
const lastUrl = () => axios.get.mock.calls.at(-1)[0];

beforeEach(() => {
  vi.clearAllMocks();
  cleanup();
  axios.get.mockResolvedValue({ data: OVERVIEW });
});

afterEach(() => { vi.useRealTimers(); });

describe('formatPkr', () => {
  it('formats with separators and compacts large values, keeping the full value', () => {
    expect(formatPkr(0)).toBe('PKR 0');
    expect(formatPkr(12700)).toBe('PKR 12,700');
    expect(formatPkr(153000)).toBe('PKR 153K');
    expect(formatPkr(2500000)).toBe('PKR 2.5M');
    expect(formatPkrFull(153000)).toBe('PKR 153,000');
  });
});

describe('DashboardOverview', () => {
  it('requests Last 7 days by default', async () => {
    render(<DashboardOverview storeId="s1" />);
    await waitFor(() => expect(axios.get).toHaveBeenCalled());
    expect(lastUrl()).toContain('/stores/s1/dashboard/overview');
    expect(lastParams()).toEqual({ range: '7d', activity_limit: 10 });
  });

  it('renders metrics from the API, not hardcoded screenshot values', async () => {
    render(<DashboardOverview storeId="s1" />);
    await waitFor(() => expect(screen.getByText('Conversations Handled')).toBeInTheDocument());
    expect(screen.getByText('4')).toBeInTheDocument();          // conversations
    expect(screen.getByText('3')).toBeInTheDocument();          // orders
    expect(screen.getByText('PKR 12,700')).toBeInTheDocument(); // revenue
    expect(screen.getByText('11 customer messages')).toBeInTheDocument();
    // screenshot sample numbers must never be baked in
    expect(screen.queryByText('34')).toBeNull();
    expect(screen.queryByText('PKR 153K')).toBeNull();
    expect(screen.queryByText(/DMS ANSWERED/i)).toBeNull();
  });

  it('shows activity and masked attention details', async () => {
    render(<DashboardOverview storeId="s1" />);
    await waitFor(() => expect(screen.getByText(/Order confirmed — Lawn Suit/)).toBeInTheDocument());
    expect(screen.getByText('Escalated to you — complaint')).toBeInTheDocument();
    expect(screen.getByText(/\+92 300 XXXXXXX/)).toBeInTheDocument();
    expect(screen.getByText('1 open')).toBeInTheDocument();
  });

  it('changing the date range refetches with the new range', async () => {
    render(<DashboardOverview storeId="s1" />);
    await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByText('Last 30 days'));
    await waitFor(() => expect(lastParams()).toEqual({ range: '30d', activity_limit: 10 }));
  });

  it('a custom date range is sent as start_date/end_date', async () => {
    render(<DashboardOverview storeId="s1" />);
    await waitFor(() => expect(axios.get).toHaveBeenCalled());
    fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '2026-08-01' } });
    fireEvent.change(screen.getByLabelText('End date'), { target: { value: '2026-08-07' } });
    await waitFor(() => expect(lastParams()).toEqual({
      start_date: '2026-08-01', end_date: '2026-08-07', activity_limit: 10,
    }));
  });

  it('switching stores refetches for the new store', async () => {
    const { rerender } = render(<DashboardOverview storeId="s1" />);
    await waitFor(() => expect(axios.get).toHaveBeenCalled());
    rerender(<DashboardOverview storeId="s2" />);
    await waitFor(() => expect(lastUrl()).toContain('/stores/s2/'));
  });

  it('a stale response cannot overwrite the newer store selection', async () => {
    let resolveS1;
    const s1Promise = new Promise((res) => { resolveS1 = res; });
    axios.get.mockImplementation((url) => {
      if (url.includes('/stores/s1/')) return s1Promise;
      return Promise.resolve({
        data: { ...OVERVIEW, metrics: { ...OVERVIEW.metrics, orders_confirmed: 99, revenue_pkr: 555 } },
      });
    });

    const { rerender } = render(<DashboardOverview storeId="s1" />);
    rerender(<DashboardOverview storeId="s2" />);
    await waitFor(() => expect(screen.getByText('PKR 555')).toBeInTheDocument());

    resolveS1({ data: OVERVIEW }); // stale store-1 response lands late
    await Promise.resolve();
    expect(screen.getByText('PKR 555')).toBeInTheDocument();
    expect(screen.queryByText('PKR 12,700')).toBeNull();
  });

  it('manual refresh refetches without changing the selected range', async () => {
    render(<DashboardOverview storeId="s1" />);
    await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByText('Last 30 days'));
    await waitFor(() => expect(lastParams().range).toBe('30d'));

    fireEvent.click(screen.getByLabelText('Refresh dashboard'));
    await waitFor(() => expect(axios.get.mock.calls.length).toBeGreaterThan(2));
    expect(lastParams().range).toBe('30d'); // range preserved
  });

  it('auto-refreshes on an interval and clears the timer on unmount', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { unmount } = render(<DashboardOverview storeId="s1" />);
    await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(1));

    await vi.advanceTimersByTimeAsync(25000);
    await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(2));

    unmount();
    const callsAtUnmount = axios.get.mock.calls.length;
    await vi.advanceTimersByTimeAsync(60000);
    expect(axios.get).toHaveBeenCalledTimes(callsAtUnmount); // no timer left running
  });

  it('shows a loading state before the first response', async () => {
    axios.get.mockImplementation(() => new Promise(() => {}));
    render(<DashboardOverview storeId="s1" />);
    expect(screen.getByText('Loading dashboard…')).toBeInTheDocument();
  });

  it('shows empty states when the store has no data', async () => {
    axios.get.mockResolvedValue({ data: EMPTY });
    render(<DashboardOverview storeId="s1" />);
    await waitFor(() => expect(screen.getByText('Nothing needs attention.')).toBeInTheDocument());
    expect(screen.getByText('No activity in this period yet.')).toBeInTheDocument();
    expect(screen.getByText('PKR 0')).toBeInTheDocument();
  });

  it('keeps the last good data when a background refresh fails', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<DashboardOverview storeId="s1" />);
    await waitFor(() => expect(screen.getByText('PKR 12,700')).toBeInTheDocument());

    axios.get.mockRejectedValue(new Error('network'));
    await vi.advanceTimersByTimeAsync(25000);

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    expect(screen.getByText('PKR 12,700')).toBeInTheDocument(); // prior data preserved
  });

  it('opening an attention item hands the conversation id to the parent', async () => {
    const onOpenConversation = vi.fn();
    render(<DashboardOverview storeId="s1" onOpenConversation={onOpenConversation} />);
    await waitFor(() => expect(screen.getByText('Open conversation')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Open conversation'));
    expect(onOpenConversation).toHaveBeenCalledWith('c1');
  });

  it('"View all escalations" navigates without selecting a conversation', async () => {
    const onOpenConversation = vi.fn();
    render(<DashboardOverview storeId="s1" onOpenConversation={onOpenConversation} />);
    await waitFor(() => expect(screen.getByText('View all escalations →')).toBeInTheDocument());
    fireEvent.click(screen.getByText('View all escalations →'));
    expect(onOpenConversation).toHaveBeenCalledWith(null);
  });
});
