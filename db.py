# connecting to the database

import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

def get_conn():
    return psycopg.connect(
        host=os.getenv("PGHOST"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "postgres"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD"),
        sslmode=os.getenv("PGSSLMODE", "require"),

    )

if __name__ == "__main__":
    with get_conn() as conn:
        print("Connected!", conn.execute("SELECT version()").fetchone()[0])