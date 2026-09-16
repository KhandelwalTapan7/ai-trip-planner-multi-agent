import json
import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

DB_HOST = os.environ.get("POSTGRES_HOST", "db")
DB_PORT = os.environ.get("POSTGRES_PORT", "5432")
DB_NAME = os.environ.get("POSTGRES_DB", "trip_planner")
DB_USER = os.environ.get("POSTGRES_USER", "trip_planner")
DB_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "trip_planner")


@contextmanager
def get_conn():
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('CREATE EXTENSION IF NOT EXISTS pgcrypto;')
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS trips (
                    trip_id UUID PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    origin TEXT,
                    destination TEXT,
                    start_date DATE,
                    end_date DATE,
                    travelers INTEGER DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'RUNNING',
                    current_step TEXT,
                    itinerary JSONB,
                    error_message TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                CREATE INDEX IF NOT EXISTS idx_trips_user_created
                    ON trips (user_id, created_at DESC);
                """
            )


def create_user(email, password_hash):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING user_id, email",
                (email, password_hash),
            )
            return cur.fetchone()


def get_user_by_email(email):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE email = %s", (email,))
            return cur.fetchone()


def create_trip(trip_id, user_id, origin, destination, start_date, end_date, travelers):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO trips (trip_id, user_id, origin, destination, start_date, end_date,
                                    travelers, status, current_step)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'RUNNING', 'planner')
                """,
                (trip_id, user_id, origin, destination, start_date, end_date, travelers),
            )


def mark_step(trip_id, step):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE trips SET current_step = %s, status = 'RUNNING' WHERE trip_id = %s",
                (step, trip_id),
            )


def mark_failed(trip_id, error_message):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE trips SET status = 'FAILED', error_message = %s WHERE trip_id = %s",
                (error_message, trip_id),
            )


def save_itinerary(trip_id, itinerary: dict):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE trips
                SET itinerary = %s, status = 'SUCCEEDED', current_step = 'writer'
                WHERE trip_id = %s
                """,
                (json.dumps(itinerary), trip_id),
            )


def get_trip(trip_id):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM trips WHERE trip_id = %s", (trip_id,))
            return cur.fetchone()


def list_trips(user_id):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT trip_id, origin, destination, start_date, end_date, status, created_at
                FROM trips
                WHERE user_id = %s
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
            return cur.fetchall()
