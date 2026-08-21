import React, { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import { API_URL } from '../config';
import { ShoppingBag, RefreshCw } from 'lucide-react';

// Orders arrive over WhatsApp while the seller is looking at this screen, so the
// list refreshes on its own instead of only on mount.
const REFRESH_MS = 15000;
const INVALID_STORED_NAMES = new Set([
  'order', 'confirmed', 'confirm', 'yes', 'no', 'ok', 'okay', 'cod',
  'hello', 'hi', 'send picture', 'name not provided',
]);

export const displayCustomerName = (value) => {
  const name = String(value || '').trim();
  return !name || INVALID_STORED_NAMES.has(name.toLowerCase())
    ? 'Name not provided'
    : name;
};

const OrdersView = ({ storeId }) => {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [storeName, setStoreName] = useState(storeId === 'demo-store-shoes' ? 'StepUp Footwear' : 'Noor Fashion House');
  // Ignore a slow response that lands after the seller switched stores.
  const activeStore = useRef(storeId);

  const fetchOrders = useCallback(async ({ showSpinner = true } = {}) => {
    const requestedStore = storeId;
    try {
      if (showSpinner) setLoading(true);
      const res = await axios.get(`${API_URL}/stores/${requestedStore}/orders`);
      if (activeStore.current !== requestedStore) return;
      setOrders(res.data);
    } catch (err) {
      console.error('Failed to load orders', err);
    } finally {
      if (activeStore.current === requestedStore && showSpinner) setLoading(false);
    }
  }, [storeId]);

  useEffect(() => {
    activeStore.current = storeId;
    setOrders([]);

    // Quick store name lookup for the empty state
    if (storeId === 'demo-store-shoes') setStoreName('StepUp Footwear');
    else setStoreName('Noor Fashion House');

    fetchOrders();
    const timer = setInterval(() => fetchOrders({ showSpinner: false }), REFRESH_MS);
    return () => clearInterval(timer);
  }, [storeId, fetchOrders]);

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
        boxShadow: 'var(--shadow-md)'
      }}>
        {loading ? (
          <div style={{ color: 'var(--text-secondary)' }}>Loading orders...</div>
        ) : orders.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', maxWidth: '400px', textAlign: 'center' }}>
            <div style={{ 
              width: '80px', 
              height: '80px', 
              borderRadius: '50%', 
              backgroundColor: 'var(--bg-panel-hover)', 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center',
              marginBottom: '1.5rem',
              border: '1px solid var(--border-color)'
            }}>
              <ShoppingBag size={32} color="var(--text-secondary)" strokeWidth={1.5} />
            </div>
            
            <h2 style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.75rem' }}>
              No orders found
            </h2>
            
            <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: '2rem' }}>
              There are currently no active or historical orders for {storeName}. Once customers interact via WhatsApp, their orders will appear here.
            </p>
            
            <button className="btn btn-primary" onClick={() => fetchOrders()} style={{
              padding: '0.6rem 1.25rem',
              fontWeight: 600,
              boxShadow: '0 4px 14px 0 rgba(99, 102, 241, 0.39)'
            }}>
              <RefreshCw size={16} /> Sync Orders Now
            </button>
          </div>
        ) : (
          <div style={{ width: '100%', height: '100%', padding: '1.5rem', overflowY: 'auto' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
              <span style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                {orders.length} {orders.length === 1 ? 'order' : 'orders'}
              </span>
              <button className="btn" onClick={() => fetchOrders()} aria-label="Refresh orders" style={{
                padding: '0.4rem 0.9rem', fontSize: '0.8125rem', fontWeight: 600,
                border: '1px solid var(--border-color)', borderRadius: '8px',
                background: 'var(--bg-panel-hover)', color: 'var(--text-secondary)',
                display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer',
              }}>
                <RefreshCw size={14} /> Refresh
              </button>
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-color)' }}>
                  <th style={{ padding: '1rem', color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Order ID</th>
                  <th style={{ padding: '1rem', color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Customer</th>
                  <th style={{ padding: '1rem', color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Items</th>
                  <th style={{ padding: '1rem', color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Total</th>
                  <th style={{ padding: '1rem', color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Payment</th>
                  <th style={{ padding: '1rem', color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Date</th>
                  <th style={{ padding: '1rem', color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {orders.map(order => (
                  <tr key={order.id} style={{ borderBottom: '1px solid var(--border-color)', transition: 'background 0.2s' }}>
                    <td style={{ padding: '1rem', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>{order.id.substring(0, 8)}...</td>
                    <td style={{ padding: '1rem' }}>
                      <div style={{ fontWeight: 500, fontSize: '0.875rem', color: 'var(--text-primary)' }}>{displayCustomerName(order.customer_name)}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{order.customer_phone}</div>
                    </td>
                    <td style={{ padding: '1rem', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                      {(order.items || []).length === 0 ? '—' : (order.items || []).map((it, i) => (
                        <div key={i}>
                          <span style={{ color: 'var(--text-primary)' }}>{it.product_name}</span>
                          {it.variant_description ? ` (${it.variant_description})` : ''} × {it.quantity}
                        </div>
                      ))}
                    </td>
                    <td style={{ padding: '1rem', fontWeight: 600, fontSize: '0.875rem', color: 'var(--text-primary)' }}>Rs. {order.total_amount.toLocaleString()}</td>
                    <td style={{ padding: '1rem', fontSize: '0.875rem' }}>
                      <span style={{ background: 'var(--bg-main)', border: '1px solid var(--border-color)', padding: '0.2rem 0.5rem', borderRadius: '6px', color: 'var(--text-secondary)' }}>{order.payment_method}</span>
                    </td>
                    <td style={{ padding: '1rem', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                      {new Date(order.created_at).toLocaleDateString()}
                    </td>
                    <td style={{ padding: '1rem' }}>
                      <span style={{ 
                        background: order.status === 'pending' ? 'rgba(245, 158, 11, 0.1)' : 'rgba(16, 185, 129, 0.1)',
                        color: order.status === 'pending' ? '#F59E0B' : 'var(--success)',
                        border: `1px solid ${order.status === 'pending' ? 'rgba(245, 158, 11, 0.2)' : 'rgba(16, 185, 129, 0.2)'}`,
                        padding: '0.25rem 0.75rem',
                        borderRadius: '12px',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        textTransform: 'capitalize'
                      }}>
                        {order.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default OrdersView;
