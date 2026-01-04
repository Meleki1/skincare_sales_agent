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
