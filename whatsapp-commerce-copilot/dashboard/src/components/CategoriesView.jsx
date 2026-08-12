import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { API_URL } from '../config';
import AddProductModal from './AddProductModal';

const IMG_BASE = API_URL.replace('/api', '');
const imgSrc = (url) => (url && url.startsWith('http') ? url : `${IMG_BASE}${url}`);

/**
 * Catalog view: seller's categories as folder cards, drill into a category to
 * manage its products. Store isolation is inherent (all calls are store-scoped);
 * switching stores resets state and ignores late responses from the old store.
 */
const CategoriesView = ({ storeId }) => {
  const [categories, setCategories] = useState([]);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [openCat, setOpenCat] = useState(null); // {id|null, name} — null id = Uncategorized
  const [showNew, setShowNew] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [editing, setEditing] = useState(null); // category id being renamed
  const [editName, setEditName] = useState('');
  const [addProductFor, setAddProductFor] = useState(null); // {id, name} | null

  // Guards against late responses from a previously-selected store clobbering
  // the current store's data.
  const activeStore = useRef(storeId);

  const load = useCallback(async () => {
    const requestStore = storeId;
    setLoading(true);
    setError(null);
    try {
      const [cats, prods] = await Promise.all([
        axios.get(`${API_URL}/stores/${storeId}/categories`),
        axios.get(`${API_URL}/stores/${storeId}/products`),
      ]);
      if (activeStore.current !== requestStore) return; // store switched — ignore
      setCategories(cats.data);
      setProducts(prods.data);
    } catch (err) {
      if (activeStore.current !== requestStore) return;
      console.error('Failed to load catalog', err);
      setError('Failed to load catalog.');
    } finally {
      if (activeStore.current === requestStore) setLoading(false);
    }
  }, [storeId]);

  // Reset all view state and reload whenever the store changes.
  useEffect(() => {
    activeStore.current = storeId;
    setOpenCat(null);
    setShowNew(false);
    setEditing(null);
    setAddProductFor(null);
    setCategories([]);
    setProducts([]);
    load();
  }, [storeId, load]);

  const uncategorized = products.filter((p) => !p.category_id);

  const createCategory = async () => {
    const name = newName.trim();
    if (!name) return;
    try {
      await axios.post(`${API_URL}/stores/${storeId}/categories`, {
        name, description: newDesc.trim() || null,
      });
      setNewName(''); setNewDesc(''); setShowNew(false);
      load();
    } catch (err) {
      setError(err.response?.status === 409
        ? 'A category with this name already exists.'
        : 'Failed to create category.');
    }
  };

  const renameCategory = async (id) => {
    const name = editName.trim();
    if (!name) return;
    try {
      await axios.patch(`${API_URL}/stores/${storeId}/categories/${id}`, { name });
      setEditing(null);
      load();
    } catch (err) {
      setError(err.response?.status === 409 ? 'Name already in use.' : 'Failed to rename category.');
    }
  };

  const toggleActive = async (cat) => {
    try {
      await axios.patch(`${API_URL}/stores/${storeId}/categories/${cat.id}`, { is_active: !cat.is_active });
      load();
    } catch {
      setError('Failed to update category.');
    }
  };

  const deleteCategory = async (cat) => {
    if (!window.confirm(`Delete category "${cat.name}"?`)) return;
    try {
      await axios.delete(`${API_URL}/stores/${storeId}/categories/${cat.id}`);
      load();
    } catch (err) {
      if (err.response?.status === 409) {
        alert('This category is not empty. Move or remove its products first.');
      } else {
        setError('Failed to delete category.');
      }
    }
  };

  const uploadCategoryImage = async (id, e) => {
    const file = e.target.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('image', file);
    try {
      await axios.post(`${API_URL}/stores/${storeId}/categories/${id}/image`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      load();
    } catch {
      setError('Failed to upload category image.');
    }
  };

  const moveProduct = async (productId, categoryId) => {
    try {
      await axios.patch(`${API_URL}/stores/${storeId}/products/${productId}/category`, {
        category_id: categoryId || null,
      });
      load();
    } catch {
      setError('Failed to move product.');
    }
  };

  if (loading) {
    return <div style={{ padding: '2rem', color: 'var(--text-secondary)' }}>Loading catalog...</div>;
  }

  // ---- Drill-down: products inside one category (or Uncategorized) ----
  if (openCat) {
    const inCat = openCat.id
      ? products.filter((p) => p.category_id === openCat.id)
      : uncategorized;
    return (
      <div style={{ flex: 1, padding: '0 2.5rem 2.5rem', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', margin: '0 0 1.5rem' }}>
          <div style={{ fontSize: '1rem', color: 'var(--text-secondary)' }}>
            <button onClick={() => setOpenCat(null)}
              style={{ background: 'none', border: 'none', color: 'var(--accent-primary)', cursor: 'pointer', fontWeight: 600 }}>
              Catalog
            </button>
            {' / '}<strong style={{ color: 'var(--text-primary)' }}>{openCat.name}</strong>
          </div>
          {openCat.id && (
            <button onClick={() => setAddProductFor({ id: openCat.id, name: openCat.name })}
              style={btnPrimary}>+ Add Product</button>
          )}
        </div>

        {error && <div role="alert" style={errStyle}>{error}</div>}

        {inCat.length === 0 ? (
          <div style={emptyStyle}>No products in this category yet.</div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '1.5rem' }}>
            {inCat.map((p) => (
              <div key={p.id} style={cardStyle}>
                <div style={{ height: '150px', background: '#f1f5f9', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
                  {p.image_url
                    ? <img src={imgSrc(p.image_url)} alt={p.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    : <span style={{ color: 'rgba(0,0,0,0.15)' }}>No image</span>}
                </div>
                <div style={{ padding: '1rem' }}>
                  <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.5rem' }}>{p.name}</h3>
                  <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                    Move to:{' '}
                    <select aria-label={`Move ${p.name}`}
                      value={p.category_id || ''}
                      onChange={(e) => moveProduct(p.id, e.target.value)}
                      style={{ padding: '0.25rem', borderRadius: '6px' }}>
                      <option value="">Uncategorized</option>
                      {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                    </select>
                  </label>
                </div>
              </div>
            ))}
          </div>
        )}

        {addProductFor && (
          <AddProductModal storeId={storeId}
            categoryId={addProductFor.id} categoryName={addProductFor.name}
            onClose={() => setAddProductFor(null)}
            onProductAdded={() => { setAddProductFor(null); load(); }} />
        )}
      </div>
    );
  }

  // ---- Category folders ----
  return (
    <div style={{ flex: 1, padding: '0 2.5rem 2.5rem', overflowY: 'auto' }}>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '1.5rem' }}>
        <button onClick={() => setShowNew((v) => !v)} style={btnPrimary}>+ New Category</button>
      </div>

      {error && <div role="alert" style={errStyle}>{error}</div>}

      {showNew && (
        <div style={{ ...cardStyle, padding: '1.25rem', marginBottom: '1.5rem' }}>
          <input aria-label="Category name" placeholder="Category name" value={newName}
            onChange={(e) => setNewName(e.target.value)} style={inputStyle} />
          <input aria-label="Category description" placeholder="Description (optional)" value={newDesc}
            onChange={(e) => setNewDesc(e.target.value)} style={{ ...inputStyle, marginTop: '0.5rem' }} />
          <div style={{ marginTop: '0.75rem', display: 'flex', gap: '0.5rem' }}>
            <button onClick={createCategory} style={btnPrimary}>Create</button>
            <button onClick={() => setShowNew(false)} style={btnGhost}>Cancel</button>
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: '1.5rem' }}>
        {categories.map((cat) => (
          <div key={cat.id} style={{ ...cardStyle, opacity: cat.is_active ? 1 : 0.55 }}>
            <div style={{ height: '120px', background: '#eef2f7', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
              {cat.image_url
                ? <img src={imgSrc(cat.image_url)} alt={cat.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                : <span aria-hidden="true" style={{ fontSize: '2rem', opacity: 0.3 }}>📁</span>}
            </div>
            <div style={{ padding: '1rem' }}>
              {editing === cat.id ? (
                <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem' }}>
                  <input aria-label="Rename category" value={editName}
                    onChange={(e) => setEditName(e.target.value)} style={inputStyle} />
                  <button onClick={() => renameCategory(cat.id)} style={btnPrimary}>Save</button>
                </div>
              ) : (
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <button onClick={() => setOpenCat({ id: cat.id, name: cat.name })}
                    style={{ background: 'none', border: 'none', fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-primary)', cursor: 'pointer', padding: 0, textAlign: 'left' }}>
                    {cat.name}
                  </button>
                  {!cat.is_active && <span style={{ fontSize: '0.7rem', color: 'var(--danger)' }}>Inactive</span>}
                </div>
              )}
              <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: '0.4rem 0 0.75rem' }}>
                {cat.product_count} products
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', fontSize: '0.75rem' }}>
                <button onClick={() => setOpenCat({ id: cat.id, name: cat.name })} style={btnGhost}>Open</button>
                <button onClick={() => { setEditing(cat.id); setEditName(cat.name); }} style={btnGhost}>Rename</button>
                <button onClick={() => toggleActive(cat)} style={btnGhost}>
                  {cat.is_active ? 'Deactivate' : 'Activate'}
                </button>
                <label style={{ ...btnGhost, cursor: 'pointer' }}>
                  Image
                  <input type="file" accept=".jpg,.jpeg,.png,.webp" style={{ display: 'none' }}
                    onChange={(e) => uploadCategoryImage(cat.id, e)} />
                </label>
                <button onClick={() => deleteCategory(cat)} style={{ ...btnGhost, color: 'var(--danger)' }}>Delete</button>
              </div>
            </div>
          </div>
        ))}

        {/* Uncategorized folder */}
        <div style={cardStyle}>
          <div style={{ height: '120px', background: '#f8fafc', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <span aria-hidden="true" style={{ fontSize: '2rem', opacity: 0.3 }}>📂</span>
          </div>
          <div style={{ padding: '1rem' }}>
            <button onClick={() => setOpenCat({ id: null, name: 'Uncategorized' })}
              style={{ background: 'none', border: 'none', fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-primary)', cursor: 'pointer', padding: 0 }}>
              Uncategorized
            </button>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.4rem' }}>
              {uncategorized.length} products
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

const cardStyle = {
  background: 'var(--bg-panel)', borderRadius: '14px',
  border: '1px solid var(--border-color)', overflow: 'hidden',
  boxShadow: 'var(--shadow-sm)',
};
const btnPrimary = {
  padding: '0.5rem 1rem', borderRadius: '8px', background: 'var(--accent-primary)',
  color: '#fff', border: 'none', fontWeight: 600, cursor: 'pointer',
};
const btnGhost = {
  padding: '0.35rem 0.6rem', borderRadius: '6px', background: 'var(--bg-panel-hover)',
  color: 'var(--text-secondary)', border: '1px solid var(--border-color)', cursor: 'pointer',
};
const inputStyle = {
  padding: '0.6rem', borderRadius: '8px', border: '1px solid var(--border-color)',
  width: '100%', color: 'var(--text-primary)', background: 'var(--bg-card)',
};
const errStyle = { color: 'var(--danger)', marginBottom: '1rem', fontSize: '0.875rem' };
const emptyStyle = {
  padding: '3rem', textAlign: 'center', color: 'var(--text-secondary)',
  background: 'var(--bg-panel)', borderRadius: '16px', border: '1px solid var(--border-color)',
};

export default CategoriesView;
