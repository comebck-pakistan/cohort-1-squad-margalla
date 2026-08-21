import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));

import axios from 'axios';
import ConversationView from '../ConversationView';

const CONVS = [
  { id: 'c1', customer_phone: '923001111111', is_ai_controlled: true, order_stage: 'BROWSING', last_message_at: null },
  { id: 'c2', customer_phone: '923002222222', is_ai_controlled: true, order_stage: 'BROWSING', last_message_at: null },
];

const DETAILS = {
  id: 'c2',
  customer_phone: '923002222222',
  is_ai_controlled: true,
  order_stage: 'BROWSING',
  messages: [{ id: 'm1', direction: 'inbound', content: 'Deep linked thread', created_at: '2026-08-21T09:00:00Z' }],
};

beforeEach(() => {
  vi.clearAllMocks();
  cleanup();
  axios.get.mockImplementation((url) => {
    if (url.endsWith('/conversations')) return Promise.resolve({ data: CONVS });
    if (url.endsWith('/conversations/c2')) return Promise.resolve({ data: DETAILS });
    return Promise.resolve({ data: { ...DETAILS, id: 'c1', messages: [] } });
  });
});

afterEach(() => { vi.useRealTimers(); });

describe('ConversationView deep link', () => {
  it('preselects the conversation handed over from an escalation', async () => {
    render(<ConversationView storeId="s1" initialConversationId="c2" />);
    await waitFor(() =>
      expect(axios.get).toHaveBeenCalledWith(expect.stringContaining('/conversations/c2')));
    await waitFor(() => expect(screen.getByText('Deep linked thread')).toBeInTheDocument());
  });

  it('without a deep link nothing is preselected (unchanged behaviour)', async () => {
    render(<ConversationView storeId="s1" />);
    await waitFor(() => expect(axios.get).toHaveBeenCalled());
    const detailCalls = axios.get.mock.calls.filter(([url]) => /\/conversations\/[^/]+$/.test(url));
    expect(detailCalls).toHaveLength(0);
  });
});
