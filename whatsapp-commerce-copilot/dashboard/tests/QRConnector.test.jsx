import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act, fireEvent } from '@testing-library/react';
import QRConnector from '../src/components/QRConnector';
import App from '../src/App';
import axios from 'axios';

vi.mock('axios');

describe('QRConnector Polling and Timeout', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
  });

  it('polls sequentially and prevents overlapping setInterval requests', async () => {
    let resolveFirstReq;
    axios.get.mockImplementationOnce(() => new Promise(resolve => {
      resolveFirstReq = resolve;
    }));
    axios.get.mockResolvedValue({ data: { status: 'initializing' } }); // for subsequent calls

    const setStatus = vi.fn();

    render(<QRConnector storeId="test" status="initializing" setStatus={setStatus} />);

    // Initial poll is pending
    expect(axios.get).toHaveBeenCalledTimes(1);

    // Advance time by 10 seconds. Since the first request is pending, it should NOT poll again
    await act(async () => {
      vi.advanceTimersByTime(10000);
    });

    expect(axios.get).toHaveBeenCalledTimes(1);

    // Now resolve the first request
    await act(async () => {
      resolveFirstReq({ data: { status: 'initializing' } });
    });

    // Advance 5s, now it should poll again
    await act(async () => {
      vi.advanceTimersByTime(5000);
    });

    expect(axios.get).toHaveBeenCalledTimes(2);
  });

  it('clears timeout when valid QR is received', async () => {
    axios.get.mockResolvedValue({ data: { status: 'waiting_for_qr', qr_code: 'qr-data' } });
    const setStatus = vi.fn();

    render(<QRConnector storeId="test" status="waiting_for_qr" setStatus={setStatus} />);

    await act(async () => {
      await Promise.resolve();
    });

    // Advance to 90 seconds (QR_TIMEOUT_MS)
    await act(async () => {
      vi.advanceTimersByTime(90000);
    });

    // Timeout should not be triggered because QR was received
    expect(screen.queryByText(/Connection timed out/i)).not.toBeInTheDocument();
  });

  it('stops polling when status becomes connected', async () => {
    axios.get.mockResolvedValue({ data: { status: 'connected' } });
    const setStatus = vi.fn();

    const { rerender } = render(<QRConnector storeId="test" status="initializing" setStatus={setStatus} />);

    await act(async () => {
      await Promise.resolve();
    });

    rerender(<QRConnector storeId="test" status="connected" setStatus={setStatus} />);

    await act(async () => {
      vi.advanceTimersByTime(5000);
    });

    // Should not poll again after being connected
    expect(axios.get).toHaveBeenCalledTimes(1);
  });

  it('starts a clean attempt on Retry', async () => {
    axios.post.mockResolvedValue({ data: { status: 'initializing', qr_code: null } });
    axios.get.mockResolvedValue({ data: { status: 'initializing' } });
    const setStatus = vi.fn();

    render(<QRConnector storeId="test" status="failed" setStatus={setStatus} />);

    // Advance to clear anything if present
    await act(async () => {
      vi.advanceTimersByTime(5000);
    });

    const retryButton = screen.getByRole('button', { name: /Retry/i });
    fireEvent.click(retryButton);

    await act(async () => {
      await Promise.resolve();
    });

    expect(axios.post).toHaveBeenCalledTimes(1);
  });

  it('unmount clears timers', async () => {
    axios.get.mockResolvedValue({ data: { status: 'initializing' } });
    const setStatus = vi.fn();

    const { unmount } = render(<QRConnector storeId="test" status="initializing" setStatus={setStatus} />);

    await act(async () => {
      await Promise.resolve();
    });

    unmount();

    await act(async () => {
      vi.advanceTimersByTime(5000);
    });

    // Only the initial fetch should have happened
    expect(axios.get).toHaveBeenCalledTimes(1);
  });

  it('repeated Retry clicks do not produce duplicate requests', async () => {
    // Delay resolution to keep `isRetrying` active
    axios.post.mockImplementation(() => new Promise(resolve => setTimeout(() => resolve({ data: { status: 'initializing' } }), 1000)));
    const setStatus = vi.fn();

    render(<QRConnector storeId="test" status="failed" setStatus={setStatus} />);

    const retryButton = screen.getByRole('button', { name: /Retry/i });

    // Click multiple times
    fireEvent.click(retryButton);
    fireEvent.click(retryButton);
    fireEvent.click(retryButton);

    // Advance timers so promise resolves
    await act(async () => {
      vi.advanceTimersByTime(1500);
      await Promise.resolve();
    });

    expect(axios.post).toHaveBeenCalledTimes(1);
  });

  it('App and QRConnector integration - only one poller runs during QR initialization', async () => {
    axios.get.mockImplementation((url) => {
      if (url.includes('/whatsapp/status')) {
        return Promise.resolve({ data: { status: 'initializing', phone_number: null } });
      }
      if (url.includes('/orders')) {
        return Promise.resolve({ data: [] }); // return empty array for orders map
      }
      return Promise.resolve({ data: { name: 'Test Store' } });
    });

    render(<App />);

    // Click "Conversations" tab to render QRConnector
    const conversationsTab = screen.getByText('Conversations');
    fireEvent.click(conversationsTab);

    // Initial fetch
    await act(async () => {
      await Promise.resolve();
    });

    axios.get.mockClear();

    // Advance by 5 seconds
    await act(async () => {
      vi.advanceTimersByTime(5000);
    });

    const statusCalls = axios.get.mock.calls.filter(call => call[0].includes('/whatsapp/status'));
    expect(statusCalls.length).toBe(1);
  });
});
