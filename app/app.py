import os
import psycopg
from flask import Flask, request, jsonify

app = Flask(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@pg-node1:5432,pg-node2:5432/postgres?target_session_attrs=read-write",
)


def get_connection():
    return psycopg.connect(DATABASE_URL)


with get_connection() as conn:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id   serial PRIMARY KEY,
            item text,
            qty  int
        )
    """)
    conn.commit()


@app.route("/api/orders", methods=["POST"])
def create_order():
    data = request.get_json()
    item = data["item"]
    qty = data["qty"]

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO orders (item, qty) VALUES (%s, %s)",
            (item, qty),
        )

    return jsonify({"status": "created", "item": item, "qty": qty}), 201


@app.route("/api/orders", methods=["GET"])
def list_orders():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, item, qty FROM orders ORDER BY id")
            rows = [{"id": r[0], "item": r[1], "qty": r[2]} for r in cur.fetchall()]

    return jsonify(rows)


@app.route("/health")
def health():
    return jsonify({"status": "ok", "db": DATABASE_URL})
