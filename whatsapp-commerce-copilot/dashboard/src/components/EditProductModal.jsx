import React, { useState } from 'react';
import axios from 'axios';
import { API_URL } from '../config';
import { fieldErrorsFrom, galleryBlockerSummary } from '../gallery';

const IMG_BASE = API_URL.replace('/api', '');
const imgSrc = (url) => (url && url.startsWith('http') ? url : `${IMG_BASE}${url}`);

/**
 * View and edit one product: details (name, price, description, SKU) and its
 * picture. Details and image are separate calls because the backend keeps them
 * on separate endpoints (JSON PATCH vs multipart PUT), so a failed image upload
 * never rolls back a saved text edit.
 *
 * Variants are shown read-only — variant pricing/stock has its own endpoints and
 * editing it here would duplicate that flow.
 */
const EditProductModal = ({ storeId, product, onClose, onSaved }) => {
  const [name, setName] = useState(product.name || '');
  const [price, setPrice] = useState(String(product.base_price ?? ''));
  const [description, setDescription] = useState(product.description || '');
  const [sku, setSku] = useState(product.sku || '');
  const [imageUrl, setImageUrl] = useState(product.image_url || null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [fieldErrors, setFieldErrors] = useState({});

  // Colour lives on the variant. A product with exactly one active variant has
  // a single colour that can be edited here; several variants means several
  // colours, which are managed per variant.
  const activeVariants = (product.variants || []).filter((v) => v.is_active !== false);
  const singleVariant = activeVariants.length === 1 ? activeVariants[0] : null;
  const [color, setColor] = useState(singleVariant?.color || '');

  const blockers = galleryBlockerSummary(product);

  const base = `${API_URL}/stores/${storeId}/products/${product.id}`;

  const saveDetails = async () => {
    setBusy(true);
    setError(null);
    try {
      await axios.patch(base, {
        name: name.trim(),
        price: price === '' ? undefined : Number(price),
        description,
        sku,
        ...(singleVariant ? { color } : {}),
      });
      onSaved?.();
      onClose();
    } catch (err) {
      // Surface the API's own reason rather than a generic failure, and mark
      // the individual fields when it names them.
      const detail = err?.response?.data?.detail;
      setFieldErrors(fieldErrorsFrom(detail));
      setError(
        (typeof detail === 'string' && detail)
        || detail?.message
        || 'Could not save changes.',
      );
    } finally {
      setBusy(false);
    }
  };

  const uploadImage = async (file) => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append('image', file);
      const res = await axios.put(`${base}/image`, form);
      setImageUrl(res.data?.image_url ?? null);
      onSaved?.();
    } catch (err) {
      setError(err?.response?.data?.detail || 'Could not upload the picture.');
    } finally {
      setBusy(false);
    }
  };

  const removeImage = async () => {
    setBusy(true);
    setError(null);
    try {
      await axios.delete(`${base}/image`);
      setImageUrl(null);
      onSaved?.();
    } catch (err) {
      setError(err?.response?.data?.detail || 'Could not remove the picture.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Edit ${product.name}`}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.45)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50, padding: '1rem',
      }}
    >
      <div style={{
        background: 'var(--bg-panel)', borderRadius: '16px', border: '1px solid var(--border-color)',
        width: 'min(560px, 100%)', maxHeight: '90vh', overflowY: 'auto', padding: '1.5rem',
        boxShadow: 'var(--shadow-md)',
      }}>
        <h2 style={{ fontSize: '1.15rem', fontWeight: 600, marginBottom: '1.25rem' }}>
          Edit Product
        </h2>

        {/* Why this product is not reaching customers as a picture — shown up
            front so the seller can fix it without guessing. */}
        {blockers && (
          <div style={{
            marginBottom: '1rem', padding: '0.6rem 0.85rem', borderRadius: '8px',
            border: '1px solid rgba(234,179,8,0.35)', background: 'rgba(234,179,8,0.08)',
            color: 'var(--text-secondary)', fontSize: '0.8125rem',
          }}>
            <strong style={{ color: 'var(--text-primary)' }}>Not gallery-ready</strong>
            <br />
            {blockers}
          </div>
        )}

        {error && (
          <div role="alert" style={{
            marginBottom: '1rem', padding: '0.6rem 0.85rem', borderRadius: '8px',
            border: '1px solid rgba(239,68,68,0.25)', background: 'rgba(239,68,68,0.06)',
            color: 'var(--danger)', fontSize: '0.8125rem',
          }}>{error}</div>
        )}

        {/* Picture */}
        <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.25rem', alignItems: 'flex-start' }}>
          <div style={{
            width: '120px', height: '120px', flexShrink: 0, borderRadius: '10px', overflow: 'hidden',
            background: 'var(--bg-panel-hover)', border: '1px solid var(--border-color)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            {imageUrl
              ? <img src={imgSrc(imageUrl)} alt={product.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              : <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>No image</span>}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <label style={{ ...ghost, cursor: 'pointer', display: 'inline-block' }}>
              {imageUrl ? 'Replace picture' : 'Upload picture'}
              <input type="file" accept="image/*" aria-label="Product picture"
                     style={{ display: 'none' }}
                     onChange={(e) => uploadImage(e.target.files?.[0])} />
            </label>
            {imageUrl && (
              <button type="button" onClick={removeImage} disabled={busy}
                      style={{ ...ghost, color: 'var(--danger)' }}>
                Remove picture
              </button>
            )}
          </div>
        </div>

        {/* Details */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
          <label style={label}>
            Name
            <input aria-label="Product name" value={name} onChange={(e) => setName(e.target.value)} style={input} />
          </label>
          <label style={label}>
            Price (PKR)
            <input aria-label="Product price" type="number" min="0" value={price}
                   onChange={(e) => setPrice(e.target.value)} style={input} />
          </label>
          <label style={label}>
            Colour
            <input
              aria-label="Product colour"
              value={singleVariant ? color : activeVariants.map((v) => v.color).filter(Boolean).join(', ')}
              onChange={(e) => setColor(e.target.value)}
              disabled={!singleVariant}
              placeholder={singleVariant ? 'e.g. Blue' : ''}
              style={{ ...input, opacity: singleVariant ? 1 : 0.6 }}
            />
            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
              {singleVariant
                ? 'Customers pick a colour before seeing designs.'
                : 'Set per variant on a product with several colours.'}
            </span>
            {fieldErrors.color && (
              <span role="alert" style={{ color: 'var(--danger)', fontSize: '0.7rem' }}>
                {fieldErrors.color}
              </span>
            )}
          </label>
          <label style={label}>
            SKU
            <input aria-label="Product SKU" value={sku} onChange={(e) => setSku(e.target.value)} style={input} />
          </label>
          <label style={label}>
            Description
            <textarea aria-label="Product description" rows={3} value={description}
                      onChange={(e) => setDescription(e.target.value)} style={{ ...input, resize: 'vertical' }} />
          </label>
        </div>

        {/* Variants are managed elsewhere; shown here so the seller can see what
            the customer will be offered. */}
        {product.variants?.length > 0 && (
          <div style={{ marginTop: '1.25rem' }}>
            <div style={{ fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase',
                          letterSpacing: '0.5px', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
              Variants
            </div>
            <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
              {product.variants.map((v) => (
                <li key={v.id} style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
                  {[v.color, v.size].filter(Boolean).join(' / ') || 'Default'} — PKR {Number(v.price).toLocaleString()} · stock {v.stock}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end', marginTop: '1.5rem' }}>
          <button type="button" onClick={onClose} style={ghost}>Cancel</button>
          <button type="button" onClick={saveDetails} disabled={busy} style={primary}>
            {busy ? 'Saving…' : 'Save changes'}
          </button>
        </div>
      </div>
    </div>
  );
};

const label = { display: 'flex', flexDirection: 'column', gap: '0.3rem', fontSize: '0.8125rem', color: 'var(--text-secondary)' };
const input = { padding: '0.5rem 0.65rem', borderRadius: '8px', border: '1px solid var(--border-color)', fontSize: '0.875rem' };
const primary = { padding: '0.5rem 1rem', borderRadius: '8px', background: 'var(--accent-primary)', color: '#fff', border: 'none', fontWeight: 600, cursor: 'pointer' };
const ghost = { padding: '0.5rem 0.9rem', borderRadius: '8px', background: 'var(--bg-panel)', color: 'var(--text-secondary)', border: '1px solid var(--border-color)', cursor: 'pointer', fontWeight: 600, fontSize: '0.8125rem' };

export default EditProductModal;
