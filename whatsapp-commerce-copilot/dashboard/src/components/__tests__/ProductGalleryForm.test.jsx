import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';

vi.mock('axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

import axios from 'axios';
import AddProductModal from '../AddProductModal';
import EditProductModal from '../EditProductModal';
import CategoriesView from '../CategoriesView';

const CAT_ID = 'cat-cotton';

/** Render the form the way the seller reaches it: from inside a category. */
const renderAdd = (props = {}) => render(
  <AddProductModal storeId="s1" categoryId={CAT_ID} categoryName="Cotton"
    onClose={() => {}} onProductAdded={() => {}} {...props} />,
);

const fill = ({ name = 'Blue Kurta', price = '2500', stock = '3', color = 'Blue' } = {}) => {
  if (name !== null) fireEvent.change(screen.getByLabelText('Product Name'), { target: { value: name } });
  if (price !== null) fireEvent.change(screen.getByLabelText('Price'), { target: { value: price } });
  if (stock !== null) fireEvent.change(screen.getByLabelText('Stock Quantity'), { target: { value: stock } });
  if (color !== null) fireEvent.change(screen.getByLabelText('Colour'), { target: { value: color } });
};

const attachImage = (type = 'image/jpeg', filename = 'p.jpg') => {
  const file = new File(['x'], filename, { type });
  fireEvent.change(screen.getByLabelText('Product Image'), { target: { files: [file] } });
  return file;
};

const submit = () => fireEvent.click(screen.getByText('Add Product'));

const formBody = () => {
  const data = axios.post.mock.calls[0][1];
  return Object.fromEntries(data.entries());
};

beforeEach(() => {
  vi.clearAllMocks();
  cleanup();
  axios.post.mockResolvedValue({ data: { id: 'p1' } });
  global.URL.createObjectURL = vi.fn(() => 'blob:preview');
  global.URL.revokeObjectURL = vi.fn();
});
afterEach(() => cleanup());

describe('Seller form: catalogue-picture required fields', () => {
  it('a complete product is submitted with every gallery field', async () => {
    renderAdd();
    fill();
    attachImage();
    submit();

    await waitFor(() => expect(axios.post).toHaveBeenCalled());
    const body = formBody();
    expect(body.name).toBe('Blue Kurta');
    expect(body.price).toBe('2500');
    expect(body.stock).toBe('3');
    expect(body.color).toBe('Blue');
    expect(body.category_id).toBe(CAT_ID);
    expect(body.gallery_ready).toBe('true');
    expect(body.image).toBeInstanceOf(File);
  });

  it.each([
    ['name', { name: '' }, /name is required/i],
    ['a placeholder name', { name: 'test' }, /placeholder/i],
    ['colour', { color: '' }, /colour is required/i],
    ['a positive price', { price: '0' }, /greater than zero/i],
  ])('refuses to save without %s', async (_label, overrides, expected) => {
    renderAdd();
    fill(overrides);
    attachImage();
    submit();

    await waitFor(() => expect(screen.getAllByRole('alert').length).toBeGreaterThan(0));
    expect(screen.getByText(expected)).toBeInTheDocument();
    expect(axios.post).not.toHaveBeenCalled();
  });

  it('refuses to save a picture product with no image', async () => {
    renderAdd();
    fill();
    submit();

    await waitFor(() => expect(screen.getByText(/image is required/i)).toBeInTheDocument());
    expect(axios.post).not.toHaveBeenCalled();
  });

  it('requires stock before a product can be shown to customers', async () => {
    renderAdd();
    fill({ stock: '0' });
    attachImage();
    submit();

    await waitFor(() => expect(screen.getByText(/stock must be at least 1/i)).toBeInTheDocument());
    expect(axios.post).not.toHaveBeenCalled();
  });

  it('marks every gallery field as required once the picture option is on', () => {
    renderAdd();
    expect(screen.getByText('Product Image *')).toBeInTheDocument();
    expect(screen.getByText('Colour *')).toBeInTheDocument();
    expect(screen.getByText('Product Name *')).toBeInTheDocument();
    expect(screen.getByText('Price (Rs.) *')).toBeInTheDocument();
    expect(screen.getByText('Stock Quantity *')).toBeInTheDocument();
  });

  it('a text-only product still saves without colour or image', async () => {
    renderAdd({ categoryId: null, categoryName: null });
    fill({ color: null });
    submit();

    await waitFor(() => expect(axios.post).toHaveBeenCalled());
    expect(formBody().gallery_ready).toBeUndefined();
  });

  it('shows a preview once a picture is chosen', async () => {
    renderAdd();
    attachImage();
    await waitFor(() =>
      expect(screen.getByAltText('Selected product preview')).toHaveAttribute('src', 'blob:preview'));
  });

  it('keeps everything already typed when one field fails', async () => {
    renderAdd();
    fill({ color: '' });
    attachImage();
    submit();

    await waitFor(() => expect(screen.getByText(/colour is required/i)).toBeInTheDocument());
    // The valid values survive — the seller does not retype the form.
    expect(screen.getByLabelText('Product Name')).toHaveValue('Blue Kurta');
    expect(screen.getByLabelText('Price')).toHaveValue(2500);
    expect(screen.getByLabelText('Stock Quantity')).toHaveValue(3);
    expect(screen.getByAltText('Selected product preview')).toBeInTheDocument();
  });

  it("shows the API's own per-field reasons and keeps the form open", async () => {
    axios.post.mockRejectedValueOnce({
      response: { data: { detail: {
        message: 'Product is not ready for the picture catalogue',
        fields: { image: 'Product image is required', color: 'Colour is required' },
      } } },
    });
    renderAdd();
    fill();
    attachImage();
    submit();

    await waitFor(() =>
      expect(screen.getByText('Product is not ready for the picture catalogue')).toBeInTheDocument());
    expect(screen.getByText('Product image is required')).toBeInTheDocument();
    expect(screen.getByText('Colour is required')).toBeInTheDocument();
    // Still filled in, still on screen.
    expect(screen.getByLabelText('Product Name')).toHaveValue('Blue Kurta');
  });

  it('a rejected image upload never saves a product with a broken picture', async () => {
    axios.post.mockRejectedValueOnce({
      response: { data: { detail: 'Unsupported image format or corrupted file.' } },
    });
    renderAdd();
    fill();
    attachImage('image/tiff', 'p.tiff');
    submit();

    await waitFor(() =>
      expect(screen.getByText('Unsupported image format or corrupted file.')).toBeInTheDocument());
    expect(axios.post).toHaveBeenCalledTimes(1);
  });

  it('cannot offer the picture catalogue outside a category', () => {
    renderAdd({ categoryId: null, categoryName: null });
    const toggle = screen.getByLabelText('Send as a catalogue picture');
    expect(toggle).toBeDisabled();
    expect(toggle).not.toBeChecked();
  });
});

describe('Editing an existing product', () => {
  const READY = {
    id: 'p1', name: 'Blue Kurta', base_price: 2500, description: 'Soft',
    sku: 'BK-1', image_url: '/uploads/a.jpg', category_id: CAT_ID,
    gallery_ready: true, gallery_blockers: {},
    variants: [{ id: 'v1', color: 'Blue', size: 'M', price: 2500, stock: 4, is_active: true }],
  };
  const LEGACY = {
    ...READY, id: 'p2', name: 'Legacy Kurta', image_url: null, category_id: null,
    gallery_ready: false,
    gallery_blockers: { image: 'Product image is required', category_id: 'A saved category is required' },
    variants: [{ id: 'v2', color: null, size: 'M', price: 2500, stock: 4, is_active: true }],
  };

  beforeEach(() => {
    axios.patch.mockResolvedValue({ data: READY });
  });

  it('a historical text-only product is labelled, not blocked', () => {
    render(<EditProductModal storeId="s1" product={LEGACY} onClose={() => {}} />);
    expect(screen.getByText('Not gallery-ready')).toBeInTheDocument();
    expect(screen.getByText(/Product image is required/)).toBeInTheDocument();
    // Editing is still possible — that is the seller's way out of the state.
    expect(screen.getByLabelText('Product name')).toBeEnabled();
    expect(screen.getByText('Save changes')).toBeEnabled();
  });

  it('a gallery-ready product carries no warning', () => {
    render(<EditProductModal storeId="s1" product={READY} onClose={() => {}} />);
    expect(screen.queryByText('Not gallery-ready')).toBeNull();
  });

  it('saves a corrected colour on a single-variant product', async () => {
    render(<EditProductModal storeId="s1" product={LEGACY} onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText('Product colour'), { target: { value: 'Green' } });
    fireEvent.click(screen.getByText('Save changes'));

    await waitFor(() => expect(axios.patch).toHaveBeenCalledWith(
      'http://localhost:8000/api/stores/s1/products/p2',
      expect.objectContaining({ color: 'Green' }),
    ));
  });

  it('leaves colour to the variants when there are several', () => {
    render(<EditProductModal storeId="s1" onClose={() => {}} product={{
      ...READY,
      variants: [
        { id: 'v1', color: 'Blue', size: 'M', price: 2500, stock: 4, is_active: true },
        { id: 'v2', color: 'Red', size: 'M', price: 2700, stock: 2, is_active: true },
      ],
    }} />);
    const input = screen.getByLabelText('Product colour');
    expect(input).toBeDisabled();
    expect(input).toHaveValue('Blue, Red');
  });
});

describe('Catalog view', () => {
  const CATS = [{
    id: CAT_ID, store_id: 's1', name: 'Cotton', image_url: null,
    display_order: 1, is_active: true, product_count: 2,
  }];
  const PRODUCTS = [
    { id: 'p1', name: 'Ready Kurta', base_price: 2500, image_url: '/uploads/a.jpg',
      category_id: CAT_ID, gallery_ready: true, gallery_blockers: {}, variants: [] },
    { id: 'p2', name: 'Legacy Kurta', base_price: 2200, image_url: null,
      category_id: CAT_ID, gallery_ready: false,
      gallery_blockers: { image: 'Product image is required' }, variants: [] },
  ];

  beforeEach(() => {
    axios.get.mockImplementation((url) => {
      if (url.endsWith('/categories')) return Promise.resolve({ data: CATS });
      if (url.endsWith('/products')) return Promise.resolve({ data: PRODUCTS });
      return Promise.resolve({ data: [] });
    });
  });

  it('flags only the products customers will never be sent a picture of', async () => {
    render(<CategoriesView storeId="s1" />);
    await waitFor(() => expect(screen.getByText('Cotton')).toBeInTheDocument());
    fireEvent.click(screen.getAllByText('Open')[0]);

    await waitFor(() => expect(screen.getByText('Legacy Kurta')).toBeInTheDocument());
    expect(screen.getAllByText('Not gallery-ready')).toHaveLength(1);
  });

  it('deletes a product once the seller confirms', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    axios.delete.mockResolvedValue({ data: {} });

    render(<CategoriesView storeId="s1" />);
    await waitFor(() => expect(screen.getByText('Cotton')).toBeInTheDocument());
    fireEvent.click(screen.getAllByText('Open')[0]);
    await waitFor(() => expect(screen.getByLabelText('Delete Legacy Kurta')).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('Delete Legacy Kurta'));

    // The product is named in the prompt — deletion is irreversible.
    expect(confirmSpy).toHaveBeenCalledWith(expect.stringContaining('Legacy Kurta'));
    await waitFor(() => expect(axios.delete).toHaveBeenCalledWith(
      'http://localhost:8000/api/stores/s1/products/p2'));
    confirmSpy.mockRestore();
  });

  it('deletes nothing when the seller cancels', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);

    render(<CategoriesView storeId="s1" />);
    await waitFor(() => expect(screen.getByText('Cotton')).toBeInTheDocument());
    fireEvent.click(screen.getAllByText('Open')[0]);
    await waitFor(() => expect(screen.getByLabelText('Delete Ready Kurta')).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('Delete Ready Kurta'));
    expect(axios.delete).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('surfaces a failed delete instead of appearing to succeed', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    axios.delete.mockRejectedValueOnce(new Error('boom'));

    render(<CategoriesView storeId="s1" />);
    await waitFor(() => expect(screen.getByText('Cotton')).toBeInTheDocument());
    fireEvent.click(screen.getAllByText('Open')[0]);
    await waitFor(() => expect(screen.getByLabelText('Delete Ready Kurta')).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('Delete Ready Kurta'));
    await waitFor(() => expect(screen.getByText('Failed to delete product.')).toBeInTheDocument());
    confirmSpy.mockRestore();
  });
});
