"""Create a small demo SQLite database with a flat `sales` table."""
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "demo.db"

REGIONS = ["North", "South", "East", "West"]
SEGMENTS = ["Consumer", "Corporate", "Small Business"]
PRODUCTS = [
    ("Laptop", "Electronics", 550, 750), ("Smartphone", "Electronics", 300, 450),
    ("Monitor", "Electronics", 120, 210), ("Office Chair", "Furniture", 90, 160),
    ("Standing Desk", "Furniture", 180, 320), ("Notebook Pack", "Stationery", 4, 9),
    ("Pen Set", "Stationery", 3, 8),
]


def build(db_path: Path = DB_PATH, seed: int = 7) -> Path:
    rnd = random.Random(seed)
    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE IF EXISTS sales")
    conn.execute(
        """CREATE TABLE sales (
            order_id TEXT, order_date TEXT, customer_id TEXT, region TEXT,
            segment TEXT, category TEXT, product TEXT, quantity INTEGER,
            revenue REAL, profit REAL)"""
    )
    customers = {f"C{i:03d}": (rnd.choice(REGIONS), rnd.choice(SEGMENTS)) for i in range(1, 81)}
    start = date(2025, 1, 1)
    rows = []
    for i in range(1, 1501):
        cust = rnd.choice(list(customers))
        region, segment = customers[cust]
        order_date = (start + timedelta(days=rnd.randint(0, 364))).isoformat()
        for _ in range(rnd.randint(1, 3)):
            product, category, cost, price = rnd.choice(PRODUCTS)
            qty = rnd.randint(1, 5)
            discount = rnd.choice([0, 0, 5, 10])
            revenue = round(qty * price * (1 - discount / 100), 2)
            rows.append((f"O{i:05d}", order_date, cust, region, segment, category,
                         product, qty, revenue, round(revenue - qty * cost, 2)))
    conn.executemany("INSERT INTO sales VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    return db_path


if __name__ == "__main__":
    print(f"Built {build()}")
