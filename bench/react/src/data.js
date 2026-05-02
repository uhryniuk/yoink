// Deterministic product catalog — 200 products across 5 categories

const CATEGORIES = ['Electronics', 'Clothing', 'Books', 'Home & Garden', 'Sports']
const ADJECTIVES = ['Premium', 'Deluxe', 'Classic', 'Ultra', 'Pro', 'Lite', 'Max', 'Mini']
const NOUNS = ['Widget', 'Gadget', 'Gizmo', 'Device', 'Kit', 'Bundle', 'Pack', 'Set']

function seededRandom(seed) {
  let x = Math.sin(seed + 1) * 10000
  return x - Math.floor(x)
}

export const PRODUCTS = Array.from({ length: 200 }, (_, i) => {
  const id = i + 1
  const r = (offset = 0) => seededRandom(id * 17 + offset)
  const category = CATEGORIES[id % CATEGORIES.length]
  const adj = ADJECTIVES[Math.floor(r(1) * ADJECTIVES.length)]
  const noun = NOUNS[Math.floor(r(2) * NOUNS.length)]
  const price = (9.99 + r(3) * 990).toFixed(2)
  const rating = (1 + r(4) * 4).toFixed(1)
  const reviews = Math.floor(r(5) * 4200)

  return {
    id,
    name: `${adj} ${noun} ${id}`,
    category,
    price: parseFloat(price),
    rating: parseFloat(rating),
    reviews,
    inStock: r(6) > 0.15,
    description: `The ${adj} ${noun} ${id} is a top-rated ${category.toLowerCase()} product. ` +
      `Rated ${rating}/5 by ${reviews.toLocaleString()} verified buyers. ` +
      `${r(7) > 0.5 ? 'Free shipping on orders over $50.' : 'Express delivery available.'}`,
    tags: [category, r(8) > 0.5 ? 'bestseller' : 'new', r(9) > 0.7 ? 'sale' : null].filter(Boolean),
  }
})

export const CATEGORIES_LIST = CATEGORIES
