import React, { useState } from 'react';
import axios from 'axios';
import { API_URL } from '../config';

const AddProductModal = ({ storeId, onClose, onProductAdded }) => {
  const [formData, setFormData] = useState({
    name: '',
    price: '',
    stock: '1',
    category: '',
    description: '',
    labels: '',
  });
  const [image, setImage] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value
    });
  };

  const handleImageChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setImage(e.target.files[0]);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.name || !formData.price) {
      setError("Name and Price are required.");
      return;
    }
    
    setLoading(true);
    setError(null);
    
    const data = new FormData();
    data.append('name', formData.name);
    data.append('price', formData.price);
    data.append('stock', formData.stock || '1');
    if (formData.category) data.append('category', formData.category);
    if (formData.description) data.append('description', formData.description);
    if (formData.labels) data.append('labels', formData.labels);
    if (image) data.append('image', image);

    try {
      await axios.post(`${API_URL}/stores/${storeId}/products`, data, {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      });
      onProductAdded();
      onClose();
    } catch (err) {
      console.error(err);
      setError("Failed to add product. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      position: 'fixed',
      top: 0, left: 0, right: 0, bottom: 0,
      backgroundColor: 'rgba(0,0,0,0.5)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 100,
      backdropFilter: 'blur(4px)'
    }}>
      <div style={{
        background: 'var(--bg-panel)',
        borderRadius: '16px',
        border: '1px solid var(--border-color)',
        padding: '2rem',
        width: '100%',
        maxWidth: '500px',
        maxHeight: '90vh',
        overflowY: 'auto'
      }}>
        <h2 style={{ fontSize: '1.25rem', marginBottom: '1.5rem', fontWeight: 600 }}>Add New Product</h2>
        
        {error && (
          <div style={{ color: '#ef4444', marginBottom: '1rem', fontSize: '0.875rem' }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Product Image</label>
            <input 
              type="file" 
              accept="image/*" 
              onChange={handleImageChange}
              style={{
                background: 'var(--bg-card)',
                padding: '0.75rem',
                borderRadius: '8px',
                border: '1px solid var(--border-color)',
                width: '100%',
                color: 'var(--text-primary)'
              }}
            />
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Product Name *</label>
            <input 
              type="text" 
              name="name" 
              value={formData.name} 
              onChange={handleChange}
              placeholder="e.g. Blue Kurta"
              style={{
                background: 'var(--bg-card)',
                padding: '0.75rem',
                borderRadius: '8px',
                border: '1px solid var(--border-color)',
                width: '100%',
                color: 'var(--text-primary)'
              }}
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Price (Rs.) *</label>
              <input 
                type="number" 
                name="price" 
                value={formData.price} 
                onChange={handleChange}
                placeholder="e.g. 1500"
                style={{
                  background: 'var(--bg-card)',
                  padding: '0.75rem',
                  borderRadius: '8px',
                  border: '1px solid var(--border-color)',
                  width: '100%',
                  color: 'var(--text-primary)'
                }}
              />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Stock Quantity *</label>
              <input 
                type="number" 
                name="stock" 
                value={formData.stock} 
                onChange={handleChange}
                min="0"
                placeholder="e.g. 10"
                style={{
                  background: 'var(--bg-card)',
                  padding: '0.75rem',
                  borderRadius: '8px',
                  border: '1px solid var(--border-color)',
                  width: '100%',
                  color: 'var(--text-primary)'
                }}
              />
            </div>
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Category</label>
            <input 
              type="text" 
              name="category" 
              value={formData.category} 
              onChange={handleChange}
              placeholder="e.g. Kurta"
              style={{
                background: 'var(--bg-card)',
                padding: '0.75rem',
                borderRadius: '8px',
                border: '1px solid var(--border-color)',
                width: '100%',
                color: 'var(--text-primary)'
              }}
            />
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Labels / Search Tags (comma separated)</label>
            <input 
              type="text" 
              name="labels" 
              value={formData.labels} 
              onChange={handleChange}
              placeholder="e.g. blue dress, summer wear, cotton"
              style={{
                background: 'var(--bg-card)',
                padding: '0.75rem',
                borderRadius: '8px',
                border: '1px solid var(--border-color)',
                width: '100%',
                color: 'var(--text-primary)'
              }}
            />
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>These are used by the AI to find the product when a customer asks.</p>
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Description</label>
            <textarea 
              name="description" 
              value={formData.description} 
              onChange={handleChange}
              placeholder="Short product description"
              style={{
                background: 'var(--bg-card)',
                padding: '0.75rem',
                borderRadius: '8px',
                border: '1px solid var(--border-color)',
                width: '100%',
                color: 'var(--text-primary)',
                minHeight: '80px',
                resize: 'vertical'
              }}
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '1rem', marginTop: '1rem' }}>
            <button 
              type="button" 
              onClick={onClose}
              style={{
                padding: '0.75rem 1.5rem',
                borderRadius: '8px',
                background: 'transparent',
                border: '1px solid var(--border-color)',
                color: 'var(--text-primary)',
                cursor: 'pointer'
              }}
            >
              Cancel
            </button>
            <button 
              type="submit" 
              disabled={loading}
              style={{
                padding: '0.75rem 1.5rem',
                borderRadius: '8px',
                background: 'var(--accent-primary)',
                border: 'none',
                color: '#fff',
                cursor: loading ? 'not-allowed' : 'pointer',
                opacity: loading ? 0.7 : 1
              }}
            >
              {loading ? 'Adding...' : 'Add Product'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default AddProductModal;
