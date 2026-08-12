import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';

vi.mock('axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import axios from 'axios';
import CategoriesView from '../CategoriesView';

const CATS = [
  { id: 'c1', store_id: 's1', name: 'Cotton', image_url: null, display_order: 1, is_active: true, product_count: 2 },
  { id: 'c2', store_id: 's1', name: 'Lawn', image_url: null, display_order: 2, is_active: false, product_count: 0 },
];
const PRODUCTS = [
  { id: 'p1', name: 'White Cotton Kurta', category_id: 'c1', image_url: null, base_price: 1000, variants: [] },
  { id: 'p2', name: 'Blue Cotton Shirt', category_id: 'c1', image_url: null, base_price: 1200, variants: [] },
  { id: 'p3', name: 'Loose Item', category_id: null, image_url: null, base_price: 500, variants: [] },
];

function mockLists(cats = CATS, prods = PRODUCTS) {
  axios.get.mockImplementation((url) => {
    if (url.endsWith('/categories')) return Promise.resolve({ data: cats });
    if (url.endsWith('/products')) return Promise.resolve({ data: prods });
    return Promise.resolve({ data: [] });
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  cleanup();
  mockLists();
  axios.post.mockResolvedValue({ data: {} });
  axios.patch.mockResolvedValue({ data: {} });
  axios.delete.mockResolvedValue({ data: {} });
});

describe('CategoriesView', () => {
  it('loads and renders category folders with counts + Uncategorized', async () => {
    render(<CategoriesView storeId="s1" />);
    await waitFor(() => expect(screen.getByText('Cotton')).toBeInTheDocument());
    expect(screen.getByText('Lawn')).toBeInTheDocument();
    expect(screen.getByText('2 products')).toBeInTheDocument();      // Cotton count
    expect(screen.getByText('Uncategorized')).toBeInTheDocument();
    expect(screen.getByText('1 products')).toBeInTheDocument();      // uncategorized count
    // inactive marker
    expect(screen.getByText('Inactive')).toBeInTheDocument();
  });

  it('creates a category via POST and reloads', async () => {
    render(<CategoriesView storeId="s1" />);
    await waitFor(() => expect(screen.getByText('Cotton')).toBeInTheDocument());
    fireEvent.click(screen.getByText('+ New Category'));
    fireEvent.change(screen.getByLabelText('Category name'), { target: { value: 'Silk' } });
    fireEvent.click(screen.getByText('Create'));
    await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
      'http://localhost:8000/api/stores/s1/categories',
      { name: 'Silk', description: null },
    ));
  });

  it('deactivates a category via PATCH', async () => {
    render(<CategoriesView storeId="s1" />);
    await waitFor(() => expect(screen.getByText('Cotton')).toBeInTheDocument());
    // Cotton is active → shows "Deactivate"
    fireEvent.click(screen.getAllByText('Deactivate')[0]);
    await waitFor(() => expect(axios.patch).toHaveBeenCalledWith(
      'http://localhost:8000/api/stores/s1/categories/c1',
      { is_active: false },
    ));
  });

  it('opens a category and shows its products', async () => {
    render(<CategoriesView storeId="s1" />);
    await waitFor(() => expect(screen.getByText('Cotton')).toBeInTheDocument());
    fireEvent.click(screen.getAllByText('Open')[0]);
    await waitFor(() => expect(screen.getByText('White Cotton Kurta')).toBeInTheDocument());
    expect(screen.getByText('Blue Cotton Shirt')).toBeInTheDocument();
    // add-product entry available for a real category
    expect(screen.getByText('+ Add Product')).toBeInTheDocument();
  });

  it('opens Add Product modal scoped to the category', async () => {
    render(<CategoriesView storeId="s1" />);
    await waitFor(() => expect(screen.getByText('Cotton')).toBeInTheDocument());
    fireEvent.click(screen.getAllByText('Open')[0]);
    await waitFor(() => expect(screen.getByText('+ Add Product')).toBeInTheDocument());
    fireEvent.click(screen.getByText('+ Add Product'));
    // modal title includes category name
    expect(screen.getByText('Add New Product — Cotton')).toBeInTheDocument();
  });

  it('moves a product to another category via PATCH', async () => {
    render(<CategoriesView storeId="s1" />);
    await waitFor(() => expect(screen.getByText('Cotton')).toBeInTheDocument());
    fireEvent.click(screen.getAllByText('Open')[0]);
    await waitFor(() => expect(screen.getByText('White Cotton Kurta')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Move White Cotton Kurta'), { target: { value: 'c2' } });
    await waitFor(() => expect(axios.patch).toHaveBeenCalledWith(
      'http://localhost:8000/api/stores/s1/products/p1/category',
      { category_id: 'c2' },
    ));
  });

  it('shows Uncategorized products when opened', async () => {
    render(<CategoriesView storeId="s1" />);
    await waitFor(() => expect(screen.getByText('Cotton')).toBeInTheDocument());
    // the Uncategorized folder heading is a button
    fireEvent.click(screen.getAllByText('Uncategorized')[0]);
    await waitFor(() => expect(screen.getByText('Loose Item')).toBeInTheDocument());
  });

  it('surfaces a 409 as an actionable delete error (no silent delete)', async () => {
    axios.delete.mockRejectedValueOnce({ response: { status: 409 } });
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
    const confirmSpy = vi.spyOn(window, 'confirm').mockImplementation(() => true);
    render(<CategoriesView storeId="s1" />);
    await waitFor(() => expect(screen.getByText('Cotton')).toBeInTheDocument());
    fireEvent.click(screen.getAllByText('Delete')[0]);
    await waitFor(() => expect(alertSpy).toHaveBeenCalledWith(
      expect.stringMatching(/not empty/i),
    ));
    alertSpy.mockRestore();
    confirmSpy.mockRestore();
  });

  it('store switch clears stale state and refetches', async () => {
    const { rerender } = render(<CategoriesView storeId="s1" />);
    await waitFor(() => expect(screen.getByText('Cotton')).toBeInTheDocument());

    // second store has different categories
    mockLists(
      [{ id: 'x1', store_id: 's2', name: 'Sneakers', image_url: null, display_order: 1, is_active: true, product_count: 0 }],
      [],
    );
    rerender(<CategoriesView storeId="s2" />);
    await waitFor(() => expect(screen.getByText('Sneakers')).toBeInTheDocument());
    // stale store-1 category is gone
    expect(screen.queryByText('Cotton')).toBeNull();
  });

  it('ignores a late response from the previous store', async () => {
    // Store s1 resolves slowly; we switch to s2 before it lands.
    let resolveS1;
    const s1Promise = new Promise((res) => { resolveS1 = res; });
    axios.get.mockImplementation((url) => {
      if (url.includes('/stores/s1/')) return s1Promise; // hang
      if (url.endsWith('/categories')) return Promise.resolve({ data: [{ id: 'x1', store_id: 's2', name: 'Sneakers', image_url: null, display_order: 1, is_active: true, product_count: 0 }] });
      return Promise.resolve({ data: [] });
    });

    const { rerender } = render(<CategoriesView storeId="s1" />);
    rerender(<CategoriesView storeId="s2" />);
    await waitFor(() => expect(screen.getByText('Sneakers')).toBeInTheDocument());

    // Now the stale s1 response arrives — it must be ignored.
    resolveS1({ data: CATS });
    await Promise.resolve();
    expect(screen.queryByText('Cotton')).toBeNull();
    expect(screen.getByText('Sneakers')).toBeInTheDocument();
  });
});
