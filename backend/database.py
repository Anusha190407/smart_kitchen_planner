import sqlite3
import os
import json
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "smart_kitchen.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

@contextmanager
def get_db():
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS restaurants (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_updated TEXT NOT NULL
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            restaurant_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (restaurant_id) REFERENCES restaurants (id) ON DELETE CASCADE
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS meals (
            restaurant_id TEXT NOT NULL,
            meal_id INTEGER NOT NULL,
            meal_name TEXT NOT NULL,
            category TEXT NOT NULL,
            cuisine TEXT NOT NULL,
            base_price_inr REAL NOT NULL,
            PRIMARY KEY (restaurant_id, meal_id),
            FOREIGN KEY (restaurant_id) REFERENCES restaurants (id) ON DELETE CASCADE
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_orders (
            restaurant_id TEXT NOT NULL,
            date TEXT NOT NULL,
            day_of_week TEXT NOT NULL,
            meal_id INTEGER NOT NULL,
            meal_name TEXT NOT NULL,
            category TEXT NOT NULL,
            cuisine TEXT NOT NULL,
            checkout_price REAL NOT NULL,
            base_price REAL NOT NULL,
            promo_active INTEGER NOT NULL,
            featured_on_menu INTEGER NOT NULL,
            festival_or_event INTEGER NOT NULL,
            num_orders INTEGER NOT NULL,
            PRIMARY KEY (restaurant_id, date, meal_id),
            FOREIGN KEY (restaurant_id) REFERENCES restaurants (id) ON DELETE CASCADE
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS next_7_days_inputs (
            restaurant_id TEXT NOT NULL,
            date TEXT NOT NULL,
            day_of_week TEXT NOT NULL,
            meal_id INTEGER NOT NULL,
            meal_name TEXT NOT NULL,
            category TEXT NOT NULL,
            cuisine TEXT NOT NULL,
            checkout_price REAL NOT NULL,
            base_price REAL NOT NULL,
            promo_active INTEGER NOT NULL,
            featured_on_menu INTEGER NOT NULL,
            festival_or_event INTEGER NOT NULL,
            predicted_orders REAL,
            predicted_low REAL,
            predicted_high REAL,
            confidence TEXT,
            PRIMARY KEY (restaurant_id, date, meal_id),
            FOREIGN KEY (restaurant_id) REFERENCES restaurants (id) ON DELETE CASCADE
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS recipes (
            restaurant_id TEXT NOT NULL,
            valid_from TEXT NOT NULL,
            meal_id INTEGER NOT NULL,
            meal_name TEXT NOT NULL,
            category TEXT NOT NULL,
            cuisine TEXT NOT NULL,
            ingredient TEXT NOT NULL,
            unit TEXT NOT NULL,
            qty_per_serving REAL NOT NULL,
            PRIMARY KEY (restaurant_id, meal_id, ingredient),
            FOREIGN KEY (restaurant_id) REFERENCES restaurants (id) ON DELETE CASCADE
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS ingredient_master (
            restaurant_id TEXT NOT NULL,
            valid_from TEXT NOT NULL,
            ingredient TEXT NOT NULL,
            unit TEXT NOT NULL,
            shelf_life_days INTEGER NOT NULL,
            supplier_lead_time_days INTEGER NOT NULL,
            unit_cost_inr REAL NOT NULL,
            PRIMARY KEY (restaurant_id, ingredient),
            FOREIGN KEY (restaurant_id) REFERENCES restaurants (id) ON DELETE CASCADE
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory_history (
            restaurant_id TEXT NOT NULL,
            date TEXT NOT NULL,
            ingredient TEXT NOT NULL,
            unit TEXT NOT NULL,
            opening_stock REAL NOT NULL,
            received_qty REAL NOT NULL,
            used_qty REAL NOT NULL,
            wasted_qty REAL NOT NULL,
            shelf_life_days INTEGER NOT NULL,
            supplier_lead_time_days INTEGER NOT NULL,
            unit_cost REAL NOT NULL,
            PRIMARY KEY (restaurant_id, date, ingredient),
            FOREIGN KEY (restaurant_id) REFERENCES restaurants (id) ON DELETE CASCADE
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS current_stock (
            restaurant_id TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            ingredient TEXT NOT NULL,
            unit TEXT NOT NULL,
            stock_on_hand REAL NOT NULL,
            earliest_expiry_date TEXT,
            qty_in_earliest_batch REAL,
            order_in_transit_qty REAL,
            order_arrival_date TEXT,
            PRIMARY KEY (restaurant_id, ingredient),
            FOREIGN KEY (restaurant_id) REFERENCES restaurants (id) ON DELETE CASCADE
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS model_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            restaurant_id TEXT NOT NULL,
            version TEXT NOT NULL,
            trained_at TEXT NOT NULL,
            metrics_json TEXT NOT NULL,
            baselines_json TEXT NOT NULL,
            feature_importance_json TEXT NOT NULL,
            validation_chart_json TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (restaurant_id) REFERENCES restaurants (id) ON DELETE CASCADE
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            restaurant_id TEXT PRIMARY KEY,
            email_alerts_enabled INTEGER DEFAULT 0,
            alert_email TEXT,
            notify_stockout INTEGER DEFAULT 1,
            notify_expiry INTEGER DEFAULT 1,
            notify_arrival INTEGER DEFAULT 1,
            FOREIGN KEY (restaurant_id) REFERENCES restaurants (id) ON DELETE CASCADE
        )
        """)

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at", DB_PATH)
