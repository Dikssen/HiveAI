"""
Sample backend code for code review.
Contains intentional issues for the AI to find.
"""
import psycopg2
import requests


# Hardcoded credentials — bad practice
DB_PASSWORD = "super_secret_password_123"
API_KEY = "sk-live-abc123xyz789"


def get_db_connection():
    # Hardcoded DB URL
    conn = psycopg2.connect(
        host="localhost",
        database="production",
        user="admin",
        password=DB_PASSWORD,
    )
    return conn


def get_user_orders(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    # SQL injection vulnerability — string concatenation
    query = "SELECT * FROM orders WHERE user_id = " + str(user_id)
    cursor.execute(query)
    orders = cursor.fetchall()
    conn.close()
    return orders


def process_payment(order_id, card_number):
    print(f"Processing payment for order {order_id}")  # should use logging
    try:
        response = requests.post(
            "https://payment-gateway.example.com/charge",
            json={
                "order_id": order_id,
                "card": card_number,
                "api_key": API_KEY,
            },
            # No timeout specified — can hang forever
        )
        result = response.json()
        print(f"Payment result: {result}")
        return result
    except:  # bare except — catches everything including KeyboardInterrupt
        print("Payment failed")
        return None


def generate_report(start_date, end_date):
    # TODO: This is very slow for large datasets — needs pagination
    # FIXME: Memory leak when result set is large
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT o.*, u.email, u.name FROM orders o JOIN users u ON o.user_id = u.id "
        "WHERE o.created_at BETWEEN %s AND %s",
        (start_date, end_date),
    )
    # Loading all rows into memory at once — bad for large datasets
    all_rows = cursor.fetchall()
    conn.close()
    return all_rows


def send_notification(user_id, message):
    # No input validation
    # No rate limiting
    # No error handling
    requests.post(
        "https://notifications.example.com/send",
        json={"user_id": user_id, "message": message},
    )


class UserService:
    def get_user(self, user_id):
        # No caching
        # N+1 query problem — called in a loop elsewhere
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        return cursor.fetchone()

    def update_user(self, user_id, data):
        # No input validation
        # No authorization check
        conn = get_db_connection()
        cursor = conn.cursor()
        for key, value in data.items():
            # Dynamic column name — SQL injection risk
            cursor.execute(
                f"UPDATE users SET {key} = %s WHERE id = %s", (value, user_id)
            )
        conn.commit()
        conn.close()
