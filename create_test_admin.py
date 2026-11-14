# Inserts the test_admin user into gym_user and user_login.
# Run once from this directory: python create_test_admin.py

import psycopg
from werkzeug.security import generate_password_hash

from db import get_conn

FIRST_NAME = "test"
LAST_NAME = "admin"
EMAIL = "test_admin@hokiefit.test"
PASSWORD = "Test1!."
ROLE = "staff"  # gym_user.role only allows gym_user, instructor or staff


def main():
    password_hash = generate_password_hash(PASSWORD)

    try:
        # The connection block commits on success and rolls back on error,
        # so a user is never created without a matching login.
        with get_conn() as conn:
            user_id = conn.execute(
                """
                INSERT INTO gym_user (first_name, last_name, email, role)
                VALUES (%s, %s, %s, %s)
                RETURNING user_id
                """,
                (FIRST_NAME, LAST_NAME, EMAIL, ROLE),
            ).fetchone()[0]

            conn.execute(
                "INSERT INTO user_login (user_id, password_hash) VALUES (%s, %s)",
                (user_id, password_hash),
            )
    except psycopg.errors.UniqueViolation:
        print(f"A user with email {EMAIL} already exists; nothing was inserted.")
        return

    print(f"Created {EMAIL} with user_id {user_id}")


if __name__ == "__main__":
    main()
