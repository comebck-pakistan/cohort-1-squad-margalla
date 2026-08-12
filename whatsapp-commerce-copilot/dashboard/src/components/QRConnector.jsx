import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { API_URL } from '../config';
import { normalizePhoneNumber, PHONE_HELP_MESSAGE } from '../phone';
import { QrCode, RefreshCcw, AlertTriangle, WifiOff, Smartphone, Copy, Check } from 'lucide-react';

const QR_TIMEOUT_MS = 90_000; // 90 seconds
const POLL_INTERVAL_MS = 5_000; // 5 seconds

// Generic, safe fallback. We never render a raw gateway URL, MDN link, or other
// internal/technical error text to the seller.
const SAFE_CONNECT_ERROR = 'Could not connect to WhatsApp. Please try again.';

function safeErrorMessage(err) {
  const detail = err?.response?.data?.detail;
  if (
    typeof detail === 'string' &&
    detail.trim() &&
    !/https?:\/\/|gateway:|Server error|Internal Server Error/i.test(detail)
  ) {
    return detail;
  }
  return SAFE_CONNECT_ERROR;
}

function formatPairingCode(code) {
  if (!code) return '';
  const clean = String(code).replace(/\s+/g, '');
  if (clean.length === 8) return `${clean.slice(0, 4)}-${clean.slice(4)}`;
  return clean.replace(/(.{4})/g, '$1 ').trim();
}

const QRConnector = ({ storeId, status, setStatus }) => {
  const [qrCode, setQrCode] = useState(null);
  const [pairingCode, setPairingCode] = useState(null);
  const [method, setMethod] = useState('qr'); // 'qr' | 'phone'
  const [phoneInput, setPhoneInput] = useState('');
  const [phoneError, setPhoneError] = useState(null);
  const [copied, setCopied] = useState(false);
  const [timedOut, setTimedOut] = useState(false);
  const [error, setError] = useState(null);
  const [isRetrying, setIsRetrying] = useState(false);
  const timeoutRef = useRef(null);
  const currentStatusRef = useRef(status);
  const lastPhoneRef = useRef(null); // normalized digits used for the current attempt

  // Sync ref with prop
  useEffect(() => {
    currentStatusRef.current = status;
  }, [status]);

  // Reset state when status changes to non-waiting or QR is received
  useEffect(() => {
    if (status !== 'initializing' && status !== 'waiting_for_qr') {
      setTimedOut(false);
      if (status !== 'failed') setError(null);
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
      // Clear pairing code on terminal states so dead codes disappear immediately
      if (status === 'failed' || status === 'connected' || status === 'disconnected') {
        setPairingCode(null);
      }
    } else if (qrCode) {
      // Clear timeout if a valid QR is received
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
      setTimedOut(false);
    }
  }, [status, qrCode]);

  useEffect(() => {
    let isMounted = true;
    let pollTimer;
    let isPolling = false;
    const isConnecting = status === 'initializing' || status === 'waiting_for_qr';

    if (isConnecting && !timedOut) {
      // Set absolute timeout only once per connection attempt (unless we already have a QR)
      if (!timeoutRef.current && !qrCode) {
        timeoutRef.current = setTimeout(() => {
          setTimedOut(true);
        }, QR_TIMEOUT_MS);
      }

      // Sequential polling
      const checkStatus = async () => {
        if (!isMounted || timedOut || isPolling) return;
        isPolling = true;

        try {
          const res = await axios.get(`${API_URL}/stores/${storeId}/whatsapp/status`);
          if (!isMounted) return;

          setStatus(res.data.status);
          if (res.data.qr_code) {
            setQrCode(res.data.qr_code);
          }
          if (res.data.pairing_code) {
            setPairingCode(res.data.pairing_code);
          }
          if (res.data.status === 'failed') {
            setError('Connection failed. Please retry.');
          }
        } catch (err) {
          console.error(err);
        } finally {
          isPolling = false;
          const currentStatus = currentStatusRef.current;
          if (isMounted && (currentStatus === 'initializing' || currentStatus === 'waiting_for_qr')) {
            pollTimer = setTimeout(checkStatus, POLL_INTERVAL_MS);
          }
        }
      };

      checkStatus(); // immediate first poll
    }

    return () => {
      isMounted = false;
      clearTimeout(pollTimer);
    };
  }, [status, storeId, setStatus, timedOut, qrCode]);

  useEffect(() => {
    return () => {
      clearTimeout(timeoutRef.current);
    };
  }, []);

  // Core connect call. phoneDigits === null means QR mode (no phone validation).
  const connect = async (phoneDigits) => {
    if (isRetrying) return;
    setIsRetrying(true);
    setTimedOut(false);
    setError(null);
    setQrCode(null);
    setPairingCode(null);
    lastPhoneRef.current = phoneDigits;

    // Clear old timeout to force a fresh one
    clearTimeout(timeoutRef.current);
    timeoutRef.current = null;

    try {
      const res = await axios.post(`${API_URL}/stores/${storeId}/whatsapp/connect`, {
        phone_number: phoneDigits,
      });
      setStatus(res.data?.status || 'initializing');
      if (res.data?.qr_code) {
        setQrCode(res.data.qr_code);
      }
      if (res.data?.pairing_code) {
        setPairingCode(res.data.pairing_code);
      }
    } catch (err) {
      setError(safeErrorMessage(err));
      setStatus('failed');
    } finally {
      setIsRetrying(false);
    }
  };

  // QR mode: no phone required, no phone validation.
  const handleConnectQR = () => {
    setPhoneError(null);
    connect(null);
  };

  // Phone mode: validate/normalize BEFORE calling the API. Invalid input never POSTs.
  const handleConnectPhone = () => {
    const result = normalizePhoneNumber(phoneInput);
    if (!result.ok) {
      setPhoneError(PHONE_HELP_MESSAGE);
      return;
    }
    setPhoneError(null);
    connect(result.digits);
  };

  const handleRetry = () => {
    // Re-run the same attempt that was in flight (phone digits or QR).
    if (lastPhoneRef.current) {
      connect(lastPhoneRef.current);
    } else {
      connect(null);
    }
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(String(pairingCode).replace(/\s+/g, ''));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard unavailable — the code is still visible for manual entry.
    }
  };

  const handleDisconnect = async () => {
    try {
      await axios.delete(`${API_URL}/stores/${storeId}/whatsapp`);
      setStatus('disconnected');
      setQrCode(null);
      setPairingCode(null);
      setTimedOut(false);
      setError(null);
      setPhoneError(null);
    } catch (err) {
      console.error(err);
    }
  };

  const renderPairingCard = () => {
    if (!pairingCode) return null;
    return (
      <div style={{ marginBottom: '1.5rem', width: '100%' }}>
        <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
          Link with phone number — enter this code on your phone:
        </p>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <div style={{
            flex: 1,
            padding: '0.75rem',
            background: 'var(--bg-panel-hover)',
            border: '1px solid var(--border-color)',
            borderRadius: '8px',
            fontSize: '1.5rem',
            fontWeight: '700',
            letterSpacing: '0.25rem',
            color: 'var(--text-primary)',
            textAlign: 'center',
          }}>
            {formatPairingCode(pairingCode)}
          </div>
          <button
            className="btn btn-outline"
            onClick={handleCopy}
            aria-label="Copy pairing code"
            style={{ padding: '0.75rem' }}
          >
            {copied ? <Check size={16} color="var(--success, #22c55e)" /> : <Copy size={16} />}
          </button>
        </div>
        {copied && (
          <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.375rem' }}>
            Copied!
          </p>
        )}
        <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.5rem', lineHeight: 1.5, textAlign: 'left' }}>
          Open WhatsApp → Settings/Menu → Linked Devices → Link a Device → Link with phone number
          instead, then enter this code.
        </p>
      </div>
    );
  };

  const renderContent = () => {
    // Failed state
    if (status === 'failed' || timedOut) {
      const wasPairing = !!lastPhoneRef.current;
      const failTitle = timedOut
        ? 'Connection Timed Out'
        : wasPairing
          ? 'Pairing Session Expired'
          : 'Connection Failed';
      const failMessage = timedOut
        ? 'No QR code was received within the expected time. Please try again in a moment.'
        : wasPairing
          ? 'The pairing session could not be established. Generate a new code or try scanning the QR code instead.'
          : (error || SAFE_CONNECT_ERROR);
      const retryLabel = wasPairing ? 'Generate New Code' : 'Retry';

      return (
        <>
          <div style={{
            width: '64px', height: '64px', borderRadius: '50%',
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            marginBottom: '1.5rem'
          }}>
            {timedOut
              ? <WifiOff size={28} color="var(--danger)" />
              : <AlertTriangle size={28} color="var(--danger)" />
            }
          </div>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>
            {failTitle}
          </h2>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginBottom: '1.5rem', lineHeight: 1.5 }}>
            {failMessage}
          </p>
          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <button className="btn btn-primary" onClick={handleRetry} disabled={isRetrying}
              style={{ boxShadow: '0 4px 14px 0 rgba(99, 102, 241, 0.39)' }}>
              <RefreshCcw size={14} /> {retryLabel}
            </button>
            <button className="btn btn-outline" onClick={handleDisconnect}
              style={{ borderColor: 'rgba(239, 68, 68, 0.3)', color: 'var(--danger)' }}>
              Cancel
            </button>
          </div>
        </>
      );
    }

    // QR code and/or pairing code available
    if ((status === 'initializing' || status === 'waiting_for_qr') && (qrCode || pairingCode)) {
      return (
        <>
          {qrCode && (
            <>
              <div style={{ marginBottom: '1.5rem', padding: '1rem', background: '#fff', borderRadius: '12px' }}>
                <img src={qrCode} alt="WhatsApp QR Code" style={{ width: '256px', height: '256px' }} />
              </div>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>
                Scan to Connect
              </h2>
              <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>
                Open WhatsApp on your phone, tap Menu or Settings and select Linked Devices. Point your phone to this screen to capture the code.
              </p>
            </>
          )}

          {renderPairingCard()}

          <button className="btn btn-outline" onClick={handleDisconnect}
            style={{ borderColor: 'rgba(239, 68, 68, 0.3)', color: 'var(--danger)' }}>
            Cancel
          </button>
        </>
      );
    }

    // Waiting for QR (spinner)
    if (status === 'initializing' || status === 'waiting_for_qr') {
      return (
        <>
          <div style={{
            width: '64px', height: '64px', borderRadius: '50%',
            backgroundColor: 'rgba(126, 121, 250, 0.1)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            marginBottom: '1.5rem'
          }}>
            <RefreshCcw size={28} color="var(--accent-primary)" style={{ animation: 'spin 2s linear infinite' }} />
          </div>
          <style>{`@keyframes spin { 100% { transform: rotate(360deg); } }`}</style>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>
            {lastPhoneRef.current ? 'Generating Pairing Code...' : 'Generating QR Code...'}
          </h2>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
            Please wait while we initialize the WhatsApp client for your store.
          </p>
        </>
      );
    }

    // Default: disconnected — show connect prompt with method tabs
    const tabBase = {
      flex: 1,
      padding: '0.625rem',
      borderRadius: '8px',
      border: '1px solid var(--border-color)',
      background: 'transparent',
      color: 'var(--text-secondary)',
      cursor: 'pointer',
      fontSize: '0.8125rem',
      fontWeight: 600,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      gap: '0.375rem',
    };
    const tabActive = {
      ...tabBase,
      background: 'var(--bg-panel-hover)',
      borderColor: 'var(--accent-primary)',
      color: 'var(--text-primary)',
    };

    return (
      <>
        <div style={{
          width: '60px', height: '60px', borderRadius: '50%',
          backgroundColor: 'var(--bg-panel-hover)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          marginBottom: '1.5rem',
          border: '1px solid var(--border-color)'
        }}>
          <QrCode size={24} color="var(--text-secondary)" strokeWidth={1.5} />
        </div>
        <h2 style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>
          Connect WhatsApp
        </h2>
        <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', lineHeight: 1.5, marginBottom: '1.5rem' }}>
          Connect your WhatsApp account to enable the AI Copilot. Choose how you want to link your device.
        </p>

        {/* Method tabs */}
        <div style={{ display: 'flex', gap: '0.5rem', width: '100%', marginBottom: '1.5rem' }}>
          <button
            type="button"
            onClick={() => { setMethod('qr'); setPhoneError(null); }}
            style={method === 'qr' ? tabActive : tabBase}
          >
            <QrCode size={15} /> Scan QR Code
          </button>
          <button
            type="button"
            onClick={() => { setMethod('phone'); }}
            style={method === 'phone' ? tabActive : tabBase}
          >
            <Smartphone size={15} /> Link with Phone Number
          </button>
        </div>

        {method === 'phone' && (
          <div style={{ width: '100%', marginBottom: '1.5rem' }}>
            <label
              htmlFor="wa-phone-input"
              style={{ display: 'block', fontSize: '0.75rem', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '0.5rem', textAlign: 'left' }}
            >
              Phone Number (with country code)
            </label>
            <input
              id="wa-phone-input"
              type="tel"
              className="input"
              aria-label="Phone number"
              aria-invalid={phoneError ? 'true' : 'false'}
              placeholder="e.g. +92 300 1234567"
              value={phoneInput}
              onChange={(e) => { setPhoneInput(e.target.value); if (phoneError) setPhoneError(null); }}
              onKeyDown={(e) => { if (e.key === 'Enter') handleConnectPhone(); }}
              style={{ width: '100%' }}
            />
            {phoneError && (
              <p role="alert" style={{ fontSize: '0.75rem', color: 'var(--danger)', marginTop: '0.5rem', textAlign: 'left', lineHeight: 1.5 }}>
                {phoneError}
              </p>
            )}
          </div>
        )}

        {method === 'qr' ? (
          <button className="btn btn-primary" onClick={handleConnectQR} disabled={isRetrying}
            style={{ width: '100%', boxShadow: '0 4px 14px 0 rgba(99, 102, 241, 0.39)' }}>
            Generate QR Code
          </button>
        ) : (
          <button className="btn btn-primary" onClick={handleConnectPhone} disabled={isRetrying}
            style={{ width: '100%', boxShadow: '0 4px 14px 0 rgba(99, 102, 241, 0.39)' }}>
            Generate Pairing Code
          </button>
        )}
      </>
    );
  };

  return (
    <div style={{ flex: 1, padding: '0 2.5rem 2.5rem', display: 'flex', flexDirection: 'column' }}>
      <div className="grid-background" style={{
        flex: 1,
        backgroundColor: 'var(--bg-panel)',
        border: '1px solid var(--border-color)',
        borderRadius: '16px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        boxShadow: 'var(--shadow-md)',
        position: 'relative'
      }}>

        {/* The Card */}
        <div style={{
          backgroundColor: 'var(--bg-panel)',
          border: '1px solid var(--border-color)',
          borderRadius: '16px',
          padding: '3rem',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          maxWidth: '450px',
          textAlign: 'center',
          boxShadow: 'var(--shadow-md)',
          position: 'relative',
          zIndex: 10
        }}>
          {renderContent()}
        </div>

        {/* Subtle radial gradient behind the card for depth */}
        <div style={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          width: '600px',
          height: '600px',
          background: 'radial-gradient(circle, rgba(99, 102, 241, 0.08) 0%, transparent 70%)',
          pointerEvents: 'none',
          zIndex: 0
        }}></div>

      </div>
    </div>
  );
};

export default QRConnector;
