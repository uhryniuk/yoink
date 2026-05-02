import React from 'react'
import { Link } from 'react-router-dom'
import { PRODUCTS, CATEGORIES_LIST } from './data'

export default function Home() {
  return (
    <div>
      <h2 style={{ marginBottom: '1rem' }}>Welcome to ShopBench</h2>
      <p style={{ marginBottom: '1.5rem', color: '#555' }}>
        A realistic ecommerce SPA for load testing yoink. {PRODUCTS.length} products
        across {CATEGORIES_LIST.length} categories, loaded in batches to simulate lazy rendering.
      </p>
      <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
        {CATEGORIES_LIST.map(cat => (
          <Link
            key={cat}
            to={`/products?category=${encodeURIComponent(cat)}`}
            style={{
              background: 'white', padding: '1rem 1.5rem', borderRadius: '8px',
              boxShadow: '0 1px 4px rgba(0,0,0,.1)', textDecoration: 'none', color: '#1a1a2e',
              fontWeight: 500,
            }}
          >
            {cat}
          </Link>
        ))}
      </div>
      <p style={{ marginTop: '2rem' }}>
        <Link to="/products">Browse all {PRODUCTS.length} products →</Link>
      </p>
    </div>
  )
}
