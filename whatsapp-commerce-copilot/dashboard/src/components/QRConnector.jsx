import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { API_URL } from '../config';
import { QrCode, RefreshCcw, AlertTriangle, WifiOff } from 'lucide-react';

const QR_TIMEOUT_MS = 90_000; // 90 seconds
const POLL_INTERVAL_MS = 5_000; // 5 seconds

const QRConnector = ({ storeId, status, setStatus }) => {
  const [qrCode, setQrCode] = useState(null);
  const [timedOut, setTimedOut] = useState(false);
  const [error, setError] = useState(null);
  const timeoutRef = useRef(null);
  const currentStatusRef = useRef(status);

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

  const [isRetrying, setIsRetrying] = useState(false);

  const handleRetry = async () => {
    if (isRetrying) return;
    setIsRetrying(true);
    setTimedOut(false);
    setError(null);
    setQrCode(null);

    // Clear old timeout to force a fresh one
    clearTimeout(timeoutRef.current);
    timeoutRef.current = null;

    try {
      const res = await axios.post(`${API_URL}/stores/${storeId}/whatsapp/connect`);
      setStatus(res.data?.status || 'initializing');
      if (res.data?.qr_code) {
        setQrCode(res.data.qr_code);
      }
    } catch (err) {
      const detail = err.response?.data?.detail || err.message;
      setError(detail);
      setStatus('failed');
    } finally {
      setIsRetrying(false);
    }
  };

  const handleDisconnect = async () => {
    try {
      await axios.delete(`${API_URL}/stores/${storeId}/whatsapp`);
      setStatus('disconnected');
      setQrCode(null);
      setTimedOut(false);
      setError(null);
    } catch (err) {
      console.error(err);
    }
  };

  const renderContent = () => {
    // Failed state
    if (status === 'failed' || timedOut) {
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
            {timedOut ? 'Connection Timed Out' : 'Connection Failed'}
          </h2>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginBottom: '1.5rem', lineHeight: 1.5 }}>
            {timedOut
              ? 'No QR code was received within the expected time. The Evolution API may be unavailable.'
              : (error || 'Something went wrong while connecting. Please try again.')
            }
          </p>
          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <button className="btn btn-primary" onClick={handleRetry}
              style={{ boxShadow: '0 4px 14px 0 rgba(99, 102, 241, 0.39)' }}>
              <RefreshCcw size={14} /> Retry
            </button>
            <button className="btn btn-outline" onClick={handleDisconnect}
              style={{ borderColor: 'rgba(239, 68, 68, 0.3)', color: 'var(--danger)' }}>
              Cancel
            </button>
          </div>
        </>
      );
    }

    // QR code available
    if ((status === 'initializing' || status === 'waiting_for_qr') && qrCode) {
      return (
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
            Generating QR Code...
          </h2>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
            Please wait while we initialize the WhatsApp client for your store.
          </p>
        </>
      );
    }

    // Default: disconnected — show connect prompt
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
        <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
          Click "Connect" in the sidebar to generate a QR code for your store.
        </p>
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
