import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API_URL } from '../config';
import { GALLERY_FIELDS, validateGalleryFields, fieldErrorsFrom } from '../gallery';

const inputStyle = (invalid) => ({
  background: 'var(--bg-card)',
  padding: '0.75rem',
  borderRadius: '8px',
  border: `1px solid ${invalid ? '#ef4444' : 'var(--border-color)'}`,
  width: '100%',
  color: 'var(--text-primary)',
});

const labelStyle = {
  display: 'block', marginBottom: '0.5rem',
  fontSize: '0.875rem', color: 'var(--text-secondary)',
};

const FieldError = ({ children }) =>
  children ? (
    <p role="alert" style={{ color: '#ef4444', fontSize: '0.75rem', marginTop: '0.25rem' }}>
      {children}
    </p>
  ) : null;

/**
 * Add a product, optionally as a catalogue-picture entry.
 *
 * A product only reaches a customer as a *picture* when it has a name, a saved
 * category, a colour, a positive price, stock, and an image — the colour and
 * category are what the customer's "Cotton" → "Blue" browse actually filters
 * on. Ticking "Send as a catalogue picture" makes those fields binding here and
 * in the API, so a product the seller believes is sendable really is one.
 * Leaving it unticked keeps the old lightweight text-only product.
 */
const AddProductModal = ({ storeId, onClose, onProductAdded, categoryId = null, categoryName = null }) => {
  const [formData, setFormData] = useState({
    name: '',
    price: '',
    stock: '1',
    color: '',
    category: '',
    description: '',
    labels: '',
  });
  const [image, setImage] = useState(null);
  const [preview, setPreview] = useState(null);
  const [uploadPct, setUploadPct] = useState(null);
  // Only offer the picture catalogue when the product is being filed under a
  // real category — without one it could never qualify.
  const [galleryReady, setGalleryReady] = useState(Boolean(categoryId));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [fieldErrors, setFieldErrors] = useState({});

  useEffect(() => {
    if (!image) return undefined;
    const url = URL.createObjectURL(image);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [image]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    // Clear only this field's error — a correction here must not wipe the
    // messages still pointing at other fields.
    setFieldErrors((prev) => {
      if (!prev[name]) return prev;
      const next = { ...prev };
      delete next[name];
      return next;
    });
  };

  const handleImageChange = (e) => {
    const file = e.target.files?.[0] || null;
    setImage(file);
    setFieldErrors((prev) => {
      if (!prev[GALLERY_FIELDS.IMAGE]) return prev;
      const next = { ...prev };
      delete next[GALLERY_FIELDS.IMAGE];
      return next;
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    const invalid = validateGalleryFields({
      ...formData, categoryId, hasImage: Boolean(image),
    }, galleryReady);
    if (Object.keys(invalid).length) {
      setFieldErrors(invalid);
      setError(galleryReady
        ? 'Fill in everything a catalogue picture needs, or untick "Send as a catalogue picture".'
        : 'Please correct the highlighted fields.');
      return;
    }

    setLoading(true);
    setError(null);
    setFieldErrors({});

    const data = new FormData();
    data.append('name', formData.name);
    data.append('price', formData.price);
    data.append('stock', formData.stock || '1');
    if (formData.color) data.append('color', formData.color);
    if (formData.category) data.append('category', formData.category);
    if (categoryId) data.append('category_id', categoryId);
    if (formData.description) data.append('description', formData.description);
    if (formData.labels) data.append('labels', formData.labels);
    if (image) data.append('image', image);
    if (galleryReady) data.append('gallery_ready', 'true');

    try {
      await axios.post(`${API_URL}/stores/${storeId}/products`, data, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (evt) => {
          if (!image || !evt.total) return;
          setUploadPct(Math.round((evt.loaded * 100) / evt.total));
        },
      });
      onProductAdded();
      onClose();
    } catch (err) {
      // The API names each offending field; show them next to the inputs and
      // keep everything the seller already typed.
      const detail = err.response?.data?.detail;
      const fields = fieldErrorsFrom(detail);
      setFieldErrors(fields);
      setError(
        (typeof detail === 'string' && detail)
        || detail?.message
        || 'Failed to add product. Please try again.',
      );
    } finally {
      setLoading(false);
      setUploadPct(null);
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
        <h2 style={{ fontSize: '1.25rem', marginBottom: '1.5rem', fontWeight: 600 }}>
          Add New Product{categoryName ? ` — ${categoryName}` : ''}
        </h2>

        {error && (
          <div role="alert" style={{ color: '#ef4444', marginBottom: '1rem', fontSize: '0.875rem' }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>

          <label style={{
            display: 'flex', alignItems: 'flex-start', gap: '0.6rem',
            padding: '0.75rem', borderRadius: '8px',
            background: 'var(--bg-card)', border: '1px solid var(--border-color)',
            cursor: categoryId ? 'pointer' : 'not-allowed', opacity: categoryId ? 1 : 0.6,
          }}>
            <input
              type="checkbox"
              checked={galleryReady}
              disabled={!categoryId}
              onChange={(e) => setGalleryReady(e.target.checked)}
              aria-label="Send as a catalogue picture"
              style={{ marginTop: '0.15rem' }}
            />
            <span style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
              <strong style={{ color: 'var(--text-primary)' }}>Send as a catalogue picture</strong>
              <br />
              {categoryId
                ? 'Customers browsing this category and colour will be sent this product’s photo.'
                : 'Add the product from inside a category to offer it as a picture.'}
            </span>
          </label>

          <div>
            <label style={labelStyle} htmlFor="product-image">
              Product Image{galleryReady ? ' *' : ''}
            </label>
            {preview && (
              <img
                src={preview}
                alt="Selected product preview"
                style={{
                  width: '96px', height: '96px', objectFit: 'cover',
                  borderRadius: '8px', marginBottom: '0.5rem',
                  border: '1px solid var(--border-color)',
                }}
              />
            )}
            <input
              id="product-image"
              type="file"
              accept=".jpg,.jpeg,.png,.webp,.avif"
              onChange={handleImageChange}
              aria-label="Product Image"
              style={inputStyle(Boolean(fieldErrors[GALLERY_FIELDS.IMAGE]))}
            />
            {uploadPct !== null && (
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                Uploading… {uploadPct}%
              </p>
            )}
            <FieldError>{fieldErrors[GALLERY_FIELDS.IMAGE]}</FieldError>
          </div>

          <div>
            <label style={labelStyle} htmlFor="product-name">Product Name *</label>
            <input
              id="product-name"
              type="text"
              name="name"
              value={formData.name}
              onChange={handleChange}
              placeholder="e.g. Blue Kurta"
              aria-label="Product Name"
              style={inputStyle(Boolean(fieldErrors.name))}
            />
            <FieldError>{fieldErrors.name}</FieldError>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label style={labelStyle} htmlFor="product-price">Price (Rs.) *</label>
              <input
                id="product-price"
                type="number"
                name="price"
                value={formData.price}
                onChange={handleChange}
                placeholder="e.g. 1500"
                aria-label="Price"
                style={inputStyle(Boolean(fieldErrors.price))}
              />
              <FieldError>{fieldErrors.price}</FieldError>
            </div>
            <div>
              <label style={labelStyle} htmlFor="product-stock">Stock Quantity *</label>
              <input
                id="product-stock"
                type="number"
                name="stock"
                value={formData.stock}
                onChange={handleChange}
                min="0"
                placeholder="e.g. 10"
                aria-label="Stock Quantity"
                style={inputStyle(Boolean(fieldErrors.stock))}
              />
              <FieldError>{fieldErrors.stock}</FieldError>
            </div>
          </div>

          <div>
            <label style={labelStyle} htmlFor="product-color">
              Colour{galleryReady ? ' *' : ''}
            </label>
            <input
              id="product-color"
              type="text"
              name="color"
              value={formData.color}
              onChange={handleChange}
              placeholder="e.g. Blue"
              aria-label="Colour"
              style={inputStyle(Boolean(fieldErrors.color))}
            />
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
              Customers pick a colour before seeing designs, so this is how the product is found.
            </p>
            <FieldError>{fieldErrors.color}</FieldError>
          </div>

          <div>
            <label style={labelStyle} htmlFor="product-category">Category</label>
            <input
              id="product-category"
              type="text"
              name="category"
              value={formData.category}
              onChange={handleChange}
              placeholder="e.g. Kurta"
              aria-label="Category"
              style={inputStyle(Boolean(fieldErrors.category_id))}
            />
            <FieldError>{fieldErrors.category_id}</FieldError>
          </div>

          <div>
            <label style={labelStyle} htmlFor="product-labels">Labels / Search Tags (comma separated)</label>
            <input
              id="product-labels"
              type="text"
              name="labels"
              value={formData.labels}
              onChange={handleChange}
              placeholder="e.g. blue dress, summer wear, cotton"
              aria-label="Labels"
              style={inputStyle(false)}
            />
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>These are used by the AI to find the product when a customer asks.</p>
          </div>

          <div>
            <label style={labelStyle} htmlFor="product-description">Description</label>
            <textarea
              id="product-description"
              name="description"
              value={formData.description}
              onChange={handleChange}
              placeholder="Short product description"
              aria-label="Description"
              style={{ ...inputStyle(false), minHeight: '80px', resize: 'vertical' }}
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '1rem', marginTop: '1rem' }}>
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              style={{
                padding: '0.75rem 1.5rem',
                borderRadius: '8px',
                border: 'none',
                background: 'transparent',
                color: 'var(--text-secondary)',
                fontWeight: 600,
                cursor: loading ? 'not-allowed' : 'pointer'
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
                border: 'none',
                background: loading ? 'var(--border-color)' : 'var(--accent-primary)',
                color: loading ? 'var(--text-secondary)' : '#fff',
                fontWeight: 600,
                cursor: loading ? 'not-allowed' : 'pointer'
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
