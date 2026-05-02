import React, { useState, useEffect } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { PRODUCTS, CATEGORIES_LIST } from './data'

// Simulate batch loading: 3 tranches with realistic delays
// Batch 0: immediate, Batch 1: 300ms, Batch 2: 800ms
function useBatchedProducts(filtered) {
  const [visible, setVisible] = useState([])

  useEffect(() => {
    setVisible([])
    const batches = [
      filtered.slice(0, Math.ceil(filtered.length / 3)),
      filtered.slice(Math.ceil(filtered.length / 3), Math.ceil(2 * filtered.length / 3)),
      filtered.slice(Math.ceil(2 * filtered.length / 3)),
    ]

    setVisible(batches[0])

    const t1 = setTimeout(() => setVisible(prev => [...prev, ...batches[1]]), 300)
    const t2 = setTimeout(() => setVisible(prev => [...prev, ...batches[2]]), 800)

    return () => { clearTimeout(t1); clearTimeout(t2) }
  }, [filtered.length, filtered[0]?.id])

  return { visible, total: filtered.length, loading: visible.length < filtered.length }
}

export default function ProductList() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [sort, setSort] = useState('default')
  const categoryFilter = searchParams.get('category') || ''

  const filtered = PRODUCTS.filter(p =>
    !categoryFilter || p.category === categoryFilter
  ).sort((a, b) => {
    if (sort === 'price-asc') return a.price - b.price
    if (sort === 'price-desc') return b.price - a.price
    if (sort === 'rating') return b.rating - a.rating
    return a.id - b.id
  })

  const { visible, total, loading } = useBatchedProducts(filtered)

  return (
    <div>
      <div className="filters">
        <select value={categoryFilter} onChange={e => {
          const v = e.target.value
          v ? setSearchParams({ category: v }) : setSearchParams({})
        }}>
          <option value="">All Categories</option>
          {CATEGORIES_LIST.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={sort} onChange={e => setSort(e.target.value)}>
          <option value="default">Default sort</option>
          <option value="price-asc">Price: Low → High</option>
          <option value="price-desc">Price: High → Low</option>
          <option value="rating">Top Rated</option>
        </select>
        <span style={{ color: '#666', alignSelf: 'center', fontSize: '.9rem' }}>
          {visible.length}/{total} products
          {loading && <span style={{ color: '#e44', marginLeft: '.5rem' }}>loading…</span>}
        </span>
      </div>

      <div className="product-grid">
        {visible.map(p => (
          <Link key={p.id} to={`/products/${p.id}`} style={{ textDecoration: 'none', color: 'inherit' }}>
            <div className="product-card">
              {p.tags.includes('bestseller') && <span className="badge">Bestseller</span>}
              {p.tags.includes('sale') && <span className="badge" style={{ background: '#ffe2e2', color: '#c00' }}>Sale</span>}
              <p className="category">{p.category}</p>
              <h3>{p.name}</h3>
              <p className="rating">{'★'.repeat(Math.round(p.rating))}{'☆'.repeat(5 - Math.round(p.rating))} {p.rating}</p>
              <p className="price">${p.price.toFixed(2)}</p>
              <p style={{ fontSize: '.75rem', color: '#888' }}>{p.reviews.toLocaleString()} reviews</p>
              {!p.inStock && <p style={{ color: '#c00', fontSize: '.75rem' }}>Out of stock</p>}
            </div>
          </Link>
        ))}
      </div>

      {loading && (
        <div className="spinner">Loading more products…</div>
      )}
    </div>
  )
}
