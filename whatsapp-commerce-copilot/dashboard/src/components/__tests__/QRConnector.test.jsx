import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';

vi.mock('axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));

import axios from 'axios';
import QRConnector from '../QRConnector';

const CONNECT_URL = 'http://localhost:8000/api/stores/s1/whatsapp/connect';

// Stateful wrapper so setStatus actually re-renders (status is parent-controlled).
function Wrapper() {
  const [status, setStatus] = React.useState('disconnected');
  return <QRConnector storeId="s1" status={status} setStatus={setStatus} />;
}

function renderConnector() {
  render(<Wrapper />);
}

// Switch to phone mode, type a value, and submit.
function submitPhone(value) {
  fireEvent.click(screen.getByText('Link with Phone Number'));
  const input = screen.getByLabelText('Phone number');
  fireEvent.change(input, { target: { value } });
  fireEvent.click(screen.getByText('Generate Pairing Code'));
}

beforeEach(() => {
  vi.clearAllMocks();
  cleanup();
  axios.post.mockResolvedValue({ data: { status: 'waiting_for_qr' } });
  axios.get.mockResolvedValue({ data: { status: 'waiting_for_qr' } });
  axios.delete.mockResolvedValue({ data: { status: 'disconnected' } });
});

describe('QRConnector phone linking', () => {
  it('sends normalized digits for "+92 300-1234567"', async () => {
    renderConnector();
    submitPhone('+92 300-1234567');
    await waitFor(() => expect(axios.post).toHaveBeenCalled());
    expect(axios.post).toHaveBeenCalledWith(CONNECT_URL, { phone_number: '923001234567' });
  });

  it('sends normalized digits for "(+92) 300 1234567"', async () => {
    renderConnector();
    submitPhone('(+92) 300 1234567');
    await waitFor(() => expect(axios.post).toHaveBeenCalled());
    expect(axios.post).toHaveBeenCalledWith(CONNECT_URL, { phone_number: '923001234567' });
  });

  it('leaves plain digits unchanged', async () => {
    renderConnector();
    submitPhone('923001234567');
    await waitFor(() => expect(axios.post).toHaveBeenCalled());
    expect(axios.post).toHaveBeenCalledWith(CONNECT_URL, { phone_number: '923001234567' });
  });

  it('rejects letters without calling the API and shows a safe error', async () => {
    renderConnector();
    submitPhone('92abc123');
    expect(axios.post).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent(/international phone number with country code/i);
  });

  it('rejects too-short numbers without calling the API', () => {
    renderConnector();
    submitPhone('1234');
    expect(axios.post).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  it('rejects too-long numbers without calling the API', () => {
    renderConnector();
    submitPhone('1234567890123456');
    expect(axios.post).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  it('QR mode connects without a phone number', async () => {
    renderConnector();
    fireEvent.click(screen.getByText('Generate QR Code'));
    await waitFor(() => expect(axios.post).toHaveBeenCalled());
    expect(axios.post).toHaveBeenCalledWith(CONNECT_URL, { phone_number: null });
  });

  it('never renders an internal gateway URL from an error detail', async () => {
    axios.post.mockRejectedValueOnce({
      response: {
        data: {
          detail:
            "Server error '500 Internal Server Error' for url 'http://gateway:3001/sessions/s1/connect'",
        },
      },
    });
    renderConnector();
    submitPhone('923001234567');

    // Phone mode failure shows pairing-specific message, never raw gateway URLs
    await waitFor(() =>
      expect(screen.getByText('Pairing Session Expired')).toBeInTheDocument()
    );
    expect(screen.queryByText(/gateway:3001/)).toBeNull();
    expect(screen.queryByText(/Internal Server Error/)).toBeNull();
  });

  it('shows a safe backend error detail when it is not technical', async () => {
    axios.post.mockRejectedValueOnce({
      response: {
        data: {
          detail: 'Enter an international phone number with country code, for example 923001234567.',
        },
      },
    });
    renderConnector();
    // Use QR mode so the error detail (not pairing-specific text) is displayed
    fireEvent.click(screen.getByText('Generate QR Code'));

    await waitFor(() =>
      expect(
        screen.getByText(/international phone number with country code, for example 923001234567/i)
      ).toBeInTheDocument()
    );
  });
});

// ── NEW: Pairing failure UI tests ─────────────────────────────────────

describe('QRConnector pairing failure', () => {
  it('shows "Pairing Session Expired" when pairing fails', async () => {
    // Simulate: user submits phone → API returns failed status
    axios.post.mockResolvedValueOnce({ data: { status: 'failed', pairing_code: null } });
    // Status poll also returns failed
    axios.get.mockResolvedValue({ data: { status: 'failed' } });

    renderConnector();
    submitPhone('923001234567');

    await waitFor(() =>
      expect(screen.getByText('Pairing Session Expired')).toBeInTheDocument()
    );
    // Should show pairing-specific message
    expect(screen.getByText(/Generate a new code or try scanning the QR code/i)).toBeInTheDocument();
  });

  it('shows "Generate New Code" button on pairing failure', async () => {
    axios.post.mockResolvedValueOnce({ data: { status: 'failed', pairing_code: null } });
    axios.get.mockResolvedValue({ data: { status: 'failed' } });

    renderConnector();
    submitPhone('923001234567');

    await waitFor(() =>
      expect(screen.getByText('Generate New Code')).toBeInTheDocument()
    );
  });

  it('QR path shows generic "Connection Failed" on failure', async () => {
    axios.post.mockResolvedValueOnce({ data: { status: 'failed' } });
    axios.get.mockResolvedValue({ data: { status: 'failed' } });

    renderConnector();
    fireEvent.click(screen.getByText('Generate QR Code'));

    await waitFor(() =>
      expect(screen.getByText('Connection Failed')).toBeInTheDocument()
    );
    // Should show generic Retry, not "Generate New Code"
    expect(screen.getByText('Retry')).toBeInTheDocument();
  });
});
