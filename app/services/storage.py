from app.db.database import get_connection


def create_customer(session_id, email, name=None, phone=None):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO customers (session_id, email, name, phone)
        VALUES (?, ?, ?, ?)
    """, (session_id, email, name, phone))

    conn.commit()
    customer_id = cur.lastrowid
    conn.close()
    return customer_id


def create_order(customer_id, amount):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO orders (customer_id, amount, status)
        VALUES (?, ?, ?)
    """, (customer_id, amount, "pending"))

    conn.commit()
    order_id = cur.lastrowid
    conn.close()
    return order_id


def mark_order_paid(order_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE orders SET status = 'paid'
        WHERE id = ?
    """, (order_id,))

    conn.commit()
    conn.close()


def create_payment(order_id, reference, amount, status):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO payments (order_id, reference, status, amount)
        VALUES (?, ?, ?, ?)
    """, (order_id, reference, status, amount))

    conn.commit()
    conn.close()


def get_session_id_by_payment_reference(reference: str) -> str | None:
    """
    Get session_id from payment reference by joining payments -> orders -> customers.
    Returns None if not found.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT c.session_id
        FROM payments p
        JOIN orders o ON p.order_id = o.id
        JOIN customers c ON o.customer_id = c.id
        WHERE p.reference = ?
        LIMIT 1
    """, (reference,))

    result = cur.fetchone()
    conn.close()

    return result[0] if result else None