import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { API_URL } from '../config';
import AddProductModal from './AddProductModal';

const ProductsView = ({ storeId }) => {
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);

  useEffect(() => {
    const fetchProducts = async () => {
      try {
        setLoading(true);
        const res = await axios.get(`${API_URL}/stores/${storeId}/products`);
        setProducts(res.data);
      } catch (err) {
        console.error('Failed to load products', err);
      } finally {
        setLoading(false);
      }
    };

    fetchProducts();
  }, [storeId]);

  const refreshProducts = async () => {
    try {
      const res = await axios.get(`${API_URL}/stores/${storeId}/products`);
      setProducts(res.data);
    } catch (err) {
      console.error('Failed to reload products', err);
    }
  };

  const handleDeleteProduct = async (productId) => {
    if (!window.confirm("Are you sure you want to delete this product?")) return;
    try {
      await axios.delete(`${API_URL}/stores/${storeId}/products/${productId}`);
      refreshProducts();
    } catch (err) {
      console.error('Failed to delete product', err);
      alert('Failed to delete product.');
    }
  };

  const handleUpdateStock = async (productId, currentStock, change) => {
    const newStock = Math.max(0, currentStock + change);
    try {
      await axios.patch(`${API_URL}/stores/${storeId}/products/${productId}/stock`, {
        stock: newStock
      });
      refreshProducts();
    } catch (err) {
      console.error('Failed to update stock', err);
      alert('Failed to update stock.');
    }
  };

  const handleImageUpload = async (productId, e) => {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('image', file);

    try {
      await axios.put(`${API_URL}/stores/${storeId}/products/${productId}/image`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      refreshProducts();
    } catch (err) {
      console.error('Failed to update image', err);
      alert('Failed to update image.');
    }
  };

  const handleDeleteImage = async (productId) => {
    if (!window.confirm("Remove image?")) return;
    try {
      await axios.delete(`${API_URL}/stores/${storeId}/products/${productId}/image`);
      refreshProducts();
    } catch (err) {
      console.error('Failed to delete image', err);
      alert('Failed to delete image.');
    }
  };

  // Helper to generate a dummy gradient based on category
  const getGradient = (category) => {
    if (category.toLowerCase().includes('sneaker')) {
      return 'linear-gradient(to bottom, #f1f5f9, #e2e8f0)';
    } else if (category.toLowerCase().includes('loafer')) {
      return 'linear-gradient(to bottom, #ffedd5, #fed7aa)';
    } else if (category.toLowerCase().includes('kurta')) {
      return 'linear-gradient(to bottom, #ccfbf1, #99f6e4)';
    }
    return 'linear-gradient(to bottom, #f1f5f9, #e2e8f0)';
  };

  return (
    <div style={{ flex: 1, padding: '0 2.5rem 2.5rem', overflowY: 'auto' }}>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '1.5rem' }}>
        <button
          onClick={() => setShowAddModal(true)}
          style={{
            padding: '0.5rem 1rem',
            borderRadius: '8px',
            background: 'var(--accent-primary)',
            color: '#fff',
            border: 'none',
            fontWeight: 500,
            cursor: 'pointer',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
          }}
        >
          + Add Product
        </button>
      </div>

      {loading ? (
        <div style={{ color: 'var(--text-secondary)' }}>Loading products...</div>
      ) : products.length === 0 ? (
        <div className="grid-background" style={{
          padding: '3rem',
          textAlign: 'center',
          color: 'var(--text-secondary)',
          background: 'var(--bg-panel)',
          borderRadius: '16px',
          border: '1px solid var(--border-color)'
        }}>
          No products found for this store.
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '2rem' }}>
          {products.map(product => (
            <div key={product.id} style={{
              background: 'var(--bg-panel)',
              borderRadius: '16px',
              border: '1px solid var(--border-color)',
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
              boxShadow: 'var(--shadow-md)'
            }}>

              {/* Image Placeholder or Actual Image */}
              <div style={{
                height: '180px',
                background: product.image_url ? '#fff' : getGradient(product.category),
                position: 'relative',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                overflow: 'hidden'
              }}>
                {product.image_url ? (
                  <img
                    src={product.image_url.startsWith('http') ? product.image_url : `${API_URL.replace('/api', '')}${product.image_url}`}
                    alt={product.name}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  />
                ) : (
                  <>
                    {/* Decorative circle to simulate studio lighting */}
                    <div style={{
                      position: 'absolute',
                      width: '150px',
                      height: '150px',
                      background: 'radial-gradient(circle, rgba(0,0,0,0.05) 0%, transparent 70%)',
                      top: '10%',
                      left: '50%',
                      transform: 'translateX(-50%)'
                    }}></div>

                    <span style={{ color: 'rgba(0,0,0,0.08)', fontWeight: 600, letterSpacing: '2px', textTransform: 'uppercase' }}>
                      {product.category}
                    </span>
                  </>
                )}

                <span style={{
                  position: 'absolute',
                  top: '1rem',
                  right: '1rem',
                  fontSize: '0.7rem',
                  background: 'rgba(255,255,255,0.7)',
                  backdropFilter: 'blur(4px)',
                  color: 'var(--text-primary)',
                  padding: '0.3rem 0.6rem',
                  borderRadius: '12px',
                  border: '1px solid rgba(0,0,0,0.05)',
                  boxShadow: 'var(--shadow-sm)'
                }}>
                  {product.category}
                </span>

                <div style={{
                  position: 'absolute',
                  bottom: '0.5rem',
                  right: '0.5rem',
                  display: 'flex',
                  gap: '0.5rem'
                }}>
                  <label htmlFor={`img-upload-${product.id}`} style={{
                    fontSize: '0.7rem',
                    background: 'rgba(255,255,255,0.9)',
                    color: 'var(--text-primary)',
                    padding: '0.3rem 0.6rem',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    border: '1px solid var(--border-color)',
                    fontWeight: 600
                  }}>
                    Replace Image
                  </label>
                  <input
                    type="file"
                    id={`img-upload-${product.id}`}
                    style={{ display: 'none' }}
                    accept="image/*"
                    onChange={(e) => handleImageUpload(product.id, e)}
                  />
                  {product.image_url && (
                    <button
                      onClick={() => handleDeleteImage(product.id)}
                      style={{
                        fontSize: '0.7rem',
                        background: 'var(--danger)',
                        color: 'white',
                        padding: '0.3rem 0.6rem',
                        borderRadius: '4px',
                        cursor: 'pointer',
                        border: 'none',
                        fontWeight: 600
                      }}
                    >
                      Remove
                    </button>
                  )}
                </div>
              </div>

              {/* Product Details */}
              <div style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', flex: 1 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.5rem' }}>
                  <h3 style={{ fontSize: '1.125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                    {product.name}
                  </h3>
                  <button
                    onClick={() => handleDeleteProduct(product.id)}
                    style={{ color: 'var(--danger)', background: 'rgba(239, 68, 68, 0.1)', border: 'none', borderRadius: '4px', padding: '0.2rem 0.5rem', cursor: 'pointer', fontSize: '0.7rem', fontWeight: 600 }}
                  >
                    Delete
                  </button>
                </div>

                <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginBottom: '1.25rem', lineHeight: 1.5, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                  {product.description || `Premium ${product.category} for your everyday style.`}
                </p>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                  <span style={{ fontWeight: 600, fontSize: '0.875rem', color: 'var(--accent-primary)' }}>
                    Rs. {product.base_price.toLocaleString()}
                  </span>
                  <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                    SKU: {product.sku}
                  </span>
                </div>

                <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: '1.25rem' }}>
                  <h4 style={{ fontSize: '0.7rem', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '1rem', fontWeight: 600, letterSpacing: '0.5px' }}>
                    Variants
                  </h4>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                    {product.variants && product.variants.map(v => (
                      <div key={v.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.875rem' }}>
                        <span style={{ color: 'var(--text-primary)' }}>
                          <span style={{ textTransform: 'capitalize' }}>{v.color || 'Default'}</span>
                          {v.size && <span style={{ color: 'var(--text-muted)', margin: '0 0.4rem' }}>•</span>}
                          {v.size && <span>{v.size}</span>}
                        </span>

                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <button onClick={() => handleUpdateStock(product.id, v.stock, -1)} style={{ background: 'var(--bg-panel-hover)', border: '1px solid var(--border-color)', borderRadius: '4px', width: '24px', height: '24px', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-secondary)' }}>-</button>
                          <span style={{ color: v.stock > 0 ? 'var(--text-secondary)' : 'var(--danger)', fontSize: '0.8rem', fontWeight: 600, minWidth: '1.5rem', textAlign: 'center' }}>
                            {v.stock > 0 ? v.stock : 'Out'}
                          </span>
                          <button onClick={() => handleUpdateStock(product.id, v.stock, 1)} style={{ background: 'var(--bg-panel-hover)', border: '1px solid var(--border-color)', borderRadius: '4px', width: '24px', height: '24px', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-secondary)' }}>+</button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

            </div>
          ))}
        </div>
      )}

      {showAddModal && (
        <AddProductModal
          storeId={storeId}
          onClose={() => setShowAddModal(false)}
          onProductAdded={refreshProducts}
        />
      )}
    </div>
  );
};

export default ProductsView;
