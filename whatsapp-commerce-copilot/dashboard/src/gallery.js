/**
 * Catalogue-picture rules, mirrored from the backend.
 *
 * The API is the authority — it re-checks all of this and a direct call cannot
 * bypass it. These exist so the seller sees the problem next to the input
 * instead of after a round trip, and so the field keys the form highlights are
 * exactly the keys the API sends back.
 */

// Must match app/services/catalog_gallery.py.
export const GALLERY_FIELDS = {
  NAME: 'name',
  CATEGORY: 'category_id',
  COLOR: 'color',
  PRICE: 'price',
  IMAGE: 'image',
  STOCK: 'stock',
  ACTIVE: 'is_active',
};

const PLACEHOLDER_NAMES = new Set([
  'test', 'testing', 'product', 'products', 'item', 'sample',
  'demo', 'abc', 'xyz', 'na', 'n/a', 'none', 'untitled', 'new product',
]);

export const nameError = (name) => {
  const cleaned = (name || '').trim();
  if (!cleaned) return 'Product name is required';
  if ((cleaned.match(/\p{L}/gu) || []).length < 2) return 'Product name must contain at least 2 letters';
  if (PLACEHOLDER_NAMES.has(cleaned.toLowerCase())) return 'Product name looks like a placeholder';
  return null;
};

export const priceError = (price) => {
  if (price === '' || price === null || price === undefined) return 'Price is required';
  const value = Number(price);
  if (Number.isNaN(value)) return 'Price must be a number';
  if (value <= 0) return 'Price must be greater than zero';
  return null;
};

export const stockError = (stock) => {
  if (stock === '' || stock === null || stock === undefined) return 'Stock is required';
  const value = Number(stock);
  if (!Number.isInteger(value)) return 'Stock must be a whole number';
  if (value < 0) return 'Stock cannot be negative';
  return null;
};

/**
 * Validate the add/edit form.
 *
 * `galleryReady` is what makes the picture-only fields binding: an ordinary
 * text-only product still just needs a name and a positive price, which is what
 * keeps historical products editable.
 */
export function validateGalleryFields(
  { name, price, stock, color, categoryId, hasImage },
  galleryReady,
) {
  const errors = {};

  const nErr = nameError(name);
  if (nErr) errors[GALLERY_FIELDS.NAME] = nErr;

  const pErr = priceError(price);
  if (pErr) errors[GALLERY_FIELDS.PRICE] = pErr;

  if (!galleryReady) return errors;

  const sErr = stockError(stock);
  if (sErr) errors[GALLERY_FIELDS.STOCK] = sErr;
  else if (Number(stock) <= 0) errors[GALLERY_FIELDS.STOCK] = 'Stock must be at least 1 to be shown';

  if (!(color || '').trim()) errors[GALLERY_FIELDS.COLOR] = 'Colour is required';
  if (!categoryId) errors[GALLERY_FIELDS.CATEGORY] = 'A saved category is required';
  if (!hasImage) errors[GALLERY_FIELDS.IMAGE] = 'Product image is required';

  return errors;
}

/**
 * Pull the per-field map out of an API error body.
 * Plain-string details (the generic validation messages) carry no field map.
 */
export function fieldErrorsFrom(detail) {
  if (detail && typeof detail === 'object' && detail.fields && typeof detail.fields === 'object') {
    return { ...detail.fields };
  }
  return {};
}

/** Human summary of why a product is not sendable as a picture. */
export function galleryBlockerSummary(product) {
  const blockers = product?.gallery_blockers;
  if (!blockers || !Object.keys(blockers).length) return null;
  return Object.values(blockers).join(' · ');
}
