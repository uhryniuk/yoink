import React, { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { PRODUCTS } from './data'

function generateReviews(product) {
  const count = Math.min(5, Math.ceil(product.reviews / 800))
  const names = ['Alex T.', 'Jordan M.', 'Sam K.', 'Riley P.', 'Casey R.']
  const bodies = [
    'Exactly as described. Shipping was fast and the quality exceeded expectations.',
    'Good value for the price. Would buy again.',
    'Solid product, does what it says. Minor packaging issue but product was fine.',
    'Outstanding quality. Highly recommend to anyone looking for this type of item.',
    'Works great. Setup was easy and it has been reliable since day one.',
  ]
  return names.slice(0, count).map((name, i) => ({
    author: name,
    rating: Math.max(1, Math.round(product.rating - (i === 2 ? 1 : 0))),
    body: bodies[i % bodies.length],
  }))
}

export default function ProductDetail() {
  const { id } = useParams()
  const [product, setProduct] = useState(null)
  const [reviews, setReviews] = useState([])
  const [reviewsLoaded, setReviewsLoaded] = useState(false)

  useEffect(() => {
    // Simulate async product + review loading
    const p = PRODUCTS.find(x => x.id === parseInt(id, 10))
    setProduct(p || null)
    setReviewsLoaded(false)

    if (p) {
      const t = setTimeout(() => {
        setReviews(generateReviews(p))
        setReviewsLoaded(true)
      }, 400)
      return () => clearTimeout(t)
    }
  }, [id])

  if (!product) {
    return <p>Product not found. <Link to="/products">Back to products</Link></p>
  }

  return (
    <div className="product-detail">
      <Link to="/products" style={{ fontSize: '.9rem', color: '#888' }}>← Back to products</Link>
      <h2 style={{ marginTop: '1rem' }}>{product.name}</h2>
      <p className="category" style={{ margin: '.5rem 0' }}>{product.category}</p>
      <p className="price" style={{ fontSize: '1.5rem', margin: '.5rem 0' }}>${product.price.toFixed(2)}</p>
      <p className="rating" style={{ fontSize: '1rem', margin: '.5rem 0' }}>
        {'★'.repeat(Math.round(product.rating))}{'☆'.repeat(5 - Math.round(product.rating))} {product.rating}/5
        <span style={{ color: '#888', fontSize: '.85rem', marginLeft: '.5rem' }}>
          ({product.reviews.toLocaleString()} reviews)
        </span>
      </p>
      {product.tags.map(t => (
        <span key={t} className="badge" style={{ marginRight: '.3rem' }}>{t}</span>
      ))}
      <p style={{ margin: '1.5rem 0', lineHeight: 1.6 }}>{product.description}</p>
      {product.inStock
        ? <button className="btn">Add to Cart</button>
        : <p style={{ color: '#c00' }}>Out of stock</p>}

      <div className="reviews">
        <h3 style={{ marginBottom: '1rem' }}>Customer Reviews</h3>
        {!reviewsLoaded && <div className="spinner">Loading reviews…</div>}
        {reviewsLoaded && reviews.map((r, i) => (
          <div key={i} className="review">
            <strong>{r.author}</strong>
            <span style={{ marginLeft: '.5rem', color: '#f90' }}>
              {'★'.repeat(r.rating)}{'☆'.repeat(5 - r.rating)}
            </span>
            <p style={{ marginTop: '.3rem', color: '#444' }}>{r.body}</p>
          </div>
        ))}
        {reviewsLoaded && <p className="reviews-loaded" style={{ display: 'none' }}>reviews-ready</p>}
      </div>
    </div>
  )
}
