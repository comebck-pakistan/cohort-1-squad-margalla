import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { API_URL, STORE_ID } from './config';
import Sidebar from './components/Sidebar';
import ConversationView from './components/ConversationView';
import OrdersView from './components/OrdersView';
import CategoriesView from './components/CategoriesView';
import QRConnector from './components/QRConnector';
import { Bell, UserCircle } from 'lucide-react';
import './index.css';

function App() {
  const [currentStore, setCurrentStore] = useState(STORE_ID);
  const [storeData, setStoreData] = useState(null);
  const [whatsappStatus, setWhatsappStatus] = useState('disconnected');
  const [connectedNumber, setConnectedNumber] = useState(null);
  const [activeTab, setActiveTab] = useState('orders'); // Matching the screenshot default

  // Fetch store details & whatsapp status
  useEffect(() => {
    const fetchStore = async () => {
      try {
        const res = await axios.get(`${API_URL}/stores/${currentStore}`);
        setStoreData(res.data);
      } catch (err) {
        console.error("Failed to load store", err);
      }
    };

    const fetchWhatsapp = async () => {
      try {
        const res = await axios.get(`${API_URL}/stores/${currentStore}/whatsapp/status`);
        setWhatsappStatus(res.data.status);
        if (res.data.phone_number) {
          setConnectedNumber(res.data.phone_number);
        } else {
          setConnectedNumber(null);
        }
      } catch (err) {
        console.error("Failed to load WA status", err);
      }
    };

    fetchStore();
    fetchWhatsapp();
  }, [currentStore]);

  // Handle background polling when not in QR connection phase
  useEffect(() => {
    let isMounted = true;
    let pollTimer = null;
    let isPolling = false;

    const pollWhatsapp = async () => {
      if (!isMounted || isPolling) return;
      isPolling = true;
      try {
        const res = await axios.get(`${API_URL}/stores/${currentStore}/whatsapp/status`);
        if (!isMounted) return;
        setWhatsappStatus(res.data.status);
        if (res.data.phone_number) {
          setConnectedNumber(res.data.phone_number);
        } else {
          setConnectedNumber(null);
        }
      } catch (err) {
        console.error("Failed to poll WA status", err);
      } finally {
        isPolling = false;
        if (isMounted) {
          pollTimer = setTimeout(pollWhatsapp, 5000);
        }
      }
    };

    if (whatsappStatus !== 'initializing' && whatsappStatus !== 'waiting_for_qr') {
      pollTimer = setTimeout(pollWhatsapp, 5000);
    }

    return () => {
      isMounted = false;
      clearTimeout(pollTimer);
    };
  }, [currentStore, whatsappStatus]);

  return (
    <div style={{ display: 'flex', height: '100vh', width: '100vw', overflow: 'hidden' }}>
      <Sidebar
        currentStore={currentStore}
        setCurrentStore={setCurrentStore}
        storeData={storeData}
        whatsappStatus={whatsappStatus}
        setWhatsappStatus={setWhatsappStatus}
        connectedNumber={connectedNumber}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
      />

      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', backgroundColor: 'var(--bg-main)' }}>
        {/* Header */}
        <header style={{
          padding: '2rem 2.5rem 1.5rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start'
        }}>
          <div>
            <h1 style={{ fontSize: '1.75rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.25rem' }}>
              {activeTab === 'conversations' ? 'Conversations' :
               activeTab === 'orders' ? 'Orders' : 'Products & Catalog'}
            </h1>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
              {storeData ? storeData.business_name : 'Loading...'}
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem', color: 'var(--text-secondary)' }}>
            <button style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer' }}>
              <Bell size={20} />
            </button>
            <button style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer' }}>
              <UserCircle size={22} />
            </button>
          </div>
        </header>

        {/* Main Content Area */}
        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', position: 'relative' }}>
          {whatsappStatus !== 'connected' && activeTab === 'conversations' ? (
            <QRConnector storeId={currentStore} status={whatsappStatus} setStatus={setWhatsappStatus} />
          ) : (
            <>
              {activeTab === 'conversations' && <ConversationView storeId={currentStore} />}
              {activeTab === 'orders' && <OrdersView storeId={currentStore} />}
              {activeTab === 'products' && <CategoriesView storeId={currentStore} />}
            </>
          )}
        </div>
      </main>
    </div>
  );
}

export default App;
