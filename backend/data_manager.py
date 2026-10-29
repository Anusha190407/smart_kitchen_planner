import os
import io
import json
import datetime
import pandas as pd
import numpy as np
from openpyxl import Workbook, load_workbook
from backend.database import get_db

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
SAMPLE_EXCEL_PATH = os.path.join(DATA_DIR, "smart_kitchen_dataset.xlsx")

REQUIRED_COLUMNS = {
    "Meals": ["meal_id", "meal_name", "category", "cuisine", "base_price_inr"],
    "Daily_Orders": ["date", "day_of_week", "meal_id", "meal_name", "category", "cuisine", "checkout_price", "base_price", "promo_active", "featured_on_menu", "festival_or_event", "num_orders"],
    "Next_7_Days_Inputs": ["date", "day_of_week", "meal_id", "meal_name", "category", "cuisine", "checkout_price", "base_price", "promo_active", "featured_on_menu", "festival_or_event", "predicted_orders"],
    "Recipes": ["valid_from", "meal_id", "meal_name", "category", "cuisine", "ingredient", "unit", "qty_per_serving"],
    "Ingredient_Master": ["valid_from", "ingredient", "unit", "shelf_life_days", "supplier_lead_time_days", "unit_cost_inr"],
    "Inventory_History": ["date", "ingredient", "unit", "opening_stock", "received_qty", "used_qty", "wasted_qty", "shelf_life_days", "supplier_lead_time_days", "unit_cost"],
    "Current_Stock": ["as_of_date", "ingredient", "unit", "stock_on_hand", "earliest_expiry_date", "qty_in_earliest_batch", "order_in_transit_qty", "order_arrival_date"]
}

def parse_date_str(val):
    if pd.isna(val) or val is None or str(val).strip() == "":
        return None
    val_str = str(val).strip().split(" ")[0]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            dt = datetime.datetime.strptime(val_str, fmt).date()
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    try:
        dt = pd.to_datetime(val).date()
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return None

def format_date_display(iso_date):
    if not iso_date:
        return ""
    try:
        parts = str(iso_date).split("-")
        if len(parts) == 3:
            return f"{parts[2]}-{parts[1]}-{parts[0]}"
    except Exception:
        pass
    return str(iso_date)

def validate_sheet_data(sheet_name: str, rows: list, existing_data: dict = None) -> list:
    errors = []
    if sheet_name not in REQUIRED_COLUMNS:
        return [f"Unknown sheet or table name: {sheet_name}"]
    
    req_cols = REQUIRED_COLUMNS[sheet_name]
    if not rows:
        return [f"Table {sheet_name} is empty."]
    
    first_row = rows[0]
    missing_cols = [c for c in req_cols if c not in first_row]
    if missing_cols:
        errors.append(f"Missing required columns in {sheet_name}: {', '.join(missing_cols)}")
        return errors

    date_cols = [c for c in ["date", "valid_from", "as_of_date", "earliest_expiry_date", "order_arrival_date"] if c in req_cols]
    seen_date_meal = set()
    seen_dates = set()
    
    for idx, row in enumerate(rows):
        row_num = idx + 1
        for dc in date_cols:
            if dc in row and row[dc] is not None and str(row[dc]).strip() != "":
                parsed = parse_date_str(row[dc])
                if not parsed:
                    errors.append(f"Row {row_num}: Invalid date format '{row[dc]}' for column {dc}.")
        
        # Check negative quantities
        for num_col in ["base_price_inr", "checkout_price", "base_price", "num_orders", "qty_per_serving", 
                        "shelf_life_days", "supplier_lead_time_days", "unit_cost_inr", "opening_stock", 
                        "received_qty", "used_qty", "wasted_qty", "unit_cost", "stock_on_hand", "qty_in_earliest_batch"]:
            if num_col in row and row[num_col] is not None and str(row[num_col]).strip() != "":
                try:
                    val = float(row[num_col])
                    if val < 0:
                        errors.append(f"Row {row_num}: Negative value {val} not allowed for {num_col}.")
                except ValueError:
                    errors.append(f"Row {row_num}: Column {num_col} must be numeric.")

        if sheet_name == "Daily_Orders":
            d_val = parse_date_str(row.get("date"))
            m_id = row.get("meal_id")
            if d_val and m_id is not None:
                key = (d_val, int(m_id) if str(m_id).isdigit() else str(m_id))
                if key in seen_date_meal:
                    errors.append(f"Row {row_num}: Duplicate order record for date {d_val} and meal_id {m_id}.")
                seen_date_meal.add(key)
                seen_dates.add(d_val)
                
    if sheet_name == "Daily_Orders" and len(seen_dates) > 1:
        sorted_dates = sorted([datetime.datetime.strptime(d, "%Y-%m-%d").date() for d in seen_dates])
        cur = sorted_dates[0]
        end = sorted_dates[-1]
        missing_days = []
        while cur <= end:
            if cur.strftime("%Y-%m-%d") not in seen_dates:
                missing_days.append(cur.strftime("%d-%m-%Y"))
            cur += datetime.timedelta(days=1)
        if missing_days:
            sample_missing = missing_days[:5]
            more = f" and {len(missing_days)-5} more" if len(missing_days) > 5 else ""
            errors.append(f"Missing days detected in history: {', '.join(sample_missing)}{more}.")

    # Cross-table validation if existing_data provided
    if existing_data:
        known_meal_ids = existing_data.get("known_meal_ids", set())
        known_ingredients = existing_data.get("known_ingredients", set())

        if sheet_name in ["Daily_Orders", "Next_7_Days_Inputs", "Recipes"] and known_meal_ids:
            for idx, row in enumerate(rows):
                m_id = row.get("meal_id")
                if m_id is not None:
                    try:
                        m_id_int = int(m_id)
                        if m_id_int not in known_meal_ids:
                            errors.append(f"Row {idx+1}: Unknown meal_id {m_id}.")
                    except Exception:
                        pass
                        
        if sheet_name == "Recipes" and known_ingredients:
            for idx, row in enumerate(rows):
                ing = str(row.get("ingredient", "")).strip()
                if ing and ing not in known_ingredients:
                    errors.append(f"Row {idx+1}: Recipe ingredient '{ing}' not found in Ingredient_Master.")

        if sheet_name in ["Inventory_History", "Current_Stock"] and known_ingredients:
            for idx, row in enumerate(rows):
                ing = str(row.get("ingredient", "")).strip()
                if ing and ing not in known_ingredients:
                    errors.append(f"Row {idx+1}: Ingredient '{ing}' not found in Ingredient_Master.")

    return errors

def load_sample_dataset_for_restaurant(restaurant_id: str):
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Load Meals
        df_meals = pd.read_csv(os.path.join(DATA_DIR, "meals.csv"))
        for _, r in df_meals.iterrows():
            cursor.execute("""
                INSERT OR REPLACE INTO meals (restaurant_id, meal_id, meal_name, category, cuisine, base_price_inr)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (restaurant_id, int(r['meal_id']), str(r['meal_name']), str(r['category']), str(r['cuisine']), float(r['base_price_inr'])))

        # Load Ingredient Master
        df_ing = pd.read_csv(os.path.join(DATA_DIR, "ingredient_master.csv"))
        for _, r in df_ing.iterrows():
            cursor.execute("""
                INSERT OR REPLACE INTO ingredient_master (restaurant_id, valid_from, ingredient, unit, shelf_life_days, supplier_lead_time_days, unit_cost_inr)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (restaurant_id, parse_date_str(r['valid_from']), str(r['ingredient']), str(r['unit']), int(r['shelf_life_days']), int(r['supplier_lead_time_days']), float(r['unit_cost_inr'])))

        # Load Recipes
        df_rec = pd.read_csv(os.path.join(DATA_DIR, "recipes.csv"))
        for _, r in df_rec.iterrows():
            cursor.execute("""
                INSERT OR REPLACE INTO recipes (restaurant_id, valid_from, meal_id, meal_name, category, cuisine, ingredient, unit, qty_per_serving)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (restaurant_id, parse_date_str(r['valid_from']), int(r['meal_id']), str(r['meal_name']), str(r['category']), str(r['cuisine']), str(r['ingredient']), str(r['unit']), float(r['qty_per_serving'])))

        # Load Daily Orders
        df_orders = pd.read_csv(os.path.join(DATA_DIR, "daily_orders.csv"))
        for _, r in df_orders.iterrows():
            cursor.execute("""
                INSERT OR REPLACE INTO daily_orders (restaurant_id, date, day_of_week, meal_id, meal_name, category, cuisine, checkout_price, base_price, promo_active, featured_on_menu, festival_or_event, num_orders)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (restaurant_id, parse_date_str(r['date']), str(r['day_of_week']), int(r['meal_id']), str(r['meal_name']), str(r['category']), str(r['cuisine']), float(r['checkout_price']), float(r['base_price']), int(r['promo_active']), int(r['featured_on_menu']), int(r['festival_or_event']), int(r['num_orders'])))

        # Load Next 7 Days Inputs
        df_next = pd.read_csv(os.path.join(DATA_DIR, "next_7_days_inputs.csv"))
        for _, r in df_next.iterrows():
            pred = None if pd.isna(r.get('predicted_orders')) else float(r['predicted_orders'])
            cursor.execute("""
                INSERT OR REPLACE INTO next_7_days_inputs (restaurant_id, date, day_of_week, meal_id, meal_name, category, cuisine, checkout_price, base_price, promo_active, featured_on_menu, festival_or_event, predicted_orders)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (restaurant_id, parse_date_str(r['date']), str(r['day_of_week']), int(r['meal_id']), str(r['meal_name']), str(r['category']), str(r['cuisine']), float(r['checkout_price']), float(r['base_price']), int(r['promo_active']), int(r['featured_on_menu']), int(r['festival_or_event']), pred))

        # Load Inventory History
        df_inv = pd.read_csv(os.path.join(DATA_DIR, "inventory_history.csv"))
        for _, r in df_inv.iterrows():
            cursor.execute("""
                INSERT OR REPLACE INTO inventory_history (restaurant_id, date, ingredient, unit, opening_stock, received_qty, used_qty, wasted_qty, shelf_life_days, supplier_lead_time_days, unit_cost)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (restaurant_id, parse_date_str(r['date']), str(r['ingredient']), str(r['unit']), float(r['opening_stock']), float(r['received_qty']), float(r['used_qty']), float(r['wasted_qty']), int(r['shelf_life_days']), int(r['supplier_lead_time_days']), float(r['unit_cost'])))

        # Load Current Stock
        df_stock = pd.read_csv(os.path.join(DATA_DIR, "current_stock.csv"))
        for _, r in df_stock.iterrows():
            earliest_exp = parse_date_str(r.get('earliest_expiry_date'))
            arrival_date = parse_date_str(r.get('order_arrival_date'))
            cursor.execute("""
                INSERT OR REPLACE INTO current_stock (restaurant_id, as_of_date, ingredient, unit, stock_on_hand, earliest_expiry_date, qty_in_earliest_batch, order_in_transit_qty, order_arrival_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (restaurant_id, parse_date_str(r['as_of_date']), str(r['ingredient']), str(r['unit']), float(r['stock_on_hand']), earliest_exp, float(r['qty_in_earliest_batch']) if not pd.isna(r.get('qty_in_earliest_batch')) else 0.0, float(r['order_in_transit_qty']) if not pd.isna(r.get('order_in_transit_qty')) else 0.0, arrival_date))

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE restaurants SET last_updated = ? WHERE id = ?", (now_str, restaurant_id))

def get_app_today_date(restaurant_id: str) -> str:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(date) as max_date FROM daily_orders WHERE restaurant_id = ?", (restaurant_id,))
        row = cursor.fetchone()
        if row and row['max_date']:
            max_dt = datetime.datetime.strptime(row['max_date'], "%Y-%m-%d").date()
            today_dt = max_dt + datetime.timedelta(days=1)
            return today_dt.strftime("%Y-%m-%d")
        return datetime.date.today().strftime("%Y-%m-%d")

def get_sheet_template(sheet_name: str) -> bytes:
    if sheet_name not in REQUIRED_COLUMNS:
        raise ValueError(f"Unknown sheet {sheet_name}")
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append(REQUIRED_COLUMNS[sheet_name])
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()
