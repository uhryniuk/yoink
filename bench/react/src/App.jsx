import React from 'react'
import { Routes, Route, Link } from 'react-router-dom'
import ProductList from './ProductList'
import ProductDetail from './ProductDetail'
import Home from './Home'

export default function App() {
  return (
    <>
      <header>
        <h1>ShopBench</h1>
      </header>
      <div className="container">
        <nav>
          <Link to="/">Home</Link>
          <Link to="/products">Products</Link>
        </nav>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/products" element={<ProductList />} />
          <Route path="/products/:id" element={<ProductDetail />} />
        </Routes>
      </div>
    </>
  )
}
