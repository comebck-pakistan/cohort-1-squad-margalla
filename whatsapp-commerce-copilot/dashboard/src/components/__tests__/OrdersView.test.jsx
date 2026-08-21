import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';

vi.mock('axios', () => ({
  default: { get: vi.fn() },
}));

import axios from 'axios';
import OrdersView from '../OrdersView';

const ORDER = {
  id: 'order-abcdef123456',
  store_id: 's1',
  status: 'pending',
  total_amount: 7000,
  customer_name: 'Ali Khan',
  customer_phone: '923001234567',
  customer_address: 'House 12, Gulberg',
  customer_city: 'Lahore',
  payment_method: 'COD',
  created_at: '2026-08-20T10:00:00',
  items: [{
    product_id: 'p1', variant_id: 'v1', product_name: 'Printed Lawn Suit',
    variant_description: 'white medium', quantity: 2, unit_price: 3500, line_total: 7000,
  }],
};

beforeEach(() => {
  vi.clearAllMocks();
  cleanup();
  axios.get.mockResolvedValue({ data: [ORDER] });
});

afterEach(() => {
  vi.useRealTimers();
});

describe('OrdersView', () => {
  it('renders an order that came in over WhatsApp, with its line items', async () => {
    render(<OrdersView storeId="s1" />);
    await waitFor(() => expect(screen.getByText('Ali Khan')).toBeInTheDocument());
    expect(screen.getByText('923001234567')).toBeInTheDocument();
    expect(screen.getByText('Rs. 7,000')).toBeInTheDocument();
    expect(screen.getByText('COD')).toBeInTheDocument();
    // the ordered product is visible to the seller
    expect(screen.getByText('Printed Lawn Suit')).toBeInTheDocument();
    expect(screen.getByText(/white medium.*× 2/)).toBeInTheDocument();
    expect(screen.getByText('1 order')).toBeInTheDocument();
  });

  it('shows the empty state when the store has no orders', async () => {
    axios.get.mockResolvedValue({ data: [] });
    render(<OrdersView storeId="s1" />);
    await waitFor(() => expect(screen.getByText('No orders found')).toBeInTheDocument());
  });

  it('does not present an old command as the customer name', async () => {
    axios.get.mockResolvedValue({ data: [{ ...ORDER, customer_name: 'Order' }] });
    render(<OrdersView storeId="s1" />);
    await waitFor(() => expect(screen.getByText('Name not provided')).toBeInTheDocument());
    expect(screen.queryByText('Order')).toBeNull();
  });

  it('"Sync Orders Now" actually refetches (it used to be a dead button)', async () => {
    axios.get.mockResolvedValue({ data: [] });
    render(<OrdersView storeId="s1" />);
    await waitFor(() => expect(screen.getByText('No orders found')).toBeInTheDocument());
    expect(axios.get).toHaveBeenCalledTimes(1);

    // an order lands in the meantime
    axios.get.mockResolvedValue({ data: [ORDER] });
    fireEvent.click(screen.getByText('Sync Orders Now'));
    await waitFor(() => expect(screen.getByText('Ali Khan')).toBeInTheDocument());
  });

  it('refreshes on its own so a new order appears without a reload', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    axios.get.mockResolvedValue({ data: [] });
    render(<OrdersView storeId="s1" />);
    await waitFor(() => expect(screen.getByText('No orders found')).toBeInTheDocument());

    axios.get.mockResolvedValue({ data: [ORDER] });
    await vi.advanceTimersByTimeAsync(15000);
    await waitFor(() => expect(screen.getByText('Ali Khan')).toBeInTheDocument());
  });

  it('clears stale orders when the seller switches store', async () => {
    const { rerender } = render(<OrdersView storeId="s1" />);
    await waitFor(() => expect(screen.getByText('Ali Khan')).toBeInTheDocument());

    axios.get.mockResolvedValue({ data: [] });
    rerender(<OrdersView storeId="s2" />);
    await waitFor(() => expect(screen.getByText('No orders found')).toBeInTheDocument());
    expect(screen.queryByText('Ali Khan')).toBeNull();
  });

  it('ignores a late response from the previous store', async () => {
    let resolveS1;
    const s1Promise = new Promise((res) => { resolveS1 = res; });
    axios.get.mockImplementation((url) => {
      if (url.includes('/stores/s1/')) return s1Promise;   // hangs
      return Promise.resolve({ data: [] });
    });

    const { rerender } = render(<OrdersView storeId="s1" />);
    rerender(<OrdersView storeId="s2" />);
    await waitFor(() => expect(screen.getByText('No orders found')).toBeInTheDocument());

    resolveS1({ data: [ORDER] });   // stale response arrives
    await Promise.resolve();
    expect(screen.queryByText('Ali Khan')).toBeNull();
  });
});
