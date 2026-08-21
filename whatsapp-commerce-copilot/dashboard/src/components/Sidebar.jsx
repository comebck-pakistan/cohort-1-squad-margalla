import React from 'react';
import axios from 'axios';
import { API_URL } from '../config';
import { MessageSquare, Package, ShoppingCart, Power, Settings, HelpCircle, Phone, LayoutDashboard } from 'lucide-react';

const Sidebar = ({ currentStore, setCurrentStore, storeData, whatsappStatus, setWhatsappStatus, connectedNumber, activeTab, setActiveTab }) => {
  const isConnecting = whatsappStatus === 'initializing' || whatsappStatus === 'waiting_for_qr';

  const handleConnect = () => {
    setActiveTab('conversations');
  };

  const handleDisconnect = async () => {
    try {
      await axios.delete(`${API_URL}/stores/${currentStore}/whatsapp`);
      setWhatsappStatus('disconnected');
    } catch (err) {
      console.error(err);
    }
  };

  const navItems = [
    { id: 'overview', label: 'Overview', icon: <LayoutDashboard size={18} /> },
    { id: 'conversations', label: 'Conversations', icon: <MessageSquare size={18} /> },
    { id: 'orders', label: 'Orders', icon: <ShoppingCart size={18} /> },
    { id: 'products', label: 'Catalog', icon: <Package size={18} /> },
  ];

  return (
    <aside style={{ 
      width: '260px', 
      backgroundColor: 'var(--bg-sidebar)', 
      borderRight: '1px solid var(--border-color)', 
      display: 'flex', 
      flexDirection: 'column', 
      padding: '1.5rem 1rem' 
    }}>
      <div style={{ padding: '0 0.5rem', marginBottom: '2rem' }}>
        <h2 style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.25rem' }}>Copilot Dashboard</h2>
        <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>WhatsApp AI Agent</p>
      </div>

      <div style={{ marginBottom: '1.5rem', padding: '0 0.5rem' }}>
        <label style={{ display: 'block', fontSize: '0.7rem', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '0.5rem', fontWeight: 600, letterSpacing: '0.5px' }}>Active Store</label>
        <select 
          value={currentStore} 
          onChange={(e) => setCurrentStore(e.target.value)}
          style={{ width: '100%', border: 'none', backgroundColor: 'var(--bg-main)', color: 'var(--text-primary)', fontWeight: 500 }}
        >
          <option value="demo-store-fashion">Noor Fashion House</option>
          <option value="demo-store-shoes">StepUp Footwear</option>
        </select>
      </div>

      <div style={{ marginBottom: '2rem', padding: '1rem', backgroundColor: 'var(--bg-sidebar)', borderRadius: '12px', border: '1px solid var(--border-color)', margin: '0 0.5rem 2rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-primary)' }}>
              <MessageSquare size={16} />
              <span style={{ fontSize: '0.875rem', fontWeight: 600 }}>WhatsApp</span>
            </div>
            {whatsappStatus === 'connected' && connectedNumber && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', color: 'var(--text-secondary)' }}>
                <Phone size={12} />
                <span style={{ fontSize: '0.75rem', fontFamily: 'monospace' }}>+{connectedNumber.replace('@s.whatsapp.net', '')}</span>
              </div>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
            <span className={`status-dot ${whatsappStatus}`}></span>
            {whatsappStatus === 'connected' && <span style={{fontSize: '0.7rem', color: 'var(--success)', fontWeight: 600}}>Ready</span>}
            {whatsappStatus === 'failed' && <span style={{fontSize: '0.7rem', color: 'var(--danger)', fontWeight: 600}}>Failed</span>}
          </div>
        </div>
        
        {whatsappStatus === 'connected' ? (
          <button className="btn btn-outline" style={{ width: '100%', borderColor: 'rgba(239, 68, 68, 0.3)', color: 'var(--danger)' }} onClick={handleDisconnect}>
            <Power size={14} /> Disconnect
          </button>
        ) : whatsappStatus === 'failed' ? (
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button className="btn btn-primary" style={{ flex: 1, boxShadow: '0 4px 14px 0 rgba(99, 102, 241, 0.39)' }} onClick={handleConnect}>
              <Power size={14} /> Retry
            </button>
            <button className="btn btn-outline" style={{ borderColor: 'rgba(239, 68, 68, 0.3)', color: 'var(--danger)', padding: '0.5rem' }} onClick={handleDisconnect}>
              ✕
            </button>
          </div>
        ) : isConnecting ? (
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button className="btn btn-primary" style={{ flex: 1, opacity: 0.7 }} disabled>
              <Power size={14} /> Scan QR Code
            </button>
            <button className="btn btn-outline" style={{ borderColor: 'rgba(239, 68, 68, 0.3)', color: 'var(--danger)', padding: '0.5rem' }} onClick={handleDisconnect}>
              ✕
            </button>
          </div>
        ) : (
          <button className="btn btn-primary" style={{ width: '100%', boxShadow: '0 4px 14px 0 rgba(99, 102, 241, 0.39)' }} onClick={handleConnect}>
            <Power size={14} /> Connect
          </button>
        )}
      </div>

      <nav style={{ flex: 1, padding: '0 0.5rem' }}>
        <label style={{ display: 'block', fontSize: '0.7rem', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '0.75rem', fontWeight: 600, letterSpacing: '0.5px' }}>Menu</label>
        <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          {navItems.map(item => (
            <li key={item.id}>
              <button 
                onClick={() => setActiveTab(item.id)}
                style={{ 
                  width: '100%', 
                  display: 'flex', 
                  alignItems: 'center', 
                  gap: '0.75rem', 
                  padding: '0.6rem 1rem', 
                  background: activeTab === item.id ? 'rgba(99, 102, 241, 0.1)' : 'transparent',
                  color: activeTab === item.id ? 'var(--accent-primary)' : 'var(--text-secondary)',
                  border: 'none',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  textAlign: 'left',
                  fontSize: '0.875rem',
                  fontWeight: activeTab === item.id ? 600 : 500,
                  transition: 'all 0.15s ease'
                }}
              >
                {item.icon}
                {item.label}
              </button>
            </li>
          ))}
        </ul>
      </nav>

      <div style={{ padding: '1rem 1rem 0', borderTop: '1px solid var(--border-color)', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
        <button style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.6rem 0.5rem', background: 'transparent', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: '0.875rem', fontWeight: 500 }}>
          <Settings size={18} /> Settings
        </button>
        <button style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.6rem 0.5rem', background: 'transparent', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: '0.875rem', fontWeight: 500 }}>
          <HelpCircle size={18} /> Support
        </button>
      </div>
    </aside>
  );
};

export default Sidebar;
