#!/usr/bin/env python3
"""Generate 1000 static HTML product pages for bench-static."""

import os
import random

CATEGORIES = ["Electronics", "Clothing", "Books", "Home & Garden", "Sports"]
ADJECTIVES = ["Premium", "Deluxe", "Classic", "Ultra", "Pro", "Lite", "Max", "Mini"]
NOUNS = ["Widget", "Gadget", "Gizmo", "Device", "Kit", "Bundle", "Pack", "Set"]

out_dir = os.path.join(os.path.dirname(__file__), "html")
os.makedirs(out_dir, exist_ok=True)

index_items = []

for i in range(1, 1001):
    category = CATEGORIES[i % len(CATEGORIES)]
    name = f"{random.choice(ADJECTIVES)} {random.choice(NOUNS)} {i}"
    price = round(random.uniform(9.99, 999.99), 2)
    rating = round(random.uniform(1.0, 5.0), 1)
    reviews = random.randint(0, 4200)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{name} — BenchShop</title>
</head>
<body>
  <header><h1>BenchShop</h1></header>
  <main>
    <div class="product-card" data-id="{i}">
      <h2 class="product-name">{name}</h2>
      <p class="product-category">{category}</p>
      <p class="product-price">${price}</p>
      <p class="product-rating">Rating: {rating}/5 ({reviews} reviews)</p>
      <p class="product-description">
        This is the product description for {name}. It belongs to the {category} category
        and offers excellent value for the price of ${price}.
      </p>
      <button class="add-to-cart">Add to Cart</button>
    </div>
    <nav class="pagination">
      <a href="/product-{max(1, i - 1)}.html">← Previous</a>
      <span>Product {i} of 1000</span>
      <a href="/product-{min(1000, i + 1)}.html">Next →</a>
    </nav>
  </main>
</body>
</html>"""

    path = os.path.join(out_dir, f"product-{i}.html")
    with open(path, "w") as f:
        f.write(html)

    index_items.append(f'<li><a href="/product-{i}.html" class="product-link">{name} — ${price}</a></li>')

index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>BenchShop — 1000 Products</title>
</head>
<body>
  <header><h1>BenchShop Static</h1></header>
  <main>
    <p>Serving {len(index_items)} static product pages.</p>
    <ul class="product-list">
      {"".join(index_items[:50])}
    </ul>
  </main>
</body>
</html>"""

with open(os.path.join(out_dir, "index.html"), "w") as f:
    f.write(index_html)

print(f"Generated {len(index_items)} product pages + index.html in {out_dir}/")
