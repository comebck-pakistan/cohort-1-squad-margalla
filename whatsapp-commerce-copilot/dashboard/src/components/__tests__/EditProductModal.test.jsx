import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';

vi.mock('axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

import axios from 'axios';
import EditProductModal from '../EditProductModal';
import CategoriesView from '../CategoriesView';

const PRODUCT = {
  id: 'p1', name: 'White Cotton Kurta', base_price: 2400, description: 'Soft cotton',
  sku: 'WCK-1', image_url: '/uploads/kurta.jpg', category_id: 'c1',
  variants: [{ id: 'v1', color: 'white', size: 'M', price: 2400, stock: 5 }],
};

beforeEach(() => {
  vi.clearAllMocks();
  cleanup();
  axios.patch.mockResolvedValue({ data: { ...PRODUCT } });
  axios.put.mockResolvedValue({ data: { image_url: '/uploads/new.jpg' } });
  axios.delete.mockResolvedValue({ data: {} });
});

afterEach(() => cleanup());

describe('EditProductModal', () => {
  it('prefills the product details', () => {
    render(<EditProductModal storeId="s1" product={PRODUCT} onClose={() => {}} />);
    expect(screen.getByLabelText('Product name')).toHaveValue('White Cotton Kurta');
    expect(screen.getByLabelText('Product price')).toHaveValue(2400);
    expect(screen.getByLabelText('Product SKU')).toHaveValue('WCK-1');
    expect(screen.getByLabelText('Product description')).toHaveValue('Soft cotton');
    expect(screen.getByText(/white \/ M — PKR 2,400 · stock 5/)).toBeInTheDocument();
  });

  it('saves edited details with PATCH and closes', async () => {
    const onClose = vi.fn();
    const onSaved = vi.fn();
    render(<EditProductModal storeId="s1" product={PRODUCT} onClose={onClose} onSaved={onSaved} />);

    fireEvent.change(screen.getByLabelText('Product name'), { target: { value: 'Blue Cotton Kurta' } });
    fireEvent.change(screen.getByLabelText('Product price'), { target: { value: '2600' } });
    fireEvent.click(screen.getByText('Save changes'));

    // The single variant's colour rides along — it is what the customer's
    // colour browse filters on, so editing it here must persist.
    await waitFor(() => expect(axios.patch).toHaveBeenCalledWith(
      'http://localhost:8000/api/stores/s1/products/p1',
      { name: 'Blue Cotton Kurta', price: 2600, description: 'Soft cotton', sku: 'WCK-1', color: 'white' },
    ));
    expect(onSaved).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it('uploads a replacement picture with PUT', async () => {
    render(<EditProductModal storeId="s1" product={PRODUCT} onClose={() => {}} />);
    const file = new File(['x'], 'new.jpg', { type: 'image/jpeg' });
    fireEvent.change(screen.getByLabelText('Product picture'), { target: { files: [file] } });

    await waitFor(() => expect(axios.put).toHaveBeenCalledWith(
      'http://localhost:8000/api/stores/s1/products/p1/image',
      expect.any(FormData),
    ));
  });

  it('removes the picture with DELETE and hides the remove control', async () => {
    render(<EditProductModal storeId="s1" product={PRODUCT} onClose={() => {}} />);
    fireEvent.click(screen.getByText('Remove picture'));
    await waitFor(() => expect(axios.delete).toHaveBeenCalledWith(
      'http://localhost:8000/api/stores/s1/products/p1/image'));
    await waitFor(() => expect(screen.queryByText('Remove picture')).toBeNull());
  });

  it('a product with no image offers upload rather than replace', () => {
    render(<EditProductModal storeId="s1" product={{ ...PRODUCT, image_url: null }} onClose={() => {}} />);
    expect(screen.getByText('Upload picture')).toBeInTheDocument();
    expect(screen.queryByText('Remove picture')).toBeNull();
  });

  it("surfaces the API's reason when a save is rejected and stays open", async () => {
    axios.patch.mockRejectedValueOnce({ response: { data: { detail: 'Duplicate store-level SKU' } } });
    const onClose = vi.fn();
    render(<EditProductModal storeId="s1" product={PRODUCT} onClose={onClose} />);
    fireEvent.click(screen.getByText('Save changes'));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Duplicate store-level SKU'));
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe('CategoriesView product click', () => {
  const CATS = [{ id: 'c1', store_id: 's1', name: 'Cotton', image_url: null, display_order: 1, is_active: true, product_count: 1 }];

  beforeEach(() => {
    axios.get.mockImplementation((url) => {
      if (url.endsWith('/categories')) return Promise.resolve({ data: CATS });
      if (url.endsWith('/products')) return Promise.resolve({ data: [PRODUCT] });
      return Promise.resolve({ data: [] });
    });
  });

  it('clicking a product card opens the edit dialog', async () => {
    render(<CategoriesView storeId="s1" />);
    await waitFor(() => expect(screen.getByText('Cotton')).toBeInTheDocument());
    fireEvent.click(screen.getAllByText('Open')[0]);
    await waitFor(() => expect(screen.getByLabelText('Open White Cotton Kurta')).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('Open White Cotton Kurta'));
    expect(screen.getByRole('dialog', { name: /Edit White Cotton Kurta/ })).toBeInTheDocument();
  });

  it('the explicit Edit product button opens the same dialog', async () => {
    render(<CategoriesView storeId="s1" />);
    await waitFor(() => expect(screen.getByText('Cotton')).toBeInTheDocument());
    fireEvent.click(screen.getAllByText('Open')[0]);
    await waitFor(() => expect(screen.getByText('Edit product')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Edit product'));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByLabelText('Product name')).toHaveValue('White Cotton Kurta');
  });

  it('shows the product price on the card', async () => {
    render(<CategoriesView storeId="s1" />);
    await waitFor(() => expect(screen.getByText('Cotton')).toBeInTheDocument());
    fireEvent.click(screen.getAllByText('Open')[0]);
    await waitFor(() => expect(screen.getByText('PKR 2,400')).toBeInTheDocument());
  });
});
