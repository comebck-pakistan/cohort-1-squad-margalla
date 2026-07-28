import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { API_URL } from '../config';
import { QrCode, RefreshCcw } from 'lucide-react';

const QRConnector = ({ storeId, status, setStatus }) => {
  const [qrCode, setQrCode] = useState(null);

  useEffect(() => {
    let interval;
    if (status === 'initializing' || status === 'waiting_for_qr') {
      const checkStatus = async () => {
        try {
          const res = await axios.get(`${API_URL}/stores/${storeId}/whatsapp/status`);
          setStatus(res.data.status);
          if (res.data.qr_code) {
            setQrCode(res.data.qr_code);
          }
        } catch (err) {
          console.error(err);
        }
      };

      interval = setInterval(checkStatus, 3000);
    }
    
    return () => clearInterval(interval);
  }, [status, storeId, setStatus]);

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
          
          {(status === 'initializing' || status === 'waiting_for_qr') && qrCode ? (
            <>
              <div style={{ marginBottom: '1.5rem', padding: '1rem', background: '#fff', borderRadius: '12px' }}>
                <img src={qrCode} alt="WhatsApp QR Code" style={{ width: '256px', height: '256px' }} />
              </div>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>
                Scan to Connect
              </h2>
              <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                Open WhatsApp on your phone, tap Menu or Settings and select Linked Devices. Point your phone to this screen to capture the code.
              </p>
            </>
          ) : (status === 'initializing' || status === 'waiting_for_qr') && !qrCode ? (
            <>
              <div style={{ 
                width: '64px', 
                height: '64px', 
                borderRadius: '50%', 
                backgroundColor: 'rgba(126, 121, 250, 0.1)', 
                display: 'flex', 
                alignItems: 'center', 
                justifyContent: 'center',
                marginBottom: '1.5rem'
              }}>
                <RefreshCcw size={28} color="var(--accent-primary)" className="animate-spin" style={{ animation: 'spin 2s linear infinite' }} />
              </div>
              <style>{`@keyframes spin { 100% { transform: rotate(360deg); } }`}</style>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>
                Generating QR Code...
              </h2>
              <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                Please wait while we initialize the WhatsApp client for your store.
              </p>
            </>
          ) : (
            <>
              <div style={{ 
                width: '60px', 
                height: '60px', 
                borderRadius: '50%', 
                backgroundColor: 'var(--bg-panel-hover)', 
                display: 'flex', 
                alignItems: 'center', 
                justifyContent: 'center',
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
          )}
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
